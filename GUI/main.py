"""Main GUI window for FastGH."""

import wx
import wx.adv
import platform
import threading
import webbrowser
from application import get_app
from models.repository import Repository
from version import APP_NAME
from .wx_safety import safe_raise

# Global hotkey support (Windows only)
if platform.system() != "Darwin":
    try:
        from keyboard_handler.wx_handler import WXKeyboardHandler
        HOTKEY_SUPPORTED = True
    except ImportError:
        HOTKEY_SUPPORTED = False
else:
    HOTKEY_SUPPORTED = False

# Global window reference
window = None
tray_icon = None


def create_tray_icon_image():
    """Create a simple tray icon image."""
    # Create a 16x16 bitmap with GitHub-like colors
    size = 16
    bmp = wx.Bitmap(size, size, 32)
    dc = wx.MemoryDC(bmp)

    # Fill with transparent/dark background
    dc.SetBackground(wx.Brush(wx.Colour(36, 41, 46)))  # GitHub dark
    dc.Clear()

    # Draw a simple "G" shape
    dc.SetPen(wx.Pen(wx.Colour(255, 255, 255), 2))
    dc.SetBrush(wx.TRANSPARENT_BRUSH)

    # Draw circle
    dc.DrawCircle(8, 8, 6)

    # Draw the G bar
    dc.DrawLine(8, 8, 12, 8)

    dc.SelectObject(wx.NullBitmap)
    return bmp


class TaskBarIcon(wx.adv.TaskBarIcon):
    """System tray icon for FastGH."""

    def __init__(self, frame):
        super().__init__()
        self.frame = frame

        # Create icon
        icon = wx.Icon()
        icon.CopyFromBitmap(create_tray_icon_image())
        self.SetIcon(icon, APP_NAME)

        # Bind events
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_left_dclick)

    def CreatePopupMenu(self):
        """Create the right-click context menu."""
        menu = wx.Menu()

        if self.frame.IsShown():
            m_showhide = menu.Append(-1, "&Hide Window\tCtrl+H")
        else:
            m_showhide = menu.Append(-1, "&Show Window\tCtrl+H")
        self.Bind(wx.EVT_MENU, self.on_show_hide, m_showhide)

        menu.AppendSeparator()

        m_refresh = menu.Append(-1, "&Refresh\tF5")
        self.Bind(wx.EVT_MENU, self.on_refresh, m_refresh)

        menu.AppendSeparator()

        m_exit = menu.Append(-1, "E&xit")
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)

        return menu

    def on_left_dclick(self, event):
        """Handle double-click on tray icon."""
        self.frame.toggle_visibility()

    def on_show_hide(self, event):
        """Toggle window visibility."""
        self.frame.toggle_visibility()

    def on_refresh(self, event):
        """Refresh data."""
        self.frame.refresh_all()

    def on_exit(self, event):
        """Exit application."""
        self.frame.exit_app()


