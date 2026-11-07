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

platform::MenuBarActions g_menuActions;
NSStatusItem* g_statusItem = nil;

}  // namespace

// The menu bar icon's menu items call back into the main window.
@interface FastGHStatusTarget : NSObject
- (void)show:(id)sender;
- (void)refresh:(id)sender;
- (void)quit:(id)sender;
@end

@implementation FastGHStatusTarget
- (void)show:(id)sender {
    if (g_menuActions.show) g_menuActions.show();
}
- (void)refresh:(id)sender {
    if (g_menuActions.refresh) g_menuActions.refresh();
}
- (void)quit:(id)sender {
    if (g_menuActions.quit) g_menuActions.quit();
}
@end

namespace {

FastGHStatusTarget* g_statusTarget = nil;

// The G mark as a template image, so the menu bar draws it in its own colours.
NSImage* StatusImage() {
    NSImage* image = [NSImage imageWithSize:NSMakeSize(18, 18) flipped:NO drawingHandler:^BOOL(NSRect rect) {
        [[NSColor blackColor] set];
        NSBezierPath* arc = [NSBezierPath bezierPath];
        [arc appendBezierPathWithArcWithCenter:NSMakePoint(9, 9) radius:6.5 startAngle:20 endAngle:-40 clockwise:NO];
        arc.lineWidth = 2;
        [arc stroke];
        NSBezierPath* bar = [NSBezierPath bezierPath];
        [bar moveToPoint:NSMakePoint(9, 9)];
        [bar lineToPoint:NSMakePoint(15.5, 9)];
        bar.lineWidth = 2;
        [bar stroke];
        return YES;
    }];
    [image setTemplate:YES];
    image.accessibilityDescription = @"FastGH";
    return image;
}

void ShowStatusItem() {
    if (g_statusItem) return;
    if (!g_statusTarget) g_statusTarget = [[FastGHStatusTarget alloc] init];
    g_statusItem = [NSStatusBar.systemStatusBar statusItemWithLength:NSSquareStatusItemLength];
    g_statusItem.button.image = StatusImage();
    g_statusItem.button.accessibilityTitle = @"FastGH";
    g_statusItem.button.toolTip = @"FastGH";
    NSMenu* menu = [[NSMenu alloc] initWithTitle:@"FastGH"];
    auto add = [&](NSString* title, SEL action) {
        NSMenuItem* item = [menu addItemWithTitle:title action:action keyEquivalent:@""];
        item.target = g_statusTarget;
    };
    add(@"Show FastGH", @selector(show:));
    add(@"Refresh", @selector(refresh:));
    [menu addItem:[NSMenuItem separatorItem]];
    add(@"Quit FastGH", @selector(quit:));
    g_statusItem.menu = menu;
}

void RemoveStatusItem() {
    if (!g_statusItem) return;
    [NSStatusBar.systemStatusBar removeStatusItem:g_statusItem];
    g_statusItem = nil;
}

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

void SetMenuBarActions(MenuBarActions actions) {
    g_menuActions = std::move(actions);
}

void HideApp(wxFrame* frame) {
    // Out of the Dock and Cmd+Tab, into the menu bar. Hiding the app as well gives
    // the focus (and VoiceOver) back to the app used before.
    ShowStatusItem();
    if (frame) frame->Hide();
    [NSApp hide:nil];
    NSApp.activationPolicy = NSApplicationActivationPolicyAccessory;
}

void ShowApp(wxFrame* frame) {
    NSApp.activationPolicy = NSApplicationActivationPolicyRegular;
    RemoveStatusItem();
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
    return NSApp.activationPolicy == NSApplicationActivationPolicyRegular && NSApp.isActive && !NSApp.isHidden && frame && frame->IsShown() && !frame->IsIconized();
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
