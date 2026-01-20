"""GitHub API wrapper with OAuth Device Flow authentication."""

import time
import threading
from datetime import datetime
import requests
import config
import wx
from models.repository import Repository
from models.issue import Issue, PullRequest, Comment
from models.commit import Commit
from models.user import UserProfile
from models.workflow import Workflow, WorkflowRun, WorkflowJob
from models.release import Release, ReleaseAsset
from models.notification import Notification
from models.event import Event

# GitHub OAuth App Client ID
# You need to create an OAuth App at https://github.com/settings/developers
# and enable Device Flow in the app settings
GITHUB_CLIENT_ID = "Ov23liErbWGLzAKTlLFW"  # Replace with your client ID

# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"


class AccountSetupCancelled(Exception):
    """Raised when user cancels account setup."""
    pass


def _exit_app():
    """Safely exit the application from within wxPython context."""
    raise AccountSetupCancelled()


class GitHubAccount:
    """GitHub account wrapper with authentication and API methods."""

    def __init__(self, app, index):
        self.app = app
        self.index = index
        self.ready = False
        self.me = None
        self._session = requests.Session()

        # Load config
        if config.is_portable_mode():
            self.prefs = config.Config(name="account" + str(index), autosave=True)
            self.confpath = self.prefs._user_config_home + "/account" + str(index)
        else:
            self.prefs = config.Config(name="FastGH/account" + str(index), autosave=True)
            self.confpath = self.prefs._user_config_home + "/FastGH/account" + str(index)

        # Load or get access token
        self.prefs.access_token = self.prefs.get("access_token", "")

        if not self.prefs.access_token:
            self._authenticate()

        # Set up authenticated session
        self._session.headers.update({
            "Authorization": f"Bearer {self.prefs.access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })

        # Verify credentials and get user info
        self._verify_credentials()

        self.ready = True

    def _authenticate(self):
        """Perform OAuth Device Flow authentication."""
        if GITHUB_CLIENT_ID == "YOUR_CLIENT_ID_HERE":
            wx.MessageBox(
                "GitHub OAuth App not configured!\n\n"
                "Please edit github_api.py and set GITHUB_CLIENT_ID to your OAuth App's client ID.\n\n"
                "Create an OAuth App at:\nhttps://github.com/settings/developers",
                "Configuration Required",
                wx.OK | wx.ICON_ERROR
            )
            _exit_app()

        # Step 1: Request device code
        response = requests.post(
            "https://github.com/login/device/code",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "scope": "repo user notifications"
            },
            headers={"Accept": "application/json"}
        )

        if response.status_code != 200:
            wx.MessageBox(
                f"Failed to get device code: {response.text}",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
            _exit_app()

        data = response.json()
        device_code = data["device_code"]
        user_code = data["user_code"]
        verification_uri = data["verification_uri"]
        expires_in = data.get("expires_in", 900)
        interval = data.get("interval", 5)

        # Copy code to clipboard
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(user_code))
            wx.TheClipboard.Close()
            code_copied = True
        else:
            code_copied = False

        # Step 2: Show user the code and open browser
        copied_msg = " (copied to clipboard)" if code_copied else ""
        result = wx.MessageBox(
            f"To authorize FastGH:\n\n"
            f"1. Go to: {verification_uri}\n"
            f"2. Paste the code: {user_code}{copied_msg}\n\n"
            f"Click OK to open the browser, then authorize the app.\n"
            f"Click Cancel to abort.",
            "GitHub Authorization",
            wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        )

        if result == wx.CANCEL:
            _exit_app()

        # Open browser
        import webbrowser
        webbrowser.open(verification_uri)

        # Step 3: Poll for access token
        progress = wx.ProgressDialog(
            "Waiting for Authorization",
            f"Please enter code {user_code} at {verification_uri}\n\nWaiting for you to authorize...",
            maximum=expires_in,
            style=wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME
        )

        start_time = time.time()
        access_token = None

        while time.time() - start_time < expires_in:
            elapsed = int(time.time() - start_time)
            cont, _ = progress.Update(elapsed, f"Waiting for authorization... ({elapsed}s)")

            if not cont:
                progress.Destroy()
                _exit_app()

            # Poll for token
            response = requests.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                headers={"Accept": "application/json"}
            )

            if response.status_code == 200:
                token_data = response.json()

                if "access_token" in token_data:
                    access_token = token_data["access_token"]
                    break
                elif token_data.get("error") == "authorization_pending":
                    # Still waiting, continue polling
                    pass
                elif token_data.get("error") == "slow_down":
                    interval += 5
                elif token_data.get("error") == "expired_token":
                    progress.Destroy()
                    wx.MessageBox(
                        "Authorization expired. Please try again.",
                        "Authentication Error",
                        wx.OK | wx.ICON_ERROR
                    )
                    _exit_app()
                elif token_data.get("error") == "access_denied":
                    progress.Destroy()
                    wx.MessageBox(
                        "Authorization denied.",
                        "Authentication Error",
                        wx.OK | wx.ICON_ERROR
                    )
                    _exit_app()

            time.sleep(interval)

        progress.Destroy()

        if not access_token:
            wx.MessageBox(
                "Authorization timed out. Please try again.",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
            _exit_app()

        # Save the token
        self.prefs.access_token = access_token

    def _verify_credentials(self):
        """Verify credentials and get user info."""
        response = self._session.get(f"{GITHUB_API_URL}/user")

        if response.status_code == 401:
            # Token invalid, clear and re-authenticate
            self.prefs.access_token = ""
            self._authenticate()
            self._session.headers["Authorization"] = f"Bearer {self.prefs.access_token}"
            response = self._session.get(f"{GITHUB_API_URL}/user")

        if response.status_code != 200:
            wx.MessageBox(
                f"Failed to verify credentials: {response.text}",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
            _exit_app()

        self.me = response.json()

    def get_repos(self, sort="updated", per_page=100) -> list[Repository]:
        """Get user's repositories, sorted by last updated."""
        repos = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/user/repos",
                params={
                    "sort": sort,
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member"
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for repo_data in data:
                repos.append(Repository.from_github_api(repo_data))

            if len(data) < per_page:
                break

            page += 1

        return repos

    def get_starred(self, per_page=100) -> list[Repository]:
        """Get user's starred repositories, sorted by last updated."""
        repos = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/user/starred",
                params={
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for repo_data in data:
                repos.append(Repository.from_github_api(repo_data))

            if len(data) < per_page:
                break

            page += 1

        # Sort by updated_at descending (use epoch for None values)
        epoch = datetime(1970, 1, 1)
        repos.sort(key=lambda r: r.updated_at.replace(tzinfo=None) if r.updated_at else epoch, reverse=True)
        return repos

    def get_watched(self, per_page=100) -> list[Repository]:
        """Get user's watched/subscribed repositories, sorted by last updated."""
        repos = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/user/subscriptions",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for repo_data in data:
                repos.append(Repository.from_github_api(repo_data))

            if len(data) < per_page:
                break

            page += 1

        # Sort by updated_at descending (use epoch for None values)
        epoch = datetime(1970, 1, 1)
        repos.sort(key=lambda r: r.updated_at.replace(tzinfo=None) if r.updated_at else epoch, reverse=True)
        return repos

    def get_repo(self, owner: str, repo: str) -> Repository | None:
        """Get a single repository by owner and name."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}"
        )

        if response.status_code != 200:
            return None

        return Repository.from_github_api(response.json())

    @property
    def username(self) -> str:
        """Get the username of the authenticated user."""
        return self.me.get("login", "") if self.me else ""

    @property
    def display_name(self) -> str:
        """Get the display name of the authenticated user."""
        if self.me:
            return self.me.get("name") or self.me.get("login", "")
        return ""

    # ============ Issues API ============

    def get_issues(self, owner: str, repo: str, state: str = "open", per_page: int = 100) -> list[Issue]:
        """Get issues for a repository."""
        issues = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues",
                params={
                    "state": state,
                    "per_page": per_page,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc"
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                # Skip pull requests (they appear in issues endpoint too)
                if 'pull_request' not in item:
                    issues.append(Issue.from_github_api(item))

            if len(data) < per_page:
                break

            page += 1

        return issues

    def get_issue(self, owner: str, repo: str, number: int) -> Issue | None:
        """Get a single issue by number."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{number}"
        )

        if response.status_code != 200:
            return None

        return Issue.from_github_api(response.json())

    def create_issue(self, owner: str, repo: str, title: str, body: str = "", labels: list[str] = None) -> Issue | None:
        """Create a new issue."""
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels

        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues",
            json=data
        )

        if response.status_code != 201:
            return None

        return Issue.from_github_api(response.json())

    def update_issue(self, owner: str, repo: str, number: int, title: str = None, body: str = None, state: str = None) -> Issue | None:
        """Update an issue."""
        data = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state

        response = self._session.patch(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{number}",
            json=data
        )

        if response.status_code != 200:
            return None

        return Issue.from_github_api(response.json())

    def close_issue(self, owner: str, repo: str, number: int) -> bool:
        """Close an issue."""
        result = self.update_issue(owner, repo, number, state="closed")
        return result is not None

    def reopen_issue(self, owner: str, repo: str, number: int) -> bool:
        """Reopen an issue."""
        result = self.update_issue(owner, repo, number, state="open")
        return result is not None

    def get_issue_comments(self, owner: str, repo: str, number: int, per_page: int = 100) -> list[Comment]:
        """Get comments on an issue."""
        comments = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{number}/comments",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                comments.append(Comment.from_github_api(item))

            if len(data) < per_page:
                break

            page += 1

        return comments

    def create_issue_comment(self, owner: str, repo: str, number: int, body: str) -> Comment | None:
        """Create a comment on an issue."""
        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/{number}/comments",
            json={"body": body}
        )

        if response.status_code != 201:
            return None

        return Comment.from_github_api(response.json())

    def delete_issue_comment(self, owner: str, repo: str, comment_id: int) -> bool:
        """Delete a comment."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/issues/comments/{comment_id}"
        )
        return response.status_code == 204

    # ============ Pull Requests API ============

    def get_pull_requests(self, owner: str, repo: str, state: str = "open", per_page: int = 100) -> list[PullRequest]:
        """Get pull requests for a repository."""
        prs = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls",
                params={
                    "state": state,
                    "per_page": per_page,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc"
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                prs.append(PullRequest.from_github_api(item))

            if len(data) < per_page:
                break

            page += 1

        return prs

    def get_pull_request(self, owner: str, repo: str, number: int) -> PullRequest | None:
        """Get a single pull request by number."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{number}"
        )

        if response.status_code != 200:
            return None

        return PullRequest.from_github_api(response.json())

    def create_pull_request(self, owner: str, repo: str, title: str, head: str, base: str, body: str = "", draft: bool = False) -> PullRequest | None:
        """Create a new pull request."""
        data = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": draft
        }

        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls",
            json=data
        )

        if response.status_code != 201:
            return None

        return PullRequest.from_github_api(response.json())

    def update_pull_request(self, owner: str, repo: str, number: int, title: str = None, body: str = None, state: str = None) -> PullRequest | None:
        """Update a pull request."""
        data = {}
        if title is not None:
            data["title"] = title
        if body is not None:
            data["body"] = body
        if state is not None:
            data["state"] = state

        response = self._session.patch(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{number}",
            json=data
        )

        if response.status_code != 200:
            return None

        return PullRequest.from_github_api(response.json())

    def merge_pull_request(self, owner: str, repo: str, number: int, commit_title: str = None, commit_message: str = None, merge_method: str = "merge") -> bool:
        """Merge a pull request.

        merge_method can be: 'merge', 'squash', or 'rebase'
        """
        data = {"merge_method": merge_method}
        if commit_title:
            data["commit_title"] = commit_title
        if commit_message:
            data["commit_message"] = commit_message

        response = self._session.put(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{number}/merge",
            json=data
        )

        return response.status_code == 200

    def close_pull_request(self, owner: str, repo: str, number: int) -> bool:
        """Close a pull request."""
        result = self.update_pull_request(owner, repo, number, state="closed")
        return result is not None

    def get_pr_comments(self, owner: str, repo: str, number: int, per_page: int = 100) -> list[Comment]:
        """Get comments on a pull request (issue comments, not review comments)."""
        return self.get_issue_comments(owner, repo, number, per_page)

    def create_pr_comment(self, owner: str, repo: str, number: int, body: str) -> Comment | None:
        """Create a comment on a pull request."""
        return self.create_issue_comment(owner, repo, number, body)

    # ============ Repository Permissions ============

    def get_repo_permission(self, owner: str, repo: str) -> str | None:
        """Get current user's permission level for a repository.

        Returns: 'admin', 'write', 'read', or None if no access
        """
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}"
        )

        if response.status_code != 200:
            return None

        data = response.json()
        permissions = data.get('permissions', {})

        if permissions.get('admin'):
            return 'admin'
        elif permissions.get('push'):
            return 'write'
        elif permissions.get('pull'):
            return 'read'
        return None

    def can_merge(self, owner: str, repo: str) -> bool:
        """Check if current user can merge PRs in this repository."""
        permission = self.get_repo_permission(owner, repo)
        return permission in ('admin', 'write')

    # ============ Commits API ============

    def get_commits(self, owner: str, repo: str, sha: str = None, per_page: int = 100, max_commits: int = 0) -> list[Commit]:
        """Get commits for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: SHA or branch to start listing commits from (default: default branch)
            per_page: Number of commits per page
            max_commits: Maximum number of commits to return (0 = all)
        """
        commits = []
        page = 1

        # Optimize per_page if max_commits is set and smaller
        if max_commits > 0 and max_commits < per_page:
            per_page = max_commits

        params = {
            "per_page": per_page,
            "page": page
        }
        if sha:
            params["sha"] = sha

        while True:
            params["page"] = page
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits",
                params=params
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                commits.append(Commit.from_github_api(item))
                # Check if we've reached the limit
                if max_commits > 0 and len(commits) >= max_commits:
                    return commits

            if len(data) < per_page:
                break

            page += 1

        return commits

    def get_commit(self, owner: str, repo: str, sha: str) -> Commit | None:
        """Get a single commit by SHA."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{sha}"
        )

        if response.status_code != 200:
            return None

        return Commit.from_github_api(response.json())

    def get_branches(self, owner: str, repo: str, per_page: int = 100) -> list[dict]:
        """Get branches for a repository, sorted by last commit date (most recent first)."""
        branches = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            branches.extend(data)

            if len(data) < per_page:
                break

            page += 1

        # Fetch commit dates for sorting
        for branch in branches:
            commit_sha = branch.get('commit', {}).get('sha')
            if commit_sha:
                # Get commit info to get the date
                response = self._session.get(
                    f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{commit_sha}"
                )
                if response.status_code == 200:
                    commit_data = response.json()
                    commit_date = commit_data.get('commit', {}).get('committer', {}).get('date')
                    branch['last_commit_date'] = commit_date
                else:
                    branch['last_commit_date'] = None
            else:
                branch['last_commit_date'] = None

        # Sort by last commit date (most recent first), None values at end
        branches.sort(
            key=lambda b: b.get('last_commit_date') or '',
            reverse=True
        )

        return branches

    # ============ Search API ============

    def search_repos(self, query: str, sort: str = "best-match", per_page: int = 30) -> list[Repository]:
        """Search for repositories.

        Args:
            query: Search query (can include qualifiers like 'language:python')
            sort: Sort by 'stars', 'forks', 'help-wanted-issues', 'updated', or 'best-match'
            per_page: Results per page (max 100)
        """
        repos = []

        params = {
            "q": query,
            "per_page": per_page
        }
        if sort and sort != "best-match":
            params["sort"] = sort

        response = self._session.get(
            f"{GITHUB_API_URL}/search/repositories",
            params=params
        )

        if response.status_code != 200:
            return repos

        data = response.json()
        for item in data.get('items', []):
            repos.append(Repository.from_github_api(item))

        return repos

    def search_users(self, query: str, sort: str = "best-match", per_page: int = 30) -> list[UserProfile]:
        """Search for users.

        Args:
            query: Search query (can include qualifiers like 'location:london')
            sort: Sort by 'followers', 'repositories', 'joined', or 'best-match'
            per_page: Results per page (max 100)
        """
        users = []

        params = {
            "q": query,
            "per_page": per_page
        }
        if sort and sort != "best-match":
            params["sort"] = sort

        response = self._session.get(
            f"{GITHUB_API_URL}/search/users",
            params=params
        )

        if response.status_code != 200:
            return users

        data = response.json()
        # Search results don't include full user info, need to fetch each
        for item in data.get('items', []):
            # Create a basic profile from search results
            users.append(UserProfile(
                id=item.get('id', 0),
                login=item.get('login', ''),
                name=None,
                avatar_url=item.get('avatar_url', ''),
                html_url=item.get('html_url', ''),
                bio=None,
                company=None,
                location=None,
                email=None,
                blog=None,
                twitter_username=None,
                public_repos=0,
                public_gists=0,
                followers=0,
                following=0,
                created_at=None,
                updated_at=None,
                type=item.get('type', 'User')
            ))

        return users

    # ============ User API ============

    def get_user(self, username: str) -> UserProfile | None:
        """Get a user's profile."""
        response = self._session.get(
            f"{GITHUB_API_URL}/users/{username}"
        )

        if response.status_code != 200:
            return None

        return UserProfile.from_github_api(response.json())

    def get_user_repos(self, username: str, sort: str = "updated", per_page: int = 100) -> list[Repository]:
        """Get a user's public repositories."""
        repos = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/users/{username}/repos",
                params={
                    "sort": sort,
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for repo_data in data:
                repos.append(Repository.from_github_api(repo_data))

            if len(data) < per_page:
                break

            page += 1

        return repos

    # ============ Following API ============

    def get_following(self, per_page: int = 100) -> list[UserProfile]:
        """Get users the authenticated user is following."""
        users = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/user/following",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                users.append(UserProfile(
                    id=item.get('id', 0),
                    login=item.get('login', ''),
                    name=None,
                    avatar_url=item.get('avatar_url', ''),
                    html_url=item.get('html_url', ''),
                    bio=None,
                    company=None,
                    location=None,
                    email=None,
                    blog=None,
                    twitter_username=None,
                    public_repos=0,
                    public_gists=0,
                    followers=0,
                    following=0,
                    created_at=None,
                    updated_at=None,
                    type=item.get('type', 'User')
                ))

            if len(data) < per_page:
                break

            page += 1

        return users

    def is_following(self, username: str) -> bool:
        """Check if authenticated user is following a user."""
        response = self._session.get(
            f"{GITHUB_API_URL}/user/following/{username}"
        )
        return response.status_code == 204

    def follow_user(self, username: str) -> bool:
        """Follow a user."""
        response = self._session.put(
            f"{GITHUB_API_URL}/user/following/{username}"
        )
        return response.status_code == 204

    def unfollow_user(self, username: str) -> bool:
        """Unfollow a user."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/user/following/{username}"
        )
        return response.status_code == 204

    # ============ Starring API ============

    def is_starred(self, owner: str, repo: str) -> bool:
        """Check if authenticated user has starred a repository."""
        response = self._session.get(
            f"{GITHUB_API_URL}/user/starred/{owner}/{repo}"
        )
        return response.status_code == 204

    def star_repo(self, owner: str, repo: str) -> bool:
        """Star a repository."""
        response = self._session.put(
            f"{GITHUB_API_URL}/user/starred/{owner}/{repo}"
        )
        return response.status_code == 204

    def unstar_repo(self, owner: str, repo: str) -> bool:
        """Unstar a repository."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/user/starred/{owner}/{repo}"
        )
        return response.status_code == 204

    # ============ Watching API ============

    def is_watching(self, owner: str, repo: str) -> bool:
        """Check if authenticated user is watching a repository."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/subscription"
        )
        return response.status_code == 200

    def watch_repo(self, owner: str, repo: str) -> bool:
        """Watch a repository (subscribe to notifications)."""
        response = self._session.put(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/subscription",
            json={"subscribed": True}
        )
        return response.status_code == 200

    def unwatch_repo(self, owner: str, repo: str) -> bool:
        """Unwatch a repository (unsubscribe from notifications)."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/subscription"
        )
        return response.status_code == 204

    # ============ Actions API ============

    def get_workflows(self, owner: str, repo: str, per_page: int = 100) -> list[Workflow]:
        """Get workflows for a repository."""
        workflows = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/workflows",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get('workflows', [])
            if not items:
                break

            for item in items:
                workflows.append(Workflow.from_github_api(item))

            if len(items) < per_page:
                break

            page += 1

        return workflows

    def get_workflow_runs(self, owner: str, repo: str, workflow_id: int = None,
                          branch: str = None, status: str = None, per_page: int = 30) -> list[WorkflowRun]:
        """Get workflow runs for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            workflow_id: Filter by workflow ID (optional)
            branch: Filter by branch (optional)
            status: Filter by status - 'queued', 'in_progress', 'completed' (optional)
            per_page: Results per page
        """
        runs = []

        params = {"per_page": per_page}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status

        if workflow_id:
            url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
        else:
            url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs"

        response = self._session.get(url, params=params)

        if response.status_code != 200:
            return runs

        data = response.json()
        for item in data.get('workflow_runs', []):
            runs.append(WorkflowRun.from_github_api(item))

        return runs

    def get_workflow_run(self, owner: str, repo: str, run_id: int) -> WorkflowRun | None:
        """Get a single workflow run."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}"
        )

        if response.status_code != 200:
            return None

        return WorkflowRun.from_github_api(response.json())

    def get_workflow_run_jobs(self, owner: str, repo: str, run_id: int, per_page: int = 100) -> list[WorkflowJob]:
        """Get jobs for a workflow run."""
        jobs = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get('jobs', [])
            if not items:
                break

            for item in items:
                jobs.append(WorkflowJob.from_github_api(item))

            if len(items) < per_page:
                break

            page += 1

        return jobs

    def rerun_workflow(self, owner: str, repo: str, run_id: int) -> bool:
        """Re-run a workflow."""
        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/rerun"
        )
        return response.status_code == 201

    def rerun_failed_jobs(self, owner: str, repo: str, run_id: int) -> bool:
        """Re-run only failed jobs in a workflow run."""
        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
        )
        return response.status_code == 201

    def cancel_workflow_run(self, owner: str, repo: str, run_id: int) -> bool:
        """Cancel a workflow run."""
        response = self._session.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/cancel"
        )
        return response.status_code == 202

    def get_workflow_run_logs_url(self, owner: str, repo: str, run_id: int) -> str | None:
        """Get the download URL for workflow run logs.

        Returns a URL that can be used to download a zip file of the logs.
        """
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/logs",
            allow_redirects=False
        )

        if response.status_code == 302:
            return response.headers.get("Location")
        return None

    def get_job_logs(self, owner: str, repo: str, job_id: int) -> str | None:
        """Get the logs for a specific job as plain text."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
            headers={"Accept": "application/vnd.github.v3+json"}
        )

        if response.status_code == 200:
            return response.text
        elif response.status_code == 302:
            # Follow redirect to get actual logs
            log_url = response.headers.get("Location")
            if log_url:
                log_response = self._session.get(log_url)
                if log_response.status_code == 200:
                    return log_response.text
        return None

    # ============ Releases API ============

    def get_releases(self, owner: str, repo: str, per_page: int = 30) -> list[Release]:
        """Get releases for a repository."""
        releases = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                releases.append(Release.from_github_api(item))

            if len(data) < per_page:
                break

            page += 1

        return releases

    def get_release(self, owner: str, repo: str, release_id: int) -> Release | None:
        """Get a single release by ID."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases/{release_id}"
        )

        if response.status_code != 200:
            return None

        return Release.from_github_api(response.json())

    def get_latest_release(self, owner: str, repo: str) -> Release | None:
        """Get the latest release for a repository."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases/latest"
        )

        if response.status_code != 200:
            return None

        return Release.from_github_api(response.json())

    def get_release_by_tag(self, owner: str, repo: str, tag: str) -> Release | None:
        """Get a release by tag name."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases/tags/{tag}"
        )

        if response.status_code != 200:
            return None

        return Release.from_github_api(response.json())

    def download_asset(self, owner: str, repo: str, asset_id: int, dest_path: str,
                       progress_callback=None) -> bool:
        """Download a release asset to the specified path.

        Args:
            owner: Repository owner
            repo: Repository name
            asset_id: Asset ID to download
            dest_path: Full path where to save the file
            progress_callback: Optional callback(downloaded_bytes, total_bytes)

        Returns:
            True if download succeeded, False otherwise
        """
        # Get asset info first to get the download URL
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases/assets/{asset_id}",
            headers={"Accept": "application/octet-stream"},
            stream=True,
            allow_redirects=True
        )

        if response.status_code != 200:
            return False

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        try:
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)
            return True
        except Exception:
            return False

    # ============ Notifications API ============

    def get_notifications(self, all: bool = False, participating: bool = False,
                          per_page: int = 50) -> list[Notification]:
        """Get notifications for the authenticated user.

        Args:
            all: Show all notifications (default shows only unread)
            participating: Only show where you're directly involved
            per_page: Results per page
        """
        notifications = []
        page = 1

        while True:
            params = {
                "per_page": per_page,
                "page": page
            }
            if all:
                params["all"] = "true"
            if participating:
                params["participating"] = "true"

            response = self._session.get(
                f"{GITHUB_API_URL}/notifications",
                params=params
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                notifications.append(Notification.from_api(item))

            if len(data) < per_page:
                break

            page += 1

        return notifications

    def get_repo_notifications(self, owner: str, repo: str, all: bool = False,
                               participating: bool = False, per_page: int = 50) -> list[Notification]:
        """Get notifications for a specific repository."""
        notifications = []
        page = 1

        while True:
            params = {
                "per_page": per_page,
                "page": page
            }
            if all:
                params["all"] = "true"
            if participating:
                params["participating"] = "true"

            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/notifications",
                params=params
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                notifications.append(Notification.from_api(item))

            if len(data) < per_page:
                break

            page += 1

        return notifications

    def mark_notifications_read(self, last_read_at: str = None) -> bool:
        """Mark all notifications as read.

        Args:
            last_read_at: ISO 8601 timestamp. Only mark notifications updated before this time.
                         If not provided, all notifications are marked as read.
        """
        data = {}
        if last_read_at:
            data["last_read_at"] = last_read_at

        response = self._session.put(
            f"{GITHUB_API_URL}/notifications",
            json=data
        )
        return response.status_code in (202, 205)

    def mark_repo_notifications_read(self, owner: str, repo: str, last_read_at: str = None) -> bool:
        """Mark all notifications in a repository as read."""
        data = {}
        if last_read_at:
            data["last_read_at"] = last_read_at

        response = self._session.put(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/notifications",
            json=data
        )
        return response.status_code in (202, 205)

    def mark_thread_read(self, thread_id: str) -> bool:
        """Mark a notification thread as read."""
        response = self._session.patch(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}"
        )
        return response.status_code in (200, 205)

    def mark_thread_done(self, thread_id: str) -> bool:
        """Mark a notification thread as done (removes from inbox)."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}"
        )
        return response.status_code == 204

    def get_thread_subscription(self, thread_id: str) -> dict | None:
        """Get subscription status for a thread."""
        response = self._session.get(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}/subscription"
        )
        if response.status_code == 200:
            return response.json()
        return None

    def subscribe_to_thread(self, thread_id: str) -> bool:
        """Subscribe to a notification thread."""
        response = self._session.put(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}/subscription",
            json={"subscribed": True}
        )
        return response.status_code == 200

    def unsubscribe_from_thread(self, thread_id: str) -> bool:
        """Unsubscribe from a notification thread."""
        response = self._session.delete(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}/subscription"
        )
        return response.status_code == 204

    def mute_thread(self, thread_id: str) -> bool:
        """Mute a notification thread (ignore future notifications)."""
        response = self._session.put(
            f"{GITHUB_API_URL}/notifications/threads/{thread_id}/subscription",
            json={"ignored": True}
        )
        return response.status_code == 200

    # ============ Events/Activity Feed API ============

    def get_received_events(self, per_page: int = 100, max_pages: int = 3) -> list[Event]:
        """Get events received by the authenticated user.

        This is the activity feed showing actions by users you follow
        and activity on repos you watch.

        Note: GitHub limits this to 300 events max (10 pages of 30, or 3 pages of 100).
        """
        events = []
        page = 1

        while page <= max_pages:
            response = self._session.get(
                f"{GITHUB_API_URL}/users/{self.username}/received_events",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            for item in data:
                events.append(Event.from_api(item))

            if len(data) < per_page:
                break

            page += 1

        return events

    def get_user_events(self, username: str, per_page: int = 30) -> list[Event]:
        """Get events performed by a specific user."""
        events = []

        response = self._session.get(
            f"{GITHUB_API_URL}/users/{username}/events",
            params={"per_page": per_page}
        )

        if response.status_code != 200:
            return events

        data = response.json()
        for item in data:
            events.append(Event.from_api(item))

        return events

    def get_repo_events(self, owner: str, repo: str, per_page: int = 30) -> list[Event]:
        """Get events for a specific repository."""
        events = []

        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/events",
            params={"per_page": per_page}
        )

        if response.status_code != 200:
            return events

        data = response.json()
        for item in data:
            events.append(Event.from_api(item))

        return events

    def get_org_events(self, org: str, per_page: int = 30) -> list[Event]:
        """Get public events for an organization."""
        events = []

        response = self._session.get(
            f"{GITHUB_API_URL}/orgs/{org}/events",
            params={"per_page": per_page}
        )

        if response.status_code != 200:
            return events

        data = response.json()
        for item in data:
            events.append(Event.from_api(item))

        return events
