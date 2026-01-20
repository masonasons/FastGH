"""Releases dialog for FastGH."""

import os
import wx
import webbrowser
import platform
import threading
from application import get_app
from models.repository import Repository
from models.release import Release, ReleaseAsset
from . import theme


class ReleasesDialog(wx.Dialog):
    """Dialog for viewing repository releases."""

    def __init__(self, parent, repo: Repository):
        self.repo = repo
        self.app = get_app()
        self.account = self.app.currentAccount
        self.owner = repo.owner
        self.repo_name = repo.name
        self.releases = []

        title = f"Releases - {repo.full_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(900, 600))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

        # Load releases
        self.load_releases()

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Releases list
        list_label = wx.StaticText(self.panel, label="&Releases:")
        main_sizer.Add(list_label, 0, wx.LEFT | wx.TOP, 10)

        self.releases_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.releases_list, 1, wx.EXPAND | wx.ALL, 10)

        # Release details
        details_label = wx.StaticText(self.panel, label="Release &Details:")
        main_sizer.Add(details_label, 0, wx.LEFT, 10)

        self.details_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(850, 100)
        )
        main_sizer.Add(self.details_text, 0, wx.EXPAND | wx.ALL, 10)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.view_btn = wx.Button(self.panel, label="&View Details")
        btn_sizer.Add(self.view_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.download_zip_btn = wx.Button(self.panel, label="Download &ZIP")
        btn_sizer.Add(self.download_zip_btn, 0, wx.RIGHT, 5)

        self.download_tar_btn = wx.Button(self.panel, label="Download &Tarball")
        btn_sizer.Add(self.download_tar_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.view_btn.Bind(wx.EVT_BUTTON, self.on_view)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.download_zip_btn.Bind(wx.EVT_BUTTON, self.on_download_zip)
        self.download_tar_btn.Bind(wx.EVT_BUTTON, self.on_download_tar)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.releases_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_view)
        self.releases_list.Bind(wx.EVT_LISTBOX, self.on_selection_change)
        self.releases_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def load_releases(self):
        """Load releases in background."""
        self.releases_list.Clear()
        self.releases_list.Append("Loading...")
        self.releases = []
        self.details_text.SetValue("")

        def do_load():
            releases = self.account.get_releases(self.owner, self.repo_name)
            wx.CallAfter(self.update_list, releases)

        threading.Thread(target=do_load, daemon=True).start()

    def update_list(self, releases):
        """Update the releases list."""
        self.releases = releases
        self.releases_list.Clear()

        if not releases:
            self.releases_list.Append("No releases found")
        else:
            for release in releases:
                self.releases_list.Append(release.format_display())

        self.update_buttons()

    def update_buttons(self):
        """Update button states based on selection."""
        release = self.get_selected_release()
        has_selection = release is not None

        self.view_btn.Enable(has_selection)
        self.open_browser_btn.Enable(has_selection)
        self.download_zip_btn.Enable(has_selection)
        self.download_tar_btn.Enable(has_selection)

    def get_selected_release(self) -> Release | None:
        """Get the currently selected release."""
        selection = self.releases_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.releases):
            return self.releases[selection]
        return None

    def on_view(self, event):
        """View release details in a dialog."""
        release = self.get_selected_release()
        if release:
            dlg = ViewReleaseDialog(self, self.repo, release)
            dlg.ShowModal()
            dlg.Destroy()

    def on_open_browser(self, event):
        """Open release in browser."""
        release = self.get_selected_release()
        if release:
            webbrowser.open(release.html_url)

    def on_download_zip(self, event):
        """Download source code as ZIP."""
        release = self.get_selected_release()
        if release and release.zipball_url:
            webbrowser.open(release.zipball_url)

    def on_download_tar(self, event):
        """Download source code as tarball."""
        release = self.get_selected_release()
        if release and release.tarball_url:
            webbrowser.open(release.tarball_url)

    def on_selection_change(self, event):
        """Handle selection change - show release details."""
        self.update_buttons()
        release = self.get_selected_release()
        if release:
            self.show_release_preview(release)

    def show_release_preview(self, release: Release):
        """Show release preview in details text."""
        lines = []
        lines.append(f"Tag: {release.tag_name}")
        if release.name != release.tag_name:
            lines.append(f"Name: {release.name}")
        lines.append(f"Type: {release.get_status_label()}")
        lines.append(f"Author: {release.author_login}")
        if release.published_at:
            lines.append(f"Published: {release.published_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Assets: {len(release.assets)}")

        if release.body:
            lines.append("")
            # Truncate body for preview
            body_preview = release.body[:200]
            if len(release.body) > 200:
                body_preview += "..."
            lines.append(body_preview)

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.details_text.SetValue(sep.join(lines))

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


