"""Pull Requests dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.issue import PullRequest, Comment
from . import theme
from .issues import CommentDialog


class PullRequestsDialog(wx.Dialog):
    """Dialog for viewing and managing repository pull requests."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.pull_requests = []
        self.current_filter = "open"
        self.can_merge = False

        title = f"Pull Requests - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(850, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Check merge permissions and load PRs
        self.check_permissions()
        self.load_pull_requests()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter controls
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        filter_label = wx.StaticText(self.panel, label="&Filter:")
        filter_sizer.Add(filter_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.filter_choice = wx.Choice(self.panel, choices=["Open", "Closed", "All"])
        self.filter_choice.SetSelection(0)
        filter_sizer.Add(self.filter_choice, 0, wx.RIGHT, 10)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        filter_sizer.Add(self.refresh_btn, 0)

        main_sizer.Add(filter_sizer, 0, wx.ALL, 10)

        # Pull requests list
        list_label = wx.StaticText(self.panel, label="&Pull Requests:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.pr_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.pr_list, 1, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View PR")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.comment_btn = wx.Button(self.panel, label="&Comment")
        btn_sizer.Add(self.comment_btn, 0, wx.RIGHT, 5)

        self.merge_btn = wx.Button(self.panel, label="&Merge")
        btn_sizer.Add(self.merge_btn, 0, wx.RIGHT, 5)

        self.close_pr_btn = wx.Button(self.panel, label="C&lose PR")
        btn_sizer.Add(self.close_pr_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.filter_choice.Bind(wx.EVT_CHOICE, self.on_filter_change)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.comment_btn.Bind(wx.EVT_BUTTON, self.on_comment)
        self.merge_btn.Bind(wx.EVT_BUTTON, self.on_merge)
        self.close_pr_btn.Bind(wx.EVT_BUTTON, self.on_close_pr)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.pr_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.pr_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.pr_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def check_permissions(self):
        """Check if user can merge PRs."""
        def do_check():
            can_merge = self.account.can_merge(self.owner, self.repo_name)
            wx.CallAfter(self.set_can_merge, can_merge)

        threading.Thread(target=do_check, daemon=True).start()

    def set_can_merge(self, can_merge: bool):
        """Set merge capability."""
        self.can_merge = can_merge
        self.update_buttons()

    def load_pull_requests(self):
        """Load pull requests in background."""
        self.pr_list.Clear()
        self.pr_list.Append("Loading...")
        self.pull_requests = []

        def do_load():
            filter_map = {"Open": "open", "Closed": "closed", "All": "all"}
            state = filter_map.get(self.filter_choice.GetStringSelection(), "open")
            prs = self.account.get_pull_requests(self.owner, self.repo_name, state=state)
            wx.CallAfter(self.update_list, prs)

        threading.Thread(target=do_load, daemon=True).start()

    def update_list(self, pull_requests):
        """Update the pull requests list."""
        self.pull_requests = pull_requests
        self.pr_list.Clear()

        if not pull_requests:
            self.pr_list.Append("No pull requests found")
        else:
            for pr in pull_requests:
                self.pr_list.Append(pr.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states based on selection."""
        pr = self.get_selected_pr()
        has_selection = pr is not None

        self.view_btn.Enable(has_selection)
        self.comment_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

        # Merge and close buttons depend on PR state and permissions
        can_merge = has_selection and self.can_merge and pr and pr.state == "open" and not pr.merged
        can_close = has_selection and self.can_merge and pr and pr.state == "open" and not pr.merged

        self.merge_btn.Enable(can_merge)
        self.close_pr_btn.Enable(can_close)

    def get_selected_pr(self) -> PullRequest | None:
        """Get the currently selected pull request."""
        selection = self.pr_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.pull_requests):
            return self.pull_requests[selection]
        return None

    def on_filter_change(self, event):
        """Handle filter change."""
        self.load_pull_requests()

    def on_refresh(self, event):
        """Refresh the pull requests list."""
        self.load_pull_requests()

    def on_view(self, event):
        """View pull request details."""
        pr = self.get_selected_pr()
        if pr:
            dlg = ViewPullRequestDialog(self, self.repo, pr, self.can_merge)
            dlg.ShowModal()
            dlg.Destroy()
            # Refresh in case state changed
            self.load_pull_requests()

    def on_comment(self, event):
        """Add a comment to the pull request."""
        pr = self.get_selected_pr()
        if pr:
            dlg = CommentDialog(self, f"Comment on PR #{pr.number}")
            if dlg.ShowModal() == wx.ID_OK:
                comment_text = dlg.get_comment()
                if comment_text.strip():
                    result = self.account.create_pr_comment(
                        self.owner, self.repo_name, pr.number, comment_text
                    )
                    if result:
                        wx.MessageBox("Comment added successfully!", "Success", wx.OK | wx.ICON_INFORMATION)
                    else:
                        wx.MessageBox("Failed to add comment.", "Error", wx.OK | wx.ICON_ERROR)
            dlg.Destroy()

    def on_merge(self, event):
        """Merge the pull request."""
        pr = self.get_selected_pr()
        if not pr:
            return

        dlg = MergeDialog(self, pr)
        if dlg.ShowModal() == wx.ID_OK:
            merge_method = dlg.get_merge_method()
            commit_title = dlg.get_commit_title()
            commit_message = dlg.get_commit_message()

            if self.account.merge_pull_request(
                self.owner, self.repo_name, pr.number,
                commit_title=commit_title,
                commit_message=commit_message,
                merge_method=merge_method
            ):
                wx.MessageBox(f"Pull request #{pr.number} merged successfully!", "Success", wx.OK | wx.ICON_INFORMATION)
                self.load_pull_requests()
            else:
                wx.MessageBox("Failed to merge pull request. It may have conflicts or not be mergeable.", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def on_close_pr(self, event):
        """Close the pull request without merging."""
        pr = self.get_selected_pr()
        if not pr:
            return

        result = wx.MessageBox(
            f"Close pull request #{pr.number}: {pr.title} without merging?",
            "Confirm Close",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            if self.account.close_pull_request(self.owner, self.repo_name, pr.number):
                self.load_pull_requests()
            else:
                wx.MessageBox("Failed to close pull request.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open pull request in browser."""
        pr = self.get_selected_pr()
        if pr:
            webbrowser.open(pr.html_url)

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
        """Close the dialog."""
        self.EndModal(wx.ID_CLOSE)


class ViewPullRequestDialog(wx.Dialog):
    """Dialog for viewing pull request details."""

    def __init__(self, parent, repo: Repository, pr: PullRequest, can_merge: bool):
        self.repo = repo
        self.pr = pr
        self.can_merge = can_merge
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.comments = []

        title = f"PR #{pr.number} - {pr.title}"
        wx.Dialog.__init__(self, parent, title=title, size=(850, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load comments
        self.load_comments()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # PR details
        details_label = wx.StaticText(self.panel, label="PR &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT | wx.TOP, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(800, 130)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build details
        details = []
        details.append(f"Title: {self.pr.title}")

        if self.pr.merged:
            state_str = "MERGED"
        elif self.pr.draft:
            state_str = "DRAFT"
        else:
            state_str = self.pr.state.upper()
        details.append(f"State: {state_str}")

        details.append(f"Author: {self.pr.user.login}")
        details.append(f"Branch: {self.pr.head_ref} -> {self.pr.base_ref}")

        if self.pr.labels:
            labels_str = ", ".join(l.name for l in self.pr.labels)
            details.append(f"Labels: {labels_str}")
        if self.pr.assignees:
            assignees_str = ", ".join(a.login for a in self.pr.assignees)
            details.append(f"Assignees: {assignees_str}")

        details.append(f"Changes: +{self.pr.additions} -{self.pr.deletions} in {self.pr.changed_files} file(s)")
        details.append(f"Commits: {self.pr.commits_count} | Comments: {self.pr.comments_count}")

        if self.pr.mergeable is not None:
            mergeable_str = "Yes" if self.pr.mergeable else "No"
            if self.pr.mergeable_state:
                mergeable_str += f" ({self.pr.mergeable_state})"
            details.append(f"Mergeable: {mergeable_str}")

        if self.pr.created_at:
            details.append(f"Created: {self.pr._format_relative_time(self.pr.created_at)}")
        if self.pr.merged_at and self.pr.merged_by:
            details.append(f"Merged: {self.pr._format_relative_time(self.pr.merged_at)} by {self.pr.merged_by.login}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(details))

        # PR body
        body_label = wx.StaticText(self.panel, label="&Description:")
        main_sizer.Add(body_label, 0, wx.LEFT, 10)

        self.body_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(800, 100)
        )
        self.body_text.SetValue(self.pr.body or "No description provided.")
        main_sizer.Add(self.body_text, 0, wx.EXPAND | wx.ALL, 10)

        # Comments
        comments_label = wx.StaticText(self.panel, label="&Comments:")
        main_sizer.Add(comments_label, 0, wx.LEFT, 10)

        self.comments_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.comments_list, 1, wx.EXPAND | wx.ALL, 10)

        # Comment content
        content_label = wx.StaticText(self.panel, label="Comment C&ontent:")
        main_sizer.Add(content_label, 0, wx.LEFT, 10)

        self.comment_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(800, 80)
        )
        main_sizer.Add(self.comment_text, 0, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_comment_btn = wx.Button(self.panel, label="&Add Comment")
        btn_sizer.Add(self.add_comment_btn, 0, wx.RIGHT, 5)

        self.merge_btn = wx.Button(self.panel, label="&Merge PR")
        btn_sizer.Add(self.merge_btn, 0, wx.RIGHT, 5)

        self.close_pr_btn = wx.Button(self.panel, label="C&lose PR")
        btn_sizer.Add(self.close_pr_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # Enable/disable merge and close based on permissions and state
        can_do_merge = self.can_merge and self.pr.state == "open" and not self.pr.merged
        self.merge_btn.Enable(can_do_merge)
        self.close_pr_btn.Enable(can_do_merge)

        self.panel.SetSizer(main_sizer)
        self.body_text.SetFocus()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.comments_list.Bind(wx.EVT_LISTBOX, self.on_comment_select)
        self.add_comment_btn.Bind(wx.EVT_BUTTON, self.on_add_comment)
        self.merge_btn.Bind(wx.EVT_BUTTON, self.on_merge)
        self.close_pr_btn.Bind(wx.EVT_BUTTON, self.on_close_pr)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def load_comments(self):
        """Load comments in background."""
        self.comments_list.Clear()
        self.comments_list.Append("Loading comments...")

        def do_load():
            comments = self.account.get_pr_comments(self.owner, self.repo_name, self.pr.number)
            wx.CallAfter(self.update_comments, comments)

        threading.Thread(target=do_load, daemon=True).start()

    def update_comments(self, comments):
        """Update comments list."""
        self.comments = comments
        self.comments_list.Clear()

        if not comments:
            self.comments_list.Append("No comments yet")
        else:
            for comment in comments:
                time_str = comment.created_at.strftime("%Y-%m-%d %H:%M") if comment.created_at else "Unknown"
                preview = comment.body[:50].replace("\n", " ") + "..." if len(comment.body) > 50 else comment.body.replace("\n", " ")
                self.comments_list.Append(f"{comment.user.login} ({time_str}): {preview}")

    def on_comment_select(self, event):
        """Show selected comment content."""
        selection = self.comments_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.comments):
            comment = self.comments[selection]
            self.comment_text.SetValue(comment.body)

    def on_add_comment(self, event):
        """Add a new comment."""
        dlg = CommentDialog(self, f"Comment on PR #{self.pr.number}")
        if dlg.ShowModal() == wx.ID_OK:
            comment_text = dlg.get_comment()
            if comment_text.strip():
                result = self.account.create_pr_comment(
                    self.owner, self.repo_name, self.pr.number, comment_text
                )
                if result:
                    self.load_comments()
                else:
                    wx.MessageBox("Failed to add comment.", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def on_merge(self, event):
        """Merge the pull request."""
        dlg = MergeDialog(self, self.pr)
        if dlg.ShowModal() == wx.ID_OK:
            merge_method = dlg.get_merge_method()
            commit_title = dlg.get_commit_title()
            commit_message = dlg.get_commit_message()

            if self.account.merge_pull_request(
                self.owner, self.repo_name, self.pr.number,
                commit_title=commit_title,
                commit_message=commit_message,
                merge_method=merge_method
            ):
                self.pr.merged = True
                self.pr.state = "closed"
                self.merge_btn.Enable(False)
                self.close_pr_btn.Enable(False)
                wx.MessageBox(f"Pull request #{self.pr.number} merged successfully!", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to merge pull request. It may have conflicts or not be mergeable.", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def on_close_pr(self, event):
        """Close the pull request without merging."""
        result = wx.MessageBox(
            f"Close pull request #{self.pr.number} without merging?",
            "Confirm Close",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            if self.account.close_pull_request(self.owner, self.repo_name, self.pr.number):
                self.pr.state = "closed"
                self.merge_btn.Enable(False)
                self.close_pr_btn.Enable(False)
                wx.MessageBox("Pull request closed.", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to close pull request.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open in browser."""
        webbrowser.open(self.pr.html_url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)


class MergeDialog(wx.Dialog):
    """Dialog for merge options."""

    def __init__(self, parent, pr: PullRequest):
        self.pr = pr
        title = f"Merge PR #{pr.number}"
        wx.Dialog.__init__(self, parent, title=title, size=(500, 350))

        self.init_ui()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # PR info
        info_label = wx.StaticText(self.panel, label=f"Merging: {self.pr.title}")
        main_sizer.Add(info_label, 0, wx.ALL, 10)

        branch_label = wx.StaticText(self.panel, label=f"{self.pr.head_ref} -> {self.pr.base_ref}")
        main_sizer.Add(branch_label, 0, wx.LEFT | wx.BOTTOM, 10)

        # Merge method
        method_label = wx.StaticText(self.panel, label="&Merge Method:")
        main_sizer.Add(method_label, 0, wx.LEFT | wx.TOP, 10)

        self.method_choice = wx.Choice(self.panel, choices=[
            "Create a merge commit",
            "Squash and merge",
            "Rebase and merge"
        ])
        self.method_choice.SetSelection(0)
        main_sizer.Add(self.method_choice, 0, wx.ALL, 10)

        # Commit title
        title_label = wx.StaticText(self.panel, label="Commit &Title (optional):")
        main_sizer.Add(title_label, 0, wx.LEFT, 10)

        default_title = f"Merge pull request #{self.pr.number} from {self.pr.head_ref}"
        self.title_text = wx.TextCtrl(self.panel, value=default_title, size=(450, -1))
        main_sizer.Add(self.title_text, 0, wx.EXPAND | wx.ALL, 10)

        # Commit message
        msg_label = wx.StaticText(self.panel, label="Commit M&essage (optional):")
        main_sizer.Add(msg_label, 0, wx.LEFT, 10)

        self.message_text = wx.TextCtrl(
            self.panel,
            value=self.pr.title,
            style=wx.TE_MULTILINE,
            size=(450, 80)
        )
        main_sizer.Add(self.message_text, 0, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.merge_btn = wx.Button(self.panel, wx.ID_OK, label="&Merge")
        btn_sizer.Add(self.merge_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(self.cancel_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.method_choice.SetFocus()

    def get_merge_method(self) -> str:
        """Get selected merge method."""
        methods = ["merge", "squash", "rebase"]
        return methods[self.method_choice.GetSelection()]

    def get_commit_title(self) -> str:
        """Get commit title."""
        return self.title_text.GetValue().strip()

    def get_commit_message(self) -> str:
        """Get commit message."""
        return self.message_text.GetValue().strip()
