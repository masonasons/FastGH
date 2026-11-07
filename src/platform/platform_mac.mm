// macOS: hiding as the system does, a global hotkey, the Dock badge, appearance.

#include "platform/platform.h"

#import <AppKit/AppKit.h>
#include <Carbon/Carbon.h>
#include <wx/defs.h>
#include <wx/frame.h>

#include <map>

namespace {

EventHotKeyRef g_hotKey = nullptr;
EventHandlerRef g_handler = nullptr;
std::function<void()> g_callback;

OSStatus OnHotKey(EventHandlerCallRef, EventRef, void*) {
    // Carbon calls this on the main thread, from the run loop.
    if (g_callback) g_callback();
    return noErr;
}

// wx key codes to the keyboard's virtual key codes (US layout positions).
UInt32 MacKeyCode(int keyCode) {
    static const std::map<int, UInt32> keys = {
        {'A', kVK_ANSI_A}, {'B', kVK_ANSI_B}, {'C', kVK_ANSI_C}, {'D', kVK_ANSI_D}, {'E', kVK_ANSI_E},
        {'F', kVK_ANSI_F}, {'G', kVK_ANSI_G}, {'H', kVK_ANSI_H}, {'I', kVK_ANSI_I}, {'J', kVK_ANSI_J},
        {'K', kVK_ANSI_K}, {'L', kVK_ANSI_L}, {'M', kVK_ANSI_M}, {'N', kVK_ANSI_N}, {'O', kVK_ANSI_O},
        {'P', kVK_ANSI_P}, {'Q', kVK_ANSI_Q}, {'R', kVK_ANSI_R}, {'S', kVK_ANSI_S}, {'T', kVK_ANSI_T},
        {'U', kVK_ANSI_U}, {'V', kVK_ANSI_V}, {'W', kVK_ANSI_W}, {'X', kVK_ANSI_X}, {'Y', kVK_ANSI_Y},
        {'Z', kVK_ANSI_Z}, {'0', kVK_ANSI_0}, {'1', kVK_ANSI_1}, {'2', kVK_ANSI_2}, {'3', kVK_ANSI_3},
        {'4', kVK_ANSI_4}, {'5', kVK_ANSI_5}, {'6', kVK_ANSI_6}, {'7', kVK_ANSI_7}, {'8', kVK_ANSI_8},
        {'9', kVK_ANSI_9}, {WXK_F1, kVK_F1}, {WXK_F2, kVK_F2}, {WXK_F3, kVK_F3}, {WXK_F4, kVK_F4},
        {WXK_F5, kVK_F5}, {WXK_F6, kVK_F6}, {WXK_F7, kVK_F7}, {WXK_F8, kVK_F8}, {WXK_F9, kVK_F9},
        {WXK_F10, kVK_F10}, {WXK_F11, kVK_F11}, {WXK_F12, kVK_F12}, {WXK_SPACE, kVK_Space},
        {WXK_HOME, kVK_Home}, {WXK_END, kVK_End}, {WXK_PAGEUP, kVK_PageUp}, {WXK_PAGEDOWN, kVK_PageDown},
        {WXK_UP, kVK_UpArrow}, {WXK_DOWN, kVK_DownArrow}, {WXK_LEFT, kVK_LeftArrow},
        {WXK_RIGHT, kVK_RightArrow}, {',', kVK_ANSI_Comma}, {'.', kVK_ANSI_Period}, {'/', kVK_ANSI_Slash},
        {';', kVK_ANSI_Semicolon}, {'\'', kVK_ANSI_Quote}, {'[', kVK_ANSI_LeftBracket},
        {']', kVK_ANSI_RightBracket}, {'-', kVK_ANSI_Minus}, {'=', kVK_ANSI_Equal}, {'`', kVK_ANSI_Grave},
    };
    auto it = keys.find(keyCode);
    return it == keys.end() ? UINT32_MAX : it->second;
}

}  // namespace

namespace platform {

void ApplyAppearance(const std::string& mode) {
    if (mode == "on") NSApp.appearance = [NSAppearance appearanceNamed:NSAppearanceNameDarkAqua];
    else if (mode == "auto") NSApp.appearance = nil;
    // "off" meant "leave the look alone" in the Python app, which on macOS was the
    // system's: keep following it rather than forcing light.
    else NSApp.appearance = nil;
}

bool RegisterGlobalHotkey(wxFrame* frame, int modifiers, int keyCode, std::function<void()> callback) {
    UnregisterGlobalHotkey(frame);
    UInt32 key = MacKeyCode(keyCode);
    if (key == UINT32_MAX) return false;
    UInt32 mods = 0;
    if (modifiers & wxMOD_CONTROL) mods |= cmdKey;  // wx's Control is Command here
    if (modifiers & wxMOD_RAW_CONTROL) mods |= controlKey;
    if (modifiers & wxMOD_ALT) mods |= optionKey;
    if (modifiers & wxMOD_SHIFT) mods |= shiftKey;
    if (!g_handler) {
        EventTypeSpec type = {kEventClassKeyboard, kEventHotKeyPressed};
        InstallApplicationEventHandler(&OnHotKey, 1, &type, nullptr, &g_handler);
    }
    EventHotKeyID id = {'FGH ', 1};
    if (RegisterEventHotKey(key, mods, id, GetApplicationEventTarget(), 0, &g_hotKey) != noErr) {
        g_hotKey = nullptr;
        return false;
    }
    g_callback = std::move(callback);
    return true;
}

void UnregisterGlobalHotkey(wxFrame*) {
    if (g_hotKey) UnregisterEventHotKey(g_hotKey);
    g_hotKey = nullptr;
    g_callback = nullptr;
}

void HideApp(wxFrame*) {
    // The system's Hide: the window stays open, and focus (and VoiceOver) goes
    // back to the app used before, just as with Cmd+H.
    [NSApp hide:nil];
}

void ShowApp(wxFrame* frame) {
    [NSApp unhide:nil];
    if (frame) {
        if (frame->IsIconized()) frame->Iconize(false);
        frame->Show();
        frame->Raise();
    }
    [NSApp activateIgnoringOtherApps:YES];
    if (frame) [frame->GetWXWindow() makeKeyAndOrderFront:nil];
}

bool IsAppFrontmost(wxFrame* frame) {
    return NSApp.isActive && !NSApp.isHidden && frame && frame->IsShown() && !frame->IsIconized();
}

void Announce(const std::string& text) {
    NSString* message = [NSString stringWithUTF8String:text.c_str()];
    if (!message) return;
    NSAccessibilityPostNotificationWithUserInfo(
        NSApp.mainWindow ?: (id)NSApp, NSAccessibilityAnnouncementRequestedNotification,
        @{NSAccessibilityAnnouncementKey: message,
          NSAccessibilityPriorityKey: @(NSAccessibilityPriorityHigh)});
}

void SetBadgeCount(int count) {
    NSApp.dockTile.badgeLabel = count > 0 ? [NSString stringWithFormat:@"%d", count] : nil;
}

}  // namespace platform
