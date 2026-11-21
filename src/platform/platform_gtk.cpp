// Linux (and the BSDs), through GTK: the global hotkey (XInput 2 raw keys, or the
// desktop's GlobalShortcuts portal under Wayland), the screen reader
// announcements, labels, the launcher badge, appearance and one running copy.

#include "platform/platform.h"

#include <wx/app.h>
#include <wx/frame.h>
#include <wx/window.h>

#include <gtk/gtk.h>

#include <atomic>
#include <set>
#include <string>
#include <thread>

#include <cerrno>
#include <poll.h>
#include <unistd.h>

#ifdef GDK_WINDOWING_X11
// Last: Xlib's macros (None, Status, Bool...) clash with wxWidgets' names.
#include <gdk/gdkx.h>
#include <X11/Xlib.h>
#include <X11/extensions/XInput2.h>
#endif

namespace {

std::function<void()> g_hotkeyCallback;
// The X server time of the last hotkey press: the window manager lets a window
// take the focus when shown for a key pressed at a known time (Marco and
// others refuse it otherwise, to stop windows stealing the focus).
std::atomic<unsigned long> g_hotkeyTime{0};

// From any thread: the callback runs on the UI thread, never inside a D-Bus
// handler or the key watcher.
void RunHotkey() {
    if (wxTheApp) wxTheApp->CallAfter([] {
        if (g_hotkeyCallback) g_hotkeyCallback();
    });
}

GDBusConnection* SessionBus() {
    static GDBusConnection* bus = [] {
        GError* error = nullptr;
        GDBusConnection* b = g_bus_get_sync(G_BUS_TYPE_SESSION, nullptr, &error);
        if (error) g_error_free(error);
        return b;
    }();
    return bus;
}

// --- Keys: wx key codes to GDK key values (X11 keysyms) ---

guint KeyvalFor(int keyCode) {
    if (keyCode >= 'A' && keyCode <= 'Z') return GDK_KEY_a + (keyCode - 'A');
    if (keyCode >= '0' && keyCode <= '9') return GDK_KEY_0 + (keyCode - '0');
    if (keyCode >= WXK_F1 && keyCode <= WXK_F24) return GDK_KEY_F1 + (keyCode - WXK_F1);
    switch (keyCode) {
        case ',': return GDK_KEY_comma;
        case '.': return GDK_KEY_period;
        case '/': return GDK_KEY_slash;
        case ';': return GDK_KEY_semicolon;
        case '\'': return GDK_KEY_apostrophe;
        case '[': return GDK_KEY_bracketleft;
        case ']': return GDK_KEY_bracketright;
        case '-': return GDK_KEY_minus;
        case '=': return GDK_KEY_equal;
        case '`': return GDK_KEY_grave;
        case '\\': return GDK_KEY_backslash;
        case WXK_SPACE: return GDK_KEY_space;
        case WXK_HOME: return GDK_KEY_Home;
        case WXK_END: return GDK_KEY_End;
        case WXK_PAGEUP: return GDK_KEY_Page_Up;
        case WXK_PAGEDOWN: return GDK_KEY_Page_Down;
        case WXK_INSERT: return GDK_KEY_Insert;
        case WXK_DELETE: return GDK_KEY_Delete;
        case WXK_UP: return GDK_KEY_Up;
        case WXK_DOWN: return GDK_KEY_Down;
        case WXK_LEFT: return GDK_KEY_Left;
        case WXK_RIGHT: return GDK_KEY_Right;
    }
    return 0;
}

// --- The hotkey under X11 ---
// Screen readers that read the keyboard themselves (Linda, through its key
// daemon and synchronous grabs) hand keys on by replaying them, and a replayed
// key skips grabs on the root window: a passive key grab alone never hears the
// hotkey there. XInput 2 raw key events reach the root window whatever holds the
// keyboard, so they are what the hotkey listens to, on an X connection and
// thread of its own. The key is grabbed as well, where nothing else has it, only
// so that the window with the focus doesn't get it typed into it too.

#ifdef GDK_WINDOWING_X11
struct X11Hotkey {
    Display* display = nullptr;
    int xiOpcode = 0;
    KeyCode code = 0;
    unsigned mods = 0;  // ShiftMask, ControlMask, Mod1Mask, Mod4Mask
    bool grabbed = false;
    std::thread thread;
    int wake[2] = {-1, -1};
} g_x11;

// Caps Lock and Num Lock on or off: the same hotkey.
const unsigned kLockMasks[] = {0, LockMask, Mod2Mask, LockMask | Mod2Mask};

// Errors on FastGH's own connection, collected rather than left to GDK's
// handler (which stops the program on an error from a display it doesn't know).
// Only set while the main thread makes requests on that connection.
int g_xErrors = 0;
int CountXError(Display*, XErrorEvent*) {
    g_xErrors++;
    return 0;
}

// Watches raw key events: `code` pressed with exactly the modifiers in `mods`
// held (by the keys the X server's modifier map names) is the hotkey.
void WatchKeys(Display* display, int xiOpcode, KeyCode code, unsigned mods, int wakeFd) {
    // Which keys are Shift, Control, Alt and Super.
    std::set<int> modifierKeys[4];
    const unsigned masks[4] = {ShiftMask, ControlMask, Mod1Mask, Mod4Mask};
    const int indexes[4] = {ShiftMapIndex, ControlMapIndex, Mod1MapIndex, Mod4MapIndex};
    if (XModifierKeymap* map = XGetModifierMapping(display)) {
        for (int m = 0; m < 4; m++)
            for (int k = 0; k < map->max_keypermod; k++)
                if (KeyCode c = map->modifiermap[indexes[m] * map->max_keypermod + k]) modifierKeys[m].insert(c);
        XFreeModifiermap(map);
    }
    std::set<int> down;  // raw events carry no modifier state: what is held is kept here
    auto held = [&] {
        unsigned state = 0;
        for (int m = 0; m < 4; m++)
            for (int c : modifierKeys[m])
                if (down.count(c)) state |= masks[m];
        return state;
    };
    int xfd = ConnectionNumber(display);
    for (;;) {
        while (XPending(display)) {
            XEvent event;
            XNextEvent(display, &event);
            // While this connection's own grab has the hotkey, its release comes
            // here as a core event, not a raw one: without this, the key would
            // stay "down" and the next press would pass for a repeat.
            if (event.type == KeyRelease) {
                down.erase(event.xkey.keycode);
                continue;
            }
            XGenericEventCookie* cookie = &event.xcookie;
            if (event.type != GenericEvent || cookie->extension != xiOpcode || !XGetEventData(display, cookie))
                continue;
            int key = static_cast<XIRawEvent*>(cookie->data)->detail;
            if (cookie->evtype == XI_RawKeyPress) {
                // A key already down (a repeat, or the same key from a second
                // device as a screen reader passes it on) isn't pressed again.
                bool fresh = down.insert(key).second;
                if (fresh && key == code && held() == mods) {
                    g_hotkeyTime = static_cast<XIRawEvent*>(cookie->data)->time;
                    RunHotkey();
                }
            } else if (cookie->evtype == XI_RawKeyRelease) {
                down.erase(key);
            }
            XFreeEventData(display, cookie);
        }
        pollfd fds[2] = {{xfd, POLLIN, 0}, {wakeFd, POLLIN, 0}};
        if (poll(fds, 2, -1) < 0 && errno != EINTR) break;
        if (fds[1].revents) break;
        if (fds[0].revents & (POLLERR | POLLHUP)) break;
    }
}

void X11Ungrab() {
    if (!g_x11.display) return;
    if (g_x11.thread.joinable()) {
        char byte = 1;
        if (write(g_x11.wake[1], &byte, 1) < 0) {}
        g_x11.thread.join();
    }
    for (int& fd : g_x11.wake) {
        if (fd >= 0) close(fd);
        fd = -1;
    }
    XCloseDisplay(g_x11.display);  // which lets the grab go
    g_x11 = X11Hotkey();
}

bool X11Grab(int modifiers, guint keyval) {
    GdkDisplay* gdkDisplay = gdk_display_get_default();
    Display* display = XOpenDisplay(DisplayString(GDK_DISPLAY_XDISPLAY(gdkDisplay)));
    if (!display) return false;
    KeyCode code = XKeysymToKeycode(display, keyval);
    int xiOpcode = 0, event = 0, error = 0, major = 2, minor = 2;
    if (!code || !XQueryExtension(display, "XInputExtension", &xiOpcode, &event, &error)) {
        XCloseDisplay(display);
        return false;
    }
    unsigned mods = 0;
    if (modifiers & wxMOD_CONTROL) mods |= ControlMask;
    if (modifiers & wxMOD_ALT) mods |= Mod1Mask;
    if (modifiers & wxMOD_SHIFT) mods |= ShiftMask;
    if (modifiers & wxMOD_WIN) mods |= Mod4Mask;
    Window root = DefaultRootWindow(display);

    auto* previous = XSetErrorHandler(CountXError);
    g_xErrors = 0;
    // Before XInput 2.1, raw events stopped at grabs.
    bool raw = XIQueryVersion(display, &major, &minor) == Success && (major > 2 || (major == 2 && minor >= 1));
    if (raw) {
        unsigned char bits[XIMaskLen(XI_LASTEVENT)] = {};
        XISetMask(bits, XI_RawKeyPress);
        XISetMask(bits, XI_RawKeyRelease);
        XIEventMask mask{XIAllMasterDevices, static_cast<int>(sizeof bits), bits};
        XISelectEvents(display, root, &mask, 1);
        XSync(display, False);
        raw = g_xErrors == 0;
    }
    g_xErrors = 0;
    for (unsigned lock : kLockMasks) XGrabKey(display, code, mods | lock, root, False, GrabModeAsync, GrabModeAsync);
    XSync(display, False);
    // Another program has it (BadAccess): let go of whatever did take, and only listen.
    bool grabbed = g_xErrors == 0;
    if (!grabbed) {
        for (unsigned lock : kLockMasks) XUngrabKey(display, code, mods | lock, root);
        XSync(display, False);
    }
    XSetErrorHandler(previous);

    if (!raw || pipe(g_x11.wake) != 0) {
        XCloseDisplay(display);
        return false;
    }
    g_x11.display = display;
    g_x11.xiOpcode = xiOpcode;
    g_x11.code = code;
    g_x11.mods = mods;
    g_x11.grabbed = grabbed;
    g_x11.thread = std::thread(WatchKeys, display, xiOpcode, code, mods, g_x11.wake[0]);
    return true;
}

bool IsX11() {
    return GDK_IS_X11_DISPLAY(gdk_display_get_default());
}
#else
bool IsX11() { return false; }
void X11Ungrab() {}
bool X11Grab(int, guint) { return false; }
#endif

// --- The hotkey under Wayland: the GlobalShortcuts portal ---
// The desktop owns the key: FastGH asks for it (CreateSession, BindShortcuts),
// the desktop may ask the user to confirm or pick another, and it says when the
// shortcut is pressed (Activated). Each portal call answers later, through a
// Request object's Response signal.

constexpr const char* kPortal = "org.freedesktop.portal.Desktop";
constexpr const char* kPortalPath = "/org/freedesktop/portal/desktop";
constexpr const char* kShortcuts = "org.freedesktop.portal.GlobalShortcuts";
constexpr const char* kShortcutId = "toggle-window";

struct PortalState {
    unsigned generation = 0;  // bumped on every new registration; stale answers are dropped
    std::string session;      // the session's object path, once created
    guint activatedSub = 0;
    std::string activationToken;  // from the last Activated, to raise the window under Wayland
} g_portal;

std::string NextToken() {
    static std::atomic<unsigned> counter{0};
    return "fastgh" + std::to_string(++counter);
}

// The path the portal will give the request made with `token`.
std::string RequestPath(GDBusConnection* bus, const std::string& token) {
    std::string sender = g_dbus_connection_get_unique_name(bus) + 1;  // without the ':'
    for (char& c : sender)
        if (c == '.') c = '_';
    return std::string(kPortalPath) + "/request/" + sender + "/" + token;
}

// Calls `method` on the portal and `done(response, results)` when its Request answers.
void PortalRequest(const char* method, GVariant* params, const std::string& token,
                   std::function<void(guint32, GVariant*)> done) {
    GDBusConnection* bus = SessionBus();
    struct Pending {
        std::function<void(guint32, GVariant*)> done;
        guint sub = 0;
    };
    auto* pending = new Pending{std::move(done)};
    // Subscribed before the call, so a fast answer isn't missed.
    pending->sub = g_dbus_connection_signal_subscribe(
        bus, kPortal, "org.freedesktop.portal.Request", "Response", RequestPath(bus, token).c_str(), nullptr,
        G_DBUS_SIGNAL_FLAGS_NONE,
        [](GDBusConnection* conn, const gchar*, const gchar*, const gchar*, const gchar*, GVariant* signal,
           gpointer data) {
            auto* p = static_cast<Pending*>(data);
            guint32 response = 2;
            GVariant* results = nullptr;
            g_variant_get(signal, "(u@a{sv})", &response, &results);
            g_dbus_connection_signal_unsubscribe(conn, p->sub);
            p->done(response, results);
            if (results) g_variant_unref(results);
            delete p;
        },
        pending, nullptr);
    g_dbus_connection_call(
        bus, kPortal, kPortalPath, kShortcuts, method, params, G_VARIANT_TYPE("(o)"), G_DBUS_CALL_FLAGS_NONE, -1,
        nullptr,
        [](GObject* source, GAsyncResult* res, gpointer data) {
            GError* error = nullptr;
            GVariant* reply = g_dbus_connection_call_finish(G_DBUS_CONNECTION(source), res, &error);
            if (reply) {
                g_variant_unref(reply);
                return;
            }
            // No answer will come.
            g_error_free(error);
            auto* p = static_cast<Pending*>(data);
            g_dbus_connection_signal_unsubscribe(G_DBUS_CONNECTION(source), p->sub);
            p->done(2, nullptr);
            delete p;
        },
        pending);
}

void OnActivated(GDBusConnection*, const gchar*, const gchar*, const gchar*, const gchar*, GVariant* params,
                 gpointer) {
    const gchar* session = nullptr;
    const gchar* id = nullptr;
    guint64 timestamp = 0;
    GVariant* options = nullptr;
    g_variant_get(params, "(&o&st@a{sv})", &session, &id, &timestamp, &options);
    if (session == g_portal.session && std::string(id) == kShortcutId) {
        const gchar* token = nullptr;
        if (options && g_variant_lookup(options, "activation_token", "&s", &token) && token)
            g_portal.activationToken = token;
        RunHotkey();
    }
    if (options) g_variant_unref(options);
}

void PortalClose() {
    GDBusConnection* bus = SessionBus();
    g_portal.generation++;
    if (bus && g_portal.activatedSub) g_dbus_connection_signal_unsubscribe(bus, g_portal.activatedSub);
    g_portal.activatedSub = 0;
    if (bus && !g_portal.session.empty())
        g_dbus_connection_call(bus, kPortal, g_portal.session.c_str(), "org.freedesktop.portal.Session", "Close",
                               nullptr, nullptr, G_DBUS_CALL_FLAGS_NONE, -1, nullptr, nullptr, nullptr);
    g_portal.session.clear();
}

bool PortalAvailable(GDBusConnection* bus) {
    GError* error = nullptr;
    GVariant* reply = g_dbus_connection_call_sync(
        bus, kPortal, kPortalPath, "org.freedesktop.DBus.Properties", "Get",
        g_variant_new("(ss)", kShortcuts, "version"), G_VARIANT_TYPE("(v)"), G_DBUS_CALL_FLAGS_NONE, 2000, nullptr,
        &error);
    if (!reply) {
        g_error_free(error);
        return false;
    }
    g_variant_unref(reply);
    return true;
}

// The XDG shortcut form of the hotkey: "CTRL+ALT+g".
std::string PortalTrigger(int modifiers, guint keyval) {
    std::string trigger;
    if (modifiers & wxMOD_CONTROL) trigger += "CTRL+";
    if (modifiers & wxMOD_ALT) trigger += "ALT+";
    if (modifiers & wxMOD_SHIFT) trigger += "SHIFT+";
    if (modifiers & wxMOD_WIN) trigger += "LOGO+";
    const char* name = gdk_keyval_name(keyval);
    return name ? trigger + name : std::string();
}

bool PortalBind(int modifiers, guint keyval) {
    GDBusConnection* bus = SessionBus();
    if (!bus || !PortalAvailable(bus)) return false;
    std::string trigger = PortalTrigger(modifiers, keyval);
    if (trigger.empty()) return false;

    unsigned generation = g_portal.generation;
    g_portal.activatedSub = g_dbus_connection_signal_subscribe(bus, kPortal, kShortcuts, "Activated", kPortalPath,
                                                               nullptr, G_DBUS_SIGNAL_FLAGS_NONE, OnActivated,
                                                               nullptr, nullptr);

    std::string token = NextToken();
    GVariantBuilder options;
    g_variant_builder_init(&options, G_VARIANT_TYPE_VARDICT);
    g_variant_builder_add(&options, "{sv}", "handle_token", g_variant_new_string(token.c_str()));
    g_variant_builder_add(&options, "{sv}", "session_handle_token", g_variant_new_string(NextToken().c_str()));
    PortalRequest("CreateSession", g_variant_new("(a{sv})", &options), token,
                  [generation, trigger](guint32 response, GVariant* results) {
                      if (generation != g_portal.generation || response != 0 || !results) return;
                      GVariant* handle = g_variant_lookup_value(results, "session_handle", nullptr);
                      if (!handle) return;
                      g_portal.session = g_variant_get_string(handle, nullptr);  // "s" or "o"
                      g_variant_unref(handle);

                      GVariantBuilder shortcut;
                      g_variant_builder_init(&shortcut, G_VARIANT_TYPE_VARDICT);
                      g_variant_builder_add(&shortcut, "{sv}", "description",
                                            g_variant_new_string("Show or hide FastGH"));
                      g_variant_builder_add(&shortcut, "{sv}", "preferred_trigger",
                                            g_variant_new_string(trigger.c_str()));
                      GVariantBuilder shortcuts;
                      g_variant_builder_init(&shortcuts, G_VARIANT_TYPE("a(sa{sv})"));
                      g_variant_builder_add(&shortcuts, "(sa{sv})", kShortcutId, &shortcut);
                      std::string bindToken = NextToken();
                      GVariantBuilder bindOptions;
                      g_variant_builder_init(&bindOptions, G_VARIANT_TYPE_VARDICT);
                      g_variant_builder_add(&bindOptions, "{sv}", "handle_token",
                                            g_variant_new_string(bindToken.c_str()));
                      PortalRequest("BindShortcuts",
                                    g_variant_new("(oa(sa{sv})sa{sv})", g_portal.session.c_str(), &shortcuts, "",
                                                  &bindOptions),
                                    bindToken, [](guint32, GVariant*) {});
                  });
    return true;
}

// --- One running copy, over D-Bus ---

constexpr const char* kBusName = "io.github.masonasons.FastGH";
constexpr const char* kObjectPath = "/io/github/masonasons/FastGH";
constexpr const char* kInterfaceXml =
    "<node><interface name='io.github.masonasons.FastGH'><method name='Activate'/></interface></node>";

std::function<void()> g_showCallback;

}  // namespace

