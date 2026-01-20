"""Theme support for FastGH - dark/light mode."""

import wx
import platform

# Dark mode colors
DARK_BG = wx.Colour(32, 32, 32)
DARK_FG = wx.Colour(255, 255, 255)
DARK_CTRL_BG = wx.Colour(45, 45, 45)

# Light mode colors (system default)
LIGHT_BG = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
LIGHT_FG = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)


def is_system_dark_mode():
    """Detect if the system is using dark mode."""
    try:
        if platform.system() == "Darwin":
            # macOS
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True
            )
            return result.stdout.strip().lower() == "dark"
        elif platform.system() == "Windows":
            # Windows 10/11
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
    except:
        pass
    return False


def apply_theme(window, dark_mode=None):
    """Apply theme to window and all children.

    Args:
        window: The wx.Window to apply theme to
        dark_mode: 'on', 'off', or 'auto' (None uses app preference)
    """
    from application import get_app
    app = get_app()

    if dark_mode is None:
        dark_mode = app.prefs.get("dark_mode", "off")

    if dark_mode == "auto":
        use_dark = is_system_dark_mode()
    elif dark_mode == "on":
        use_dark = True
    else:
        use_dark = False

    if use_dark:
        bg = DARK_BG
        fg = DARK_FG
        ctrl_bg = DARK_CTRL_BG
    else:
        bg = LIGHT_BG
        fg = LIGHT_FG
        ctrl_bg = LIGHT_BG

    _apply_theme_recursive(window, bg, fg, ctrl_bg)


def _apply_theme_recursive(window, bg, fg, ctrl_bg):
    """Recursively apply theme to window and children."""
    try:
        window.SetBackgroundColour(bg)
        window.SetForegroundColour(fg)

        # Special handling for certain control types
        if isinstance(window, (wx.TextCtrl, wx.ListCtrl, wx.ListBox, wx.TreeCtrl)):
            window.SetBackgroundColour(ctrl_bg)

        # Apply to all children
        for child in window.GetChildren():
            _apply_theme_recursive(child, bg, fg, ctrl_bg)

        window.Refresh()
    except:
        pass
