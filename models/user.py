"""User profile data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


def format_relative_time(dt: Optional[datetime]) -> str:
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


def _parse_timestamp(value) -> Optional[datetime]:
    """Parse a GitHub ISO 8601 timestamp, returning None if absent or invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


@dataclass
class UserProfile:
    """GitHub user profile model."""
    id: int
    login: str
    name: Optional[str]
    avatar_url: str
    html_url: str
    bio: Optional[str]
    company: Optional[str]
    location: Optional[str]
    email: Optional[str]
    blog: Optional[str]
    twitter_username: Optional[str]
    public_repos: int
    public_gists: int
    followers: int
    following: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    type: str  # 'User' or 'Organization'

    @classmethod
    def from_github_api(cls, data: dict) -> 'UserProfile':
        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        updated_at = None
        if data.get('updated_at'):
            try:
                updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data.get('id', 0),
            login=data.get('login', ''),
            name=data.get('name'),
            avatar_url=data.get('avatar_url', ''),
            html_url=data.get('html_url', ''),
            bio=data.get('bio'),
            company=data.get('company'),
            location=data.get('location'),
            email=data.get('email'),
            blog=data.get('blog'),
            twitter_username=data.get('twitter_username'),
            public_repos=data.get('public_repos', 0),
            public_gists=data.get('public_gists', 0),
            followers=data.get('followers', 0),
            following=data.get('following', 0),
            created_at=created_at,
            updated_at=updated_at,
            type=data.get('type', 'User')
        )

    @property
    def display_name(self) -> str:
        """Get display name (name or login)."""
        return self.name or self.login

    def format_display(self) -> str:
        """Format user for list display."""
        parts = [self.login]
        if self.name:
            parts.append(f"({self.name})")
        if self.bio:
            bio_preview = self.bio[:50].replace('\n', ' ')
            if len(self.bio) > 50:
                bio_preview += "..."
            parts.append(f"- {bio_preview}")
        return " ".join(parts)

    def _format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time."""
        return format_relative_time(dt)


@dataclass
class Stargazer:
    """A user who starred a repository."""
    login: str
    html_url: str
    type: str  # 'User' or 'Organization'
    starred_at: Optional[datetime]

    @classmethod
    def from_github_api(cls, data: dict) -> 'Stargazer':
        # The star media type wraps the user alongside a starred_at timestamp;
        # the default media type returns the bare user.
        user = data.get('user') if 'user' in data else data
        user = user or {}
        return cls(
            login=user.get('login', ''),
            html_url=user.get('html_url', ''),
            type=user.get('type', 'User'),
            starred_at=_parse_timestamp(data.get('starred_at'))
        )

    def format_display(self) -> str:
        """Format stargazer for list display."""
        if self.starred_at:
            return f"{self.login} - starred {format_relative_time(self.starred_at)}"
        return self.login
