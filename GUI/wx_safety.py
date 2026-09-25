import platform

import wx


def safe_raise(window) -> bool:
    """Best-effort window raise that avoids known macOS wx crashes."""
    if window is None:
        return False
    try:
        if hasattr(window, "IsBeingDeleted") and window.IsBeingDeleted():
            return False
        if hasattr(window, "IsShown") and not window.IsShown():
            return False
        # wx Raise() has been crashing on macOS in some dialog/window states.
        if platform.system() == "Darwin":
            if hasattr(window, "SetFocus"):
                window.SetFocus()
            return False
        window.Raise()
        return True
    except RuntimeError:
        return False


def is_enter_key(event) -> bool:
    """True for either Return or the numpad Enter key."""
    return event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)


def run_key_action(action):
    """Run an action triggered from a key hook.

    On macOS, opening modal dialogs directly from key hooks can crash in
    wxWidgets Cocoa, so defer to the next event-loop turn there.
    """
    if platform.system() == "Darwin":
        wx.CallAfter(action, None)
    else:
        action(None)
