#include "core/process.h"
#include "core/util.h"

#include <cstdlib>

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
extern char** environ;
#endif

#ifdef _WIN32

namespace {

std::wstring Wide(const std::string& s) {
    if (s.empty()) return std::wstring();
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0);
    std::wstring out(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), n);
    return out;
}

// Quoting for CreateProcess's command line, as the C runtime parses it back.
std::wstring QuoteArg(const std::wstring& arg) {
    if (!arg.empty() && arg.find_first_of(L" \t\"") == std::wstring::npos) return arg;
    std::wstring out = L"\"";
    size_t backslashes = 0;
    for (wchar_t c : arg) {
        if (c == L'\\') {
            backslashes++;
        } else if (c == L'"') {
            out.append(backslashes * 2 + 1, L'\\');
            out += c;
            backslashes = 0;
        } else {
            out.append(backslashes, L'\\');
            out += c;
            backslashes = 0;
        }
    }
    out.append(backslashes * 2, L'\\');
    return out + L"\"";
}

}  // namespace

std::string FindOnPath(const std::string& program) {
    wchar_t found[MAX_PATH];
    for (const wchar_t* ext : {L".exe", L".cmd", L".bat", L""}) {
        if (SearchPathW(nullptr, Wide(program).c_str(), ext, MAX_PATH, found, nullptr)) {
            int n = WideCharToMultiByte(CP_UTF8, 0, found, -1, nullptr, 0, nullptr, nullptr);
            std::string out(n > 0 ? n - 1 : 0, '\0');
            WideCharToMultiByte(CP_UTF8, 0, found, -1, out.data(), n, nullptr, nullptr);
            return out;
        }
    }
    return std::string();
}

ProcessResult RunProcess(const std::vector<std::string>& args, const std::string& cwd,
                         const std::function<void(const std::string&)>& onOutput) {
    ProcessResult result;
    if (args.empty()) return result;

    SECURITY_ATTRIBUTES sa = {sizeof(sa), nullptr, TRUE};
    HANDLE readPipe = nullptr, writePipe = nullptr;
    if (!CreatePipe(&readPipe, &writePipe, &sa, 0)) return result;
    SetHandleInformation(readPipe, HANDLE_FLAG_INHERIT, 0);

    std::wstring commandLine;
    for (const auto& arg : args) {
        if (!commandLine.empty()) commandLine += L' ';
        commandLine += QuoteArg(Wide(arg));
    }
    STARTUPINFOW si = {sizeof(si)};
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdOutput = writePipe;
    si.hStdError = writePipe;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    PROCESS_INFORMATION pi = {};
    std::wstring dir = Wide(cwd);
    BOOL ok = CreateProcessW(nullptr, commandLine.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr,
                             dir.empty() ? nullptr : dir.c_str(), &si, &pi);
    CloseHandle(writePipe);
    if (!ok) {
        CloseHandle(readPipe);
        return result;
    }
    result.started = true;

    char buffer[4096];
    DWORD read = 0;
    while (ReadFile(readPipe, buffer, sizeof(buffer), &read, nullptr) && read > 0) {
        std::string chunk(buffer, read);
        result.output += chunk;
        if (onOutput) onOutput(chunk);
    }
    CloseHandle(readPipe);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    result.exitCode = static_cast<int>(code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return result;
}

#else

std::string FindOnPath(const std::string& program) {
    if (program.find('/') != std::string::npos) return access(program.c_str(), X_OK) == 0 ? program : "";
    std::string path = getenv("PATH") ? getenv("PATH") : "";
#ifdef __APPLE__
    // An app started from the Finder gets a minimal PATH; git from Homebrew or
    // the Xcode tools lives in these.
    path += ":/opt/homebrew/bin:/usr/local/bin:/usr/bin";
#endif
    for (const auto& dir : Split(path, ':')) {
        if (dir.empty()) continue;
        std::string candidate = dir + "/" + program;
        if (access(candidate.c_str(), X_OK) == 0) return candidate;
    }
    return std::string();
}

ProcessResult RunProcess(const std::vector<std::string>& args, const std::string& cwd,
                         const std::function<void(const std::string&)>& onOutput) {
    ProcessResult result;
    if (args.empty()) return result;
    std::string program = FindOnPath(args[0]);
    if (program.empty()) return result;

    int fds[2];
    if (pipe(fds) != 0) return result;

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDOUT_FILENO);
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDERR_FILENO);
    posix_spawn_file_actions_addclose(&actions, fds[0]);
    posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
#ifdef __APPLE__
    if (!cwd.empty()) posix_spawn_file_actions_addchdir_np(&actions, cwd.c_str());
#endif

    std::vector<char*> argv;
    for (const auto& arg : args) argv.push_back(const_cast<char*>(arg.c_str()));
    argv[0] = const_cast<char*>(program.c_str());
    argv.push_back(nullptr);

    // git asks for nothing on a terminal it doesn't have; credentials come from its helper.
    std::vector<std::string> envStrings;
    for (char** e = environ; *e; ++e) envStrings.emplace_back(*e);
    envStrings.emplace_back("GIT_TERMINAL_PROMPT=0");
    std::vector<char*> envp;
    for (auto& s : envStrings) envp.push_back(s.data());
    envp.push_back(nullptr);

    pid_t pid = 0;
    int rc = posix_spawn(&pid, program.c_str(), &actions, nullptr, argv.data(), envp.data());
    posix_spawn_file_actions_destroy(&actions);
    close(fds[1]);
    if (rc != 0) {
        close(fds[0]);
        return result;
    }
    result.started = true;

    char buffer[4096];
    ssize_t n;
    while ((n = read(fds[0], buffer, sizeof(buffer))) > 0) {
        std::string chunk(buffer, static_cast<size_t>(n));
        result.output += chunk;
        if (onOutput) onOutput(chunk);
    }
    close(fds[0]);
    int status = 0;
    waitpid(pid, &status, 0);
    result.exitCode = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
    return result;
}

#endif
