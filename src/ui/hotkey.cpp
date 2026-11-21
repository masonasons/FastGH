#include "ui/hotkey.h"

#include "core/util.h"
#include "platform/platform.h"

#include <cctype>
#include <utility>
#include <vector>

namespace {

// Named keys; letters, digits and punctuation are themselves.
const std::vector<std::pair<const char*, int>>& NamedKeys() {
    static const std::vector<std::pair<const char*, int>> keys = {
        {"space", WXK_SPACE},     {"home", WXK_HOME},       {"end", WXK_END},
        {"pageup", WXK_PAGEUP},   {"pagedown", WXK_PAGEDOWN}, {"insert", WXK_INSERT},
        {"delete", WXK_DELETE},   {"up", WXK_UP},           {"down", WXK_DOWN},
        {"left", WXK_LEFT},       {"right", WXK_RIGHT},
    };
    return keys;
}

bool IsFunctionKey(int code) { return code >= WXK_F1 && code <= WXK_F24; }

// Control, Alt or the Windows key; Shift alone only with a function key, as
// Shift with anything else is typing.
bool ModifiersEnough(int modifiers, int keyCode) {
    if (modifiers & (wxMOD_CONTROL | wxMOD_ALT | wxMOD_WIN)) return true;
    return (modifiers & wxMOD_SHIFT) && IsFunctionKey(keyCode);
}

bool IsPlainKey(int code) {
    if (code >= 'A' && code <= 'Z') return true;
    if (code >= '0' && code <= '9') return true;
    // '+' is the separator, so it can't be a key.
    return code < 128 && code != '+' && std::string(",./;'[]-=`\\").find(static_cast<char>(code)) != std::string::npos;
}

}  // namespace

std::optional<Hotkey> ParseHotkey(const std::string& spec) {
    Hotkey hotkey;
    for (std::string part : Split(ToLower(Trim(spec)), '+')) {
        part = Trim(part);
        if (part.empty()) return std::nullopt;
        if (part == "control" || part == "ctrl" || part == "command" || part == "cmd") {
            hotkey.modifiers |= wxMOD_CONTROL;
        } else if (part == "alt" || part == "option") {
            hotkey.modifiers |= wxMOD_ALT;
        } else if (part == "shift") {
            hotkey.modifiers |= wxMOD_SHIFT;
        } else if (part == "win" || part == "windows" || part == "super" || part == "meta") {
            hotkey.modifiers |= wxMOD_WIN;
        } else if (hotkey.keyCode) {
            return std::nullopt;  // two keys
        } else if (part.size() == 1 && IsPlainKey(std::toupper(static_cast<unsigned char>(part[0])))) {
            hotkey.keyCode = std::toupper(static_cast<unsigned char>(part[0]));
        } else if (part[0] == 'f' && part.size() >= 2 && part.size() <= 3 &&
                   std::isdigit(static_cast<unsigned char>(part[1])) &&
                   (part.size() == 2 || std::isdigit(static_cast<unsigned char>(part[2])))) {
            int n = std::stoi(part.substr(1));
            if (n < 1 || n > 24) return std::nullopt;
            hotkey.keyCode = WXK_F1 + n - 1;
        } else {
            bool found = false;
            for (const auto& [name, code] : NamedKeys()) {
                if (part == name) {
                    hotkey.keyCode = code;
                    found = true;
                    break;
                }
            }
            if (!found) return std::nullopt;
        }
    }
    if (!hotkey.keyCode || !ModifiersEnough(hotkey.modifiers, hotkey.keyCode)) return std::nullopt;
    return hotkey;
}

std::string FormatHotkey(const Hotkey& hotkey) {
    std::string key;
    int code = hotkey.keyCode;
    if (IsPlainKey(code)) key = std::string(1, static_cast<char>(std::tolower(code)));
    else if (IsFunctionKey(code)) key = "f" + std::to_string(code - WXK_F1 + 1);
    else
        for (const auto& [name, c] : NamedKeys())
            if (c == code) key = name;
    if (key.empty()) return std::string();

    std::string out;
#ifdef __WXOSX__
    if (hotkey.modifiers & wxMOD_CONTROL) out += "command+";
    if (hotkey.modifiers & wxMOD_ALT) out += "option+";
#else
    if (hotkey.modifiers & wxMOD_CONTROL) out += "control+";
    if (hotkey.modifiers & wxMOD_ALT) out += "alt+";
#endif
    if (hotkey.modifiers & wxMOD_SHIFT) out += "shift+";
    if (hotkey.modifiers & wxMOD_WIN) out += "win+";
    return out + key;
}

HotkeyCtrl::HotkeyCtrl(wxWindow* parent, const wxString& value) : wxTextCtrl(parent, wxID_ANY, value) {
    Bind(wxEVT_CHAR_HOOK, &HotkeyCtrl::OnCharHook, this);
}

void HotkeyCtrl::OnCharHook(wxKeyEvent& event) {
    int mods = event.GetModifiers();
#ifdef __WXOSX__
    // The Control key itself has no name here ("control" means Command on macOS).
    if (mods & wxMOD_RAW_CONTROL) {
        event.Skip();
        return;
    }
#endif
    if (!ModifiersEnough(mods, event.GetKeyCode())) {
        event.Skip();  // typing, Tab, Escape, Enter
        return;
    }
    Hotkey hotkey{mods & (wxMOD_CONTROL | wxMOD_ALT | wxMOD_SHIFT | wxMOD_WIN), event.GetKeyCode()};
    std::string text = FormatHotkey(hotkey);
    if (text.empty()) {
        // A modifier on its own (still being held), or a key with no name: let
        // Ctrl+Tab and the like do what they do.
        event.Skip();
        return;
    }
    ChangeValue(wxString::FromUTF8(text));
    // Selecting it has screen readers read the new value out; macOS and Linux announce it too.
    SetSelection(-1, -1);
    platform::Announce(text);
}
