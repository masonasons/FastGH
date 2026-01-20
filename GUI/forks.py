"""Forks dialog for FastGH."""

import wx
import threading
from application import get_app
from models.repository import Repository
from . import theme


class ForksDialog(wx.Dialog):
    """Dialog for viewing repository forks."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.forks = []

        title = f"Forks of {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(700, 500))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load forks in background
        self.load_forks()

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Info label
        info_label = wx.StaticText(
            self.panel,
            label=f"Repository has {self.repo.forks} fork(s)"
        )
        main_sizer.Add(info_label, 0, wx.ALL, 10)

        # Forks list
        self.forks_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.forks_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Fork")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.refresh_btn = wx.Button(self.panel, label="&Refresh")
        btn_sizer.Add(self.refresh_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Close")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.forks_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view_fork)
        self.forks_list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view_fork)
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def on_list_key(self, event):
        """Handle key events in the list."""
        if event.GetKeyCode() == wx.WXK_RETURN:
            self.on_view_fork(None)
        else:
            event.Skip()

    def load_forks(self):
        """Load forks in background."""
        self.forks_list.Clear()
        self.forks_list.Append("Loading forks...")
        self.view_btn.Disable()

        def do_load():
            forks = self.account.get_forks(self.repo.owner, self.repo.name)
            wx.CallAfter(self.update_forks_list, forks)

        threading.Thread(target=do_load, daemon=True).start()

    def update_forks_list(self, forks: list[Repository]):
        """Update the forks list."""
        self.forks = forks
        self.forks_list.Clear()

        if not forks:
            self.forks_list.Append("No forks found")
            self.view_btn.Disable()
            return

        self.view_btn.Enable()

        for fork in forks:
            # Format: owner/name - stars | last pushed
            pushed = fork._format_relative_time() if fork.pushed_at else "Unknown"
            display = f"{fork.full_name} - {fork.stars} stars | Pushed {pushed}"
            self.forks_list.Append(display)

        if forks:
            self.forks_list.SetSelection(0)

    def on_view_fork(self, event):
        """View the selected fork."""
        selection = self.forks_list.GetSelection()
        if selection == wx.NOT_FOUND or not self.forks:
            return

        if selection >= len(self.forks):
            return

        fork = self.forks[selection]

        # Open ViewRepoDialog for the fork
        from GUI.view import ViewRepoDialog
        dlg = ViewRepoDialog(self, fork)
        dlg.ShowModal()
        dlg.Destroy()

    def on_refresh(self, event):
        """Refresh the forks list."""
        self.load_forks()

    def on_close(self, event):
        """Close the dialog."""
        self.EndModal(wx.ID_CANCEL)
