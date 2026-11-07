#include "core/config.h"
#include "core/util.h"

#include <cstdlib>
#include <filesystem>

namespace {

// Portable mode (Windows and Linux only, as in Python): a "userdata" folder in the
// current directory holds the settings instead of the user's profile.
const std::string& PortableDir() {
    static const std::string dir = [] {
#ifdef __APPLE__
        return std::string();
#else
        std::error_code ec;
        auto path = std::filesystem::current_path(ec) / "userdata";
        if (!ec && std::filesystem::is_directory(path, ec)) return path.u8string();
        return std::string();
#endif
    }();
    return dir;
}

std::string ConfigHome() {
#ifdef _WIN32
    if (const wchar_t* appdata = _wgetenv(L"APPDATA")) return std::filesystem::path(appdata).u8string();
    return HomeDir();
#elif defined(__APPLE__)
    return JoinPath(HomeDir(), "Library/Application Support");
#else
    if (const char* xdg = std::getenv("XDG_CONFIG_HOME"); xdg && *xdg) return xdg;
    return JoinPath(HomeDir(), ".config");
#endif
}

}  // namespace

bool IsPortableMode() {
    return !PortableDir().empty();
}

std::string AppConfigDir() {
    if (IsPortableMode()) return PortableDir();
    return JoinPath(ConfigHome(), "FastGH");
}

std::string AccountConfigDir(int index) {
    return JoinPath(AppConfigDir(), "account" + std::to_string(index));
}

Config::Config(std::string dir) : m_dir(std::move(dir)) {
    std::string text;
    if (ReadFile(JoinPath(m_dir, "config.json"), text)) {
        json parsed = json::parse(text, nullptr, false);
        if (parsed.is_object()) m_data = std::move(parsed);
    }
}

bool Config::Has(const std::string& key) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_data.find(key);
    return it != m_data.end() && !it->is_null();
}

json Config::GetJson(const std::string& key, const json& fallback) const {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto it = m_data.find(key);
    return it == m_data.end() || it->is_null() ? fallback : *it;
}

void Config::Remove(const std::string& key) {
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_data.erase(key);
    }
    Save();
}

void Config::Save() const {
    std::string text;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        // indent=1 as the Python config wrote it, so the files diff cleanly.
        text = m_data.dump(1, ' ', false, json::error_handler_t::replace);
    }
    MakeDirs(m_dir);
    WriteFileAtomic(JoinPath(m_dir, "config.json"), text);
}
