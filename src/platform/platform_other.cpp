// Linux and others: no global hotkey, plain show/hide.

#include "platform/platform.h"

#include <wx/frame.h>

namespace platform {

void ApplyAppearance(const std::string&) {}
bool RegisterGlobalHotkey(wxFrame*, int, int, std::function<void()>) { return false; }
void UnregisterGlobalHotkey(wxFrame*) {}
void HideApp(wxFrame* frame) { frame->Hide(); }
void ShowApp(wxFrame* frame) {
    if (frame->IsIconized()) frame->Iconize(false);
    frame->Show();
    frame->Raise();
}
bool IsAppFrontmost(wxFrame* frame) { return frame->IsShown() && frame->IsActive(); }
void Announce(const std::string&) {}
void SetMenuBarActions(MenuBarActions) {}

void SetBadgeCount(int) {}

}  // namespace platform