class ViewReleaseDialog(wx.Dialog):
    """Dialog for viewing full release details with assets."""

    def __init__(self, parent, repo: Repository, release: Release):
        self.repo = repo
        self.release = release
        self.app = get_app()
        self.account = self.app.currentAccount

        title = f"Release {release.tag_name}"
        wx.Dialog.__init__(self, parent, title=title, size=(900, 700))

        self.init_ui()
        self.bind_events()
        theme.apply_theme(self)

    def init_ui(self):
        """Initialize the UI."""
        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Release info
        info_label = wx.StaticText(self.panel, label="Release &Information:")
        main_sizer.Add(info_label, 0, wx.LEFT | wx.TOP, 10)

        self.info_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_DONTWRAP,
            size=(850, 80)
        )
        main_sizer.Add(self.info_text, 0, wx.EXPAND | wx.ALL, 10)

        # Build info
        self.update_info_text()

        # Release notes
        notes_label = wx.StaticText(self.panel, label="Release &Notes:")
        main_sizer.Add(notes_label, 0, wx.LEFT, 10)

        self.notes_text = wx.TextCtrl(
            self.panel,
            style=wx.TE_READONLY | wx.TE_MULTILINE,
            size=(850, 150)
        )
        self.notes_text.SetValue(self.release.body or "No release notes")
        main_sizer.Add(self.notes_text, 0, wx.EXPAND | wx.ALL, 10)

        # Assets list
        assets_label = wx.StaticText(self.panel, label="&Assets:")
        main_sizer.Add(assets_label, 0, wx.LEFT, 10)

        self.assets_list = wx.ListBox(self.panel, style=wx.LB_SINGLE)
        main_sizer.Add(self.assets_list, 1, wx.EXPAND | wx.ALL, 10)

        # Populate assets
        self.update_assets_list()

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.download_btn = wx.Button(self.panel, label="&Download Selected")
        btn_sizer.Add(self.download_btn, 0, wx.RIGHT, 5)

        self.download_all_btn = wx.Button(self.panel, label="Download &All Assets")
        btn_sizer.Add(self.download_all_btn, 0, wx.RIGHT, 5)

        self.open_browser_btn = wx.Button(self.panel, label="Open in &Browser")
        btn_sizer.Add(self.open_browser_btn, 0, wx.RIGHT, 5)

        self.close_btn = wx.Button(self.panel, wx.ID_CLOSE, label="Cl&ose")
        btn_sizer.Add(self.close_btn, 0)

        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        self.panel.SetSizer(main_sizer)
        self.update_buttons()

    def update_info_text(self):
        """Update the info text."""
        r = self.release
        lines = []
        lines.append(f"Tag: {r.tag_name}")
        if r.name != r.tag_name:
            lines.append(f"Name: {r.name}")
        lines.append(f"Type: {r.get_status_label()}")
        lines.append(f"Author: {r.author_login}")
        if r.published_at:
            lines.append(f"Published: {r.published_at.strftime('%Y-%m-%d %H:%M:%S')}")
        elif r.created_at:
            lines.append(f"Created: {r.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        sep = "\r\n" if platform.system() != "Darwin" else "\n"
        self.info_text.SetValue(sep.join(lines))

    def update_assets_list(self):
        """Update the assets list."""
        self.assets_list.Clear()

        if not self.release.assets:
            self.assets_list.Append("No assets")
        else:
            for asset in self.release.assets:
                self.assets_list.Append(asset.format_display())

    def update_buttons(self):
        """Update button states."""
        has_assets = len(self.release.assets) > 0
        has_selection = self.assets_list.GetSelection() != wx.NOT_FOUND and has_assets

        self.download_btn.Enable(has_selection)
        self.download_all_btn.Enable(has_assets)

    def get_selected_asset(self) -> ReleaseAsset | None:
        """Get the currently selected asset."""
        selection = self.assets_list.GetSelection()
        if selection != wx.NOT_FOUND and selection < len(self.release.assets):
            return self.release.assets[selection]
        return None

    def bind_events(self):
        """Bind event handlers."""
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.download_btn.Bind(wx.EVT_BUTTON, self.on_download)
        self.download_all_btn.Bind(wx.EVT_BUTTON, self.on_download_all)
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        self.assets_list.Bind(wx.EVT_LISTBOX, self.on_asset_selection)
        self.assets_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_download)
        self.assets_list.Bind(wx.EVT_KEY_DOWN, self.on_key)

    def on_asset_selection(self, event):
        """Handle asset selection change."""
        self.update_buttons()

    def on_download(self, event):
        """Download selected asset."""
        asset = self.get_selected_asset()
        if not asset:
            return

        self.download_asset(asset)

    def on_download_all(self, event):
        """Download all assets."""
        if not self.release.assets:
            return

        # Ask for confirmation
        count = len(self.release.assets)
        result = wx.MessageBox(
            f"Download all {count} assets in background?",
            "Confirm Download",
            wx.YES_NO | wx.ICON_QUESTION
        )

        if result != wx.YES:
            return

        download_dir = self.app.prefs.download_location

        # Ensure download directory exists
        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except Exception as e:
                wx.MessageBox(
                    f"Could not create download directory:\n{e}",
                    "Error",
                    wx.OK | wx.ICON_ERROR
                )
                return

        # Check for existing files
        existing = []
        for asset in self.release.assets:
            dest_path = os.path.join(download_dir, asset.name)
            if os.path.exists(dest_path):
                existing.append(asset.name)

        if existing:
            result = wx.MessageBox(
                f"{len(existing)} file(s) already exist. Overwrite?",
                "Files Exist",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result != wx.YES:
                return

        # Start background download of all assets
        def do_download_all():
            succeeded = 0
            failed = 0

            for asset in self.release.assets:
                dest_path = os.path.join(download_dir, asset.name)
                success = self.account.download_asset(
                    self.repo.owner,
                    self.repo.name,
                    asset.id,
                    dest_path
                )
                if success:
                    succeeded += 1
                else:
                    failed += 1

            wx.CallAfter(download_all_complete, succeeded, failed)

        def download_all_complete(succeeded, failed):
            if failed == 0:
                wx.MessageBox(
                    f"Downloaded {succeeded} assets to:\n{download_dir}",
                    "Download Complete",
                    wx.OK | wx.ICON_INFORMATION
                )
            else:
                wx.MessageBox(
                    f"Downloaded {succeeded} assets, {failed} failed.\n\nLocation: {download_dir}",
                    "Download Complete",
                    wx.OK | wx.ICON_WARNING
                )

        threading.Thread(target=do_download_all, daemon=True).start()

    def download_asset(self, asset: ReleaseAsset, show_success: bool = True):
        """Download a single asset in background."""
        download_dir = self.app.prefs.download_location

        # Ensure download directory exists
        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except Exception as e:
                wx.MessageBox(
                    f"Could not create download directory:\n{e}",
                    "Error",
                    wx.OK | wx.ICON_ERROR
                )
                return

        dest_path = os.path.join(download_dir, asset.name)

        # Check if file exists
        if os.path.exists(dest_path):
            result = wx.MessageBox(
                f"File already exists:\n{dest_path}\n\nOverwrite?",
                "File Exists",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result != wx.YES:
                return

        def do_download():
            success = self.account.download_asset(
                self.repo.owner,
                self.repo.name,
                asset.id,
                dest_path
            )
            wx.CallAfter(download_complete, success)

        def download_complete(success):
            if success:
                if show_success:
                    wx.MessageBox(
                        f"Downloaded:\n{dest_path}",
                        "Download Complete",
                        wx.OK | wx.ICON_INFORMATION
                    )
            else:
                wx.MessageBox(
                    f"Failed to download {asset.name}",
                    "Error",
                    wx.OK | wx.ICON_ERROR
                )

        threading.Thread(target=do_download, daemon=True).start()

    def on_open_browser(self, event):
        """Open release in browser."""
        webbrowser.open(self.release.html_url)

    def on_key(self, event):
        """Handle key events."""
        key = event.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.on_download(None)
        else:
            event.Skip()

    def on_close(self, event):
        """Close dialog."""
        self.EndModal(wx.ID_CLOSE)
