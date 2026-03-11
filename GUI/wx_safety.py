import platform


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
