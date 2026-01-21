"""Repository data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Repository:
    """Universal repository data model."""
    id: int
    name: str
    full_name: str
    description: Optional[str]
    owner: str
    stars: int
    forks: int
    open_issues: int
    language: Optional[str]
    updated_at: Optional[datetime]
    pushed_at: Optional[datetime]
    url: str
    html_url: str
    private: bool

    @classmethod
    def from_github_api(cls, data: dict) -> 'Repository':
        """Create a Repository from GitHub API response data."""
        updated_at = None
        if data.get('updated_at'):
            try:
                updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        pushed_at = None
        if data.get('pushed_at'):
            try:
                pushed_at = datetime.fromisoformat(data['pushed_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data['id'],
            name=data['name'],
            full_name=data['full_name'],
            description=data.get('description'),
            owner=data['owner']['login'],
            stars=data.get('stargazers_count', 0),
            forks=data.get('forks_count', 0),
            open_issues=data.get('open_issues_count', 0),
            language=data.get('language'),
            updated_at=updated_at,
            pushed_at=pushed_at,
            url=data['url'],
            html_url=data['html_url'],
            private=data.get('private', False),
        )

    def format_display(self) -> str:
        """Format repository for display in list."""
        desc = self.description or "No description"
        if len(desc) > 80:
            desc = desc[:77] + "..."

        lang = self.language or "Unknown"
        pushed = self._format_relative_time() if self.pushed_at else "Unknown"

        return (
            f"{self.full_name} - {desc}\n"
            f"Stars: {self.stars} | Forks: {self.forks} | "
            f"Issues: {self.open_issues} | {lang} | Pushed {pushed}"
        )

    def format_single_line(self) -> str:
        """Format repository for single-line display."""
        lang = self.language or "Unknown"
        if self.pushed_at:
            local_time = self.pushed_at.astimezone() if self.pushed_at.tzinfo else self.pushed_at
            pushed = local_time.strftime("%Y-%m-%d %H:%M")
        else:
            pushed = "Unknown"
        return f"{self.full_name} | {self.stars} stars | {lang} | Pushed {pushed}"

    def _format_relative_time(self) -> str:
        """Format pushed_at as relative time."""
        if not self.pushed_at:
            return "Unknown"

        now = datetime.now(self.pushed_at.tzinfo) if self.pushed_at.tzinfo else datetime.now()
        diff = now - self.pushed_at

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
