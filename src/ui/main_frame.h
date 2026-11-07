#pragma once

// What the other windows ask of the main window (ui/main_frame.cpp).

#include <wx/wx.h>

#include <string>

namespace mainwin {

wxFrame* Get();  // null before it is created and after it closes
// Reload every tab (the feed, repositories, starred, watched, following, notifications).
void RefreshAll();
// Re-render the feed after its filters changed (no network).
void RefreshFeedFilters();
// After the Options dialog saved: timers, the global hotkey, theme.
void ApplyOptions();
// After the current account changed (Accounts dialog).
void AccountChanged();
// Registers a show/hide hotkey ("control+alt+g"); false when the system refused it.
bool SetGlobalHotkey(const std::string& hotkey);
// Show and focus the window, or hide FastGH (on macOS, the whole app, as Cmd+H).
void ShowWindow();
void HideWindow();
void ToggleWindow();
// A system notification (Notification Center / Windows toast).
void Notify(const wxString& title, const wxString& message);

}  // namespace mainwin

namespace mainwin {
// For ui/app.cpp: create the window (once), and end FastGH.
wxFrame* Create();
void Exit();
}  // namespace mainwin
