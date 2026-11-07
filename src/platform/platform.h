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

// macOS: hide FastGH out of the Dock and Cmd+Tab into a menu bar icon (focus
// returns to the previous app), and bring it back. Elsewhere: hide / show and
// raise the frame (the tray icon is the main window's).
void HideApp(wxFrame* frame);
void ShowApp(wxFrame* frame);
// What the macOS menu bar icon's menu does while FastGH is hidden.
struct MenuBarActions {
    std::function<void()> show;
    std::function<void()> refresh;
    std::function<void()> quit;
};
void SetMenuBarActions(MenuBarActions actions);

// Whether FastGH is the active app with `frame` visible.
bool IsAppFrontmost(wxFrame* frame);

// Has the screen reader say `text` (VoiceOver announcement on macOS; on Windows
// nothing yet, the status bar carries it). UTF-8.
void Announce(const std::string& text);

// The unread notification count on the Dock icon (macOS); 0 clears it.
void SetBadgeCount(int count);

}  // namespace platform
