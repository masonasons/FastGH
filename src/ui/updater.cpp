// Checking for and installing updates from the "latest" GitHub release (a port
// of Application.cfu / download_update). The release body names the commit it
// was built from; a build from another commit is an update.

#include "ui/dialogs.h"
#include "ui/main_frame.h"
#include "ui/ui_common.h"

#include "core/http.h"
#include "core/util.h"
#include "version.h"

#include <wx/progdlg.h>
#include <wx/stdpaths.h>
#include <wx/filename.h>

#include <atomic>
#include <regex>

namespace {

struct UpdateInfo {
    bool ok = false;
    std::string error;
    std::string version;
    std::string commit;
    std::string assetUrl;
};

UpdateInfo FetchLatest() {
    UpdateInfo info;
    HttpRequest req;
    req.url = "https://api.github.com/repos/masonasons/FastGH/releases";
    req.headers = {"Accept: application/vnd.github+json"};
    HttpResponse res = HttpSend(req);
    if (!res.ok()) {
        info.error = res.completed ? "HTTP " + std::to_string(res.status) : res.error;
        return info;
    }
    json releases = json::parse(res.body, nullptr, false);
    if (!releases.is_array() || releases.empty()) {
        info.error = "No releases found.";
        return info;
    }
    const json& latest = releases[0];
    std::string body = latest.value("body", "");
    std::smatch m;
    if (std::regex_search(body, m, std::regex(R"(Automated build from commit\s+([a-f0-9]+))"))) info.commit = m[1];
    if (std::regex_search(body, m, std::regex(R"(\*\*Version:\*\*\s*(\d+\.\d+\.\d+))"))) info.version = m[1];
    else info.version = latest.value("tag_name", "unknown");
    if (latest.contains("assets") && latest["assets"].is_array()) {
        for (const auto& asset : latest["assets"]) {
            std::string name = ToLower(asset.value("name", ""));
#ifdef _WIN32
            bool mine = name.find("windows") != std::string::npos && EndsWith(name, ".zip");
#else
            bool mine = EndsWith(name, ".dmg");
#endif
            if (mine) {
                info.assetUrl = asset.value("browser_download_url", "");
                break;
            }
        }
    }
    info.ok = true;
    return info;
}

std::vector<int> ParseVersion(const std::string& v) {
    std::vector<int> parts;
    for (const auto& p : Split(ReplaceAll(v, "v", ""), '.')) {
        try {
            parts.push_back(std::stoi(p));
        } catch (...) {
            return {};
        }
    }
    return parts;
}

void Install(const UpdateInfo& info) {
    wxWindow* owner = GetActiveOwner();
    auto* progress = new wxProgressDialog("Downloading Update", "Downloading FastGH update...", 100, owner,
                                          wxPD_APP_MODAL | wxPD_AUTO_HIDE | wxPD_CAN_ABORT | wxPD_ELAPSED_TIME);
    auto cancelled = std::make_shared<std::atomic<bool>>(false);
    std::string fileName = info.assetUrl.substr(info.assetUrl.rfind('/') + 1);
#ifdef _WIN32
    std::string dest = ToU8(wxFileName(wxStandardPaths::Get().GetExecutablePath()).GetPath()) + "\\FastGH-update.zip";
#else
    std::string dest = JoinPath(JoinPath(HomeDir(), "Downloads"), fileName);
#endif
    std::string url = info.assetUrl;
    RunAsync(owner,
             [url, dest, progress, cancelled] {
                 HttpRequest req;
                 req.url = url;
                 req.saveTo = dest;
                 req.timeoutMs = 60000;
                 auto lastUpdate = std::make_shared<long long>(0);
                 req.progress = [progress, cancelled, lastUpdate](uint64_t received, uint64_t total) {
                     long long now = wxGetLocalTimeMillis().GetValue();
                     if (total && now - *lastUpdate > 250) {
                         *lastUpdate = now;
                         int percent = static_cast<int>(received * 100 / total);
                         wxString text = wxString::Format("Downloading: %.1f MB / %.1f MB", received / 1048576.0,
                                                          total / 1048576.0);
                         RunOnUiThread([progress, cancelled, percent, text] {
                             if (!cancelled->load() && !progress->Update(std::min(percent, 99), text))
                                 cancelled->store(true);
                         });
                     }
                     return !cancelled->load();
                 };
                 return HttpSend(req);
             },
             [progress, cancelled, dest](HttpResponse res) {
                 progress->Destroy();
                 if (cancelled->load()) return;
                 if (!res.ok()) {
                     ShowError(GetActiveOwner(), U8("Failed to download the update: " +
                                                     (res.completed ? "HTTP " + std::to_string(res.status) : res.error)),
                               "Update Error");
                     return;
                 }
#ifdef _WIN32
                 // Unpack over the program folder once FastGH has exited, then start it again.
                 wxString dir = wxFileName(wxStandardPaths::Get().GetExecutablePath()).GetPath();
                 wxString script = dir + "\\updater.bat";
                 wxString zip = U8(dest), extract = dir + "\\FastGH-update";
                 wxString text =
                     "@echo off\r\ntimeout /t 2 /nobreak >nul\r\n"
                     "powershell -Command \"Expand-Archive -Path '" + zip + "' -DestinationPath '" + extract +
                     "' -Force\"\r\n"
                     "xcopy /s /y /q \"" + extract + "\\FastGH\\*\" \"" + dir + "\\\"\r\n"
                     "rmdir /s /q \"" + extract + "\"\r\ndel \"" + zip + "\"\r\n"
                     "start \"\" \"" + dir + "\\FastGH.exe\"\r\ndel \"%~f0\"\r\n";
                 WriteFileAtomic(ToU8(script), ToU8(text));
                 ShowInfo(GetActiveOwner(), "Update ready. FastGH will now restart.", "Update");
                 wxExecute("cmd /c \"" + script + "\"", wxEXEC_ASYNC | wxEXEC_HIDE_CONSOLE);
                 mainwin::Exit();
#else
                 ShowInfo(GetActiveOwner(),
                          U8("FastGH has been downloaded to:\n" + dest +
                             "\n\nIt will open now: drag FastGH to your Applications folder to finish the update."),
                          "Update Downloaded");
                 wxLaunchDefaultApplication(U8(dest));
#endif
             });
}

}  // namespace

