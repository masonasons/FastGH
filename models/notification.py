"""Notification model for FastGH."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NotificationSubject:
    """Subject of a notification (issue, PR, commit, etc.)."""
    title: str
    url: str
    type: str  # Issue, PullRequest, Commit, Release, Discussion, etc.
    latest_comment_url: Optional[str] = None

    @classmethod
    def from_api(cls, data: dict) -> "NotificationSubject":
        """Create from GitHub API response."""
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            type=data.get("type", ""),
            latest_comment_url=data.get("latest_comment_url")
        )


@dataclass
class Notification:
    """A GitHub notification."""
    id: str
    unread: bool
    reason: str
    subject: NotificationSubject
    repository_full_name: str
    repository_owner: str
    repository_name: str
    updated_at: Optional[datetime]
    last_read_at: Optional[datetime]
    url: str

    # Reason descriptions
    REASONS = {
        "assign": "You were assigned",
        "author": "You created the thread",
        "comment": "You commented",
        "ci_activity": "CI activity",
        "invitation": "You were invited",
        "manual": "You subscribed manually",
        "mention": "You were @mentioned",
        "review_requested": "Review requested",
        "security_alert": "Security alert",
        "state_change": "State changed",
        "subscribed": "You're watching the repo",
        "team_mention": "Your team was @mentioned",
    }

    @classmethod
    def from_api(cls, data: dict) -> "Notification":
        """Create from GitHub API response."""
        repo = data.get("repository", {})

        updated_at = None
        if data.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
            except:
                pass

        last_read_at = None
        if data.get("last_read_at"):
            try:
                last_read_at = datetime.fromisoformat(data["last_read_at"].replace("Z", "+00:00"))
            except:
                pass

        return cls(
            id=data.get("id", ""),
            unread=data.get("unread", False),
            reason=data.get("reason", ""),
            subject=NotificationSubject.from_api(data.get("subject", {})),
            repository_full_name=repo.get("full_name", ""),
            repository_owner=repo.get("owner", {}).get("login", ""),
            repository_name=repo.get("name", ""),
            updated_at=updated_at,
            last_read_at=last_read_at,
            url=data.get("url", "")
        )

    def get_reason_display(self) -> str:
        """Get human-readable reason."""
        return self.REASONS.get(self.reason, self.reason)

    def _format_relative_time(self) -> str:
        """Format relative time for display."""
        if not self.updated_at:
            return "Unknown"

        now = datetime.now(self.updated_at.tzinfo) if self.updated_at.tzinfo else datetime.now()
        delta = now - self.updated_at

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

    def format_display(self) -> str:
        """Format for list display."""
        unread_marker = "● " if self.unread else "○ "
        type_icon = self._get_type_icon()
        return f"{unread_marker}[{type_icon}] {self.subject.title} - {self.repository_full_name} ({self.get_reason_display()}) - {self._format_relative_time()}"

    def _get_type_icon(self) -> str:
        """Get icon/label for subject type."""
        icons = {
            "Issue": "Issue",
            "PullRequest": "PR",
            "Commit": "Commit",
            "Release": "Release",
            "Discussion": "Disc",
            "RepositoryVulnerabilityAlert": "Security",
        }
        return icons.get(self.subject.type, self.subject.type)

    def get_web_url(self) -> str:
        """Get the web URL for this notification's subject."""
        # Convert API URL to web URL
        # API: https://api.github.com/repos/owner/repo/issues/123
        # Web: https://github.com/owner/repo/issues/123
        if self.subject.url:
            return self.subject.url.replace("api.github.com/repos", "github.com").replace("/pulls/", "/pull/")
        return f"https://github.com/{self.repository_full_name}"