class MainGui(wx.Frame):
    """Main application window."""

    def __init__(self, title):
        super().__init__(None, title=title, size=(900, 600))
        self.app = get_app()
        self.Center()

        # Data caches
        self.feed = []
        self._visible_feed = []
        self.repos = []
        self.starred = []
        self.watched = []
        self.following = []
        self.notifications = []

        # Last seen item IDs for notifications (set to None initially to skip first load)
        self._last_feed_ids = None
        self._last_notification_ids = None
        self._last_starred_ids = None
        self._last_watched_ids = None
        # Feed title backfill caches: {(owner, repo, number): title_or_none}
        self._feed_pr_title_cache = {}
        self._feed_issue_title_cache = {}
        self._feed_title_backfill_running = False

        # Auto-refresh timer
        self.auto_refresh_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_auto_refresh, self.auto_refresh_timer)
        self.repo_sync_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_repo_sync_timer, self.repo_sync_timer)
        self._repo_sync_running = False

        # Global hotkey handler
        self.keyboard_handler = None
        self.current_hotkey = None
        if HOTKEY_SUPPORTED:
            self.keyboard_handler = WXKeyboardHandler(self)
            self.register_global_hotkey()

        self.init_ui()
        self.init_menu()
        self.bind_events()

        # Load data in background
        self.refresh_all()

        # Start auto-refresh timer if enabled
        self.update_auto_refresh_timer()
        self.update_repo_sync_timer()

        # Check for updates on startup if enabled
        if self.app.prefs.check_for_updates:
            threading.Thread(target=self.app.cfu, args=[True], daemon=True).start()

    def init_ui(self):
        """Initialize the UI components."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Account label
        self.account_label = wx.StaticText(self.panel, label="")
        main_sizer.Add(self.account_label, 0, wx.ALL, 5)

        # Notebook for tabs
        self.notebook = wx.Notebook(self.panel)

        # Activity Feed tab (Home/Dashboard)
        self.feed_panel = wx.Panel(self.notebook)
        feed_sizer = wx.BoxSizer(wx.VERTICAL)
        self.feed_list = wx.ListBox(self.feed_panel, style=wx.LB_SINGLE)
        feed_sizer.Add(self.feed_list, 1, wx.EXPAND)
        self.feed_panel.SetSizer(feed_sizer)
        self.notebook.AddPage(self.feed_panel, "Activity Feed")

        # Your Repositories tab
        self.repos_panel = wx.Panel(self.notebook)
        repos_sizer = wx.BoxSizer(wx.VERTICAL)
        self.repos_list = wx.ListBox(self.repos_panel, style=wx.LB_SINGLE)
        repos_sizer.Add(self.repos_list, 1, wx.EXPAND)
        self.repos_panel.SetSizer(repos_sizer)
        self.notebook.AddPage(self.repos_panel, "Your Repositories")

        # Starred tab
        self.starred_panel = wx.Panel(self.notebook)
        starred_sizer = wx.BoxSizer(wx.VERTICAL)
        self.starred_list = wx.ListBox(self.starred_panel, style=wx.LB_SINGLE)
        starred_sizer.Add(self.starred_list, 1, wx.EXPAND)
        self.starred_panel.SetSizer(starred_sizer)
        self.notebook.AddPage(self.starred_panel, "Starred")

        # Watched tab
        self.watched_panel = wx.Panel(self.notebook)
        watched_sizer = wx.BoxSizer(wx.VERTICAL)
        self.watched_list = wx.ListBox(self.watched_panel, style=wx.LB_SINGLE)
        watched_sizer.Add(self.watched_list, 1, wx.EXPAND)
        self.watched_panel.SetSizer(watched_sizer)
        self.notebook.AddPage(self.watched_panel, "Watched")

        # Following tab
        self.following_panel = wx.Panel(self.notebook)
        following_sizer = wx.BoxSizer(wx.VERTICAL)
        self.following_list = wx.ListBox(self.following_panel, style=wx.LB_SINGLE)
        following_sizer.Add(self.following_list, 1, wx.EXPAND)
        self.following_panel.SetSizer(following_sizer)
        self.notebook.AddPage(self.following_panel, "Following")

        # Notifications tab
        self.notifications_panel = wx.Panel(self.notebook)
        notifications_sizer = wx.BoxSizer(wx.VERTICAL)
        self.notifications_list = wx.ListBox(self.notifications_panel, style=wx.LB_SINGLE)
        notifications_sizer.Add(self.notifications_list, 1, wx.EXPAND)
        self.notifications_panel.SetSizer(notifications_sizer)
        self.notebook.AddPage(self.notifications_panel, "Notifications")

        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Status bar
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText("Ready")

        self.panel.SetSizer(main_sizer)

    def _menu_label(self, label, shortcut, disable_accel_on_mac=False):
        """Format menu label with shortcut.

        On macOS, certain shortcuts (Return, Ctrl+C, etc.) conflict with dialogs
        and should be shown in parens instead of as accelerators.
        """
        if not shortcut:
            return label
        if platform.system() == "Darwin" and disable_accel_on_mac:
            return f"{label} ({shortcut})"
        else:
            return f"{label}\t{shortcut}"

    def init_menu(self):
        """Initialize the menu bar."""
        menu_bar = wx.MenuBar()
        is_mac = platform.system() == "Darwin"

        # Application menu
        app_menu = wx.Menu()
        m_accounts = app_menu.Append(-1, self._menu_label("Accounts", "Ctrl+A"), "Manage accounts")
        self.Bind(wx.EVT_MENU, self.on_accounts, m_accounts)
        m_options = app_menu.Append(-1, self._menu_label("Options", "Ctrl+,"), "Application options")
        self.Bind(wx.EVT_MENU, self.on_options, m_options)
        if not is_mac:
            app_menu.AppendSeparator()
            m_hide = app_menu.Append(-1, "Hide Window\tCtrl+H", "Hide window to system tray")
            self.Bind(wx.EVT_MENU, self.on_hide, m_hide)
        app_menu.AppendSeparator()
        m_exit = app_menu.Append(wx.ID_EXIT, self._menu_label("Exit", "Alt+X"), "Exit application")
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)
        menu_bar.Append(app_menu, "&Application")

        # View menu
        view_menu = wx.Menu()
        m_refresh = view_menu.Append(-1, self._menu_label("Refresh", "F5"), "Refresh all data")
        self.Bind(wx.EVT_MENU, self.on_refresh, m_refresh)
        view_menu.AppendSeparator()
        m_feed = view_menu.Append(-1, self._menu_label("Activity Feed", "Ctrl+1"), "Show activity feed")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(0), m_feed)
        m_your_repos = view_menu.Append(-1, self._menu_label("Your Repositories", "Ctrl+2"), "Show your repositories")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(1), m_your_repos)
        m_starred = view_menu.Append(-1, self._menu_label("Starred", "Ctrl+3"), "Show starred repositories")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(2), m_starred)
        m_watched = view_menu.Append(-1, self._menu_label("Watched", "Ctrl+4"), "Show watched repositories")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(3), m_watched)
        m_following = view_menu.Append(-1, self._menu_label("Following", "Ctrl+5"), "Show users you follow")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(4), m_following)
        m_notifications = view_menu.Append(-1, self._menu_label("Notifications", "Ctrl+6"), "Show notifications")
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(5), m_notifications)
        view_menu.AppendSeparator()
        m_repo_sync_now = view_menu.Append(-1, self._menu_label("Run Repo Sync Now", "Ctrl+Shift+Y"), "Run configured repository sync now")
        self.Bind(wx.EVT_MENU, self.on_repo_sync_now, m_repo_sync_now)
        m_mark_all_read = view_menu.Append(-1, self._menu_label("Mark All Notifications Read", "Ctrl+Shift+R"), "Mark all notifications as read")
        self.Bind(wx.EVT_MENU, self.on_mark_all_notifications_read, m_mark_all_read)
        menu_bar.Append(view_menu, "&View")

        # Search menu
        search_menu = wx.Menu()
        m_search = search_menu.Append(-1, self._menu_label("Search GitHub...", "Ctrl+F"), "Search repositories and users")
        self.Bind(wx.EVT_MENU, self.on_search, m_search)
        search_menu.AppendSeparator()
        m_go_to_repo = search_menu.Append(-1, self._menu_label("Go to Repository...", "Ctrl+L"), "Jump to a repository by URL or owner/repo")
        self.Bind(wx.EVT_MENU, self.on_go_to_repo, m_go_to_repo)
        m_view_user = search_menu.Append(-1, self._menu_label("View User Profile...", "Ctrl+U"), "Look up a user by username")
        self.Bind(wx.EVT_MENU, self.on_view_user, m_view_user)
        menu_bar.Append(search_menu, "&Search")

        # Actions menu
        actions_menu = wx.Menu()
        # Return and Ctrl+C conflict with dialogs on macOS - disable accelerators
        m_view_repo = actions_menu.Append(-1, self._menu_label("View Repository Info", "Return", disable_accel_on_mac=True), "View repository details")
        self.Bind(wx.EVT_MENU, self.on_view_repo, m_view_repo)
        m_open_url = actions_menu.Append(-1, self._menu_label("Open in Browser", "Ctrl+O"), "Open selected repository in browser")
        self.Bind(wx.EVT_MENU, self.on_open_url, m_open_url)
        m_copy_url = actions_menu.Append(-1, self._menu_label("Copy URL", "Ctrl+C", disable_accel_on_mac=True), "Copy repository URL to clipboard")
        self.Bind(wx.EVT_MENU, self.on_copy_url, m_copy_url)
        m_copy_clone = actions_menu.Append(-1, self._menu_label("Copy Clone URL", "Ctrl+Shift+C"), "Copy git clone URL")
        self.Bind(wx.EVT_MENU, self.on_copy_clone, m_copy_clone)
        actions_menu.AppendSeparator()
        m_view_issues = actions_menu.Append(-1, self._menu_label("View Issues", "Ctrl+I"), "View repository issues")
        self.Bind(wx.EVT_MENU, self.on_view_issues, m_view_issues)
        m_view_prs = actions_menu.Append(-1, self._menu_label("View Pull Requests", "Ctrl+P"), "View pull requests")
        self.Bind(wx.EVT_MENU, self.on_view_prs, m_view_prs)
        m_view_commits = actions_menu.Append(-1, self._menu_label("View Commits", "Ctrl+M"), "View repository commits")
        self.Bind(wx.EVT_MENU, self.on_view_commits, m_view_commits)
        m_view_actions = actions_menu.Append(-1, self._menu_label("View Actions", "Ctrl+G"), "View GitHub Actions workflow runs")
        self.Bind(wx.EVT_MENU, self.on_view_actions, m_view_actions)
        m_view_releases = actions_menu.Append(-1, self._menu_label("View Releases", "Ctrl+R"), "View releases and download artifacts")
        self.Bind(wx.EVT_MENU, self.on_view_releases, m_view_releases)
        menu_bar.Append(actions_menu, "A&ctions")

        # Help menu
        help_menu = wx.Menu()
        m_check_updates = help_menu.Append(-1, "Check for &Updates...", "Check for application updates")
        self.Bind(wx.EVT_MENU, self.on_check_updates, m_check_updates)
        menu_bar.Append(help_menu, "&Help")

        self.SetMenuBar(menu_bar)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)

        # Double-click to open feed event
        self.feed_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_feed_event)

        # Double-click to view repo info
        self.repos_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_repo)
        self.starred_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_repo)
        self.watched_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_repo)

        # Double-click to view user profile
        self.following_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_following_user)

        # Keyboard events - use EVT_CHAR_HOOK for reliable Enter key detection
        self.feed_list.Bind(wx.EVT_CHAR_HOOK, self.on_feed_list_key_hook)
        self.repos_list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key_hook)
        self.starred_list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key_hook)
        self.watched_list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key_hook)
        self.following_list.Bind(wx.EVT_CHAR_HOOK, self.on_following_list_key_hook)
        self.notifications_list.Bind(wx.EVT_CHAR_HOOK, self.on_notifications_list_key_hook)

        # Context menu (right-click)
        self.feed_list.Bind(wx.EVT_RIGHT_DOWN, self.on_feed_context_menu)
        self.repos_list.Bind(wx.EVT_RIGHT_DOWN, self.on_context_menu)
        self.starred_list.Bind(wx.EVT_RIGHT_DOWN, self.on_context_menu)
        self.watched_list.Bind(wx.EVT_RIGHT_DOWN, self.on_context_menu)
        self.following_list.Bind(wx.EVT_RIGHT_DOWN, self.on_following_context_menu)
        self.notifications_list.Bind(wx.EVT_RIGHT_DOWN, self.on_notifications_context_menu)

        # Also bind context menu key (Applications key / Shift+F10)
        self.feed_list.Bind(wx.EVT_CONTEXT_MENU, self.on_feed_context_menu)
        self.repos_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.starred_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.watched_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.following_list.Bind(wx.EVT_CONTEXT_MENU, self.on_following_context_menu)
        self.notifications_list.Bind(wx.EVT_CONTEXT_MENU, self.on_notifications_context_menu)

        # Double-click for notifications
        self.notifications_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_notification)

    def on_list_key_hook(self, event):
        """Handle key events in list (using CHAR_HOOK for reliability)."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN or key == wx.WXK_NUMPAD_ENTER:
            # On macOS, invoking modal dialogs directly from key hooks can crash
            # in wxWidgets Cocoa. Defer to the next event-loop turn.
            if platform.system() == "Darwin":
                wx.CallAfter(self.on_view_repo, None)
            else:
                self.on_view_repo(None)
        else:
            event.Skip()

    # ============ Activity Feed Methods ============

    def get_selected_feed_event(self):
        """Get the currently selected feed event."""
        selection = self.feed_list.GetSelection()
        visible = getattr(self, '_visible_feed', self.feed)
        if selection != wx.NOT_FOUND and selection < len(visible):
            return visible[selection]
        return None

    def on_feed_list_key_hook(self, event):
        """Handle key events in feed list."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN or key == wx.WXK_NUMPAD_ENTER:
            if platform.system() == "Darwin":
                wx.CallAfter(self.on_open_feed_event, None)
            else:
                self.on_open_feed_event(None)
        else:
            event.Skip()

    def on_feed_context_menu(self, event):
        """Show context menu for feed event."""
        feed_event = self.get_selected_feed_event()
        if not feed_event:
            return

        menu = wx.Menu()

        m_open = menu.Append(-1, "&Open in Browser")
        self.Bind(wx.EVT_MENU, self.on_open_feed_event, m_open)

        menu.AppendSeparator()

        m_repo = menu.Append(-1, "View &Repository")
        self.Bind(wx.EVT_MENU, self.on_view_feed_repo, m_repo)

        m_user = menu.Append(-1, "View &User Profile")
        self.Bind(wx.EVT_MENU, self.on_view_feed_user, m_user)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_open_feed_event(self, event):
        """Open feed event - show in app if possible, otherwise browser."""
        feed_event = self.get_selected_feed_event()
        if not feed_event:
            return

        # Parse owner/repo
        parts = feed_event.repo.name.split("/")
        if len(parts) != 2:
            webbrowser.open(feed_event.get_web_url())
            return

        owner, repo_name = parts
        payload = feed_event.payload

        # Handle different event types
        if feed_event.type in ("IssuesEvent", "IssueCommentEvent"):
            issue = payload.get("issue", {})
            number = issue.get("number")
            if number:
                self._open_feed_issue(owner, repo_name, number)
                return

        elif feed_event.type in ("PullRequestEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent"):
            pr = payload.get("pull_request", {})
            number = pr.get("number")
            if number:
                self._open_feed_pr(owner, repo_name, number)
                return

        elif feed_event.type in ("DiscussionEvent", "DiscussionCommentEvent", "Discussion"):
            discussion = payload.get("discussion", {})
            number = discussion.get("number")
            if not number:
                discussion_url = (
                    discussion.get("html_url")
                    or payload.get("comment", {}).get("html_url")
                    or feed_event.get_web_url()
                )
                number = self._extract_discussion_number(discussion_url)
            if number:
                self._open_feed_discussion(owner, repo_name, number)
                return

        elif feed_event.type == "PushEvent":
            self._open_feed_commits(owner, repo_name)
            return

        elif feed_event.type == "ReleaseEvent":
            self._open_feed_releases(owner, repo_name)
            return

        elif feed_event.type in ("WatchEvent", "ForkEvent", "CreateEvent", "PublicEvent"):
            # For repo-level events, show the repo dialog
            self._open_feed_repo_direct(owner, repo_name)
            return

        # Fallback to browser
        webbrowser.open(feed_event.get_web_url())

    def _open_feed_issue(self, owner: str, repo_name: str, number: int):
        """Open an issue from the feed."""
        def fetch_and_show():
            issue = self.app.currentAccount.get_issue(owner, repo_name, number)
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if issue and repo:
                wx.CallAfter(self._show_issue_dialog, repo, issue)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load issue #{number}", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading issue #{number}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_issue_dialog(self, repo, issue):
        """Show the issue dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.issues import ViewIssueDialog
        dlg = ViewIssueDialog(self, repo, issue)
        dlg.ShowModal()
        dlg.Destroy()

    def _open_feed_pr(self, owner: str, repo_name: str, number: int):
        """Open a pull request from the feed."""
        def fetch_and_show():
            pr = self.app.currentAccount.get_pull_request(owner, repo_name, number)
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            can_merge = self.app.currentAccount.can_merge(owner, repo_name) if pr and repo else False
            if pr and repo:
                wx.CallAfter(self._show_pr_dialog, repo, pr, can_merge)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load PR #{number}", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading PR #{number}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_pr_dialog(self, repo, pr, can_merge):
        """Show the PR dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.pullrequests import ViewPullRequestDialog
        dlg = ViewPullRequestDialog(self, repo, pr, can_merge)
        dlg.ShowModal()
        dlg.Destroy()

    def _extract_discussion_number(self, url: str) -> int | None:
        """Extract discussion number from a discussion URL."""
        if not url:
            return None

        parts = url.rstrip("/").split("/")
        for i, part in enumerate(parts):
            if part == "discussions" and i + 1 < len(parts):
                try:
                    return int(parts[i + 1])
                except ValueError:
                    return None
        return None

    def _open_feed_discussion(self, owner: str, repo_name: str, number: int):
        """Open a discussion from the feed."""
        def fetch_and_show():
            discussion = self.app.currentAccount.get_discussion(owner, repo_name, number, comments_first=50)
            if discussion:
                wx.CallAfter(self._show_discussion_dialog, owner, repo_name, discussion)
            else:
                reason = self.app.currentAccount.get_last_error()
                message = f"Could not load discussion #{number}."
                if reason:
                    message += f"\n\nReason: {reason}"
                wx.CallAfter(wx.MessageBox, message, "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading discussion #{number}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_discussion_dialog(self, owner: str, repo_name: str, discussion):
        """Show the discussion dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.discussions import ViewDiscussionDialog
        dlg = ViewDiscussionDialog(self, owner, repo_name, discussion)
        dlg.ShowModal()
        dlg.Destroy()

    def _open_feed_commits(self, owner: str, repo_name: str):
        """Open commits dialog from the feed."""
        def fetch_and_show():
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if repo:
                wx.CallAfter(self._show_commits_dialog, repo)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load repository", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading {owner}/{repo_name}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_commits_dialog(self, repo):
        """Show the commits dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.commits import CommitsDialog
        dlg = CommitsDialog(self._get_dialog_parent(), repo)
        dlg.ShowModal()
        dlg.Destroy()

    def _open_feed_releases(self, owner: str, repo_name: str):
        """Open releases dialog from the feed."""
        def fetch_and_show():
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if repo:
                wx.CallAfter(self._show_releases_dialog, repo)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load repository", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading {owner}/{repo_name}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_releases_dialog(self, repo):
        """Show the releases dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.releases import ReleasesDialog
        dlg = ReleasesDialog(self._get_dialog_parent(), repo)
        dlg.ShowModal()
        dlg.Destroy()

    def _open_feed_repo_direct(self, owner: str, repo_name: str):
        """Open repo dialog directly from feed."""
        def fetch_and_show():
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if repo:
                wx.CallAfter(self._show_repo_dialog, repo)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load repository: {owner}/{repo_name}", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading {owner}/{repo_name}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def on_view_feed_repo(self, event):
        """View repository from feed event."""
        feed_event = self.get_selected_feed_event()
        if feed_event:
            # Parse owner/repo from the full name
            parts = feed_event.repo.name.split("/")
            if len(parts) == 2:
                owner, repo_name = parts
                # Fetch repo details and show dialog
                def fetch_and_show():
                    repo = self.app.currentAccount.get_repo(owner, repo_name)
                    if repo:
                        wx.CallAfter(self._show_repo_dialog, repo)
                    else:
                        wx.CallAfter(wx.MessageBox, f"Could not load repository: {feed_event.repo.name}", "Error", wx.OK | wx.ICON_ERROR)

                self.status_bar.SetStatusText(f"Loading {feed_event.repo.name}...")
                threading.Thread(target=fetch_and_show, daemon=True).start()

    def _show_repo_dialog(self, repo):
        """Show the view repo dialog."""
        self.status_bar.SetStatusText("Ready")
        from GUI.view import ViewRepoDialog
        dlg = ViewRepoDialog(self._get_dialog_parent(), repo)
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_feed_user(self, event):
        """View user profile from feed event."""
        feed_event = self.get_selected_feed_event()
        if feed_event:
            from GUI.search import UserProfileDialog
            dlg = UserProfileDialog(self._get_dialog_parent(), feed_event.actor.login)
            dlg.ShowModal()
            dlg.Destroy()

    def on_context_menu(self, event):
        """Show context menu for repository."""
        repo = self.get_selected_repo()
        if not repo:
            return

        menu = wx.Menu()

        m_view = menu.Append(-1, "&View Repository Info")
        self.Bind(wx.EVT_MENU, self.on_view_repo, m_view)

        m_open = menu.Append(-1, "&Open in Browser")
        self.Bind(wx.EVT_MENU, self.on_open_url, m_open)

        menu.AppendSeparator()

        m_copy_url = menu.Append(-1, "Copy &URL")
        self.Bind(wx.EVT_MENU, self.on_copy_url, m_copy_url)

        m_copy_clone = menu.Append(-1, "Copy &Clone URL")
        self.Bind(wx.EVT_MENU, self.on_copy_clone, m_copy_clone)

        menu.AppendSeparator()

        m_issues = menu.Append(-1, "View &Issues")
        self.Bind(wx.EVT_MENU, self.on_view_issues, m_issues)

        m_prs = menu.Append(-1, "View &Pull Requests")
        self.Bind(wx.EVT_MENU, self.on_view_prs, m_prs)

        m_commits = menu.Append(-1, "View Co&mmits")
        self.Bind(wx.EVT_MENU, self.on_view_commits, m_commits)

        m_actions = menu.Append(-1, "View &Actions")
        self.Bind(wx.EVT_MENU, self.on_view_actions, m_actions)

        m_releases = menu.Append(-1, "View &Releases")
        self.Bind(wx.EVT_MENU, self.on_view_releases, m_releases)

        menu.AppendSeparator()

        m_owner = menu.Append(-1, "View O&wner Profile")
        self.Bind(wx.EVT_MENU, self.on_view_owner, m_owner)

        self.PopupMenu(menu)
        menu.Destroy()

    def update_account_label(self):
        """Update the account label."""
        if self.app.currentAccount:
            name = self.app.currentAccount.display_name or self.app.currentAccount.username
            self.account_label.SetLabel(f"Logged in as: {name}")
        else:
            self.account_label.SetLabel("No account")

    def refresh_all(self):
        """Refresh all repository lists."""
        if not self.app.currentAccount:
            return

        self.update_account_label()
        self.status_bar.SetStatusText("Loading...")

        # Load in background threads
        threading.Thread(target=self._load_feed, daemon=True).start()
        threading.Thread(target=self._load_repos, daemon=True).start()
        threading.Thread(target=self._load_starred, daemon=True).start()
        threading.Thread(target=self._load_watched, daemon=True).start()
        threading.Thread(target=self._load_following, daemon=True).start()
        threading.Thread(target=self._load_notifications, daemon=True).start()

    def update_auto_refresh_timer(self):
        """Start or stop the auto-refresh timer based on settings."""
        interval = self.app.prefs.auto_refresh_interval
        if interval > 0:
            # Convert minutes to milliseconds
            self.auto_refresh_timer.Start(interval * 60 * 1000)
        else:
            self.auto_refresh_timer.Stop()

    def on_auto_refresh(self, event):
        """Handle auto-refresh timer event."""
        self.refresh_all()

    def update_repo_sync_timer(self):
        """Start or stop repository auto-sync timer based on settings."""
        enabled = self.app.prefs.repo_sync_enabled
        interval = self.app.prefs.repo_sync_interval_minutes
        if enabled and interval > 0:
            self.repo_sync_timer.Start(interval * 60 * 1000)
        else:
            self.repo_sync_timer.Stop()

    def on_repo_sync_timer(self, event):
        """Handle repository auto-sync timer event."""
        self.run_repo_sync_background(manual=False)

    def run_repo_sync_background(self, manual=False):
        """Run repository sync in background and publish short status text."""
        if self._repo_sync_running:
            return
        self._repo_sync_running = True

        def do_sync():
            try:
                results = self.app.repo_sync.sync_all_enabled() if self.app.repo_sync else []
                if not results:
                    wx.CallAfter(self.status_bar.SetStatusText, "Repo sync: no enabled repositories")
                    if manual and self.app.prefs.repo_sync_notify:
                        wx.CallAfter(self.show_notification, "Repo Sync", "No enabled repositories configured.")
                    return
                failed = [r for r in results if not r.ok]
                if failed:
                    summary = f"Repo sync: {len(results) - len(failed)}/{len(results)} succeeded"
                    wx.CallAfter(self.status_bar.SetStatusText, summary)
                    if self.app.prefs.repo_sync_notify:
                        first = failed[0]
                        wx.CallAfter(self.show_notification, "Repo Sync Errors", f"{summary}. First failure: {first.repo}")
                else:
                    summary = f"Repo sync: {len(results)} repositories synced"
                    wx.CallAfter(self.status_bar.SetStatusText, summary)
                    if self.app.prefs.repo_sync_notify and manual:
                        wx.CallAfter(self.show_notification, "Repo Sync Complete", summary)
            except Exception as exc:
                wx.CallAfter(self.status_bar.SetStatusText, f"Repo sync error: {exc}")
                if self.app.prefs.repo_sync_notify:
                    wx.CallAfter(self.show_notification, "Repo Sync Error", str(exc))
            finally:
                self._repo_sync_running = False

        threading.Thread(target=do_sync, daemon=True).start()

    def on_repo_sync_now(self, event):
        """Trigger repository sync immediately."""
        self.run_repo_sync_background(manual=True)

    def show_notification(self, title: str, message: str):
        """Show an OS desktop notification."""
        try:
            notification = wx.adv.NotificationMessage(title, message, self)
            notification.SetFlags(wx.ICON_INFORMATION)
            notification.Show(timeout=5)  # Show for 5 seconds
        except Exception as e:
            # Fallback if notifications not supported
            print(f"Notification error: {e}")

    def _check_and_notify_feed(self, new_feed):
        """Check for new feed items and notify if enabled."""
        if not self.app.prefs.notify_activity:
            return

        # Get current IDs
        new_ids = {event.id for event in new_feed}

        # Skip first load (no previous data)
        if self._last_feed_ids is None:
            self._last_feed_ids = new_ids
            return

        # Find new items
        new_item_ids = new_ids - self._last_feed_ids
        if new_item_ids:
            count = len(new_item_ids)
            # Find one of the new events to show
            new_event = next((e for e in new_feed if e.id in new_item_ids), None)
            if new_event:
                title = f"{count} new activity item{'s' if count > 1 else ''}"
                message = new_event.format_display()[:100]
                self.show_notification(title, message)

        self._last_feed_ids = new_ids

    def _check_and_notify_notifications(self, new_notifications):
        """Check for new GitHub notifications and notify if enabled."""
        if not self.app.prefs.notify_notifications:
            return

        # Get current unread notification IDs
        new_ids = {n.id for n in new_notifications if n.unread}

        # Skip first load
        if self._last_notification_ids is None:
            self._last_notification_ids = new_ids
            return

        # Find new unread notifications
        new_item_ids = new_ids - self._last_notification_ids
        if new_item_ids:
            count = len(new_item_ids)
            new_notif = next((n for n in new_notifications if n.id in new_item_ids), None)
            if new_notif:
                title = f"{count} new GitHub notification{'s' if count > 1 else ''}"
                message = f"{new_notif.subject.title} ({new_notif.repository_full_name})"
                self.show_notification(title, message)

        self._last_notification_ids = new_ids

    def _check_and_notify_starred(self, new_starred):
        """Check for starred repo updates and notify if enabled."""
        if not self.app.prefs.notify_starred:
            return

        # Get IDs with their push timestamps
        new_ids = {(r.id, r.pushed_at.isoformat() if r.pushed_at else "") for r in new_starred}
        new_id_only = {r.id for r in new_starred}

        # Skip first load
        if self._last_starred_ids is None:
            self._last_starred_ids = new_ids
            return

        old_id_only = {id for id, _ in self._last_starred_ids}

        # Find repos that have new pushes (same ID but different timestamp)
        updated_repos = []
        for repo in new_starred:
            repo_key = (repo.id, repo.pushed_at.isoformat() if repo.pushed_at else "")
            old_key = next((k for k in self._last_starred_ids if k[0] == repo.id), None)
            if old_key and old_key != repo_key:
                updated_repos.append(repo)

        if updated_repos:
            count = len(updated_repos)
            title = f"{count} starred repo{'s' if count > 1 else ''} updated"
            message = updated_repos[0].full_name
            if count > 1:
                message += f" and {count - 1} more"
            self.show_notification(title, message)

        self._last_starred_ids = new_ids

    def _check_and_notify_watched(self, new_watched):
        """Check for watched repo updates and notify if enabled."""
        if not self.app.prefs.notify_watched:
            return

        # Get IDs with their push timestamps
        new_ids = {(r.id, r.pushed_at.isoformat() if r.pushed_at else "") for r in new_watched}

        # Skip first load
        if self._last_watched_ids is None:
            self._last_watched_ids = new_ids
            return

        # Find repos that have new pushes
        updated_repos = []
        for repo in new_watched:
            repo_key = (repo.id, repo.pushed_at.isoformat() if repo.pushed_at else "")
            old_key = next((k for k in self._last_watched_ids if k[0] == repo.id), None)
            if old_key and old_key != repo_key:
                updated_repos.append(repo)

        if updated_repos:
            count = len(updated_repos)
            title = f"{count} watched repo{'s' if count > 1 else ''} updated"
            message = updated_repos[0].full_name
            if count > 1:
                message += f" and {count - 1} more"
            self.show_notification(title, message)

        self._last_watched_ids = new_ids

    def _load_feed(self):
        """Load activity feed in background."""
        try:
            self.feed = self.app.currentAccount.get_received_events()
            wx.CallAfter(self._update_feed_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading feed: {e}")

    def _render_feed_list(self):
        """Render feed list from current event data while preserving selection."""
        from models.feed_filter import load_visible_types, load_muted_repos, filter_feed
        visible = load_visible_types(self.app.currentAccount.prefs) if self.app.currentAccount else None
        muted_repos = load_muted_repos(self.app.currentAccount.prefs) if self.app.currentAccount else None
        self._visible_feed = filter_feed(self.feed, visible, muted_repos)

        selection = self.feed_list.GetSelection()
        self.feed_list.Clear()
        for event in self._visible_feed:
            self.feed_list.Append(event.format_display())
        if selection != wx.NOT_FOUND and selection < self.feed_list.GetCount():
            self.feed_list.SetSelection(selection)

    def _extract_feed_pr_key(self, event):
        """Extract a normalized key for PR-related feed events."""
        if event.type not in ("PullRequestEvent", "PullRequestReviewEvent", "PullRequestReviewCommentEvent"):
            return None

        pr = event.payload.get("pull_request", {}) or {}
        number = pr.get("number")
        if not number:
            return None

        try:
            number = int(number)
        except (TypeError, ValueError):
            return None

        parts = event.repo.name.split("/")
        if len(parts) != 2:
            return None
        owner, repo_name = parts
        return (owner, repo_name, number)

    def _extract_feed_issue_key(self, event):
        """Extract a normalized key for issue-related feed events."""
        if event.type not in ("IssuesEvent", "IssueCommentEvent"):
            return None

        issue = event.payload.get("issue", {}) or {}
        number = issue.get("number")
        if not number:
            return None

        try:
            number = int(number)
        except (TypeError, ValueError):
            return None

        parts = event.repo.name.split("/")
        if len(parts) != 2:
            return None
        owner, repo_name = parts
        return (owner, repo_name, number)

    def _apply_cached_pr_titles_to_feed(self) -> bool:
        """Apply cached PR titles into feed payloads where title is missing."""
        updated = False
        for event in self.feed:
            key = self._extract_feed_pr_key(event)
            if not key:
                continue

            pr = event.payload.get("pull_request", {}) or {}
            if (pr.get("title") or "").strip():
                continue

            if key not in self._feed_pr_title_cache:
                continue

            cached_title = self._feed_pr_title_cache.get(key)
            if cached_title:
                pr["title"] = cached_title
                event.payload["pull_request"] = pr
                updated = True
        return updated

    def _apply_cached_issue_titles_to_feed(self) -> bool:
        """Apply cached issue titles into feed payloads where title is missing."""
        updated = False
        for event in self.feed:
            key = self._extract_feed_issue_key(event)
            if not key:
                continue

            issue = event.payload.get("issue", {}) or {}
            if (issue.get("title") or "").strip():
                continue

            if key not in self._feed_issue_title_cache:
                continue

            cached_title = self._feed_issue_title_cache.get(key)
            if cached_title:
                issue["title"] = cached_title
                event.payload["issue"] = issue
                updated = True
        return updated

    def _apply_cached_feed_titles_to_feed(self) -> bool:
        """Apply all cached feed title backfills."""
        updated_pr = self._apply_cached_pr_titles_to_feed()
        updated_issue = self._apply_cached_issue_titles_to_feed()
        return updated_pr or updated_issue

    def _collect_missing_feed_title_jobs(self):
        """Collect unique feed title backfill jobs in feed order."""
        jobs = []
        seen_pr = set()
        seen_issue = set()

        for event in self.feed:
            pr_key = self._extract_feed_pr_key(event)
            if pr_key and pr_key not in seen_pr:
                seen_pr.add(pr_key)
                pr = event.payload.get("pull_request", {}) or {}
                if not (pr.get("title") or "").strip() and pr_key not in self._feed_pr_title_cache:
                    jobs.append(("pr", pr_key))

            issue_key = self._extract_feed_issue_key(event)
            if issue_key and issue_key not in seen_issue:
                seen_issue.add(issue_key)
                issue = event.payload.get("issue", {}) or {}
                if not (issue.get("title") or "").strip() and issue_key not in self._feed_issue_title_cache:
                    jobs.append(("issue", issue_key))

        return jobs

    def _finish_feed_title_backfill(self):
        """Finalize one backfill batch and queue next if needed."""
        self._feed_title_backfill_running = False
        if self._apply_cached_feed_titles_to_feed():
            self._render_feed_list()
        self._start_feed_title_backfill()

    def _start_feed_title_backfill(self):
        """Backfill missing issue/PR titles for feed rows using minimal API calls."""
        if self._feed_title_backfill_running:
            return

        jobs = self._collect_missing_feed_title_jobs()
        if not jobs:
            return

        # Keep call volume low per refresh cycle.
        batch = jobs[:8]
        self._feed_title_backfill_running = True

        def do_backfill():
            for kind, key in batch:
                owner, repo_name, number = key
                if kind == "pr":
                    pr = self.app.currentAccount.get_pull_request(owner, repo_name, number)
                    if pr and (pr.title or "").strip():
                        self._feed_pr_title_cache[key] = pr.title
                    else:
                        # Cache misses too so we don't re-query repeatedly.
                        self._feed_pr_title_cache[key] = None
                else:
                    issue = self.app.currentAccount.get_issue(owner, repo_name, number)
                    if issue and (issue.title or "").strip():
                        self._feed_issue_title_cache[key] = issue.title
                    else:
                        # Cache misses too so we don't re-query repeatedly.
                        self._feed_issue_title_cache[key] = None
            wx.CallAfter(self._finish_feed_title_backfill)

        threading.Thread(target=do_backfill, daemon=True).start()

    def _update_feed_list(self):
        """Update feed list on main thread."""
        # Check for new items and notify
        self._check_and_notify_feed(self.feed)

        # Apply any previously fetched titles before rendering.
        self._apply_cached_feed_titles_to_feed()
        self._render_feed_list()
        self._update_status()
        self._start_feed_title_backfill()

    def _load_repos(self):
        """Load user's repositories in background."""
        try:
            self.repos = self.app.currentAccount.get_repos()
            wx.CallAfter(self._update_repos_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading repos: {e}")

    def _load_starred(self):
        """Load starred repositories in background."""
        try:
            self.starred = self.app.currentAccount.get_starred()
            wx.CallAfter(self._update_starred_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading starred: {e}")

    def _load_watched(self):
        """Load watched repositories in background."""
        try:
            self.watched = self.app.currentAccount.get_watched()
            wx.CallAfter(self._update_watched_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading watched: {e}")

    def _update_repos_list(self):
        """Update repos list on main thread."""
        # Preserve selection
        selection = self.repos_list.GetSelection()
        self.repos_list.Clear()
        for repo in self.repos:
            self.repos_list.Append(repo.format_single_line())
        # Restore selection if still valid
        if selection != wx.NOT_FOUND and selection < self.repos_list.GetCount():
            self.repos_list.SetSelection(selection)
        self._update_status()

    def _update_starred_list(self):
        """Update starred list on main thread."""
        # Check for updates and notify
        self._check_and_notify_starred(self.starred)

        # Preserve selection
        selection = self.starred_list.GetSelection()
        self.starred_list.Clear()
        for repo in self.starred:
            self.starred_list.Append(repo.format_single_line())
        # Restore selection if still valid
        if selection != wx.NOT_FOUND and selection < self.starred_list.GetCount():
            self.starred_list.SetSelection(selection)
        self._update_status()

    def _update_watched_list(self):
        """Update watched list on main thread."""
        # Check for updates and notify
        self._check_and_notify_watched(self.watched)

        # Preserve selection
        selection = self.watched_list.GetSelection()
        self.watched_list.Clear()
        for repo in self.watched:
            self.watched_list.Append(repo.format_single_line())
        # Restore selection if still valid
        if selection != wx.NOT_FOUND and selection < self.watched_list.GetCount():
            self.watched_list.SetSelection(selection)
        self._update_status()

    def _load_following(self):
        """Load followed users in background."""
        try:
            self.following = self.app.currentAccount.get_following()
            wx.CallAfter(self._update_following_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading following: {e}")

    def _update_following_list(self):
        """Update following list on main thread."""
        # Preserve selection
        selection = self.following_list.GetSelection()
        self.following_list.Clear()
        for user in self.following:
            self.following_list.Append(user.format_display())
        # Restore selection if still valid
        if selection != wx.NOT_FOUND and selection < self.following_list.GetCount():
            self.following_list.SetSelection(selection)
        self._update_status()

    def _load_notifications(self):
        """Load notifications in background."""
        try:
            self.notifications = self.app.currentAccount.get_notifications()
            wx.CallAfter(self._update_notifications_list)
        except Exception as e:
            wx.CallAfter(self.status_bar.SetStatusText, f"Error loading notifications: {e}")

    def _update_notifications_list(self):
        """Update notifications list on main thread."""
        # Check for new notifications and notify
        self._check_and_notify_notifications(self.notifications)

        # Preserve selection
        selection = self.notifications_list.GetSelection()
        self.notifications_list.Clear()
        for notification in self.notifications:
            self.notifications_list.Append(notification.format_display())
        # Restore selection if still valid
        if selection != wx.NOT_FOUND and selection < self.notifications_list.GetCount():
            self.notifications_list.SetSelection(selection)
        self._update_status()

    def _update_status(self):
        """Update status bar with counts."""
        unread_count = sum(1 for n in self.notifications if n.unread)
        notif_text = f"Notifications: {unread_count}" if unread_count else "Notifications: 0"
        self.status_bar.SetStatusText(
            f"Repos: {len(self.repos)} | Starred: {len(self.starred)} | Watched: {len(self.watched)} | Following: {len(self.following)} | {notif_text}"
        )

    def get_selected_repo(self) -> Repository | None:
        """Get the currently selected repository."""
        page = self.notebook.GetSelection()

        # Tab indices: 0=Feed, 1=Repos, 2=Starred, 3=Watched, 4=Following, 5=Notifications
        if page == 1:
            selection = self.repos_list.GetSelection()
            if selection != wx.NOT_FOUND and selection < len(self.repos):
                return self.repos[selection]
        elif page == 2:
            selection = self.starred_list.GetSelection()
            if selection != wx.NOT_FOUND and selection < len(self.starred):
                return self.starred[selection]
        elif page == 3:
            selection = self.watched_list.GetSelection()
            if selection != wx.NOT_FOUND and selection < len(self.watched):
                return self.watched[selection]

        return None

    def get_selected_following_user(self):
        """Get the currently selected user from following list."""
        selection = self.following_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.following):
            return self.following[selection]
        return None

    def on_following_list_key_hook(self, event):
        """Handle key events in following list (using CHAR_HOOK for reliability)."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN or key == wx.WXK_NUMPAD_ENTER:
            if platform.system() == "Darwin":
                wx.CallAfter(self.on_view_following_user, None)
            else:
                self.on_view_following_user(None)
        else:
            event.Skip()

    def on_following_context_menu(self, event):
        """Show context menu for following user."""
        user = self.get_selected_following_user()
        if not user:
            return

        menu = wx.Menu()

        m_view = menu.Append(-1, "&View Profile")
        self.Bind(wx.EVT_MENU, self.on_view_following_user, m_view)

        m_open = menu.Append(-1, "&Open in Browser")
        self.Bind(wx.EVT_MENU, self.on_open_following_user, m_open)

        menu.AppendSeparator()

        m_unfollow = menu.Append(-1, "&Unfollow")
        self.Bind(wx.EVT_MENU, self.on_unfollow_user, m_unfollow)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_view_following_user(self, event):
        """View profile of selected following user."""
        user = self.get_selected_following_user()
        if user:
            from GUI.search import UserProfileDialog
            dlg = UserProfileDialog(self, user.login)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_following_user(self, event):
        """Open following user in browser."""
        user = self.get_selected_following_user()
        if user:
            webbrowser.open(user.html_url)

    def on_unfollow_user(self, event):
        """Unfollow the selected user."""
        user = self.get_selected_following_user()
        if not user:
            return

        result = wx.MessageBox(
            f"Unfollow {user.login}?",
            "Confirm Unfollow",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            if self.app.currentAccount.unfollow_user(user.login):
                # Refresh the following list
                threading.Thread(target=self._load_following, daemon=True).start()
            else:
                wx.MessageBox("Failed to unfollow user.", "Error", wx.OK | wx.ICON_ERROR)

    # ============ Notifications Methods ============

    def get_selected_notification(self):
        """Get the currently selected notification."""
        selection = self.notifications_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.notifications):
            return self.notifications[selection]
        return None

    def on_notifications_list_key_hook(self, event):
        """Handle key events in notifications list."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN or key == wx.WXK_NUMPAD_ENTER:
            if platform.system() == "Darwin":
                wx.CallAfter(self.on_open_notification, None)
            else:
                self.on_open_notification(None)
        elif key == wx.WXK_DELETE:
            self.on_mark_notification_done(None)
        else:
            event.Skip()

    def on_notifications_context_menu(self, event):
        """Show context menu for notification."""
        notification = self.get_selected_notification()
        if not notification:
            return

        menu = wx.Menu()

        m_open = menu.Append(-1, "&Open in Browser")
        self.Bind(wx.EVT_MENU, self.on_open_notification, m_open)

        menu.AppendSeparator()

        if notification.unread:
            m_read = menu.Append(-1, "Mark as &Read")
            self.Bind(wx.EVT_MENU, self.on_mark_notification_read, m_read)

        m_done = menu.Append(-1, "Mark as &Done")
        self.Bind(wx.EVT_MENU, self.on_mark_notification_done, m_done)

        m_mute = menu.Append(-1, "&Mute Thread")
        self.Bind(wx.EVT_MENU, self.on_mute_notification, m_mute)

        menu.AppendSeparator()

        m_repo = menu.Append(-1, "View &Repository")
        self.Bind(wx.EVT_MENU, self.on_view_notification_repo, m_repo)

        menu.AppendSeparator()

        m_mark_all = menu.Append(-1, "Mark &All as Read")
        self.Bind(wx.EVT_MENU, self.on_mark_all_notifications_read, m_mark_all)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_open_notification(self, event):
        """Open notification - show in app if possible, otherwise browser."""
        notification = self.get_selected_notification()
        if not notification:
            return

        # Mark as read
        self.app.currentAccount.mark_thread_read(notification.id)

        owner = notification.repository_owner
        repo_name = notification.repository_name
        subject_type = notification.subject.type
        subject_url = notification.subject.url

        # Try to extract number from URL
        # Format: https://api.github.com/repos/owner/repo/issues/123
        number = None
        if subject_url:
            parts = subject_url.rstrip('/').split('/')
            if parts:
                try:
                    number = int(parts[-1])
                except ValueError:
                    pass
        if subject_type == "Discussion" and not number:
            number = self._extract_discussion_number(notification.get_web_url())

        # Handle different notification types
        if subject_type == "Issue" and number:
            self._open_notification_issue(owner, repo_name, number)
        elif subject_type == "PullRequest" and number:
            self._open_notification_pr(owner, repo_name, number)
        elif subject_type == "Discussion" and number:
            self._open_notification_discussion(owner, repo_name, number)
        elif subject_type == "Release":
            self._open_notification_releases(owner, repo_name)
        elif subject_type == "Commit":
            self._open_notification_commits(owner, repo_name)
        else:
            # Fallback to browser for unsupported types.
            url = notification.get_web_url()
            if url:
                webbrowser.open(url)

        # Refresh notifications
        threading.Thread(target=self._load_notifications, daemon=True).start()

    def _open_notification_issue(self, owner: str, repo_name: str, number: int):
        """Open an issue from notification."""
        def fetch_and_show():
            issue = self.app.currentAccount.get_issue(owner, repo_name, number)
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if issue and repo:
                wx.CallAfter(self._show_issue_dialog, repo, issue)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load issue #{number}", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading issue #{number}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _open_notification_pr(self, owner: str, repo_name: str, number: int):
        """Open a pull request from notification."""
        def fetch_and_show():
            pr = self.app.currentAccount.get_pull_request(owner, repo_name, number)
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            can_merge = self.app.currentAccount.can_merge(owner, repo_name) if pr and repo else False
            if pr and repo:
                wx.CallAfter(self._show_pr_dialog, repo, pr, can_merge)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load PR #{number}", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading PR #{number}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _open_notification_discussion(self, owner: str, repo_name: str, number: int):
        """Open a discussion from notification."""
        self._open_feed_discussion(owner, repo_name, number)

    def _open_notification_releases(self, owner: str, repo_name: str):
        """Open releases dialog from notification."""
        def fetch_and_show():
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if repo:
                wx.CallAfter(self._show_releases_dialog, repo)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load repository", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading {owner}/{repo_name}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def _open_notification_commits(self, owner: str, repo_name: str):
        """Open commits dialog from notification."""
        def fetch_and_show():
            repo = self.app.currentAccount.get_repo(owner, repo_name)
            if repo:
                wx.CallAfter(self._show_commits_dialog, repo)
            else:
                wx.CallAfter(wx.MessageBox, f"Could not load repository", "Error", wx.OK | wx.ICON_ERROR)

        self.status_bar.SetStatusText(f"Loading {owner}/{repo_name}...")
        threading.Thread(target=fetch_and_show, daemon=True).start()

    def on_mark_notification_read(self, event):
        """Mark selected notification as read."""
        notification = self.get_selected_notification()
        if notification:
            if self.app.currentAccount.mark_thread_read(notification.id):
                threading.Thread(target=self._load_notifications, daemon=True).start()
            else:
                wx.MessageBox("Failed to mark notification as read.", "Error", wx.OK | wx.ICON_ERROR)

    def on_mark_notification_done(self, event):
        """Mark selected notification as done (remove from inbox)."""
        notification = self.get_selected_notification()
        if notification:
            if self.app.currentAccount.mark_thread_done(notification.id):
                threading.Thread(target=self._load_notifications, daemon=True).start()
            else:
                wx.MessageBox("Failed to mark notification as done.", "Error", wx.OK | wx.ICON_ERROR)

    def on_mute_notification(self, event):
        """Mute notification thread."""
        notification = self.get_selected_notification()
        if notification:
            if self.app.currentAccount.mute_thread(notification.id):
                wx.MessageBox(f"Muted notifications for this thread.", "Muted", wx.OK | wx.ICON_INFORMATION)
                threading.Thread(target=self._load_notifications, daemon=True).start()
            else:
                wx.MessageBox("Failed to mute thread.", "Error", wx.OK | wx.ICON_ERROR)

    def on_view_notification_repo(self, event):
        """View repository for notification."""
        notification = self.get_selected_notification()
        if notification:
            owner = notification.repository_owner
            repo_name = notification.repository_name
            self._open_feed_repo_direct(owner, repo_name)

    def on_mark_all_notifications_read(self, event):
        """Mark all notifications as read."""
        if not self.notifications:
            return

        unread_count = sum(1 for n in self.notifications if n.unread)
        if unread_count == 0:
            wx.MessageBox("No unread notifications.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        result = wx.MessageBox(
            f"Mark all {unread_count} notifications as read?",
            "Confirm",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            if self.app.currentAccount.mark_notifications_read():
                threading.Thread(target=self._load_notifications, daemon=True).start()
            else:
                wx.MessageBox("Failed to mark notifications as read.", "Error", wx.OK | wx.ICON_ERROR)

    def on_accounts(self, event):
        """Show accounts dialog."""
        from GUI.accounts import AccountsDialog
        dlg = AccountsDialog(self._get_dialog_parent())
        dlg.ShowModal()
        dlg.Destroy()

    def on_options(self, event):
        """Show options dialog."""
        from GUI.options import OptionsDialog
        dlg = OptionsDialog(self._get_dialog_parent())
        dlg.ShowModal()
        dlg.Destroy()

    def on_check_updates(self, event):
        """Check for application updates."""
        threading.Thread(target=self.app.cfu, args=[False], daemon=True).start()

    def on_refresh(self, event):
        """Refresh all data."""
        self.refresh_all()

    def on_search(self, event):
        """Open search dialog."""
        from GUI.search import SearchDialog
        dlg = SearchDialog(self._get_dialog_parent())
        dlg.ShowModal()
        dlg.Destroy()

    def on_view_user(self, event):
        """View a user profile by username."""
        dlg = wx.TextEntryDialog(self._get_dialog_parent(), "Enter GitHub username:", "View User Profile")
        if dlg.ShowModal() == wx.ID_OK:
            username = dlg.GetValue().strip()
            if username:
                from GUI.search import UserProfileDialog
                profile_dlg = UserProfileDialog(self._get_dialog_parent(), username)
                profile_dlg.ShowModal()
                profile_dlg.Destroy()
        dlg.Destroy()

    def on_go_to_repo(self, event):
        """Jump to a repository by URL or owner/repo pair."""
        import re
        dlg = wx.TextEntryDialog(
            self._get_dialog_parent(),
            "Enter repository URL or owner/repo:",
            "Go to Repository",
            ""
        )
        if dlg.ShowModal() == wx.ID_OK:
            input_text = dlg.GetValue().strip()
            if input_text:
                owner = None
                repo = None

                # Try to parse as GitHub URL
                url_match = re.match(r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', input_text)
                if url_match:
                    owner, repo = url_match.groups()
                else:
                    # Try to parse as owner/repo pair
                    pair_match = re.match(r'^([^/]+)/([^/]+)$', input_text)
                    if pair_match:
                        owner, repo = pair_match.groups()

                if owner and repo:
                    # Fetch the repository
                    repository = self.app.currentAccount.get_repo(owner, repo)
                    if repository:
                        from GUI.view import ViewRepoDialog
                        view_dlg = ViewRepoDialog(self._get_dialog_parent(), repository)
                        view_dlg.ShowModal()
                        view_dlg.Destroy()
                    else:
                        wx.MessageBox(
                            f"Repository '{owner}/{repo}' not found or you don't have access.",
                            "Repository Not Found",
                            wx.OK | wx.ICON_ERROR
                        )
                else:
                    wx.MessageBox(
                        "Invalid input. Please enter a GitHub URL or owner/repo format.\n\n"
                        "Examples:\n"
                        "  https://github.com/owner/repo\n"
                        "  owner/repo",
                        "Invalid Input",
                        wx.OK | wx.ICON_WARNING
                    )
        dlg.Destroy()

    def on_view_repo(self, event):
        """View repository details dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.view import ViewRepoDialog
            dlg = ViewRepoDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_url(self, event):
        """Open selected repository in browser."""
        repo = self.get_selected_repo()
        if repo:
            webbrowser.open(repo.html_url)

    def on_copy_url(self, event):
        """Copy repository URL to clipboard."""
        repo = self.get_selected_repo()
        if repo:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(repo.html_url))
                wx.TheClipboard.Close()
                self.status_bar.SetStatusText(f"Copied: {repo.html_url}")

    def on_copy_clone(self, event):
        """Copy git clone URL to clipboard."""
        repo = self.get_selected_repo()
        if repo:
            clone_url = f"https://github.com/{repo.full_name}.git"
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(clone_url))
                wx.TheClipboard.Close()
                self.status_bar.SetStatusText(f"Copied: {clone_url}")

    def _get_dialog_parent(self):
        """Get parent for dialogs - None on macOS to avoid menu issues."""
        return None if platform.system() == "Darwin" else self

    def on_view_issues(self, event):
        """Open issues dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.issues import IssuesDialog
            dlg = IssuesDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_view_prs(self, event):
        """Open pull requests dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.pullrequests import PullRequestsDialog
            dlg = PullRequestsDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_view_commits(self, event):
        """Open commits dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.commits import CommitsDialog
            dlg = CommitsDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_view_actions(self, event):
        """Open GitHub Actions dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.actions import ActionsDialog
            dlg = ActionsDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_view_releases(self, event):
        """Open releases dialog."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.releases import ReleasesDialog
            dlg = ReleasesDialog(self._get_dialog_parent(), repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_view_owner(self, event):
        """View the repository owner's profile."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.search import UserProfileDialog
            dlg = UserProfileDialog(self._get_dialog_parent(), repo.owner)
            dlg.ShowModal()
            dlg.Destroy()

    def on_close(self, event):
        """Handle window close - hide to tray instead of exit (exit on macOS)."""
        if platform.system() == "Darwin":
            # On macOS, actually exit since there's no tray
            self.exit_app()
        else:
            # Save window visibility state
            self.app.prefs.window_shown = False
            self.Hide()

    def on_hide(self, event):
        """Hide window to system tray."""
        self.app.prefs.window_shown = False
        self.Hide()

    def toggle_visibility(self):
        """Toggle window visibility."""
        if self.IsShown():
            self.app.prefs.window_shown = False
            self.Hide()
        else:
            self.app.prefs.window_shown = True
            self.Show()
            safe_raise(self)
            self._focus_current_list()

    def _focus_current_list(self):
        """Focus the list control for the current notebook tab."""
        page = self.notebook.GetSelection()
        lists = [
            self.feed_list,
            self.repos_list,
            self.starred_list,
            self.watched_list,
            self.following_list,
            self.notifications_list
        ]
        if 0 <= page < len(lists):
            lists[page].SetFocus()

    def register_global_hotkey(self):
        """Register the global hotkey for show/hide."""
        if not self.keyboard_handler:
            return

        hotkey = self.app.prefs.global_hotkey
        if not hotkey:
            return

        # Unregister old hotkey if different
        if self.current_hotkey and self.current_hotkey != hotkey:
            try:
                self.keyboard_handler.unregister_key(self.current_hotkey)
            except:
                pass

        # Register new hotkey
        try:
            self.keyboard_handler.register_key(hotkey, self.toggle_visibility)
            self.current_hotkey = hotkey
        except Exception as e:
            print(f"Failed to register hotkey {hotkey}: {e}")

    def update_global_hotkey(self, new_hotkey):
        """Update the global hotkey to a new value."""
        if not self.keyboard_handler:
            return False

        # Unregister old hotkey
        if self.current_hotkey:
            try:
                self.keyboard_handler.unregister_key(self.current_hotkey)
            except:
                pass

        # Register new hotkey
        if new_hotkey:
            try:
                self.keyboard_handler.register_key(new_hotkey, self.toggle_visibility)
                self.current_hotkey = new_hotkey
                self.app.prefs.global_hotkey = new_hotkey
                return True
            except Exception as e:
                print(f"Failed to register hotkey {new_hotkey}: {e}")
                # Try to restore old hotkey
                if self.current_hotkey:
                    try:
                        self.keyboard_handler.register_key(self.current_hotkey, self.toggle_visibility)
                    except:
                        pass
                return False
        else:
            self.current_hotkey = None
            self.app.prefs.global_hotkey = ""
            return True

    def exit_app(self):
        """Actually exit the application."""
        global tray_icon
        if tray_icon:
            tray_icon.RemoveIcon()
            tray_icon.Destroy()
            tray_icon = None
        self.Destroy()

    def on_exit(self, event):
        """Exit application."""
        self.exit_app()


def create_window():
    """Create the main window and system tray icon."""
    global window, tray_icon
    window = MainGui(APP_NAME)

    # Create system tray icon (not on macOS)
    if platform.system() != "Darwin":
        tray_icon = TaskBarIcon(window)

    return window
