#pragma once

// What FastGH asks of the operating system beyond wxWidgets
// (platform_mac.mm, platform_windows.cpp, platform_other.cpp).

#include <functional>
#include <string>

class wxFrame;

namespace platform {

// Light/dark appearance: "off" (light), "on" (dark), "auto" (the system's).
// On macOS this sets the app's appearance (it changes live); on Windows it is
// read at startup by wxApp::MSWEnableDarkMode.
void ApplyAppearance(const std::string& mode);

// A system-wide shortcut. `modifiers` are wxMOD_* (wxMOD_CONTROL is Command on
// macOS); `keyCode` is a wx key code ('G', WXK_F5...). Replaces any previous one.
bool RegisterGlobalHotkey(wxFrame* frame, int modifiers, int keyCode, std::function<void()> callback);
void UnregisterGlobalHotkey(wxFrame* frame);

// macOS: hide the whole app (as Cmd+H: focus returns to the previous app) and
// bring it back. Elsewhere: hide / show and raise the frame.
void HideApp(wxFrame* frame);
void ShowApp(wxFrame* frame);
// Whether FastGH is the active app with `frame` visible.
bool IsAppFrontmost(wxFrame* frame);

// Has the screen reader say `text` (VoiceOver announcement on macOS; on Windows
// nothing yet, the status bar carries it). UTF-8.
void Announce(const std::string& text);

// The unread notification count on the Dock icon (macOS); 0 clears it.
void SetBadgeCount(int count);

}  // namespace platform
