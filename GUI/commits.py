"""Commits dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from github_api import COMMITS_PER_PAGE
from models.repository import Repository
from models.commit import Commit
from . import theme
from .wx_safety import safe_raise


class CommitsDialog(wx.Dialog):
    """Dialog for viewing repository commits."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.commits = []
        self.all_branches = []  # All branches from API
        self.filtered_branches = []  # Currently displayed branches
        self.current_branch = None
        self.initial_load = True  # Track first load for focus
        self._open_view_dialog = None

        # Incremental loading state
        self.next_page = 1  # Next page of commits to request
        self.has_more = False  # Whether another page is available
        self.loading = False  # A page request is in flight
        self.load_token = 0  # Invalidates responses from a previous branch/refresh
        self._status_shown = False  # A status entry is appended after the commits

        title = f"Commits - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(900, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load branches first, then commits
        self.load_branches()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Branch selection row
        branch_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Branch search
        search_label = wx.StaticText(self.panel, label="&Filter:")
        branch_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.branch_search = wx.TextCtrl(self.panel, size=(150, -1))
        self.branch_search.SetHint("Search branches...")
        branch_sizer.Add(self.branch_search, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        # Branch dropdown
        branch_label = wx.StaticText(self.panel, label="&Branch:")
        branch_sizer.Add(branch_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.branch_choice = wx.Choice(self.panel, choices=["Loading..."])
        self.branch_choice.SetSelection(0)
        branch_sizer.Add(self.branch_choice, 1, wx.RIGHT, 10)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        branch_sizer.Add(self.refresh_btn, 0)

        main_sizer.Add(branch_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Commits list
        list_label = wx.StaticText(self.panel, label="&Commits:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.commits_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.commits_list, 1, wx.EXPAND | wx.ALL, 10)

        # Commit details
        details_label = wx.StaticText(self.panel, label="Commit &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(850, 120)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Details")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.copy_sha_btn = wx.Button(self.panel, label="Copy &SHA")
        btn_sizer.Add(self.copy_sha_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.branch_search.Bind(wx.EVT_TEXT, self.on_branch_search)
        self.branch_choice.Bind(wx.EVT_CHOICE, self.on_branch_change)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.copy_sha_btn.Bind(wx.EVT_BUTTON, self.on_copy_sha)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.commits_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.commits_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.commits_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def load_branches(self):
        """Load branches in background."""
        def do_load():
            branches = self.account.get_branches(self.owner, self.repo_name)
            wx.CallAfter(self.update_branches, branches)

        threading.Thread(target=do_load, daemon=True).start()

    def update_branches(self, branches):
        """Update branches dropdown (branches are sorted by last commit date)."""
        try:
            self.all_branches = branches or []
            self._populate_branch_choice()

            # Load commits for selected branch
            self.load_commits()
        except RuntimeError:
            pass  # Dialog was destroyed

    def _populate_branch_choice(self, filter_text=""):
        """Populate branch dropdown with filtered branches."""
        self.branch_choice.Clear()
        filter_text = filter_text.lower().strip()

        if not self.all_branches:
            self.branch_choice.Append("(no branches)")
            self.branch_choice.SetSelection(0)
            self.filtered_branches = []
            return

        # Filter branches by search text
        if filter_text:
            matching = [b for b in self.all_branches if filter_text in b.get('name', '').lower()]
        else:
            matching = self.all_branches

        self.filtered_branches = matching

        if not self.filtered_branches:
            self.branch_choice.Append("(no matching branches)")
            self.branch_choice.SetSelection(0)
            return

        # Add branches to dropdown
        default_idx = 0
        default_branch_idx = None
        main_idx = None
        for i, branch in enumerate(self.filtered_branches):
            name = branch.get('name', '')
            self.branch_choice.Append(name)
            if branch.get('is_default') and default_branch_idx is None:
                default_branch_idx = i
            if name in ('main', 'master') and main_idx is None:
                main_idx = i

        # Use the repo's default branch if known, then main/master by name,
        # otherwise the first branch (no filter only)
        if not filter_text:
            if default_branch_idx is not None:
                default_idx = default_branch_idx
            elif main_idx is not None:
                default_idx = main_idx

        self.branch_choice.SetSelection(default_idx)
        self.current_branch = self.filtered_branches[default_idx].get('name') if self.filtered_branches else None

    def on_branch_search(self, event):
        """Handle branch search text change."""
        try:
            filter_text = self.branch_search.GetValue()
            self._populate_branch_choice(filter_text)
        except RuntimeError:
            pass  # Dialog was destroyed

    def load_commits(self):
        """Load the first page of commits for the selected branch."""
        try:
            # Any page still in flight belongs to the previous branch/refresh
            self.load_token += 1
            self.commits = []
            self.next_page = 1
            self.has_more = False
            self.loading = False
            self._status_shown = False

            self.commits_list.Clear()
            self.details_text.SetValue("")

            branch = self.branch_choice.GetStringSelection()
            if not branch or branch in ("(no branches)", "(no matching branches)"):
                self.commits_list.Append("No branch selected")
                self.update_buttons()
                return

            self.current_branch = branch
            self._append_status("Loading...")
            self._fetch_page(branch)
        except RuntimeError:
            pass  # Dialog was destroyed

    def _fetch_page(self, branch):
        """Fetch the next page of commits in background."""
        self.loading = True
        page = self.next_page
        token = self.load_token

        def do_load():
            commits, has_more = self.account.get_commits(
                self.owner, self.repo_name, sha=branch,
                page=page, per_page=COMMITS_PER_PAGE
            )
            wx.CallAfter(self.update_list, token, commits, has_more)

        threading.Thread(target=do_load, daemon=True).start()

    def _append_status(self, text):
        """Append a status entry after the commits."""
        self.commits_list.Append(text)
        self._status_shown = True

    def _remove_status(self):
        """Remove the trailing status entry; returns True if it was selected."""
        if not self._status_shown:
            return False

        self._status_shown = False
        last = self.commits_list.GetCount() - 1
        was_selected = self.commits_list.GetSelection() == last
        if last >= 0:
            self.commits_list.Delete(last)
        return was_selected

    def update_list(self, token, commits, has_more):
        """Append a loaded page of commits to the list."""
        try:
            if token != self.load_token:
                return  # Stale page from a previous branch or refresh

            self.loading = False
            self.next_page += 1
            self.has_more = has_more

            first_new = len(self.commits)
            was_on_status = self._remove_status()

            for commit in commits:
                self.commits_list.Append(commit.format_display())
            self.commits.extend(commits)

            if not self.commits:
                self._append_status("No commits found")
            elif was_on_status and commits:
                # The user had arrowed onto the loading entry - land them on the
                # first commit of the page they were waiting for.
                self.commits_list.SetSelection(first_new)
                self.on_selection_change(None)

            # Focus on commits list only on initial load
            if self.initial_load:
                self.commits_list.SetFocus()
                self.initial_load = False

            self.update_buttons()
        except RuntimeError:
            pass  # Dialog was destroyed

    def _maybe_load_more(self):
        """Load the next page once the selection reaches the end of the list."""
        if self.loading or not self.has_more or not self.commits:
            return

        selection = self.commits_list.GetSelection()
        if selection == wx.NOT_FOUND or selection < len(self.commits) - 1:
            return

        self._append_status("Loading more commits...")
        self._fetch_page(self.current_branch)

    def update_buttons(self):
        """Update button states based on selection."""
        try:
            commit = self.get_selected_commit()
            has_selection = commit is not None

            self.view_btn.Enable(has_selection)
            self.copy_sha_btn.Enable(has_selection)
            self.open_browser_btn.Enable(has_selection)
        except RuntimeError:
            pass  # Dialog was destroyed

    def get_selected_commit(self) -> Commit | None:
        """Get the currently selected commit."""
        selection = self.commits_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.commits):
            return self.commits[selection]
        return None

    def on_branch_change(self, event):
        """Handle branch change."""
        self.load_commits()

    def on_refresh(self, event):
        """Refresh the commits list."""
        self.load_commits()

    def on_view(self, event):
        """View commit details in a dialog."""
        commit = self.get_selected_commit()
        if commit:
            if self._open_view_dialog:
                try:
                    if self._open_view_dialog.IsShown():
                        safe_raise(self._open_view_dialog)
                        return
                except RuntimeError:
                    self._open_view_dialog = None
            dlg = ViewCommitDialog(self, self.repo, commit)
            if platform.system() == "Darwin":
                # Nested modal dialogs can crash wx on macOS; keep this modeless.
                self._open_view_dialog = dlg
                def _clear_ref(_event):
                    self._open_view_dialog = None
                    dlg.Destroy()
                dlg.Bind(wx.EVT_CLOSE, _clear_ref)
                dlg.Show()
                wx.CallAfter(safe_raise, dlg)
            else:
                dlg.ShowModal()
                dlg.Destroy()

    def on_copy_sha(self, event):
        """Copy commit SHA to clipboard."""
        commit = self.get_selected_commit()
        if commit:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(commit.sha))
                wx.TheClipboard.Close()
                wx.MessageBox(f"Copied: {commit.short_sha}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_open_browser(self, event):
        """Open commit in browser."""
        commit = self.get_selected_commit()
        if commit:
            webbrowser.open(commit.html_url)

    def on_selection_change(self, event):
        """Handle selection change - show commit details."""
        self.update_buttons()
        commit = self.get_selected_commit()
        if commit:
            self.show_commit_preview(commit)
        self._maybe_load_more()

    def show_commit_preview(self, commit: Commit):
        """Show commit preview in details text."""
        lines = []
        lines.append(f"SHA: {commit.sha}")
        lines.append(f"Author: {commit.author.name} <{commit.author.email}>")
        if commit.author.date:
            lines.append(f"Date: {commit.author.date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(commit.message)

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(lines))

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            if platform.system() == "Darwin":
                wx.CallAfter(self.on_view, None)
            else:
                self.on_view(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close the dialog."""
        self.EndModal(wx.ID_CLOSE)


class ViewCommitDialog(wx.Dialog):
    """Dialog for viewing full commit details."""

    def __init__(self, parent, repo: Repository, commit: Commit):
        self.repo = repo
        self.commit = commit
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"Commit {commit.short_sha}"
        wx.Dialog.__init__(self, parent, title=title, size=(850, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load full commit details if needed
        if not commit.files:
            self.load_full_commit()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Commit info
        info_label = wx.StaticText(self.panel, label="Commit &Information:")
        main_sizer.Add(info_label, 0, wx.LEFT | wx.TOP, 10)

        self.info_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(800, 100)
        )
        main_sizer.Add(self.info_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build info
        self.update_info_text()

        # Commit message
        msg_label = wx.StaticText(self.panel, label="&Message:")
        main_sizer.Add(msg_label, 0, wx.LEFT, 10)

        self.message_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(800, 120)
        )
        self.message_text.SetValue(self.commit.message)
        main_sizer.Add(self.message_text, 0, wx.EXPAND | wx.ALL, 10)

        # Files changed
        files_label = wx.StaticText(self.panel, label="&Files Changed:")
        main_sizer.Add(files_label, 0, wx.LEFT, 10)

        self.files_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.files_list, 1, wx.EXPAND | wx.ALL, 10)

        # Update files list
        self.update_files_list()

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.copy_sha_btn = wx.Button(self.panel, label="Copy &SHA")
        btn_sizer.Add(self.copy_sha_btn, 0, wx.RIGHT, 5)

        self.copy_msg_btn = wx.Button(self.panel, label="Copy M&essage")
        btn_sizer.Add(self.copy_msg_btn, 0, wx.RIGHT, 5)

        self.copy_filename_btn = wx.Button(self.panel, label="Copy &Filename")
        btn_sizer.Add(self.copy_filename_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.message_text.SetFocus()

    def update_info_text(self):
        """Update the info text."""
        c = self.commit
        lines = []
        lines.append(f"SHA: {c.sha}")

        author_name = c.github_author.login if c.github_author else c.author.name
        lines.append(f"Author: {c.author.name} <{c.author.email}>")
        if c.github_author:
            lines.append(f"GitHub User: {c.github_author.login}")

        if c.author.date:
            lines.append(f"Date: {c.author.date.strftime('%Y-%m-%d %H:%M:%S')} ({c._format_relative_time(c.author.date)})")

        if c.author.name != c.committer.name or c.author.email != c.committer.email:
            lines.append(f"Committer: {c.committer.name} <{c.committer.email}>")

        if c.parents:
            parents_str = ", ".join(p[:7] for p in c.parents)
            lines.append(f"Parents: {parents_str}")

        if c.stats_total:
            lines.append(f"Changes: +{c.stats_additions} -{c.stats_deletions} ({c.stats_total} total)")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.info_text.SetValue(sep.join(lines))

    def load_full_commit(self):
        """Load full commit details."""
        def do_load():
            full_commit = self.account.get_commit(self.repo.owner, self.repo.name, self.commit.sha)
            if full_commit:
                wx.CallAfter(self.update_commit, full_commit)

        threading.Thread(target=do_load, daemon=True).start()

    def update_files_list(self):
        """Update the files list."""
        self.files_list.Clear()

        if not self.commit.files:
            self.files_list.Append("Loading files...")
        else:
            for f in self.commit.files:
                self.files_list.Append(f.format_display())

    def update_commit(self, commit: Commit):
        """Update with full commit details."""
        self.commit = commit
        self.update_info_text()
        self.update_files_list()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.copy_sha_btn.Bind(wx.EVT_BUTTON, self.on_copy_sha)
        self.copy_msg_btn.Bind(wx.EVT_BUTTON, self.on_copy_message)
        self.copy_filename_btn.Bind(wx.EVT_BUTTON, self.on_copy_filename)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def on_copy_sha(self, event):
        """Copy SHA to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.commit.sha))
            wx.TheClipboard.Close()
            wx.MessageBox(f"Copied: {self.commit.short_sha}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_copy_message(self, event):
        """Copy commit message to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.commit.message))
            wx.TheClipboard.Close()
            wx.MessageBox("Commit message copied!", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_copy_filename(self, event):
        """Copy selected filename to clipboard."""
        selection = self.files_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.commit.files):
            filename = self.commit.files[selection].filename
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(filename))
                wx.TheClipboard.Close()
                wx.MessageBox(f"Copied: {filename}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_open_browser(self, event):
        """Open in browser."""
        webbrowser.open(self.commit.html_url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
