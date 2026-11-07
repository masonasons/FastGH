#pragma once

// JSON settings files, the same files and layout the Python FastGH used, so
// settings and signed-in accounts carry over:
//   macOS:   ~/Library/Application Support/FastGH/config.json
//            ~/Library/Application Support/FastGH/account<N>/config.json
//   Windows: %APPDATA%\FastGH\...  (or a "userdata" folder beside the current
//            directory: portable mode, where the files sit directly in it)
//   Linux:   $XDG_CONFIG_HOME/FastGH/...
//
// Every Set() saves the file (as the Python Config did with autosave). Safe to
// use from any thread.

#include <nlohmann/json.hpp>

#include <mutex>
#include <string>

using json = nlohmann::json;

// The folder holding config.json (portable "userdata", or <config home>/FastGH).
std::string AppConfigDir();
// <AppConfigDir>/account<index>
std::string AccountConfigDir(int index);
bool IsPortableMode();

class Config {
public:
    // `dir` is the folder holding config.json; the file is read now.
    explicit Config(std::string dir);

    bool Has(const std::string& key) const;

    // The value, or `fallback` when missing or of another type.
    template <typename T>
    T Get(const std::string& key, const T& fallback) const {
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_data.find(key);
        if (it == m_data.end() || it->is_null()) return fallback;
        try {
            return it->get<T>();
        } catch (...) {
            return fallback;
        }
    }
    std::string GetString(const std::string& key, const std::string& fallback = "") const {
        return Get<std::string>(key, fallback);
    }
    bool GetBool(const std::string& key, bool fallback = false) const { return Get<bool>(key, fallback); }
    int GetInt(const std::string& key, int fallback = 0) const { return Get<int>(key, fallback); }
    json GetJson(const std::string& key, const json& fallback = json()) const;

    // Stores the value and saves the file.
    template <typename T>
    void Set(const std::string& key, const T& value) {
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_data[key] = value;
        }
        Save();
    }
    void SetJson(const std::string& key, const json& value) { Set<json>(key, value); }
    // Sets the value only when the key is missing (defaults on first run).
    template <typename T>
    void SetDefault(const std::string& key, const T& value) {
        if (!Has(key)) Set(key, value);
    }
    void Remove(const std::string& key);

    void Save() const;
    const std::string& Dir() const { return m_dir; }

private:
    std::string m_dir;
    mutable std::mutex m_mutex;
    json m_data = json::object();
};
