"""GitHub API wrapper with OAuth Device Flow authentication."""

import os
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
from models.workflow import Workflow, WorkflowRun, WorkflowJob, Artifact
from models.release import Release, ReleaseAsset
from models.notification import Notification
from models.event import Event
from models.content import ContentItem
from models.discussion import Discussion, DiscussionComment

# GitHub OAuth App Client ID
# You need to create an OAuth App at https://github.com/settings/developers
# and enable Device Flow in the app settings
GITHUB_CLIENT_ID = "Ov23liErbWGLzAKTlLFW"  # Replace with your client ID

# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"

# Number of commits fetched per API call when paging through a repo's history
COMMITS_PER_PAGE = 50


class AccountSetupCancelled(Exception):
    """Raised when user cancels account setup."""
    pass


def _exit_app():
    """Safely exit the application from within wxPython context."""
    raise AccountSetupCancelled()


class _AuthWaitDialog(wx.Dialog):
    """Custom dialog for waiting during OAuth authorization."""

    def __init__(self, parent, user_code, verification_uri, expires_in):
        super().__init__(parent, title="Waiting for Authorization", size=(450, 200))
        self.user_code = user_code
        self.verification_uri = verification_uri
        self.cancelled = False
        self.error = None

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Status message
        self.status_label = wx.StaticText(
            panel,
            label=f"Please enter the code on GitHub and authorize the app.\n\n"
                  f"Code: {user_code}\n"
                  f"URL: {verification_uri}"
        )
        sizer.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 15)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.copy_btn = wx.Button(panel, label="&Copy Code")
        self.copy_btn.Bind(wx.EVT_BUTTON, self.on_copy_code)
        btn_sizer.Add(self.copy_btn, 0, wx.RIGHT, 10)

        self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancel")
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        btn_sizer.Add(self.cancel_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)
        self.Centre()

    def on_copy_code(self, event):
        """Copy the code to clipboard."""
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self.user_code))
            wx.TheClipboard.Close()
            wx.MessageBox(
                f"Code copied: {self.user_code}",
                "Copied",
                wx.OK | wx.ICON_INFORMATION
            )

    def on_cancel(self, event):
        """Handle cancel button."""
        self.cancelled = True
        self.EndModal(wx.ID_CANCEL)

    def on_success(self):
        """Called when authorization succeeds."""
        self.EndModal(wx.ID_OK)

    def on_error(self, error_type):
        """Called when authorization fails."""
        self.error = error_type
        if error_type == "expired_token":
            wx.MessageBox(
                "Authorization expired. Please try again.",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
        elif error_type == "access_denied":
            wx.MessageBox(
                "Authorization denied.",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
        else:
            wx.MessageBox(
                "Authorization timed out. Please try again.",
                "Authentication Error",
                wx.OK | wx.ICON_ERROR
            )
        self.EndModal(wx.ID_CANCEL)


class GitHubAccount:
    """GitHub account wrapper with authentication and API methods."""

    def __init__(self, app, index):
        self.app = app
        self.index = index
        self.ready = False
        self.me = None
        self._last_error = ""
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

        # Step 2: Ask user if ready, then copy code
        result = wx.MessageBox(
            f"To authorize FastGH, you'll need to enter a code on GitHub.\n\n"
            f"Your code is: {user_code}\n\n"
            f"Click OK to copy the code to clipboard and open the browser.\n"
            f"Click Cancel to abort.",
            "GitHub Authorization",
            wx.OK | wx.CANCEL | wx.ICON_INFORMATION
        )

        if result == wx.CANCEL:
            _exit_app()

        # Copy code to clipboard
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(user_code))
            wx.TheClipboard.Close()
            wx.MessageBox(
                f"Code copied to clipboard!\n\n"
                f"Paste this code on the GitHub page: {user_code}",
                "Code Copied",
                wx.OK | wx.ICON_INFORMATION
            )

        # Open browser
        import webbrowser
        webbrowser.open(verification_uri)

        # Step 3: Poll for access token with custom dialog
        auth_dialog = _AuthWaitDialog(None, user_code, verification_uri, expires_in)
        start_time = time.time()
        access_token = None

        # Start polling in background
        def poll_for_token():
            nonlocal access_token, interval
            while time.time() - start_time < expires_in:
                if auth_dialog.cancelled:
                    break

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
                        wx.CallAfter(auth_dialog.on_success)
                        return
                    elif token_data.get("error") == "authorization_pending":
                        pass
                    elif token_data.get("error") == "slow_down":
                        interval += 5
                    elif token_data.get("error") in ("expired_token", "access_denied"):
                        wx.CallAfter(auth_dialog.on_error, token_data.get("error"))
                        return

                time.sleep(interval)

            # Timed out
            if not access_token and not auth_dialog.cancelled:
                wx.CallAfter(auth_dialog.on_error, "timeout")

        poll_thread = threading.Thread(target=poll_for_token, daemon=True)
        poll_thread.start()

        result = auth_dialog.ShowModal()
        auth_dialog.Destroy()

        if result == wx.ID_CANCEL:
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

    def get_repos(self, sort="pushed", per_page=100) -> list[Repository]:
        """Get user's repositories, sorted by last push time."""
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
        """Get user's starred repositories, sorted by last push time."""
        repos = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/user/starred",
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

        # Sort by pushed_at descending (use epoch for None values)
        epoch = datetime(1970, 1, 1)
        repos.sort(key=lambda r: r.pushed_at.replace(tzinfo=None) if r.pushed_at else epoch, reverse=True)
        return repos

    def get_watched(self, per_page=100) -> list[Repository]:
        """Get user's watched/subscribed repositories, sorted by last push time."""
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

        # Sort by pushed_at descending (use epoch for None values)
        epoch = datetime(1970, 1, 1)
        repos.sort(key=lambda r: r.pushed_at.replace(tzinfo=None) if r.pushed_at else epoch, reverse=True)
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

    def get_last_error(self) -> str:
        """Get the last API error message, if any."""
        return self._last_error

    def _set_last_error(self, message: str = ""):
        """Store a concise API error message for UI reporting."""
        self._last_error = (message or "").strip()

    def _graphql(self, query: str, variables: dict = None) -> dict | None:
        """Execute a GitHub GraphQL query/mutation."""
        self._set_last_error("")
        try:
            response = self._session.post(
                f"{GITHUB_API_URL}/graphql",
                json={
                    "query": query,
                    "variables": variables or {}
                }
            )
        except Exception as e:
            self._set_last_error(f"GraphQL request failed: {e}")
            return None

        if response.status_code != 200:
            body = ""
            try:
                body = response.text.strip()
            except Exception:
                body = ""
            if body:
                self._set_last_error(f"GraphQL HTTP {response.status_code}: {body[:200]}")
            else:
                self._set_last_error(f"GraphQL HTTP {response.status_code}")
            return None

        try:
            payload = response.json()
        except Exception as e:
            self._set_last_error(f"Invalid GraphQL response: {e}")
            return None

        errors = payload.get("errors") or []
        if errors:
            messages = []
            for err in errors[:3]:
                msg = err.get("message")
                if msg:
                    messages.append(msg)
            if messages:
                self._set_last_error("GraphQL error: " + " | ".join(messages))
            else:
                self._set_last_error("GraphQL returned errors.")
            return None

        data = payload.get("data")
        if data is None:
            self._set_last_error("GraphQL returned no data.")
            return None

        return data

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

    def get_pr_review_comments(self, owner: str, repo: str, number: int, per_page: int = 100) -> list[Comment]:
        """Get review comments on a pull request."""
        comments = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{number}/comments",
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
                comments.append(Comment.from_github_api(item, kind="review"))

            if len(data) < per_page:
                break

            page += 1

        return comments

    def get_pr_comments(self, owner: str, repo: str, number: int, per_page: int = 100) -> list[Comment]:
        """Get all comments on a pull request, including review comments."""
        issue_comments = self.get_issue_comments(owner, repo, number, per_page)
        review_comments = self.get_pr_review_comments(owner, repo, number, per_page)
        comments = issue_comments + review_comments

        # Keep stable ordering by creation time so the dialog mirrors issue behavior.
        comments.sort(key=lambda c: c.created_at.timestamp() if c.created_at else 0)

        return comments

    def create_pr_comment(self, owner: str, repo: str, number: int, body: str) -> Comment | None:
        """Create a comment on a pull request."""
        return self.create_issue_comment(owner, repo, number, body)

    # ============ Discussions API (GraphQL) ============

    def get_discussion(self, owner: str, repo: str, number: int, comments_first: int = 50) -> Discussion | None:
        """Get a discussion and its first page of comments."""
        query = """
        query GetDiscussion($owner: String!, $repo: String!, $number: Int!, $commentsFirst: Int!) {
          repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
              id
              number
              title
              body
              url
              isAnswered
              createdAt
              updatedAt
              author {
                login
                avatarUrl
              }
              category {
                name
              }
              comments(first: $commentsFirst) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  databaseId
                  body
                  url
                  createdAt
                  updatedAt
                  author {
                    login
                    avatarUrl
                  }
                  replies(first: 50) {
                    nodes {
                      id
                      databaseId
                      body
                      url
                      createdAt
                      updatedAt
                      author {
                        login
                        avatarUrl
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        data = self._graphql(
            query=query,
            variables={
                "owner": owner,
                "repo": repo,
                "number": number,
                "commentsFirst": comments_first
            }
        )
        if not data:
            return None

        repo_data = data.get("repository") or {}
        discussion_data = repo_data.get("discussion")
        if not discussion_data:
            self._set_last_error("Discussion not found or access denied.")
            return None

        self._set_last_error("")
        return Discussion.from_graphql(discussion_data)

    def get_discussion_comments(self, owner: str, repo: str, number: int,
                                first: int = 50, after: str = None) -> tuple[list[DiscussionComment], bool, str | None]:
        """Get one page of comments for a discussion."""
        query = """
        query GetDiscussionComments($owner: String!, $repo: String!, $number: Int!, $first: Int!, $after: String) {
          repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
              comments(first: $first, after: $after) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  databaseId
                  body
                  url
                  createdAt
                  updatedAt
                  author {
                    login
                    avatarUrl
                  }
                  replies(first: 50) {
                    nodes {
                      id
                      databaseId
                      body
                      url
                      createdAt
                      updatedAt
                      author {
                        login
                        avatarUrl
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        data = self._graphql(
            query=query,
            variables={
                "owner": owner,
                "repo": repo,
                "number": number,
                "first": first,
                "after": after
            }
        )
        if not data:
            return [], False, None

        repo_data = data.get("repository") or {}
        discussion_data = repo_data.get("discussion") or {}
        comments_connection = discussion_data.get("comments") or {}
        nodes = comments_connection.get("nodes", []) or []
        page_info = comments_connection.get("pageInfo", {}) or {}

        comments = Discussion._flatten_comment_nodes(nodes)
        has_next_page = page_info.get("hasNextPage", False)
        end_cursor = page_info.get("endCursor")
        self._set_last_error("")
        return comments, has_next_page, end_cursor

    def create_discussion_comment(self, discussion_id: str, body: str) -> DiscussionComment | None:
        """Create a comment on a discussion."""
        mutation = """
        mutation AddDiscussionComment($discussionId: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
            comment {
              id
              databaseId
              body
              url
              createdAt
              updatedAt
              author {
                login
                avatarUrl
              }
            }
          }
        }
        """

        data = self._graphql(
            query=mutation,
            variables={
                "discussionId": discussion_id,
                "body": body
            }
        )
        if not data:
            return None

        add_comment = data.get("addDiscussionComment") or {}
        comment_data = add_comment.get("comment")
        if not comment_data:
            self._set_last_error("Comment was not created.")
            return None

        self._set_last_error("")
        return DiscussionComment.from_graphql(comment_data)

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

    def get_commits(self, owner: str, repo: str, sha: str = None, page: int = 1,
                    per_page: int = COMMITS_PER_PAGE) -> tuple[list[Commit], bool]:
        """Get a single page of commits for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: SHA or branch to start listing commits from (default: default branch)
            page: 1-based page number to fetch
            per_page: Number of commits per page

        Returns:
            (commits, has_more) where has_more is True if another page is available.
        """
        params = {
            "per_page": per_page,
            "page": page
        }
        if sha:
            params["sha"] = sha

        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits",
            params=params
        )

        if response.status_code != 200:
            return [], False

        data = response.json() or []
        commits = [Commit.from_github_api(item) for item in data]

        # GitHub sends a rel="next" link while more pages remain; fall back to a
        # full page meaning there is probably more.
        has_more = "next" in response.links if response.links else len(data) == per_page

        return commits, has_more

    def get_commit(self, owner: str, repo: str, sha: str) -> Commit | None:
        """Get a single commit by SHA."""
        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{sha}"
        )

        if response.status_code != 200:
            return None

        return Commit.from_github_api(response.json())

    def get_branches(self, owner: str, repo: str, per_page: int = 100) -> list[dict]:
        """Get branches for a repository, sorted by last commit date (most recent first).

        Uses GraphQL to get branch commit dates in bulk (one request per 100
        branches, no per-branch calls). Falls back to REST if GraphQL fails.
        """
        branches = self._get_branches_graphql(owner, repo)
        if branches is not None:
            return branches
        return self._get_branches_rest(owner, repo, per_page)

    def _get_branches_graphql(self, owner: str, repo: str) -> list[dict] | None:
        """Get branches via GraphQL, sorted by last commit date (most recent first).

        GraphQL can't sort branch refs by commit date server-side (the
        TAG_COMMIT_DATE order only applies to tags), but it returns commit
        dates in bulk — one request per 100 branches with no per-branch
        calls — so we sort client-side. The repository's default branch is
        flagged with 'is_default'. Returns None on failure so the caller
        can fall back to REST.
        """
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            defaultBranchRef { name }
            refs(refPrefix: "refs/heads/", first: 100, after: $cursor) {
              pageInfo { hasNextPage endCursor }
              nodes {
                name
                target { ... on Commit { oid committedDate } }
              }
            }
          }
        }
        """

        def to_branch(node):
            target = node.get('target') or {}
            return {
                'name': node.get('name', ''),
                'commit': {'sha': target.get('oid')},
                'last_commit_date': target.get('committedDate'),
            }

        branches = []
        default_name = None
        cursor = None

        while True:
            data = self._graphql(query, {
                "owner": owner, "name": repo, "cursor": cursor
            })
            if data is None:
                return None

            repository = data.get('repository')
            if repository is None:
                return None

            if default_name is None and repository.get('defaultBranchRef'):
                default_name = repository['defaultBranchRef'].get('name')

            refs = repository.get('refs') or {}
            branches.extend(to_branch(n) for n in refs.get('nodes') or [])

            page_info = refs.get('pageInfo') or {}
            if not page_info.get('hasNextPage'):
                break
            cursor = page_info.get('endCursor')

        for branch in branches:
            branch['is_default'] = branch['name'] == default_name

        # Sort by last commit date (most recent first), None values at end
        branches.sort(
            key=lambda b: b.get('last_commit_date') or '',
            reverse=True
        )

        return branches

    def _get_branches_rest(self, owner: str, repo: str, per_page: int = 100) -> list[dict]:
        """REST fallback: list branches, then fetch commit dates for sorting."""
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

    def get_user_repos(self, username: str, sort: str = "pushed", per_page: int = 100) -> list[Repository]:
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

    def get_run_artifacts(self, owner: str, repo: str, run_id: int, per_page: int = 100) -> list[Artifact]:
        """Get the artifacts produced by a workflow run."""
        artifacts = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
                params={
                    "per_page": per_page,
                    "page": page
                }
            )

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get('artifacts', [])
            if not items:
                break

            for item in items:
                artifacts.append(Artifact.from_github_api(item))

            if len(items) < per_page:
                break

            page += 1

        return artifacts

    def download_artifact(self, owner: str, repo: str, artifact_id: int, dest_path: str,
                          progress_callback=None) -> bool:
        """Download a workflow-run artifact (a zip) to the specified path.

        Args:
            owner: Repository owner
            repo: Repository name
            artifact_id: Artifact ID to download
            dest_path: Full path where to save the zip file
            progress_callback: Optional callback(downloaded_bytes, total_bytes)

        Returns:
            True if download succeeded, False otherwise. Expired artifacts
            return False (GitHub responds 410 Gone).
        """
        # The artifact download endpoint 302-redirects to a short-lived signed
        # URL on a different host; requests drops the Authorization header on the
        # cross-host redirect, which is exactly what the signed URL expects.
        try:
            with self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip",
                stream=True,
                allow_redirects=True
            ) as response:
                if response.status_code != 200:
                    return False

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total_size)
            return True
        except Exception:
            # Don't leave a truncated zip behind on a failed/interrupted download.
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except OSError:
                pass
            return False

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

    # ============ Repository Contents API ============

    def get_contents(self, owner: str, repo: str, path: str = "", ref: str = None) -> list[ContentItem] | ContentItem | None:
        """Get contents of a file or directory in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file or directory (empty for root)
            ref: Branch, tag, or commit SHA (default: default branch)

        Returns:
            List of ContentItem for directories, single ContentItem for files, or None on error
        """
        params = {}
        if ref:
            params["ref"] = ref

        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}",
            params=params
        )

        if response.status_code != 200:
            return None

        data = response.json()

        # Directory returns a list, file returns a single object
        if isinstance(data, list):
            items = []
            for item in data:
                items.append(ContentItem.from_github_api(item))
            # Sort: directories first, then files, both alphabetically
            items.sort(key=lambda x: (0 if x.type == "dir" else 1, x.name.lower()))
            return items
        else:
            return ContentItem.from_github_api(data)

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = None) -> str | None:
        """Get the decoded content of a file.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to the file
            ref: Branch, tag, or commit SHA (default: default branch)

        Returns:
            Decoded file content as string, or None on error
        """
        item = self.get_contents(owner, repo, path, ref)

        if item is None or isinstance(item, list):
            return None

        if item.content and item.encoding == "base64":
            import base64
            try:
                return base64.b64decode(item.content).decode('utf-8')
            except (UnicodeDecodeError, ValueError):
                # Binary file or decode error
                return None

        return None

    def get_readme(self, owner: str, repo: str, ref: str = None) -> str | None:
        """Get the README content for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            ref: Branch, tag, or commit SHA (default: default branch)

        Returns:
            README content as string, or None if not found
        """
        params = {}
        if ref:
            params["ref"] = ref

        response = self._session.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/readme",
            params=params,
            headers={"Accept": "application/vnd.github.raw"}
        )

        if response.status_code == 200:
            return response.text
        return None

    # ============ Forks API ============

    def get_forks(self, owner: str, repo: str, sort: str = "newest", per_page: int = 100) -> list[Repository]:
        """Get forks of a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            sort: Sort order - 'newest', 'oldest', 'stargazers', 'watchers'
            per_page: Results per page

        Returns:
            List of Repository objects representing the forks
        """
        forks = []
        page = 1

        while True:
            response = self._session.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/forks",
                params={
                    "sort": sort,
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
                forks.append(Repository.from_github_api(item))

            if len(data) < per_page:
                break

            page += 1

        return forks
