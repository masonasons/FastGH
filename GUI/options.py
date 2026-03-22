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


EVENT_DISPLAY_NAMES = {
    "PullRequestEvent":              "&Pull Request opened/closed/merged",
    "PullRequestReviewEvent":        "Pull Request &Review submitted",
    "PullRequestReviewCommentEvent": "Pull Request Review &Comment",
    "PullRequestReviewThreadEvent":  "Pull Request Review &Thread",
    "IssuesEvent":                   "&Issue opened/closed/labeled",
    "IssueCommentEvent":             "Issue C&omment",
    "PushEvent":                     "P&ush (commits)",
    "CommitCommentEvent":            "Commit Comm&ent",
    "CreateEvent":                   "C&reate branch/tag/repo",
    "DeleteEvent":                   "&Delete branch/tag",
    "ForkEvent":                     "&Fork",
    "WatchEvent":                    "&Star (watch event)",
    "MemberEvent":                   "&Member added as collaborator",
    "GollumEvent":                   "&Wiki page updated",
    "ReleaseEvent":                  "&Release published",
    "DiscussionEvent":               "&Discussion created/answered",
    "DiscussionCommentEvent":        "Discussion Co&mment",
    "SponsorshipEvent":              "Spon&sorship",
    "PublicEvent":                   "Repo made P&ublic",
}


