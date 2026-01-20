"""Search dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.user import UserProfile
from . import theme


class SearchDialog(wx.Dialog):
    """Dialog for searching repositories and users."""

    def __init__(self, parent):
        self.app = get_app()
        self.account = self.app.currentAccount
        self.results = []  # Can be repos or users
        self.search_type = "repos"  # 'repos' or 'users'

        wx.Dialog.__init__(self, parent, title="Search GitHub", size=(900, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Search controls
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Search type
        type_label = wx.StaticText(self.panel, label="Search &for:")
        search_sizer.Add(type_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.type_choice = wx.Choice(self.panel, choices=["Repositories", "Users"])
        self.type_choice.SetSelection(0)
        search_sizer.Add(self.type_choice, 0, wx.RIGHT, 10)

        # Search query
        query_label = wx.StaticText(self.panel, label="&Query:")
        search_sizer.Add(query_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.query_text = wx.TextCtrl(self.panel, size=(300, -1), style=wx.TE_PROCESS_ENTER)
        search_sizer.Add(self.query_text, 1, wx.RIGHT, 10)

        # Sort
        sort_label = wx.StaticText(self.panel, label="&Sort:")
        search_sizer.Add(sort_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.sort_choice = wx.Choice(self.panel, choices=["Best Match", "Stars", "Forks", "Updated"])
        self.sort_choice.SetSelection(0)
        search_sizer.Add(self.sort_choice, 0, wx.RIGHT, 10)

        self.search_btn = wx.Button(self.panel, label="&Search")
        search_sizer.Add(self.search_btn, 0)

        main_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Results list
        results_label = wx.StaticText(self.panel, label="&Results:")
        main_sizer.Add(results_label, 0, wx.LEFT, 10)

        self.results_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.results_list, 1, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.query_text.SetFocus()

        # Initial button state
        self.update_buttons()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.type_choice.Bind(wx.EVT_CHOICE, self.on_type_change)
        self.query_text.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.search_btn.Bind(wx.EVT_BUTTON, self.on_search)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.results_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.results_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.results_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def on_type_change(self, event):
        """Handle search type change."""
        idx = self.type_choice.GetSelection()
        self.search_type = "repos" if idx == 0 else "users"

        # Update sort options based on type
        self.sort_choice.Clear()
        if self.search_type == "repos":
            self.sort_choice.Append("Best Match")
            self.sort_choice.Append("Stars")
            self.sort_choice.Append("Forks")
            self.sort_choice.Append("Updated")
        else:
            self.sort_choice.Append("Best Match")
            self.sort_choice.Append("Followers")
            self.sort_choice.Append("Repositories")
            self.sort_choice.Append("Joined")
        self.sort_choice.SetSelection(0)

        # Clear results
        self.results = []
        self.results_list.Clear()
        self.update_buttons()

    def on_search(self, event):
        """Perform search."""
        query = self.query_text.GetValue().strip()
        if not query:
            return

        self.results_list.Clear()
        self.results_list.Append("Searching...")
        self.results = []

        # Get sort option
        sort_map_repos = {
            "Best Match": "best-match",
            "Stars": "stars",
            "Forks": "forks",
            "Updated": "updated"
        }
        sort_map_users = {
            "Best Match": "best-match",
            "Followers": "followers",
            "Repositories": "repositories",
            "Joined": "joined"
        }

        sort_text = self.sort_choice.GetStringSelection()
        if self.search_type == "repos":
            sort = sort_map_repos.get(sort_text, "best-match")
        else:
            sort = sort_map_users.get(sort_text, "best-match")

        def do_search():
            if self.search_type == "repos":
                results = self.account.search_repos(query, sort=sort)
            else:
                results = self.account.search_users(query, sort=sort)
            wx.CallAfter(self.update_results, results)

        threading.Thread(target=do_search, daemon=True).start()

    def update_results(self, results):
        """Update results list."""
        self.results = results
        self.results_list.Clear()

        if not results:
            self.results_list.Append("No results found")
        else:
            for item in results:
                if isinstance(item, Repository):
                    self.results_list.Append(item.format_single_line())
                else:
                    self.results_list.Append(item.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states."""
        has_selection = self.results_list.GetSelection() != wx.NOT_FOUND and len(self.results) > 0
        self.view_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

    def get_selected_item(self):
        """Get the currently selected item."""
        selection = self.results_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.results):
            return self.results[selection]
        return None

    def on_view(self, event):
        """View selected item."""
        item = self.get_selected_item()
        if not item:
            return

        if isinstance(item, Repository):
            from GUI.view import ViewRepoDialog
            dlg = ViewRepoDialog(self, item)
            dlg.ShowModal()
            dlg.Destroy()
        elif isinstance(item, UserProfile):
            dlg = UserProfileDialog(self, item.login)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_browser(self, event):
        """Open in browser."""
        item = self.get_selected_item()
        if item:
            webbrowser.open(item.html_url)

    def on_selection_change(self, event):
        """Handle selection change."""
        self.update_buttons()

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.on_view(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)


