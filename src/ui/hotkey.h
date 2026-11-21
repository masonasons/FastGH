#pragma once

// The show/hide hotkey: its text form ("control+alt+g") and a field that takes
// a key press.

#include <wx/textctrl.h>

#include <optional>
#include <string>

struct Hotkey {
    int modifiers = 0;  // wxMOD_* (wxMOD_CONTROL is Command on macOS)
    int keyCode = 0;    // 'G', WXK_F5...
};

// "control+alt+g", "ctrl+shift+f5", "win+space", "shift+f12"... nullopt when it
// isn't one: an unknown name, no key, or no Control, Alt or Windows key (Shift
// alone only goes with a function key, as it would take the key from typing).
std::optional<Hotkey> ParseHotkey(const std::string& spec);
// The text form ParseHotkey reads; empty when the key has no name.
std::string FormatHotkey(const Hotkey& hotkey);

// A text field for a hotkey. Pressing a combination with Control, Alt or the
// Windows key (Command or Option on macOS), or Shift with a function key, puts
// it in the field, as Windows' own hotkey fields do; other keys type and edit
// as usual, so the text form can still be written out, and Tab, Escape and
// Enter work as everywhere.
class HotkeyCtrl : public wxTextCtrl {
public:
    HotkeyCtrl(wxWindow* parent, const wxString& value);

private:
    void OnCharHook(wxKeyEvent& event);
};
