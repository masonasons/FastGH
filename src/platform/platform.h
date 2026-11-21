#pragma once

// What FastGH asks of the operating system beyond wxWidgets
// (platform_mac.mm, platform_windows.cpp, platform_gtk.cpp).

#include <functional>
#include <string>

class wxFrame;
class wxWindow;

namespace platform {

// Light/dark appearance: "off" (light), "on" (dark), "auto" (the system's).
// On macOS and Linux this sets the app's appearance (it changes live), where
// "off" keeps the system's, as the Python app left it; on Windows it is read at
// startup by wxApp::MSWEnableDarkMode.
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

// The unread notification count on the Dock icon (macOS), or the launcher icon
// where the Linux desktop shows one (KDE, Ubuntu's dock); 0 clears it.
void SetBadgeCount(int count);

#ifdef __WXGTK__
// Linux and the BSDs (platform_gtk.cpp).

// Makes `label` the label of `control` for screen readers, and its access key
// (Alt+letter) focus the control.
void LinkLabel(wxWindow* label, wxWindow* control);

// Shows the file selected in the file manager; false when none answered.
bool RevealFile(const std::string& path);

// One FastGH per user. First: this is it, and `show` is called whenever FastGH
// is started again. Handed: another one is running and has been asked to show
// its window. NotAnswering: another one is running and didn't answer. NoBus:
// there is no session bus to tell.
enum class InstanceClaim { First, Handed, NotAnswering, NoBus };
InstanceClaim ClaimSingleInstance(std::function<void()> show);
#endif

}  // namespace platform
