"""Issues dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.issue import Issue, Comment
from . import theme

text_box_size = (650, 120)


class IssuesDialog(wx.Dialog):
    """Dialog for viewing and managing repository issues."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.issues = []
        self.current_filter = "open"

        title = f"Issues - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(800, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load issues
        self.load_issues()

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
        filter_sizer.Add(self.refresh_btn, 0, wx.RIGHT, 10)

        self.new_issue_btn = wx.Button(self.panel, label="&New Issue")
        filter_sizer.Add(self.new_issue_btn, 0)

        main_sizer.Add(filter_sizer, 0, wx.ALL, 10)

        # Issues list
        list_label = wx.StaticText(self.panel, label="I&ssues:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.issues_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.issues_list, 1, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Issue")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.comment_btn = wx.Button(self.panel, label="&Comment")
        btn_sizer.Add(self.comment_btn, 0, wx.RIGHT, 5)

        self.toggle_state_btn = wx.Button(self.panel, label="C&lose Issue")
        btn_sizer.Add(self.toggle_state_btn, 0, wx.RIGHT, 5)

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
        self.new_issue_btn.Bind(wx.EVT_BUTTON, self.on_new_issue)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.comment_btn.Bind(wx.EVT_BUTTON, self.on_comment)
        self.toggle_state_btn.Bind(wx.EVT_BUTTON, self.on_toggle_state)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.issues_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.issues_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.issues_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def load_issues(self):
        """Load issues in background."""
        self.issues_list.Clear()
        self.issues_list.Append("Loading...")
        self.issues = []

        def do_load():
            filter_map = {"Open": "open", "Closed": "closed", "All": "all"}
            state = filter_map.get(self.filter_choice.GetStringSelection(), "open")
            issues = self.account.get_issues(self.owner, self.repo_name, state=state)
            wx.CallAfter(self.update_list, issues)

        threading.Thread(target=do_load, daemon=True).start()

    def update_list(self, issues):
        """Update the issues list."""
        self.issues = issues
        self.issues_list.Clear()

        if not issues:
            self.issues_list.Append("No issues found")
        else:
            for issue in issues:
                self.issues_list.Append(issue.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states based on selection."""
        issue = self.get_selected_issue()
        has_selection = issue is not None

        self.view_btn.Enable(has_selection)
        self.comment_btn.Enable(has_selection)
        self.toggle_state_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

        if issue:
            if issue.state == "open":
                self.toggle_state_btn.SetLabel("C&lose Issue")
            else:
                self.toggle_state_btn.SetLabel("&Reopen Issue")

    def get_selected_issue(self) -> Issue | None:
        """Get the currently selected issue."""
        selection = self.issues_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.issues):
            return self.issues[selection]
        return None

    def on_filter_change(self, event):
        """Handle filter change."""
        self.load_issues()

    def on_refresh(self, event):
        """Refresh the issues list."""
        self.load_issues()

    def on_new_issue(self, event):
        """Create a new issue."""
        dlg = NewIssueDialog(self, self.repo)
        if dlg.ShowModal() == wx.ID_OK:
            self.load_issues()
        dlg.Destroy()

    def on_view(self, event):
        """View issue details."""
        issue = self.get_selected_issue()
        if issue:
            dlg = ViewIssueDialog(self, self.repo, issue)
            dlg.ShowModal()
            dlg.Destroy()
            # Refresh in case state changed
            self.load_issues()

    def on_comment(self, event):
        """Add a comment to the issue."""
        issue = self.get_selected_issue()
        if issue:
            dlg = CommentDialog(self, f"Comment on Issue #{issue.number}")
            if dlg.ShowModal() == wx.ID_OK:
                comment_text = dlg.get_comment()
                if comment_text.strip():
                    result = self.account.create_issue_comment(
                        self.owner, self.repo_name, issue.number, comment_text
                    )
                    if result:
                        wx.MessageBox("Comment added successfully!", "Success", wx.OK | wx.ICON_INFORMATION)
                    else:
                        wx.MessageBox("Failed to add comment.", "Error", wx.OK | wx.ICON_ERROR)
            dlg.Destroy()

    def on_toggle_state(self, event):
        """Close or reopen the issue."""
        issue = self.get_selected_issue()
        if not issue:
            return

        if issue.state == "open":
            result = wx.MessageBox(
                f"Close issue #{issue.number}: {issue.title}?",
                "Confirm Close",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result == wx.YES:
                if self.account.close_issue(self.owner, self.repo_name, issue.number):
                    self.load_issues()
                else:
                    wx.MessageBox("Failed to close issue.", "Error", wx.OK | wx.ICON_ERROR)
        else:
            result = wx.MessageBox(
                f"Reopen issue #{issue.number}: {issue.title}?",
                "Confirm Reopen",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result == wx.YES:
                if self.account.reopen_issue(self.owner, self.repo_name, issue.number):
                    self.load_issues()
                else:
                    wx.MessageBox("Failed to reopen issue.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open issue in browser."""
        issue = self.get_selected_issue()
        if issue:
            webbrowser.open(issue.html_url)

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


class ViewIssueDialog(wx.Dialog):
    """Dialog for viewing issue details."""

    def __init__(self, parent, repo: Repository, issue: Issue):
        self.repo = repo
        self.issue = issue
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.comments = []

        title = f"Issue #{issue.number} - {issue.title}"
        wx.Dialog.__init__(self, parent, title=title, size=(800, 650))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load comments
        self.load_comments()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Issue details
        details_label = wx.StaticText(self.panel, label="Issue &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT | wx.TOP, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(750, 100)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build details
        details = []
        details.append(f"Title: {self.issue.title}")
        details.append(f"State: {self.issue.state.upper()}")
        details.append(f"Author: {self.issue.user.login}")
        if self.issue.labels:
            labels_str = ", ".join(l.name for l in self.issue.labels)
            details.append(f"Labels: {labels_str}")
        if self.issue.assignees:
            assignees_str = ", ".join(a.login for a in self.issue.assignees)
            details.append(f"Assignees: {assignees_str}")
        details.append(f"Comments: {self.issue.comments_count}")
        if self.issue.created_at:
            details.append(f"Created: {self.issue._format_relative_time(self.issue.created_at)}")
        if self.issue.updated_at:
            details.append(f"Updated: {self.issue._format_relative_time(self.issue.updated_at)}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(details))

        # Issue body
        body_label = wx.StaticText(self.panel, label="&Body:")
        main_sizer.Add(body_label, 0, wx.LEFT, 10)

        self.body_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(750, 120)
        )
        self.body_text.SetValue(self.issue.body or "No description provided.")
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
            size=(750, 80)
        )
        main_sizer.Add(self.comment_text, 0, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_comment_btn = wx.Button(self.panel, label="&Add Comment")
        btn_sizer.Add(self.add_comment_btn, 0, wx.RIGHT, 5)

        self.toggle_state_btn = wx.Button(self.panel, label="C&lose Issue" if self.issue.state == "open" else "&Reopen Issue")
        btn_sizer.Add(self.toggle_state_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.body_text.SetFocus()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.comments_list.Bind(wx.EVT_LISTBOX, self.on_comment_select)
        self.add_comment_btn.Bind(wx.EVT_BUTTON, self.on_add_comment)
        self.toggle_state_btn.Bind(wx.EVT_BUTTON, self.on_toggle_state)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def load_comments(self):
        """Load comments in background."""
        self.comments_list.Clear()
        self.comments_list.Append("Loading comments...")

        def do_load():
            comments = self.account.get_issue_comments(self.owner, self.repo_name, self.issue.number)
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
        dlg = CommentDialog(self, f"Comment on Issue #{self.issue.number}")
        if dlg.ShowModal() == wx.ID_OK:
            comment_text = dlg.get_comment()
            if comment_text.strip():
                result = self.account.create_issue_comment(
                    self.owner, self.repo_name, self.issue.number, comment_text
                )
                if result:
                    self.load_comments()
                else:
                    wx.MessageBox("Failed to add comment.", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def on_toggle_state(self, event):
        """Close or reopen the issue."""
        if self.issue.state == "open":
            if self.account.close_issue(self.owner, self.repo_name, self.issue.number):
                self.issue.state = "closed"
                self.toggle_state_btn.SetLabel("&Reopen Issue")
                wx.MessageBox("Issue closed.", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to close issue.", "Error", wx.OK | wx.ICON_ERROR)
        else:
            if self.account.reopen_issue(self.owner, self.repo_name, self.issue.number):
                self.issue.state = "open"
                self.toggle_state_btn.SetLabel("C&lose Issue")
                wx.MessageBox("Issue reopened.", "Success", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("Failed to reopen issue.", "Error", wx.OK | wx.ICON_ERROR)

    def on_open_browser(self, event):
        """Open in browser."""
        webbrowser.open(self.issue.html_url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)


class NewIssueDialog(wx.Dialog):
    """Dialog for creating a new issue."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"New Issue - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(600, 450))

        self.init_ui()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title_label = wx.StaticText(self.panel, label="&Title:")
        main_sizer.Add(title_label, 0, wx.LEFT | wx.TOP, 10)

        self.title_text = wx.TextCtrl(self.panel, size=(550, -1))
        main_sizer.Add(self.title_text, 0, wx.EXPAND | wx.ALL, 10)
        self.title_text.SetFocus()

        # Body
        body_label = wx.StaticText(self.panel, label="&Body:")
        main_sizer.Add(body_label, 0, wx.LEFT, 10)

        self.body_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_MULTILINE,
            size=(550, 250)
        )
        main_sizer.Add(self.body_text, 1, wx.EXPAND | wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.create_btn = wx.Button(self.panel, wx.ID_OK, label="&Create Issue")
        self.create_btn.Bind(wx.EVT_BUTTON, self.on_create)
        btn_sizer.Add(self.create_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(self.cancel_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def on_create(self, event):
        """Create the issue."""
        title = self.title_text.GetValue().strip()
        body = self.body_text.GetValue()

        if not title:
            wx.MessageBox("Please enter a title.", "Error", wx.OK | wx.ICON_ERROR)
            return

        result = self.account.create_issue(self.repo.owner, self.repo.name, title, body)
        if result:
            wx.MessageBox(f"Issue #{result.number} created successfully!", "Success", wx.OK | wx.ICON_INFORMATION)
            self.EndModal(wx.ID_OK)
        else:
            wx.MessageBox("Failed to create issue.", "Error", wx.OK | wx.ICON_ERROR)


class CommentDialog(wx.Dialog):
    """Dialog for entering a comment."""

    def __init__(self, parent, title="Add Comment"):
        wx.Dialog.__init__(self, parent, title=title, size=(500, 300))
        self.init_ui()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(self.panel, label="&Comment:")
        main_sizer.Add(label, 0, wx.LEFT | wx.TOP, 10)

        self.comment_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_MULTILINE,
            size=(450, 180)
        )
        main_sizer.Add(self.comment_text, 1, wx.EXPAND | wx.ALL, 10)
        self.comment_text.SetFocus()

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.ok_btn = wx.Button(self.panel, wx.ID_OK, label="&Submit")
        btn_sizer.Add(self.ok_btn, 0, wx.RIGHT, 5)

        self.cancel_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Cancel")
        btn_sizer.Add(self.cancel_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def get_comment(self) -> str:
        """Get the comment text."""
        return self.comment_text.GetValue()
