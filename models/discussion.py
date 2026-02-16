"""Discussion data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .issue import User


def _parse_datetime(value: str | None) -> Optional[datetime]:
    """Parse ISO datetime strings from GitHub APIs."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_author(data: dict | None) -> User:
    """Parse GraphQL author object into the shared User model."""
    if not data:
        return User(login="unknown", id=0, avatar_url="")
    raw_id = data.get("databaseId")
    if isinstance(raw_id, int):
        author_id = raw_id
    else:
        try:
            author_id = int(raw_id) if raw_id is not None else 0
        except (TypeError, ValueError):
            author_id = 0
    return User(
        login=data.get("login", "unknown"),
        id=author_id,
        avatar_url=data.get("avatarUrl", "")
    )


@dataclass
class DiscussionComment:
    """GitHub discussion comment model."""
    id: str
    database_id: Optional[int]
    body: str
    author: User
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    url: str = ""

    @classmethod
    def from_graphql(cls, data: dict) -> "DiscussionComment":
        return cls(
            id=data.get("id", ""),
            database_id=data.get("databaseId"),
            body=data.get("body", ""),
            author=_parse_author(data.get("author")),
            created_at=_parse_datetime(data.get("createdAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            url=data.get("url", "")
        )

    def _format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time."""
        if not dt:
            return "Unknown"

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt

        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"


@dataclass
class Discussion:
    """GitHub discussion model."""
    id: str
    number: int
    title: str
    body: Optional[str]
    author: User
    category_name: str
    is_answered: bool
    comments_count: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    url: str
    comments: list[DiscussionComment] = field(default_factory=list)
    comments_has_next_page: bool = False
    comments_end_cursor: Optional[str] = None

    @classmethod
    def from_graphql(cls, data: dict) -> "Discussion":
        comments_connection = data.get("comments", {}) or {}
        comment_nodes = comments_connection.get("nodes", []) or []
        page_info = comments_connection.get("pageInfo", {}) or {}

        return cls(
            id=data.get("id", ""),
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            author=_parse_author(data.get("author")),
            category_name=(data.get("category") or {}).get("name", ""),
            is_answered=data.get("isAnswered", False),
            comments_count=comments_connection.get("totalCount", 0),
            created_at=_parse_datetime(data.get("createdAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            url=data.get("url", ""),
            comments=[DiscussionComment.from_graphql(item) for item in comment_nodes],
            comments_has_next_page=page_info.get("hasNextPage", False),
            comments_end_cursor=page_info.get("endCursor")
        )

    def _format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time."""
        if not dt:
            return "Unknown"

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt

        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