void CheckForUpdates(bool silent) {
    std::string local = BUILD_COMMIT;
    if (local.empty()) {
        if (!silent)
            ShowInfo(GetActiveOwner(), "This build doesn't know its commit, so it can't check for updates.",
                     "Update Check");
        return;
    }
    RunAsync(mainwin::Get(), [] { return FetchLatest(); }, [silent, local](UpdateInfo info) {
        if (!info.ok) {
            if (!silent) ShowError(GetActiveOwner(), U8("Error checking for updates: " + info.error), "Update Check Error");
            return;
        }
        bool available;
        auto latest = ParseVersion(info.version), current = ParseVersion(APP_VERSION);
        if (!latest.empty() && latest < current) {
            available = false;  // never "update" to an older version
        } else if (!info.commit.empty()) {
            available = !StartsWith(local, info.commit) && !StartsWith(info.commit, local);
        } else {
            available = latest > current;
        }
        if (!available) {
            if (!silent)
                ShowInfo(GetActiveOwner(),
                         U8(std::string("No updates available!\n\nYou are running the latest version: ") + APP_VERSION +
                            " (commit " + local.substr(0, 8) + ")"),
                         "No Update Available");
            return;
        }
        std::string message = std::string("There is an update available.\n\nYour version: ") + APP_VERSION +
                              " (commit " + local.substr(0, 8) + ")\nLatest version: " + info.version;
        if (!info.commit.empty()) message += " (commit " + info.commit.substr(0, 8) + ")";
        message += "\n\nDo you want to download and install the update?";
        if (!AskYesNo(GetActiveOwner(), U8(message), U8("Update available: " + info.version))) return;
        if (info.assetUrl.empty()) {
            ShowError(GetActiveOwner(), "A download for this version could not be found for your platform.");
            return;
        }
        Install(info);
    });
}
