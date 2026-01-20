"""File browser dialog for FastGH."""

import wx
import webbrowser
import threading
import platform
from application import get_app
from models.repository import Repository
from models.content import ContentItem
from . import theme


class FileBrowserDialog(wx.Dialog):
    """Dialog for browsing repository files."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.current_path = ""
        self.path_history = []  # Stack for back navigation
        self.contents: list[ContentItem] = []

        title = f"Files: {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(700, 500))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load root directory
        self.load_contents("")

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Path bar
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.back_btn = wx.Button(self.panel, label="&Back")
        self.back_btn.Enable(False)
        path_sizer.Add(self.back_btn, 0, wx.RIGHT, 5)

        self.home_btn = wx.Button(self.panel, label="&Root")
        path_sizer.Add(self.home_btn, 0, wx.RIGHT, 10)

        path_label = wx.StaticText(self.panel, label="Path:")
        path_sizer.Add(path_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.path_text = wx.TextCtrl(self.panel, style=wx.TE_READONLY)
        self.path_text.SetValue("/")
        path_sizer.Add(self.path_text, 1, wx.EXPAND)

        main_sizer.Add(path_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # File list
        self.file_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.file_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Status bar
        self.status_text = wx.StaticText(self.panel, label="")
        main_sizer.Add(self.status_text, 0, wx.ALL, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.open_btn = wx.Button(self.panel, label="&Open in Browser")
        btn_sizer.Add(self.open_btn, 0, wx.RIGHT, 5)

        self.copy_url_btn = wx.Button(self.panel, label="Copy &URL")
        btn_sizer.Add(self.copy_url_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Close")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        self.home_btn.Bind(wx.EVT_BUTTON, self.on_home)
        self.file_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_item_activate)
        self.file_list.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.open_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.copy_url_btn.Bind(wx.EVT_BUTTON, self.on_copy_url)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def load_contents(self, path: str):
        """Load contents of a directory."""
        self.status_text.SetLabel("Loading...")
        self.file_list.Clear()

        def do_load():
            contents = self.account.get_contents(self.repo.owner, self.repo.name, path)
            wx.CallAfter(self.update_contents, path, contents)

        threading.Thread(target=do_load, daemon=True).start()

    def update_contents(self, path: str, contents):
        """Update the file list with contents."""
        try:
            self.current_path = path
            self.path_text.SetValue("/" + path if path else "/")
            self.back_btn.Enable(len(self.path_history) > 0)

            if contents is None:
                self.status_text.SetLabel("Failed to load contents")
                self.contents = []
                return

            if isinstance(contents, list):
                self.contents = contents
                self.file_list.Clear()

                for item in contents:
                    display = item.get_display_name()
                    if item.type != "dir":
                        size_str = item.get_size_str()
                        if size_str:
                            display += f" ({size_str})"
                    self.file_list.Append(display)

                count = len(contents)
                dirs = sum(1 for c in contents if c.type == "dir")
                files = count - dirs
                self.status_text.SetLabel(f"{dirs} folders, {files} files")

                if contents:
                    self.file_list.SetSelection(0)
            else:
                # Single file was returned, view it
                self.view_file(contents)
        except RuntimeError:
            pass  # Dialog was destroyed

    def get_selected_item(self) -> ContentItem | None:
        """Get the currently selected content item."""
        sel = self.file_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self.contents):
            return None
        return self.contents[sel]

    def on_item_activate(self, event):
        """Handle double-click or Enter on item."""
        self.activate_selected()

    def on_key(self, event):
        """Handle keyboard input."""
        key = event.GetKeyCode()

        if key == wx.WXK_RETURN or key == wx.WXK_NUMPAD_ENTER:
            self.activate_selected()
        elif key == wx.WXK_BACK:
            if self.path_history:
                self.on_back(None)
        else:
            event.Skip()

    def activate_selected(self):
        """Activate the selected item (enter directory or view file)."""
        item = self.get_selected_item()
        if not item:
            return

        if item.type == "dir":
            # Save current path for back navigation
            self.path_history.append(self.current_path)
            self.load_contents(item.path)
        else:
            self.view_file(item)

    def view_file(self, item: ContentItem):
        """View a file's contents."""
        dlg = ViewFileDialog(self, self.repo, item)
        dlg.ShowModal()
        dlg.Destroy()

    def on_back(self, event):
        """Go back to previous directory."""
        if self.path_history:
            prev_path = self.path_history.pop()
            self.load_contents(prev_path)

    def on_home(self, event):
        """Go to root directory."""
        if self.current_path:
            self.path_history.append(self.current_path)
            self.load_contents("")

    def on_view(self, event):
        """View selected item."""
        self.activate_selected()

    def on_open_browser(self, event):
        """Open selected item in browser."""
        item = self.get_selected_item()
        if item and item.html_url:
            webbrowser.open(item.html_url)

    def on_copy_url(self, event):
        """Copy URL of selected item."""
        item = self.get_selected_item()
        if item and item.html_url:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(item.html_url))
                wx.TheClipboard.Close()
                wx.MessageBox(f"Copied: {item.html_url}", "Copied", wx.OK | wx.ICON_INFORMATION)

    def on_close(self, event):
        """Handle close."""
        self.EndModal(wx.ID_CANCEL)