class UserProfileDialog(wx.Dialog):
    """Dialog for viewing a user's profile."""

    def __init__(self, parent, username: str):
        self.username = username
        self.app = get_app()
        self.account = self.app.currentAccount
        self.user = None
        self.repos = []
        self.is_following = False
        self.is_self = (username == self.account.username)

        wx.Dialog.__init__(self, parent, title=f"User: {username}", size=(900, 650))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load user data
        self.load_user()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # User info
        info_label = wx.StaticText(self.panel, label="&Profile:")
        main_sizer.Add(info_label, 0, wx.LEFT | wx.TOP, 10)

        self.info_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(850, 150)
        )
        self.info_text.SetValue("Loading...")
        main_sizer.Add(self.info_text, 0, wx.EXPAND | wx.ALL, 10)

        # Repositories
        repos_label = wx.StaticText(self.panel, label="&Repositories:")
        main_sizer.Add(repos_label, 0, wx.LEFT, 10)

        self.repos_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.repos_list, 1, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.follow_btn = wx.Button(self.panel, label="&Follow")
        btn_sizer.Add(self.follow_btn, 0, wx.RIGHT, 5)
        # Hide follow button for self
        if self.is_self:
            self.follow_btn.Hide()

        self.view_repo_btn = wx.Button(self.panel, label="&View Repository")
        btn_sizer.Add(self.view_repo_btn, 0, wx.RIGHT, 5)

        self.open_profile_btn = wx.Button(self.panel, label="Open &Profile in Browser")
        btn_sizer.Add(self.open_profile_btn, 0, wx.RIGHT, 5)

        self.open_repo_btn = wx.Button(self.panel, label="Open Repo in &Browser")
        btn_sizer.Add(self.open_repo_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

        # Initial button state
        self.update_buttons()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.follow_btn.Bind(wx.EVT_BUTTON, self.on_toggle_follow)
        self.view_repo_btn.Bind(wx.EVT_BUTTON, self.on_view_repo)
        self.open_profile_btn.Bind(wx.EVT_BUTTON, self.on_open_profile)
        self.open_repo_btn.Bind(wx.EVT_BUTTON, self.on_open_repo)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.repos_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_repo)
        self.repos_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.repos_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def load_user(self):
        """Load user data in background."""
        def do_load():
            user = self.account.get_user(self.username)
            wx.CallAfter(self.update_user, user)

            if user:
                repos = self.account.get_user_repos(self.username)
                wx.CallAfter(self.update_repos, repos)

                # Check if following (only if not self)
                if not self.is_self:
                    is_following = self.account.is_following(self.username)
                    wx.CallAfter(self.update_follow_status, is_following)

        threading.Thread(target=do_load, daemon=True).start()

    def update_follow_status(self, is_following: bool):
        """Update follow button based on status."""
        self.is_following = is_following
        # Check if dialog/button still exists (may be destroyed if closed quickly)
        try:
            if self.follow_btn:
                if is_following:
                    self.follow_btn.SetLabel("&Unfollow")
                else:
                    self.follow_btn.SetLabel("&Follow")
        except RuntimeError:
            pass  # Button was destroyed

    def update_user(self, user: UserProfile | None):
        """Update user info."""
        self.user = user

        if not user:
            self.info_text.SetValue("User not found")
            return

        # Update dialog title
        if user.name:
            self.SetTitle(f"User: {user.name} (@{user.login})")
        else:
            self.SetTitle(f"User: @{user.login}")

        # Build info text
        lines = []
        lines.append(f"Username: {user.login}")
        if user.name:
            lines.append(f"Name: {user.name}")
        lines.append(f"Type: {user.type}")

        if user.bio:
            lines.append(f"Bio: {user.bio}")
        if user.company:
            lines.append(f"Company: {user.company}")
        if user.location:
            lines.append(f"Location: {user.location}")
        if user.email:
            lines.append(f"Email: {user.email}")
        if user.blog:
            lines.append(f"Website: {user.blog}")
        if user.twitter_username:
            lines.append(f"Twitter: @{user.twitter_username}")

        lines.append("")
        lines.append(f"Public Repos: {user.public_repos} | Gists: {user.public_gists}")
        lines.append(f"Followers: {user.followers} | Following: {user.following}")

        if user.created_at:
            lines.append(f"Joined: {user.created_at.strftime('%Y-%m-%d')} ({user._format_relative_time(user.created_at)})")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.info_text.SetValue(sep.join(lines))

    def update_repos(self, repos: list[Repository]):
        """Update repositories list."""
        self.repos = repos
        self.repos_list.Clear()

        if not repos:
            self.repos_list.Append("No public repositories")
        else:
            for repo in repos:
                self.repos_list.Append(repo.format_single_line())

        self.update_buttons()

    def update_buttons(self):
        """Update button states."""
        has_repo_selection = self.repos_list.GetSelection() != wx.NOT_FOUND and len(self.repos) > 0
        self.view_repo_btn.Enable(has_repo_selection)
        self.open_repo_btn.Enable(has_repo_selection)
        self.open_profile_btn.Enable(self.user is not None)

    def get_selected_repo(self) -> Repository | None:
        """Get the currently selected repository."""
        selection = self.repos_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.repos):
            return self.repos[selection]
        return None

    def on_toggle_follow(self, event):
        """Follow or unfollow the user."""
        if self.is_self or not self.user:
            return

        if self.is_following:
            # Unfollow
            if self.account.unfollow_user(self.username):
                self.is_following = False
                self.follow_btn.SetLabel("&Follow")
                wx.MessageBox(f"Unfollowed {self.username}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to unfollow user.", "Error", wx.OK | wx.ICON_ERROR)
        else:
            # Follow
            if self.account.follow_user(self.username):
                self.is_following = True
                self.follow_btn.SetLabel("&Unfollow")
                wx.MessageBox(f"Now following {self.username}", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to follow user.", "Error", wx.OK | wx.ICON_ERROR)

    def on_view_repo(self, event):
        """View selected repository."""
        repo = self.get_selected_repo()
        if repo:
            from GUI.view import ViewRepoDialog
            dlg = ViewRepoDialog(self, repo)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_profile(self, event):
        """Open user profile in browser."""
        if self.user:
            webbrowser.open(self.user.html_url)

    def on_open_repo(self, event):
        """Open selected repo in browser."""
        repo = self.get_selected_repo()
        if repo:
            webbrowser.open(repo.html_url)

    def on_selection_change(self, event):
        """Handle selection change."""
        self.update_buttons()

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.on_view_repo(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
