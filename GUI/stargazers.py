"""Stargazers dialog for FastGH."""

import wx
import webbrowser
import threading
from application import get_app
from models.repository import Repository
from models.user import Stargazer
from . import theme
from .wx_safety import is_enter_key, run_key_action


class StargazersDialog(wx.Dialog):
    """Dialog for viewing the users who starred a repository."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.stargazers: list[Stargazer] = []
        self.next_page = 1  # Next page of stargazers to request
        self.has_more = False  # Whether another page is available
        self.loading = False  # A page request is in flight
        self._status_shown = False  # A trailing status entry is in the list
        self.initial_load = True

        title = f"Stargazers of {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(700, 500))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load stargazers in background
        self._append_status("Loading...")
        self._fetch_page()

    def init_ui(self):
        """Initialize UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Info label
        info_label = wx.StaticText(
            self.panel,
            label=f"Repository has {self.repo.stars} star(s)"
        )
        main_sizer.Add(info_label, 0, wx.ALL, 10)

        # Stargazers list
        list_label = wx.StaticText(self.panel, label="&Stargazers:")
        main_sizer.Add(list_label, 0, wx.LEFT, 10)

        self.stargazers_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.stargazers_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Profile")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CANCEL, label="&Close")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.update_buttons()

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        self.stargazers_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.stargazers_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.stargazers_list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)

    def on_char_hook(self, event):
        """Handle key events."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close(None)
        else:
            event.Skip()

    def on_list_key(self, event):
        """Handle key events in the list."""
        if is_enter_key(event):
            run_key_action(self.on_view)
        else:
            event.Skip()

    def _fetch_page(self):
        """Fetch the next page of stargazers in background."""
        self.loading = True
        page = self.next_page

        def do_load():
            stargazers, has_more = self.account.get_stargazers(
                self.repo.owner, self.repo.name, page=page
            )
            wx.CallAfter(self.update_list, stargazers, has_more)

        threading.Thread(target=do_load, daemon=True).start()

    def _append_status(self, text):
        """Append a status entry after the stargazers."""
        self.stargazers_list.Append(text)
        self._status_shown = True

    def _remove_status(self):
        """Remove the trailing status entry; returns True if it was selected."""
        if not self._status_shown:
            return False

        self._status_shown = False
        last = self.stargazers_list.GetCount() - 1
        was_selected = self.stargazers_list.GetSelection() == last
        if last >= 0:
            self.stargazers_list.Delete(last)
        return was_selected

    def update_list(self, stargazers: list[Stargazer], has_more: bool):
        """Append a loaded page of stargazers to the list."""
        try:
            self.loading = False
            self.next_page += 1
            self.has_more = has_more

            first_new = len(self.stargazers)
            was_on_status = self._remove_status()

            for stargazer in stargazers:
                self.stargazers_list.Append(stargazer.format_display())
            self.stargazers.extend(stargazers)

            if not self.stargazers:
                self._append_status("No stargazers found")
            elif self.initial_load:
                self.stargazers_list.SetSelection(0)
            elif was_on_status and stargazers:
                # The user had arrowed onto the loading entry - land them on the
                # first stargazer of the page they were waiting for.
                self.stargazers_list.SetSelection(first_new)

            if self.initial_load:
                self.stargazers_list.SetFocus()
                self.initial_load = False

            self.update_buttons()
        except RuntimeError:
            pass  # Dialog was destroyed

    def _maybe_load_more(self):
        """Load the next page once the selection reaches the end of the list."""
        if self.loading or not self.has_more or not self.stargazers:
            return

        selection = self.stargazers_list.GetSelection()
        if selection == wx.NOT_FOUND or selection < len(self.stargazers) - 1:
            return

        self._append_status("Loading more stargazers...")
        self._fetch_page()

    def get_selected_stargazer(self) -> Stargazer | None:
        """Get the currently selected stargazer."""
        selection = self.stargazers_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.stargazers):
            return self.stargazers[selection]
        return None

    def update_buttons(self):
        """Update button states based on selection."""
        has_selection = self.get_selected_stargazer() is not None
        self.view_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)

    def on_selection_change(self, event):
        """Handle selection change."""
        self.update_buttons()
        self._maybe_load_more()

    def on_view(self, event):
        """View the selected stargazer's profile."""
        stargazer = self.get_selected_stargazer()
        if stargazer:
            from GUI.search import UserProfileDialog
            dlg = UserProfileDialog(self, stargazer.login)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_browser(self, event):
        """Open the selected stargazer's profile in browser."""
        stargazer = self.get_selected_stargazer()
        if stargazer:
            webbrowser.open(stargazer.html_url)

    def on_close(self, event):
        """Close the dialog."""
        self.EndModal(wx.ID_CANCEL)