class OptionsDialog(wx.Dialog):
    """Dialog for application options."""

    def __init__(self, parent):
        self.app = get_app()
        self.parent_window = parent

        wx.Dialog.__init__(self, parent, title="Options", size=(580, 900))

        self.init_ui()
        self.bind_events()
        self.load_settings()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        outer_sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(self.panel)

        self.general_panel = wx.ScrolledWindow(self.notebook)
        self.general_panel.SetScrollRate(0, 20)
        self._build_general_tab(self.general_panel)
        self.notebook.AddPage(self.general_panel, "General")

        self.filters_panel = wx.ScrolledWindow(self.notebook)
        self.filters_panel.SetScrollRate(0, 20)
        self._build_filters_tab(self.filters_panel)
        self.notebook.AddPage(self.filters_panel, "Feed Filters")

        outer_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.ok_btn = wx.Button(self.panel, wx.ID_OK, label="&OK")
        btn_sizer.Add(self.ok_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(self.cancel_btn, 0, wx.RIGHT, 5)

        self.apply_btn = wx.Button(self.panel, label="&Apply")
        btn_sizer.Add(self.apply_btn, 0)

        outer_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(outer_sizer)

    def _build_general_tab(self, panel):
        """Build the General settings tab content."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Commits section
        commits_box = wx.StaticBox(panel, label="Commits")
        commits_sizer = wx.StaticBoxSizer(commits_box, wx.VERTICAL)

        limit_row = wx.BoxSizer(wx.HORIZONTAL)
        limit_label = wx.StaticText(panel, label="Commit &limit when loading:")
        limit_row.Add(limit_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.limit_spin = wx.SpinCtrl(panel, min=0, max=5000, initial=0, style=wx.SP_ARROW_KEYS)
        self.limit_spin.SetToolTip("Number of commits to load (0 = all commits)")
        limit_row.Add(self.limit_spin, 0, wx.RIGHT, 10)
        limit_hint = wx.StaticText(panel, label="(0 = all)")
        limit_row.Add(limit_hint, 0, wx.ALIGN_CENTER_VERTICAL)
        commits_sizer.Add(limit_row, 0, wx.ALL | wx.EXPAND, 10)

        main_sizer.Add(commits_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Downloads section
        downloads_box = wx.StaticBox(panel, label="Downloads")
        downloads_sizer = wx.StaticBoxSizer(downloads_box, wx.VERTICAL)

        download_row = wx.BoxSizer(wx.HORIZONTAL)
        download_label = wx.StaticText(panel, label="&Download location:")
        download_row.Add(download_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.download_path = wx.TextCtrl(panel, size=(280, -1))
        self.download_path.SetToolTip("Default folder for downloading release artifacts")
        download_row.Add(self.download_path, 1, wx.RIGHT, 5)
        self.browse_btn = wx.Button(panel, label="&Browse...")
        download_row.Add(self.browse_btn, 0)
        downloads_sizer.Add(download_row, 0, wx.ALL | wx.EXPAND, 10)

        main_sizer.Add(downloads_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Git section
        git_box = wx.StaticBox(panel, label="Git")
        git_sizer = wx.StaticBoxSizer(git_box, wx.VERTICAL)

        git_row = wx.BoxSizer(wx.HORIZONTAL)
        git_label = wx.StaticText(panel, label="&Git repositories path:")
        git_row.Add(git_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.git_path = wx.TextCtrl(panel, size=(280, -1))
        self.git_path.SetToolTip("Folder where repositories will be cloned")
        git_row.Add(self.git_path, 1, wx.RIGHT, 5)
        self.git_browse_btn = wx.Button(panel, label="Br&owse...")
        git_row.Add(self.git_browse_btn, 0)
        git_sizer.Add(git_row, 0, wx.ALL | wx.EXPAND, 10)

        self.git_org_structure_cb = wx.CheckBox(panel, label="Clone into &owner/repo folder structure")
        self.git_org_structure_cb.SetToolTip(
            "When enabled, repositories are cloned to owner/repo\n"
            "(e.g., masonasons/FastGH instead of just FastGH)"
        )
        git_sizer.Add(self.git_org_structure_cb, 0, wx.LEFT | wx.BOTTOM, 10)

        self.git_recursive_cb = wx.CheckBox(panel, label="Clone rec&ursively (include submodules)")
        self.git_recursive_cb.SetToolTip(
            "When enabled, git clone will use --recursive to also clone submodules"
        )
        git_sizer.Add(self.git_recursive_cb, 0, wx.LEFT | wx.BOTTOM, 10)

        self.git_lfs_cb = wx.CheckBox(panel, label="Enable Git &LFS support for clone/pull/sync")
        self.git_lfs_cb.SetToolTip(
            "Runs git lfs install/pull after clone/pull and during scheduled sync.\n"
            "If git-lfs is not installed, operations continue with a warning."
        )
        git_sizer.Add(self.git_lfs_cb, 0, wx.LEFT | wx.BOTTOM, 10)

        main_sizer.Add(git_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Repository sync section
        sync_box = wx.StaticBox(panel, label="Repository Sync")
        sync_sizer = wx.StaticBoxSizer(sync_box, wx.VERTICAL)

        self.repo_sync_enabled_cb = wx.CheckBox(
            panel, label="Enable scheduled auto sync for configured repositories"
        )
        sync_sizer.Add(self.repo_sync_enabled_cb, 0, wx.LEFT | wx.TOP, 10)

        interval_row = wx.BoxSizer(wx.HORIZONTAL)
        interval_label = wx.StaticText(panel, label="Sync interval:")
        interval_row.Add(interval_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.repo_sync_interval_spin = wx.SpinCtrl(panel, min=0, max=240, initial=0, style=wx.SP_ARROW_KEYS)
        self.repo_sync_interval_spin.SetToolTip("Minutes between sync runs (0 = disabled)")
        interval_row.Add(self.repo_sync_interval_spin, 0, wx.RIGHT, 5)
        interval_hint = wx.StaticText(panel, label="minutes (0 = disabled)")
        interval_row.Add(interval_hint, 0, wx.ALIGN_CENTER_VERTICAL)
        sync_sizer.Add(interval_row, 0, wx.ALL, 10)

        self.repo_sync_use_tools_cb = wx.CheckBox(
            panel, label="Use .GITHUB repo bootstrap updater before git sync"
        )
        sync_sizer.Add(self.repo_sync_use_tools_cb, 0, wx.LEFT | wx.BOTTOM, 10)

        tools_row = wx.BoxSizer(wx.HORIZONTAL)
        tools_label = wx.StaticText(panel, label=".GITHUB tools path:")
        tools_row.Add(tools_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.repo_sync_tools_path = wx.TextCtrl(panel, size=(300, -1))
        tools_row.Add(self.repo_sync_tools_path, 1, wx.RIGHT, 5)
        self.repo_sync_tools_browse_btn = wx.Button(panel, label="Brow&se...")
        tools_row.Add(self.repo_sync_tools_browse_btn, 0)
        sync_sizer.Add(tools_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

        main_sizer.Add(sync_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Notifications section
        notif_box = wx.StaticBox(panel, label="Desktop Notifications")
        notif_sizer = wx.StaticBoxSizer(notif_box, wx.VERTICAL)

        self.notify_activity_cb = wx.CheckBox(panel, label="Notify on new &activity feed items")
        notif_sizer.Add(self.notify_activity_cb, 0, wx.LEFT | wx.TOP, 10)

        self.notify_notifications_cb = wx.CheckBox(panel, label="Notify on new GitHub &notifications")
        notif_sizer.Add(self.notify_notifications_cb, 0, wx.LEFT | wx.TOP, 5)

        self.notify_starred_cb = wx.CheckBox(panel, label="Notify on &starred repository updates")
        notif_sizer.Add(self.notify_starred_cb, 0, wx.LEFT | wx.TOP, 5)

        self.notify_watched_cb = wx.CheckBox(panel, label="Notify on &watched repository updates")
        notif_sizer.Add(self.notify_watched_cb, 0, wx.LEFT | wx.TOP, 5)

        self.notify_repo_sync_cb = wx.CheckBox(panel, label="Notify on repository &sync results")
        notif_sizer.Add(self.notify_repo_sync_cb, 0, wx.LEFT | wx.TOP, 5)

        refresh_row = wx.BoxSizer(wx.HORIZONTAL)
        refresh_label = wx.StaticText(panel, label="Auto-&refresh interval:")
        refresh_row.Add(refresh_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.refresh_spin = wx.SpinCtrl(panel, min=0, max=60, initial=0, style=wx.SP_ARROW_KEYS)
        self.refresh_spin.SetToolTip("How often to check for updates (0 = disabled)")
        refresh_row.Add(self.refresh_spin, 0, wx.RIGHT, 5)
        refresh_hint = wx.StaticText(panel, label="minutes (0 = disabled)")
        refresh_row.Add(refresh_hint, 0, wx.ALIGN_CENTER_VERTICAL)
        notif_sizer.Add(refresh_row, 0, wx.ALL, 10)

        main_sizer.Add(notif_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Hotkey section (only show if supported)
        if HOTKEY_SUPPORTED:
            hotkey_box = wx.StaticBox(panel, label="Global Hotkey")
            hotkey_sizer = wx.StaticBoxSizer(hotkey_box, wx.VERTICAL)

            hotkey_row = wx.BoxSizer(wx.HORIZONTAL)
            hotkey_label = wx.StaticText(panel, label="Show/&Hide window:")
            hotkey_row.Add(hotkey_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
            self.hotkey_text = wx.TextCtrl(panel, size=(200, -1))
            self.hotkey_text.SetToolTip(
                "Global hotkey to show/hide window.\n"
                "Format: modifier+modifier+key\n"
                "Modifiers: control, alt, shift, win\n"
                "Example: control+alt+g"
            )
            hotkey_row.Add(self.hotkey_text, 1, wx.RIGHT, 5)
            self.clear_hotkey_btn = wx.Button(panel, label="C&lear")
            hotkey_row.Add(self.clear_hotkey_btn, 0)
            hotkey_sizer.Add(hotkey_row, 0, wx.ALL | wx.EXPAND, 10)

            hint_label = wx.StaticText(
                panel,
                label="Format: control+alt+g, win+shift+h, etc. Leave empty to disable."
            )
            hotkey_sizer.Add(hint_label, 0, wx.LEFT | wx.BOTTOM, 10)

            main_sizer.Add(hotkey_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Appearance section
        appearance_box = wx.StaticBox(panel, label="Appearance")
        appearance_sizer = wx.StaticBoxSizer(appearance_box, wx.VERTICAL)

        dark_mode_row = wx.BoxSizer(wx.HORIZONTAL)
        dark_mode_label = wx.StaticText(panel, label="&Dark mode:")
        dark_mode_row.Add(dark_mode_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.dark_mode_choice = wx.Choice(panel, choices=["Off", "Auto (follow system)", "On"])
        self.dark_mode_choice.SetToolTip(
            "Off: Always use light theme\n"
            "Auto: Follow system theme setting\n"
            "On: Always use dark theme"
        )
        dark_mode_row.Add(self.dark_mode_choice, 0)
        appearance_sizer.Add(dark_mode_row, 0, wx.ALL, 10)

        main_sizer.Add(appearance_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Updates section
        updates_box = wx.StaticBox(panel, label="Updates")
        updates_sizer = wx.StaticBoxSizer(updates_box, wx.VERTICAL)
        self.check_for_updates_cb = wx.CheckBox(panel, label="Check for &updates on startup")
        updates_sizer.Add(self.check_for_updates_cb, 0, wx.ALL, 10)
        main_sizer.Add(updates_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        main_sizer.AddStretchSpacer()
        panel.SetSizer(main_sizer)

    def _build_filters_tab(self, panel):
        """Build the Feed Filters tab content."""
        from models.feed_filter import FILTER_GROUPS
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label=(
                "Choose which event types appear in your activity feed.\n"
                "Changes apply per account and take effect immediately on Apply."
            )
        )
        intro.Wrap(520)
        main_sizer.Add(intro, 0, wx.ALL, 10)

        self.filter_checkboxes: dict = {}

        for group_label, event_types in FILTER_GROUPS:
            group_box = wx.StaticBox(panel, label=group_label)
            group_sizer = wx.StaticBoxSizer(group_box, wx.VERTICAL)

            for et in event_types:
                label = EVENT_DISPLAY_NAMES.get(et, et)
                cb = wx.CheckBox(panel, label=label)
                self.filter_checkboxes[et] = cb
                group_sizer.Add(cb, 0, wx.LEFT | wx.TOP, 8)

            group_sizer.AddSpacer(6)
            main_sizer.Add(group_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Select All / Deselect All buttons
        bulk_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.select_all_btn = wx.Button(panel, label="Select &All")
        bulk_sizer.Add(self.select_all_btn, 0, wx.RIGHT, 8)
        self.deselect_all_btn = wx.Button(panel, label="&Deselect All")
        bulk_sizer.Add(self.deselect_all_btn, 0)
        main_sizer.Add(bulk_sizer, 0, wx.LEFT | wx.BOTTOM, 10)

        # Muted Repositories section
        mute_box = wx.StaticBox(panel, label="Muted Repositories")
        mute_sizer = wx.StaticBoxSizer(mute_box, wx.VERTICAL)

        mute_intro = wx.StaticText(
            panel,
            label="Events from muted repositories are always hidden, regardless of event type."
        )
        mute_intro.Wrap(500)
        mute_sizer.Add(mute_intro, 0, wx.ALL, 8)

        self.muted_repos_list = wx.ListBox(panel, size=(-1, 100), style=wx.LB_SINGLE)
        mute_sizer.Add(self.muted_repos_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        add_row = wx.BoxSizer(wx.HORIZONTAL)
        self.muted_repo_entry = wx.TextCtrl(panel, size=(280, -1), style=wx.TE_PROCESS_ENTER)
        self.muted_repo_entry.SetHint("owner/repo")
        add_row.Add(self.muted_repo_entry, 1, wx.RIGHT, 6)
        self.mute_add_btn = wx.Button(panel, label="&Add")
        add_row.Add(self.mute_add_btn, 0, wx.RIGHT, 4)
        self.mute_remove_btn = wx.Button(panel, label="&Remove")
        add_row.Add(self.mute_remove_btn, 0)
        mute_sizer.Add(add_row, 0, wx.EXPAND | wx.ALL, 8)

        main_sizer.Add(mute_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply)
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.git_browse_btn.Bind(wx.EVT_BUTTON, self.on_git_browse)
        self.repo_sync_tools_browse_btn.Bind(wx.EVT_BUTTON, self.on_repo_sync_tools_browse)

        if HOTKEY_SUPPORTED:
            self.clear_hotkey_btn.Bind(wx.EVT_BUTTON, self.on_clear_hotkey)

        self.select_all_btn.Bind(wx.EVT_BUTTON, self.on_select_all_filters)
        self.deselect_all_btn.Bind(wx.EVT_BUTTON, self.on_deselect_all_filters)
        self.mute_add_btn.Bind(wx.EVT_BUTTON, self.on_mute_add)
        self.mute_remove_btn.Bind(wx.EVT_BUTTON, self.on_mute_remove)
        self.muted_repo_entry.Bind(wx.EVT_TEXT_ENTER, self.on_mute_add)

    def on_char_hook(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.on_close(None)
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if self.save_settings():
                self.EndModal(wx.ID_OK)
        else:
            event.Skip()

    def load_settings(self):
        """Load current settings into the dialog."""
        self.limit_spin.SetValue(self.app.prefs.commit_limit)
        self.download_path.SetValue(self.app.prefs.download_location)
        self.git_path.SetValue(self.app.prefs.git_path)
        self.git_org_structure_cb.SetValue(self.app.prefs.git_use_org_structure)
        self.git_recursive_cb.SetValue(self.app.prefs.git_clone_recursive)
        self.git_lfs_cb.SetValue(self.app.prefs.git_lfs_enabled)
        self.repo_sync_enabled_cb.SetValue(self.app.prefs.repo_sync_enabled)
        self.repo_sync_interval_spin.SetValue(self.app.prefs.repo_sync_interval_minutes)
        self.repo_sync_use_tools_cb.SetValue(self.app.prefs.repo_sync_use_github_tools)
        self.repo_sync_tools_path.SetValue(self.app.prefs.repo_sync_github_tools_path)

        # Notification settings
        self.notify_activity_cb.SetValue(self.app.prefs.notify_activity)
        self.notify_notifications_cb.SetValue(self.app.prefs.notify_notifications)
        self.notify_starred_cb.SetValue(self.app.prefs.notify_starred)
        self.notify_watched_cb.SetValue(self.app.prefs.notify_watched)
        self.notify_repo_sync_cb.SetValue(self.app.prefs.repo_sync_notify)
        self.refresh_spin.SetValue(self.app.prefs.auto_refresh_interval)

        if HOTKEY_SUPPORTED:
            self.hotkey_text.SetValue(self.app.prefs.global_hotkey)

        # Dark mode setting
        dark_mode = self.app.prefs.dark_mode
        if dark_mode == "off":
            self.dark_mode_choice.SetSelection(0)
        elif dark_mode == "auto":
            self.dark_mode_choice.SetSelection(1)
        elif dark_mode == "on":
            self.dark_mode_choice.SetSelection(2)
        else:
            self.dark_mode_choice.SetSelection(0)

        # Updates setting
        self.check_for_updates_cb.SetValue(self.app.prefs.check_for_updates)

        # Feed filter settings (per account)
        if self.app.currentAccount:
            from models.feed_filter import load_visible_types, load_muted_repos
            visible = load_visible_types(self.app.currentAccount.prefs)
            for event_type, cb in self.filter_checkboxes.items():
                cb.SetValue(True if visible is None else event_type in visible)
            muted = load_muted_repos(self.app.currentAccount.prefs) or set()
            self.muted_repos_list.Set(sorted(muted))
        else:
            for cb in self.filter_checkboxes.values():
                cb.SetValue(True)
            self.muted_repos_list.Clear()

    def save_settings(self):
        """Save settings from the dialog."""
        self.app.prefs.commit_limit = self.limit_spin.GetValue()
        self.app.prefs.download_location = self.download_path.GetValue()
        self.app.prefs.git_path = self.git_path.GetValue()
        self.app.prefs.git_use_org_structure = self.git_org_structure_cb.GetValue()
        self.app.prefs.git_clone_recursive = self.git_recursive_cb.GetValue()
        self.app.prefs.git_lfs_enabled = self.git_lfs_cb.GetValue()
        self.app.prefs.repo_sync_enabled = self.repo_sync_enabled_cb.GetValue()
        self.app.prefs.repo_sync_interval_minutes = self.repo_sync_interval_spin.GetValue()
        self.app.prefs.repo_sync_use_github_tools = self.repo_sync_use_tools_cb.GetValue()
        self.app.prefs.repo_sync_github_tools_path = self.repo_sync_tools_path.GetValue().strip()

        # Save notification settings
        self.app.prefs.notify_activity = self.notify_activity_cb.GetValue()
        self.app.prefs.notify_notifications = self.notify_notifications_cb.GetValue()
        self.app.prefs.notify_starred = self.notify_starred_cb.GetValue()
        self.app.prefs.notify_watched = self.notify_watched_cb.GetValue()
        self.app.prefs.repo_sync_notify = self.notify_repo_sync_cb.GetValue()

        old_interval = self.app.prefs.auto_refresh_interval
        new_interval = self.refresh_spin.GetValue()
        self.app.prefs.auto_refresh_interval = new_interval

        # Update auto-refresh timer if interval changed
        if old_interval != new_interval:
            from GUI import main
            if main.window and hasattr(main.window, 'update_auto_refresh_timer'):
                main.window.update_auto_refresh_timer()
        from GUI import main
        if main.window and hasattr(main.window, 'update_repo_sync_timer'):
            main.window.update_repo_sync_timer()

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

        # Save dark mode setting
        dark_mode_selection = self.dark_mode_choice.GetSelection()
        dark_mode_values = ["off", "auto", "on"]
        old_dark_mode = self.app.prefs.dark_mode
        new_dark_mode = dark_mode_values[dark_mode_selection]
        self.app.prefs.dark_mode = new_dark_mode

        # Apply theme if dark mode changed
        if old_dark_mode != new_dark_mode:
            from GUI import main
            if main.window:
                theme.apply_theme(main.window)
                # Also apply to this dialog
                theme.apply_theme(self)

        # Save updates setting
        self.app.prefs.check_for_updates = self.check_for_updates_cb.GetValue()

        # Save feed filter settings (per account)
        if self.app.currentAccount:
            from models.feed_filter import save_visible_types, save_muted_repos
            visible = {et for et, cb in self.filter_checkboxes.items() if cb.GetValue()}
            save_visible_types(self.app.currentAccount.prefs, visible)
            muted = {self.muted_repos_list.GetString(i) for i in range(self.muted_repos_list.GetCount())}
            save_muted_repos(self.app.currentAccount.prefs, muted)
            from GUI import main as _main
            if _main.window:
                _main.window._render_feed_list()

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

    def on_repo_sync_tools_browse(self, event):
        """Browse for .GITHUB tools path."""
        current = self.repo_sync_tools_path.GetValue()
        if not current or not os.path.isdir(current):
            current = os.path.expanduser("~")

        dlg = wx.DirDialog(
            self,
            "Select .GITHUB Tools Path",
            defaultPath=current,
            style=wx.DD_DEFAULT_STYLE
        )

        if dlg.ShowModal() == wx.ID_OK:
            self.repo_sync_tools_path.SetValue(dlg.GetPath())

        dlg.Destroy()

    def on_clear_hotkey(self, event):
        """Clear the hotkey field."""
        self.hotkey_text.SetValue("")

    def on_select_all_filters(self, event):
        """Check all feed filter checkboxes."""
        for cb in self.filter_checkboxes.values():
            cb.SetValue(True)

    def on_deselect_all_filters(self, event):
        """Uncheck all feed filter checkboxes."""
        for cb in self.filter_checkboxes.values():
            cb.SetValue(False)

    def on_mute_add(self, event):
        """Add a repo to the muted list."""
        repo = self.muted_repo_entry.GetValue().strip()
        if not repo:
            return
        # Basic format validation
        if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
            wx.MessageBox(
                "Please enter a repository in owner/repo format.\nExample: torvalds/linux",
                "Invalid Format",
                wx.OK | wx.ICON_WARNING,
            )
            return
        existing = [self.muted_repos_list.GetString(i) for i in range(self.muted_repos_list.GetCount())]
        if repo not in existing:
            self.muted_repos_list.Append(repo)
        self.muted_repo_entry.SetValue("")

    def on_mute_remove(self, event):
        """Remove the selected repo from the muted list."""
        sel = self.muted_repos_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self.muted_repos_list.Delete(sel)

    def on_ok(self, event):
        """Handle OK button."""
        if self.save_settings():
            self.EndModal(wx.ID_OK)

    def on_cancel(self, event):
        """Handle Cancel button."""
        self.EndModal(wx.ID_CANCEL)

    def on_apply(self, event):
        """Handle Apply button."""
        self.save_settings()

    def on_close(self, event):
        """Handle close."""
        self.EndModal(wx.ID_CANCEL)