namespace platform {

void ApplyAppearance(const std::string& mode) {
    if (!wxTheApp) return;
    // As on macOS, "off" leaves the desktop's own light or dark theme alone.
    wxTheApp->SetAppearance(mode == "on" ? wxApp::Appearance::Dark : wxApp::Appearance::System);
}

bool RegisterGlobalHotkey(wxFrame* frame, int modifiers, int keyCode, std::function<void()> callback) {
    UnregisterGlobalHotkey(frame);
    guint keyval = KeyvalFor(keyCode);
    if (!keyval) return false;
    bool ok = IsX11() ? X11Grab(modifiers, keyval) : PortalBind(modifiers, keyval);
    if (ok) g_hotkeyCallback = std::move(callback);
    return ok;
}

void UnregisterGlobalHotkey(wxFrame*) {
    X11Ungrab();
    PortalClose();
    g_hotkeyCallback = nullptr;
}

void HideApp(wxFrame* frame) {
    frame->Hide();
}

void ShowApp(wxFrame* frame) {
    if (frame->IsIconized()) frame->Iconize(false);
    // Under Wayland a window can only take the focus with the token the desktop
    // gave with the key press.
    if (!g_portal.activationToken.empty()) {
        if (GtkWidget* widget = frame->GetHandle(); widget && GTK_IS_WINDOW(widget))
            gtk_window_set_startup_id(GTK_WINDOW(widget), g_portal.activationToken.c_str());
        g_portal.activationToken.clear();
    }
    frame->Show();
    frame->Raise();
#ifdef GDK_WINDOWING_X11
    if (unsigned long time = g_hotkeyTime.exchange(0); time && IsX11()) {
        if (GtkWidget* widget = frame->GetHandle(); widget && GTK_IS_WINDOW(widget))
            gtk_window_present_with_time(GTK_WINDOW(widget), static_cast<guint32>(time));
    }
#endif
}

bool IsAppFrontmost(wxFrame* frame) {
    if (!frame->IsShown() || frame->IsIconized()) return false;
#ifdef GDK_WINDOWING_X11
    // The window manager's word for which window is active. GTK's own goes with
    // the keyboard focus, which a screen reader's keyboard grab takes away for
    // as long as the hotkey is held, so it would say "not in front" and the
    // hotkey would never hide the window.
    if (IsX11()) {
        GtkWidget* widget = frame->GetHandle();
        GdkWindow* mine = widget ? gtk_widget_get_window(widget) : nullptr;
        G_GNUC_BEGIN_IGNORE_DEPRECATIONS
        GdkWindow* active = gdk_screen_get_active_window(gdk_screen_get_default());
        G_GNUC_END_IGNORE_DEPRECATIONS
        if (active) {
            bool front = mine && active == mine;
            g_object_unref(active);
            return front;
        }
    }
#endif
    return frame->IsActive();
}

void Announce(const std::string& text) {
    // ATK's "notification" signal (ATK 2.50 and later), which Orca speaks.
    wxWindow* window = wxWindow::FindFocus();
    if (!window && wxTheApp) window = wxTheApp->GetTopWindow();
    GtkWidget* widget = window ? window->GetHandle() : nullptr;
    if (!widget || !g_signal_lookup("notification", ATK_TYPE_OBJECT)) return;
    if (AtkObject* accessible = gtk_widget_get_accessible(widget))
        g_signal_emit_by_name(accessible, "notification", text.c_str(), 2 /* ATK_LIVE_ASSERTIVE */);
}

void SetMenuBarActions(MenuBarActions) {}

void SetBadgeCount(int count) {
    // The Unity launcher API, which KDE's task manager and Ubuntu's dock read.
    GDBusConnection* bus = SessionBus();
    if (!bus) return;
    GVariantBuilder props;
    g_variant_builder_init(&props, G_VARIANT_TYPE_VARDICT);
    g_variant_builder_add(&props, "{sv}", "count", g_variant_new_int64(count));
    g_variant_builder_add(&props, "{sv}", "count-visible", g_variant_new_boolean(count > 0));
    g_dbus_connection_emit_signal(bus, nullptr, "/io/github/masonasons/FastGH/launcher",
                                  "com.canonical.Unity.LauncherEntry", "Update",
                                  g_variant_new("(sa{sv})", "application://FastGH.desktop", &props), nullptr);
}

void LinkLabel(wxWindow* label, wxWindow* control) {
    GtkWidget* labelWidget = label->GetHandle();
    GtkWidget* target = control->GetConnectWidget();
    if (labelWidget && target && GTK_IS_LABEL(labelWidget))
        gtk_label_set_mnemonic_widget(GTK_LABEL(labelWidget), target);
}

bool RevealFile(const std::string& path) {
    GDBusConnection* bus = SessionBus();
    if (!bus) return false;
    gchar* uri = g_filename_to_uri(path.c_str(), nullptr, nullptr);
    if (!uri) return false;
    const gchar* uris[] = {uri, nullptr};
    GError* error = nullptr;
    GVariant* reply = g_dbus_connection_call_sync(
        bus, "org.freedesktop.FileManager1", "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1",
        "ShowItems", g_variant_new("(^ass)", uris, ""), nullptr, G_DBUS_CALL_FLAGS_NONE, 5000, nullptr, &error);
    g_free(uri);
    if (!reply) {
        g_error_free(error);
        return false;
    }
    g_variant_unref(reply);
    return true;
}

InstanceClaim ClaimSingleInstance(std::function<void()> show) {
    GDBusConnection* bus = SessionBus();
    if (!bus) return InstanceClaim::NoBus;

    // Answer first, then take the name, so a copy started in between finds someone home.
    static GDBusNodeInfo* info = g_dbus_node_info_new_for_xml(kInterfaceXml, nullptr);
    static const GDBusInterfaceVTable vtable = {
        [](GDBusConnection*, const gchar*, const gchar*, const gchar*, const gchar*, GVariant*,
           GDBusMethodInvocation* invocation, gpointer) {
            if (g_showCallback && wxTheApp) wxTheApp->CallAfter([] {
                if (g_showCallback) g_showCallback();
            });
            g_dbus_method_invocation_return_value(invocation, nullptr);
        },
        nullptr, nullptr, {}};
    guint registration = g_dbus_connection_register_object(bus, kObjectPath, info->interfaces[0], &vtable,
                                                           nullptr, nullptr, nullptr);

    GVariant* reply = g_dbus_connection_call_sync(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                                                  "org.freedesktop.DBus", "RequestName",
                                                  g_variant_new("(su)", kBusName, 4u /* DO_NOT_QUEUE */),
                                                  G_VARIANT_TYPE("(u)"), G_DBUS_CALL_FLAGS_NONE, 5000, nullptr,
                                                  nullptr);
    if (!reply) {
        if (registration) g_dbus_connection_unregister_object(bus, registration);
        return InstanceClaim::NoBus;
    }
    guint32 result = 0;
    g_variant_get(reply, "(u)", &result);
    g_variant_unref(reply);
    if (result == 1 /* PRIMARY_OWNER */ || result == 4 /* ALREADY_OWNER */) {
        g_showCallback = std::move(show);
        return InstanceClaim::First;
    }

    if (registration) g_dbus_connection_unregister_object(bus, registration);
    GVariant* activated = g_dbus_connection_call_sync(bus, kBusName, kObjectPath, kBusName, "Activate", nullptr,
                                                      nullptr, G_DBUS_CALL_FLAGS_NONE, 5000, nullptr, nullptr);
    if (!activated) return InstanceClaim::NotAnswering;
    g_variant_unref(activated);
    return InstanceClaim::Handed;
}

}  // namespace platform