class ViewFileDialog(wx.Dialog):
    """Dialog for viewing a file's contents."""

    def __init__(self, parent, repo: Repository, item: ContentItem):
        self.repo = repo
        self.item = item
        self.app = get_app()
        self.account = self.app.currentAccount
        self.content = None

        title = f"View: {item.name}"
        wx.Dialog.__init__(self, parent, title=title, size=(800, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load file content
        self.load_content()

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # File info
        info_sizer = wx.BoxSizer(wx.HORIZONTAL)

        path_label = wx.StaticText(self.panel, label=f"Path: {self.item.path}")
        info_sizer.Add(path_label, 1, wx.EXPAND)

        size_label = wx.StaticText(self.panel, label=f"Size: {self.item.get_size_str()}")
        info_sizer.Add(size_label, 0)

        main_sizer.Add(info_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Content text
        self.content_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL | wx.TE_DONTWRAP
        )
        # Use monospace font
        font = wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.content_text.SetFont(font)
        self.content_text.SetValue("Loading...")
        main_sizer.Add(self.content_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.copy_btn = wx.Button(self.panel, label="&Copy Content")
        btn_sizer.Add(self.copy_btn, 0, wx.RIGHT, 5)

        self.open_btn = wx.Button(self.panel, label="&Open in Browser")
        btn_sizer.Add(self.open_btn, 0, wx.RIGHT, 5)

        self.download_btn = wx.Button(self.panel, label="&Download Raw")
        btn_sizer.Add(self.download_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CANCEL, label="C&lose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.copy_btn.Bind(wx.EVT_BUTTON, self.on_copy)
        self.open_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.download_btn.Bind(wx.EVT_BUTTON, self.on_download)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def load_content(self):
        """Load the file content."""
        def do_load():
            content = self.account.get_file_content(
                self.repo.owner, self.repo.name, self.item.path
            )
            wx.CallAfter(self.update_content, content)

        threading.Thread(target=do_load, daemon=True).start()

    def update_content(self, content: str | None):
        """Update the content display."""
        try:
            if content is None:
                self.content_text.SetValue(
                    "Unable to display file content.\n\n"
                    "This may be a binary file or the file is too large.\n"
                    "Use 'Open in Browser' or 'Download Raw' to view the file."
                )
                self.content = None
            else:
                # Normalize line endings for display
                if platform.system() == "Windows":
                    content = content.replace("\r\n", "\n").replace("\n", "\r\n")
                self.content_text.SetValue(content)
                self.content = content
                self.content_text.SetInsertionPoint(0)
        except RuntimeError:
            pass  # Dialog was destroyed

    def on_copy(self, event):
        """Copy content to clipboard."""
        if self.content:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(self.content))
                wx.TheClipboard.Close()
                wx.MessageBox("Content copied to clipboard.", "Copied", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("No content to copy.", "Error", wx.OK | wx.ICON_WARNING)

    def on_open_browser(self, event):
        """Open file in browser."""
        if self.item.html_url:
            webbrowser.open(self.item.html_url)

    def on_download(self, event):
        """Download raw file."""
        if self.item.download_url:
            webbrowser.open(self.item.download_url)
        else:
            wx.MessageBox("No download URL available.", "Error", wx.OK | wx.ICON_WARNING)

    def on_close(self, event):
        """Handle close."""
        self.EndModal(wx.ID_CANCEL)
