"""Commit data model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from .issue import User


@dataclass
class CommitAuthor:
    """Git commit author (not necessarily a GitHub user)."""
    name: str
    email: str
    date: Optional[datetime]

    @classmethod
    def from_github_api(cls, data: dict) -> 'CommitAuthor':
        if not data:
            return cls(name="unknown", email="", date=None)

        date = None
        if data.get('date'):
            try:
                date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        return cls(
            name=data.get('name', 'unknown'),
            email=data.get('email', ''),
            date=date
        )


@dataclass
class CommitFile:
    """File changed in a commit."""
    filename: str
    status: str  # 'added', 'removed', 'modified', 'renamed', 'copied', 'changed', 'unchanged'
    additions: int
    deletions: int
    changes: int
    previous_filename: Optional[str]  # For renamed files

    @classmethod
    def from_github_api(cls, data: dict) -> 'CommitFile':
        return cls(
            filename=data.get('filename', ''),
            status=data.get('status', 'modified'),
            additions=data.get('additions', 0),
            deletions=data.get('deletions', 0),
            changes=data.get('changes', 0),
            previous_filename=data.get('previous_filename')
        )

    def format_display(self) -> str:
        """Format file for list display."""
        status_icons = {
            'added': '[A]',
            'removed': '[D]',
            'modified': '[M]',
            'renamed': '[R]',
            'copied': '[C]',
            'changed': '[M]',
            'unchanged': '[ ]'
        }
        icon = status_icons.get(self.status, '[?]')
        stats = f"+{self.additions} -{self.deletions}"
        if self.status == 'renamed' and self.previous_filename:
            return f"{icon} {self.previous_filename} -> {self.filename} ({stats})"
        return f"{icon} {self.filename} ({stats})"


@dataclass
class Commit:
    """GitHub commit model."""
    sha: str
    message: str
    author: CommitAuthor
    committer: CommitAuthor
    github_author: Optional[User]  # GitHub user if linked
    github_committer: Optional[User]  # GitHub user if linked
    html_url: str
    parents: list[str]  # List of parent commit SHAs
    stats_additions: int
    stats_deletions: int
    stats_total: int
    files: list[CommitFile]

    @classmethod
    def from_github_api(cls, data: dict) -> 'Commit':
        commit_data = data.get('commit', {})

        author = CommitAuthor.from_github_api(commit_data.get('author'))
        committer = CommitAuthor.from_github_api(commit_data.get('committer'))

        github_author = None
        if data.get('author'):
            github_author = User.from_github_api(data['author'])

        github_committer = None
        if data.get('committer'):
            github_committer = User.from_github_api(data['committer'])

        parents = [p.get('sha', '') for p in data.get('parents', [])]

        stats = data.get('stats', {})
        files = [CommitFile.from_github_api(f) for f in data.get('files', [])]

        return cls(
            sha=data.get('sha', ''),
            message=commit_data.get('message', ''),
            author=author,
            committer=committer,
            github_author=github_author,
            github_committer=github_committer,
            html_url=data.get('html_url', ''),
            parents=parents,
            stats_additions=stats.get('additions', 0),
            stats_deletions=stats.get('deletions', 0),
            stats_total=stats.get('total', 0),
            files=files
        )

    @property
    def short_sha(self) -> str:
        """Get shortened SHA (7 characters)."""
        return self.sha[:7] if self.sha else ""

    @property
    def first_line(self) -> str:
        """Get first line of commit message."""
        return self.message.split('\n')[0] if self.message else ""

    def format_display(self) -> str:
        """Format commit for list display."""
        author_name = self.github_author.login if self.github_author else self.author.name
        date_str = self._format_relative_time(self.author.date) if self.author.date else "Unknown"
        return f"{self.first_line} - {author_name}, {date_str} [{self.short_sha}]"

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
