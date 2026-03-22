"""Discussion dialog for FastGH."""

import wx
import webbrowser
import platform
import threading
from application import get_app
from models.discussion import Discussion, DiscussionComment
from . import theme


class ViewDiscussionDialog(wx.Dialog):
    """Dialog for viewing a discussion and its comments."""

    def __init__(self, parent, owner: str, repo_name: str, discussion: Discussion):
        self.owner = owner
        self.repo_name = repo_name
        self.discussion = discussion
        self.comments = list(discussion.comments)
        self.has_next_page = discussion.comments_has_next_page
        self.end_cursor = discussion.comments_end_cursor
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"Discussion #{discussion.number} - {discussion.title}"
        wx.Dialog.__init__(self, parent, title=title, size=(880, 720))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)
        self.update_details()
        self.update_comments_list()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        details_label = wx.StaticText(self.panel, label="Discussion &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT | wx.TOP, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(840, 110)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        body_label = wx.StaticText(self.panel, label="&Body:")
        main_sizer.Add(body_label, 0, wx.LEFT, 10)

        self.body_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(840, 130)
        )
        main_sizer.Add(self.body_text, 0, wx.EXPAND | wx.ALL, 10)

        comments_label = wx.StaticText(self.panel, label="&Comments:")
        main_sizer.Add(comments_label, 0, wx.LEFT, 10)

        self.comments_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.comments_list, 1, wx.EXPAND | wx.ALL, 10)

        content_label = wx.StaticText(self.panel, label="Comment C&ontent:")
        main_sizer.Add(content_label, 0, wx.LEFT, 10)

        self.comment_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(840, 90)
        )
        main_sizer.Add(self.comment_text, 0, wx.EXPAND | wx.ALL, 10)

        add_label = wx.StaticText(self.panel, label="Add C&omment:")
        main_sizer.Add(add_label, 0, wx.LEFT, 10)

        self.add_comment_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_MULTILINE,
            size=(840, 100)
        )
        main_sizer.Add(self.add_comment_text, 0, wx.EXPAND | wx.ALL, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh Comments")
        btn_sizer.Add(self.refresh_btn, 0, wx.RIGHT, 5)

        self.load_more_btn = wx.Button(self.panel, label="Load &More")
        btn_sizer.Add(self.load_more_btn, 0, wx.RIGHT, 5)

        self.post_comment_btn = wx.Button(self.panel, label="&Post Comment")
        btn_sizer.Add(self.post_comment_btn, 0, wx.RIGHT, 5)

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
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.comments_list.Bind(wx.EVT_LISTBOX, self.on_comment_select)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh_comments)
        self.load_more_btn.Bind(wx.EVT_BUTTON, self.on_load_more_comments)
        self.post_comment_btn.Bind(wx.EVT_BUTTON, self.on_post_comment)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def update_details(self):
        """Update discussion details section."""
        details = []
        details.append(f"Title: {self.discussion.title}")
        details.append(f"Author: {self.discussion.author.login}")
        if self.discussion.category_name:
            details.append(f"Category: {self.discussion.category_name}")
        details.append(f"Answered: {'Yes' if self.discussion.is_answered else 'No'}")
        details.append(f"Comments: {self.discussion.comments_count}")
        if self.discussion.created_at:
            details.append(f"Created: {self.discussion._format_relative_time(self.discussion.created_at)}")
        if self.discussion.updated_at:
            details.append(f"Updated: {self.discussion._format_relative_time(self.discussion.updated_at)}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(details))
        self.body_text.SetValue(self.discussion.body or "No description provided.")
        self.load_more_btn.Enable(self.has_next_page)

    def update_comments_list(self):
        """Update comments list from local cache."""
        self.comments_list.Clear()
        self.comment_text.SetValue("")

        if not self.comments:
            self.comments_list.Append("No comments yet")
            return

        for comment in self.comments:
            if comment.created_at:
                time_str = comment.created_at.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = "Unknown"
            preview = comment.body.replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:60] + "..."
            if comment.is_reply:
                parent = f" to {comment.parent_author_login}" if comment.parent_author_login else ""
                self.comments_list.Append(f"[Reply{parent}] {comment.author.login} ({time_str}): {preview}")
            else:
                self.comments_list.Append(f"{comment.author.login} ({time_str}): {preview}")

    def _set_comments_loaded(self, comments: list[DiscussionComment], has_next_page: bool, end_cursor: str | None):
        """Replace comments list after a refresh."""
        self.comments = comments
        self.has_next_page = has_next_page
        self.end_cursor = end_cursor
        self.update_comments_list()
        self.load_more_btn.Enable(self.has_next_page)

    def _append_comments_loaded(self, comments: list[DiscussionComment], has_next_page: bool, end_cursor: str | None):
        """Append one page of comments."""
        if comments:
            self.comments.extend(comments)
        self.has_next_page = has_next_page
        self.end_cursor = end_cursor
        self.update_comments_list()
        self.load_more_btn.Enable(self.has_next_page)

    def on_comment_select(self, event):
        """Show selected comment content."""
        selection = self.comments_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.comments):
            self.comment_text.SetValue(self.comments[selection].body)

    def on_refresh_comments(self, event):
        """Reload first page of comments."""
        self.comments_list.Clear()
        self.comments_list.Append("Loading comments...")
        self.comment_text.SetValue("")

        def do_load():
            comments, has_next_page, end_cursor = self.account.get_discussion_comments(
                self.owner, self.repo_name, self.discussion.number, first=50
            )
            wx.CallAfter(self._set_comments_loaded, comments, has_next_page, end_cursor)

        threading.Thread(target=do_load, daemon=True).start()

    def on_load_more_comments(self, event):
        """Load next page of comments."""
        if not self.has_next_page:
            return

        self.load_more_btn.Enable(False)

        def do_load():
            comments, has_next_page, end_cursor = self.account.get_discussion_comments(
                self.owner,
                self.repo_name,
                self.discussion.number,
                first=50,
                after=self.end_cursor
            )
            wx.CallAfter(self._append_comments_loaded, comments, has_next_page, end_cursor)

        threading.Thread(target=do_load, daemon=True).start()

    def _on_post_comment_done(self, new_comment: DiscussionComment | None):
        """Handle posted comment result on main thread."""
        self.post_comment_btn.Enable(True)
        if not new_comment:
            wx.MessageBox("Failed to add comment.", "Error", wx.OK | wx.ICON_ERROR)
            return

        self.comments.append(new_comment)
        self.discussion.comments_count += 1
        self.add_comment_text.SetValue("")
        self.update_details()
        self.update_comments_list()
        self.comments_list.SetSelection(len(self.comments) - 1)
        self.comment_text.SetValue(new_comment.body)

    def on_post_comment(self, event):
        """Post a new comment."""
        body = self.add_comment_text.GetValue().strip()
        if not body:
            wx.MessageBox("Please enter a comment.", "Error", wx.OK | wx.ICON_ERROR)
            return

        self.post_comment_btn.Enable(False)

        def do_post():
            new_comment = self.account.create_discussion_comment(self.discussion.id, body)
            wx.CallAfter(self._on_post_comment_done, new_comment)

        threading.Thread(target=do_post, daemon=True).start()

    def on_open_browser(self, event):
        """Open discussion in browser."""
        webbrowser.open(self.discussion.url)

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
