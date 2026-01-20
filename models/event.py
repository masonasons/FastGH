"""GitHub Event model for FastGH."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass
class EventActor:
    """Actor (user) who performed an event."""
    id: int
    login: str
    avatar_url: str

    @classmethod
    def from_api(cls, data: dict) -> "EventActor":
        return cls(
            id=data.get("id", 0),
            login=data.get("login", ""),
            avatar_url=data.get("avatar_url", "")
        )


@dataclass
class EventRepo:
    """Repository associated with an event."""
    id: int
    name: str  # full name like "owner/repo"
    url: str

    @classmethod
    def from_api(cls, data: dict) -> "EventRepo":
        return cls(
            id=data.get("id", 0),
            name=data.get("name", ""),
            url=data.get("url", "")
        )


@dataclass
class Event:
    """A GitHub event from the activity feed."""
    id: str
    type: str
    actor: EventActor
    repo: EventRepo
    payload: dict
    public: bool
    created_at: Optional[datetime]

    # Event type descriptions
    EVENT_TYPES = {
        "CommitCommentEvent": "commented on a commit",
        "CreateEvent": "created",
        "DeleteEvent": "deleted",
        "ForkEvent": "forked",
        "GollumEvent": "updated wiki",
        "IssueCommentEvent": "commented on issue",
        "IssuesEvent": "issue",
        "MemberEvent": "added member",
        "PublicEvent": "made public",
        "PullRequestEvent": "pull request",
        "PullRequestReviewEvent": "reviewed PR",
        "PullRequestReviewCommentEvent": "commented on PR review",
        "PushEvent": "pushed",
        "ReleaseEvent": "released",
        "SponsorshipEvent": "sponsorship",
        "WatchEvent": "starred",
    }

    @classmethod
    def from_api(cls, data: dict) -> "Event":
        """Create from GitHub API response."""
        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except:
                pass

        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            actor=EventActor.from_api(data.get("actor", {})),
            repo=EventRepo.from_api(data.get("repo", {})),
            payload=data.get("payload", {}),
            public=data.get("public", True),
            created_at=created_at
        )

    def _format_relative_time(self) -> str:
        """Format relative time for display."""
        if not self.created_at:
            return "Unknown"

        now = datetime.now(self.created_at.tzinfo) if self.created_at.tzinfo else datetime.now()
        delta = now - self.created_at

        if delta.days > 365:
            years = delta.days // 365
            return f"{years}y ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months}mo ago"
        elif delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"

    def get_action_description(self) -> str:
        """Get human-readable description of the event action."""
        payload = self.payload

        if self.type == "WatchEvent":
            return "starred"

        elif self.type == "ForkEvent":
            forkee = payload.get("forkee", {})
            fork_name = forkee.get("full_name", "")
            if fork_name:
                return f"forked to {fork_name}"
            return "forked"

        elif self.type == "CreateEvent":
            ref_type = payload.get("ref_type", "")
            ref = payload.get("ref", "")
            if ref_type == "repository":
                return "created repository"
            elif ref_type == "branch":
                return f"created branch {ref}"
            elif ref_type == "tag":
                return f"created tag {ref}"
            return f"created {ref_type}"

        elif self.type == "DeleteEvent":
            ref_type = payload.get("ref_type", "")
            ref = payload.get("ref", "")
            return f"deleted {ref_type} {ref}"

        elif self.type == "PushEvent":
            # size can be 0 for force pushes, use distinct_size or commits array as fallback
            size = payload.get("size", 0)
            if size == 0:
                size = payload.get("distinct_size", 0)
            if size == 0:
                commits = payload.get("commits", [])
                size = len(commits)
            ref = payload.get("ref", "").replace("refs/heads/", "")
            if size == 0:
                return f"force pushed to {ref}"
            elif size == 1:
                return f"pushed 1 commit to {ref}"
            return f"pushed {size} commits to {ref}"

        elif self.type == "IssuesEvent":
            action = payload.get("action", "")
            issue = payload.get("issue", {})
            number = issue.get("number", "")
            title = issue.get("title", "")[:50]
            return f"{action} issue #{number}: {title}"

        elif self.type == "IssueCommentEvent":
            action = payload.get("action", "created")
            issue = payload.get("issue", {})
            number = issue.get("number", "")
            return f"commented on issue #{number}"

        elif self.type == "PullRequestEvent":
            action = payload.get("action", "")
            pr = payload.get("pull_request", {})
            number = pr.get("number", "")
            title = pr.get("title", "")[:50]
            if action == "opened":
                return f"opened PR #{number}: {title}"
            elif action == "closed":
                merged = pr.get("merged", False)
                if merged:
                    return f"merged PR #{number}: {title}"
                return f"closed PR #{number}: {title}"
            return f"{action} PR #{number}"

        elif self.type == "PullRequestReviewEvent":
            action = payload.get("action", "")
            pr = payload.get("pull_request", {})
            number = pr.get("number", "")
            review = payload.get("review", {})
            state = review.get("state", "")
            if state == "approved":
                return f"approved PR #{number}"
            elif state == "changes_requested":
                return f"requested changes on PR #{number}"
            return f"reviewed PR #{number}"

        elif self.type == "PullRequestReviewCommentEvent":
            pr = payload.get("pull_request", {})
            number = pr.get("number", "")
            return f"commented on PR #{number}"

        elif self.type == "ReleaseEvent":
            action = payload.get("action", "")
            release = payload.get("release", {})
            tag = release.get("tag_name", "")
            if action == "published":
                return f"released {tag}"
            return f"{action} release {tag}"

        elif self.type == "CommitCommentEvent":
            return "commented on a commit"

        elif self.type == "GollumEvent":
            pages = payload.get("pages", [])
            if pages:
                action = pages[0].get("action", "updated")
                title = pages[0].get("title", "")
                return f"{action} wiki page: {title}"
            return "updated wiki"

        elif self.type == "MemberEvent":
            action = payload.get("action", "")
            member = payload.get("member", {})
            login = member.get("login", "")
            return f"{action} {login} as collaborator"

        elif self.type == "PublicEvent":
            return "made repository public"

        return self.EVENT_TYPES.get(self.type, self.type)

    def format_display(self) -> str:
        """Format for list display."""
        action = self.get_action_description()
        return f"{self.actor.login} {action} in {self.repo.name} - {self._format_relative_time()}"

    def get_web_url(self) -> str:
        """Get the web URL for this event."""
        base_url = f"https://github.com/{self.repo.name}"

        if self.type == "IssuesEvent":
            issue = self.payload.get("issue", {})
            number = issue.get("number")
            if number:
                return f"{base_url}/issues/{number}"

        elif self.type == "IssueCommentEvent":
            comment = self.payload.get("comment", {})
            html_url = comment.get("html_url")
            if html_url:
                return html_url
            issue = self.payload.get("issue", {})
            number = issue.get("number")
            if number:
                return f"{base_url}/issues/{number}"

        elif self.type == "PullRequestEvent":
            pr = self.payload.get("pull_request", {})
            number = pr.get("number")
            if number:
                return f"{base_url}/pull/{number}"

        elif self.type == "PullRequestReviewEvent" or self.type == "PullRequestReviewCommentEvent":
            pr = self.payload.get("pull_request", {})
            number = pr.get("number")
            if number:
                return f"{base_url}/pull/{number}"

        elif self.type == "PushEvent":
            # Link to compare or commits
            before = self.payload.get("before", "")[:7]
            head = self.payload.get("head", "")[:7]
            if before and head:
                return f"{base_url}/compare/{before}...{head}"

        elif self.type == "ReleaseEvent":
            release = self.payload.get("release", {})
            html_url = release.get("html_url")
            if html_url:
                return html_url

        elif self.type == "ForkEvent":
            forkee = self.payload.get("forkee", {})
            html_url = forkee.get("html_url")
            if html_url:
                return html_url

        elif self.type == "CommitCommentEvent":
            comment = self.payload.get("comment", {})
            html_url = comment.get("html_url")
            if html_url:
                return html_url

        elif self.type == "CreateEvent":
            ref_type = self.payload.get("ref_type", "")
            ref = self.payload.get("ref", "")
            if ref_type == "branch" and ref:
                return f"{base_url}/tree/{ref}"
            elif ref_type == "tag" and ref:
                return f"{base_url}/releases/tag/{ref}"

        return base_url

    def get_actor_url(self) -> str:
        """Get URL to actor's profile."""
        return f"https://github.com/{self.actor.login}"
