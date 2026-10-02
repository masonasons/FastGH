"""Repository action buttons and context menu for dialogs that list repositories."""

import wx


def _show_modal(dlg):
    dlg.ShowModal()
    dlg.Destroy()


def view_files(parent, repo):
    from GUI.files import FileBrowserDialog
    _show_modal(FileBrowserDialog(parent, repo))


def view_issues(parent, repo):
    from GUI.issues import IssuesDialog
    _show_modal(IssuesDialog(parent, repo))


def view_prs(parent, repo):
    from GUI.pullrequests import PullRequestsDialog
    _show_modal(PullRequestsDialog(parent, repo))


def view_commits(parent, repo):
    from GUI.commits import CommitsDialog
    _show_modal(CommitsDialog(parent, repo))


def view_actions(parent, repo):
    from GUI.actions import ActionsDialog
    _show_modal(ActionsDialog(parent, repo))


def view_releases(parent, repo):
    from GUI.releases import ReleasesDialog
    _show_modal(ReleasesDialog(parent, repo))


def view_forks(parent, repo):
    from GUI.forks import ForksDialog
    _show_modal(ForksDialog(parent, repo))


def view_stargazers(parent, repo):
    from GUI.stargazers import StargazersDialog
    _show_modal(StargazersDialog(parent, repo))


def view_owner(parent, repo):
    from GUI.search import UserProfileDialog
    _show_modal(UserProfileDialog(parent, repo.owner))


def _copy_to_clipboard(text):
    if wx.TheClipboard.Open():
        wx.TheClipboard.SetData(wx.TextDataObject(text))
        wx.TheClipboard.Close()
        wx.MessageBox(f"Copied: {text}", "Copied", wx.OK | wx.ICON_INFORMATION)


def copy_url(parent, repo):
    _copy_to_clipboard(repo.html_url)


def copy_clone_url(parent, repo):
    _copy_to_clipboard(f"https://github.com/{repo.full_name}.git")


# Mnemonics avoid the letters already used by the search and profile dialogs.
REPO_ACTIONS = [
    ("View Fi&les", view_files),
    ("View &Issues", view_issues),
    ("View Pull Reques&ts", view_prs),
    ("View Co&mmits", view_commits),
    ("View &Actions", view_actions),
    ("View R&eleases", view_releases),
    ("View For&ks", view_forks),
    ("View Starga&zers", view_stargazers),
]
OWNER_ACTION = ("View O&wner", view_owner)
COPY_ACTIONS = [
    ("&Copy URL", copy_url),
    ("Copy Clo&ne URL", copy_clone_url),
]


class RepoActionButtons:
    """A wrapping row of buttons acting on a dialog's selected repository."""

    def __init__(self, dialog, panel, get_repo, include_owner=True):
        """
        Args:
            dialog: Dialog to parent the opened dialogs to
            panel: Panel the buttons are created on
            get_repo: Callable returning the selected Repository, or None
            include_owner: Whether to offer viewing the repository owner
        """
        self.dialog = dialog
        self.get_repo = get_repo
        self.actions = list(REPO_ACTIONS)
        if include_owner:
            self.actions.append(OWNER_ACTION)
        self.actions.extend(COPY_ACTIONS)

        self.sizer = wx.WrapSizer(wx.HORIZONTAL)
        self.buttons = []
        for label, action in self.actions:
            btn = wx.Button(panel, label=label)
            btn.Bind(wx.EVT_BUTTON, lambda e, a=action: self.run(a))
            self.sizer.Add(btn, 0, wx.RIGHT | wx.BOTTOM, 5)
            self.buttons.append(btn)

    def run(self, action):
        """Run an action on the selected repository."""
        repo = self.get_repo()
        if repo:
            action(self.dialog, repo)

    def enable(self, enabled: bool):
        for btn in self.buttons:
            btn.Enable(enabled)

    def show(self, shown: bool):
        self.sizer.ShowItems(shown)

    def show_menu(self, window, extra_items=()):
        """Pop up the repository actions as a context menu on window.

        Args:
            extra_items: (label, handler) pairs listed before the repository actions
        """
        if not self.get_repo():
            return

        menu = wx.Menu()
        for label, handler in extra_items:
            item = menu.Append(-1, label)
            window.Bind(wx.EVT_MENU, handler, item)
        if extra_items:
            menu.AppendSeparator()
        for label, action in self.actions:
            item = menu.Append(-1, label)
            window.Bind(wx.EVT_MENU, lambda e, a=action: self.run(a), item)

        window.PopupMenu(menu)
        menu.Destroy()
