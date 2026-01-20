"""Issue and Pull Request data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """GitHub user model."""
    login: str
    id: int
    avatar_url: str = ""

    @classmethod
    def from_github_api(cls, data: dict) -> 'User':
        if not data:
            return cls(login="unknown", id=0)
        return cls(
            login=data.get('login', 'unknown'),
            id=data.get('id', 0),
            avatar_url=data.get('avatar_url', '')
        )


@dataclass
class Label:
    """GitHub label model."""
    name: str
    color: str
    description: str = ""

    @classmethod
    def from_github_api(cls, data: dict) -> 'Label':
        return cls(
            name=data.get('name', ''),
            color=data.get('color', ''),
            description=data.get('description', '')
        )


@dataclass
class Comment:
    """GitHub comment model."""
    id: int
    body: str
    user: User
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    html_url: str = ""

    @classmethod
    def from_github_api(cls, data: dict) -> 'Comment':
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
            id=data['id'],
            body=data.get('body', ''),
            user=User.from_github_api(data.get('user')),
            created_at=created_at,
            updated_at=updated_at,
            html_url=data.get('html_url', '')
        )


@dataclass
class Issue:
    """GitHub issue model."""
    id: int
    number: int
    title: str
    body: Optional[str]
    state: str  # 'open' or 'closed'
    user: User
    labels: list[Label]
    assignees: list[User]
    comments_count: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    html_url: str
    is_pull_request: bool = False

    @classmethod
    def from_github_api(cls, data: dict) -> 'Issue':
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

        closed_at = None
        if data.get('closed_at'):
            try:
                closed_at = datetime.fromisoformat(data['closed_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        labels = [Label.from_github_api(l) for l in data.get('labels', [])]
        assignees = [User.from_github_api(a) for a in data.get('assignees', [])]

        return cls(
            id=data['id'],
            number=data['number'],
            title=data['title'],
            body=data.get('body'),
            state=data.get('state', 'open'),
            user=User.from_github_api(data.get('user')),
            labels=labels,
            assignees=assignees,
            comments_count=data.get('comments', 0),
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            html_url=data.get('html_url', ''),
            is_pull_request='pull_request' in data
        )

    def format_display(self) -> str:
        """Format issue for list display."""
        state_icon = "[Open]" if self.state == "open" else "[Closed]"
        labels_str = ", ".join(l.name for l in self.labels) if self.labels else ""
        labels_part = f" [{labels_str}]" if labels_str else ""
        return f"#{self.number} {state_icon} {self.title}{labels_part} - by {self.user.login}"

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
class PullRequest:
    """GitHub pull request model."""
    id: int
    number: int
    title: str
    body: Optional[str]
    state: str  # 'open' or 'closed'
    user: User
    labels: list[Label]
    assignees: list[User]
    head_ref: str  # source branch
    base_ref: str  # target branch
    merged: bool
    mergeable: Optional[bool]
    mergeable_state: Optional[str]
    merged_by: Optional[User]
    merged_at: Optional[datetime]
    comments_count: int
    commits_count: int
    additions: int
    deletions: int
    changed_files: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    html_url: str
    draft: bool = False

    @classmethod
    def from_github_api(cls, data: dict) -> 'PullRequest':
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

        closed_at = None
        if data.get('closed_at'):
            try:
                closed_at = datetime.fromisoformat(data['closed_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        merged_at = None
        if data.get('merged_at'):
            try:
                merged_at = datetime.fromisoformat(data['merged_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        labels = [Label.from_github_api(l) for l in data.get('labels', [])]
        assignees = [User.from_github_api(a) for a in data.get('assignees', [])]

        merged_by = None
        if data.get('merged_by'):
            merged_by = User.from_github_api(data['merged_by'])

        # Handle head/base refs
        head_ref = ""
        base_ref = ""
        if data.get('head'):
            head_ref = data['head'].get('ref', '')
        if data.get('base'):
            base_ref = data['base'].get('ref', '')

        return cls(
            id=data['id'],
            number=data['number'],
            title=data['title'],
            body=data.get('body'),
            state=data.get('state', 'open'),
            user=User.from_github_api(data.get('user')),
            labels=labels,
            assignees=assignees,
            head_ref=head_ref,
            base_ref=base_ref,
            merged=data.get('merged', False),
            mergeable=data.get('mergeable'),
            mergeable_state=data.get('mergeable_state'),
            merged_by=merged_by,
            merged_at=merged_at,
            comments_count=data.get('comments', 0),
            commits_count=data.get('commits', 0),
            additions=data.get('additions', 0),
            deletions=data.get('deletions', 0),
            changed_files=data.get('changed_files', 0),
            created_at=created_at,
            updated_at=updated_at,
            closed_at=closed_at,
            html_url=data.get('html_url', ''),
            draft=data.get('draft', False)
        )

    def format_display(self) -> str:
        """Format PR for list display."""
        if self.merged:
            state_icon = "[Merged]"
        elif self.state == "open":
            state_icon = "[Draft]" if self.draft else "[Open]"
        else:
            state_icon = "[Closed]"

        branch_info = f"{self.head_ref} -> {self.base_ref}"
        return f"#{self.number} {state_icon} {self.title} ({branch_info}) - by {self.user.login}"

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
