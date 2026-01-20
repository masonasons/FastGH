"""Options dialog for FastGH."""

import os
import platform
import wx
from application import get_app
from . import theme

# Check if hotkey support is available
if platform.system() != "Darwin":
    try:
        from keyboard_handler.wx_handler import WXKeyboardHandler
        HOTKEY_SUPPORTED = True
    except ImportError:
        HOTKEY_SUPPORTED = False
else:
    HOTKEY_SUPPORTED = False


class OptionsDialog(wx.Dialog):
    """Dialog for application options."""

    def __init__(self, parent):
        self.app = get_app()
        self.parent_window = parent

        wx.Dialog.__init__(self, parent, title="Options", size=(500, 380))

        self.init_ui()
        self.bind_events()
        self.load_settings()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Commits section
        commits_box = wx.StaticBox(self.panel, label="Commits")
        commits_sizer = wx.StaticBoxSizer(commits_box, wx.VERTICAL)

        # Commit limit row
        limit_row = wx.BoxSizer(wx.HORIZONTAL)

        limit_label = wx.StaticText(self.panel, label="Commit &limit when loading:")
        limit_row.Add(limit_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        self.limit_spin = wx.SpinCtrl(
            self.panel,
            min=0,
            max=1000,
            initial=0,
            style=wx.SP_ARROW_KEYS
        )
        self.limit_spin.SetToolTip("Number of commits to load (0 = all commits)")
        limit_row.Add(self.limit_spin, 0, wx.RIGHT, 10)

        limit_hint = wx.StaticText(self.panel, label="(0 = all)")
        limit_row.Add(limit_hint, 0, wx.ALIGN_CENTER_VERTICAL)

        commits_sizer.Add(limit_row, 0, wx.ALL | wx.EXPAND, 10)

        main_sizer.Add(commits_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Downloads section
        downloads_box = wx.StaticBox(self.panel, label="Downloads")
        downloads_sizer = wx.StaticBoxSizer(downloads_box, wx.VERTICAL)

        # Download location row
        download_row = wx.BoxSizer(wx.HORIZONTAL)

        download_label = wx.StaticText(self.panel, label="&Download location:")
        download_row.Add(download_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        self.download_path = wx.TextCtrl(self.panel, size=(280, -1))
        self.download_path.SetToolTip("Default folder for downloading release artifacts")
        download_row.Add(self.download_path, 1, wx.RIGHT, 5)

        self.browse_btn = wx.Button(self.panel, label="&Browse...")
        download_row.Add(self.browse_btn, 0)

        downloads_sizer.Add(download_row, 0, wx.ALL | wx.EXPAND, 10)

        main_sizer.Add(downloads_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Git section
        git_box = wx.StaticBox(self.panel, label="Git")
        git_sizer = wx.StaticBoxSizer(git_box, wx.VERTICAL)

        # Git path row
        git_row = wx.BoxSizer(wx.HORIZONTAL)

        git_label = wx.StaticText(self.panel, label="&Git repositories path:")
        git_row.Add(git_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        self.git_path = wx.TextCtrl(self.panel, size=(280, -1))
        self.git_path.SetToolTip("Folder where repositories will be cloned")
        git_row.Add(self.git_path, 1, wx.RIGHT, 5)

        self.git_browse_btn = wx.Button(self.panel, label="Br&owse...")
        git_row.Add(self.git_browse_btn, 0)

        git_sizer.Add(git_row, 0, wx.ALL | wx.EXPAND, 10)

        main_sizer.Add(git_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Hotkey section (only show if supported)
        if HOTKEY_SUPPORTED:
            hotkey_box = wx.StaticBox(self.panel, label="Global Hotkey")
            hotkey_sizer = wx.StaticBoxSizer(hotkey_box, wx.VERTICAL)

            # Hotkey row
            hotkey_row = wx.BoxSizer(wx.HORIZONTAL)

            hotkey_label = wx.StaticText(self.panel, label="Show/&Hide window:")
            hotkey_row.Add(hotkey_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

            self.hotkey_text = wx.TextCtrl(self.panel, size=(200, -1))
            self.hotkey_text.SetToolTip(
                "Global hotkey to show/hide window.\n"
                "Format: modifier+modifier+key\n"
                "Modifiers: control, alt, shift, win\n"
                "Example: control+alt+g"
            )
            hotkey_row.Add(self.hotkey_text, 1, wx.RIGHT, 5)

            self.clear_hotkey_btn = wx.Button(self.panel, label="C&lear")
            hotkey_row.Add(self.clear_hotkey_btn, 0)

            hotkey_sizer.Add(hotkey_row, 0, wx.ALL | wx.EXPAND, 10)

            # Hotkey hint
            hint_label = wx.StaticText(
                self.panel,
                label="Format: control+alt+g, win+shift+h, etc. Leave empty to disable."
            )
            hotkey_sizer.Add(hint_label, 0, wx.LEFT | wx.BOTTOM, 10)

            main_sizer.Add(hotkey_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Spacer
        main_sizer.AddStretchSpacer()

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.ok_btn = wx.Button(self.panel, wx.ID_OK, label="&OK")
        btn_sizer.Add(self.ok_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(self.cancel_btn, 0, wx.RIGHT, 5)

        self.apply_btn = wx.Button(self.panel, label="&Apply")
        btn_sizer.Add(self.apply_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply)
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.git_browse_btn.Bind(wx.EVT_BUTTON, self.on_git_browse)

        if HOTKEY_SUPPORTED:
            self.clear_hotkey_btn.Bind(wx.EVT_BUTTON, self.on_clear_hotkey)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def load_settings(self):
        """Load current settings into the dialog."""
        self.limit_spin.SetValue(self.app.prefs.commit_limit)
        self.download_path.SetValue(self.app.prefs.download_location)
        self.git_path.SetValue(self.app.prefs.git_path)

        if HOTKEY_SUPPORTED:
            self.hotkey_text.SetValue(self.app.prefs.global_hotkey)

    def save_settings(self):
        """Save settings from the dialog."""
        self.app.prefs.commit_limit = self.limit_spin.GetValue()
        self.app.prefs.download_location = self.download_path.GetValue()
        self.app.prefs.git_path = self.git_path.GetValue()

        # Save hotkey if supported
        if HOTKEY_SUPPORTED:
            new_hotkey = self.hotkey_text.GetValue().strip().lower()

            # Validate hotkey format if not empty
            if new_hotkey:
                # Basic validation - must have at least one modifier and a key
                parts = new_hotkey.split('+')
                valid_modifiers = {'control', 'ctrl', 'alt', 'shift', 'win'}
                has_modifier = any(p in valid_modifiers for p in parts)

                if not has_modifier or len(parts) < 2:
                    wx.MessageBox(
                        "Invalid hotkey format.\n\n"
                        "Please use format: modifier+key\n"
                        "Example: control+alt+g",
                        "Invalid Hotkey",
                        wx.OK | wx.ICON_WARNING
                    )
                    return False

            # Try to update the hotkey
            from GUI import main
            if main.window and hasattr(main.window, 'update_global_hotkey'):
                if not main.window.update_global_hotkey(new_hotkey):
                    wx.MessageBox(
                        f"Failed to register hotkey: {new_hotkey}\n\n"
                        "The hotkey may already be in use by another application.",
                        "Hotkey Error",
                        wx.OK | wx.ICON_ERROR
                    )
                    return False

        return True

    def on_browse(self, event):
        """Browse for download location."""
        current = self.download_path.GetValue()
        if not current or not os.path.isdir(current):
            current = os.path.expanduser("~")

        dlg = wx.DirDialog(
            self,
            "Select Download Location",
            defaultPath=current,
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
        )

        if dlg.ShowModal() == wx.ID_OK:
            self.download_path.SetValue(dlg.GetPath())

        dlg.Destroy()

    def on_git_browse(self, event):
        """Browse for git repositories path."""
        current = self.git_path.GetValue()
        if not current or not os.path.isdir(current):
            current = os.path.expanduser("~")

        dlg = wx.DirDialog(
            self,
            "Select Git Repositories Path",
            defaultPath=current,
            style=wx.DD_DEFAULT_STYLE
        )

        if dlg.ShowModal() == wx.ID_OK:
            self.git_path.SetValue(dlg.GetPath())

        dlg.Destroy()

    def on_clear_hotkey(self, event):
        """Clear the hotkey field."""
        self.hotkey_text.SetValue("")

    def on_ok(self, event):
        """Handle OK button."""
        if self.save_settings():
            self.EndModal(wx.ID_OK)

    def on_cancel(self, event):
        """Handle Cancel button."""
        self.EndModal(wx.ID_CANCEL)

    def on_apply(self, event):
        """Handle Apply button."""
        if self.save_settings():
            wx.MessageBox("Settings applied.", "Options", wx.OK | wx.ICON_INFORMATION)

    def on_close(self, event):
        """Handle close."""
        self.EndModal(wx.ID_CANCEL)
