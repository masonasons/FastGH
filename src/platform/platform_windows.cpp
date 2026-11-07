// Windows: the global hotkey through RegisterHotKey on the main window.

#include "platform/platform.h"

#include <wx/frame.h>

namespace {

const int kHotkeyId = 0xB001;
std::function<void()> g_callback;
bool g_registered = false;

}  // namespace

namespace platform {

void ApplyAppearance(const std::string&) {
    // Read at startup (wxApp::MSWEnableDarkMode in ui/app.cpp); Windows can't switch a running app.
}

bool RegisterGlobalHotkey(wxFrame* frame, int modifiers, int keyCode, std::function<void()> callback) {
    UnregisterGlobalHotkey(frame);
    if (!frame->RegisterHotKey(kHotkeyId, modifiers, keyCode)) return false;
    g_registered = true;
    g_callback = std::move(callback);
    frame->Bind(wxEVT_HOTKEY, [](wxKeyEvent&) {
        if (g_callback) g_callback();
    }, kHotkeyId);
    return true;
}

void UnregisterGlobalHotkey(wxFrame* frame) {
    if (g_registered && frame) frame->UnregisterHotKey(kHotkeyId);
    if (frame) frame->Unbind(wxEVT_HOTKEY, [](wxKeyEvent&) {}, kHotkeyId);
    g_registered = false;
    g_callback = nullptr;
}

void HideApp(wxFrame* frame) {
    frame->Hide();
}

void ShowApp(wxFrame* frame) {
    if (frame->IsIconized()) frame->Iconize(false);
    frame->Show();
    frame->Raise();
}

bool IsAppFrontmost(wxFrame* frame) {
    return frame->IsShown() && !frame->IsIconized() && frame->IsActive();
}

void Announce(const std::string&) {}

void SetBadgeCount(int) {}

}  // namespace platform
