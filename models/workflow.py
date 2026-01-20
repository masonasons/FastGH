"""GitHub Actions workflow models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Workflow:
    """GitHub Actions workflow."""
    id: int
    name: str
    path: str
    state: str  # 'active', 'disabled_manually', etc.
    html_url: str
    badge_url: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_github_api(cls, data: dict) -> "Workflow":
        """Create a Workflow from GitHub API response."""
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
            name=data.get('name', ''),
            path=data.get('path', ''),
            state=data.get('state', ''),
            html_url=data.get('html_url', ''),
            badge_url=data.get('badge_url', ''),
            created_at=created_at,
            updated_at=updated_at
        )

    def format_display(self) -> str:
        """Format workflow for display."""
        state_icon = "✓" if self.state == "active" else "○"
        return f"{state_icon} {self.name}"


@dataclass
class WorkflowRun:
    """GitHub Actions workflow run."""
    id: int
    name: str
    workflow_id: int
    head_branch: str
    head_sha: str
    status: str  # 'queued', 'in_progress', 'completed'
    conclusion: Optional[str]  # 'success', 'failure', 'cancelled', 'skipped', etc.
    event: str  # 'push', 'pull_request', 'workflow_dispatch', etc.
    run_number: int
    run_attempt: int
    html_url: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    run_started_at: Optional[datetime]
    actor_login: str
    actor_avatar_url: str
    triggering_actor_login: str

    @classmethod
    def from_github_api(cls, data: dict) -> "WorkflowRun":
        """Create a WorkflowRun from GitHub API response."""
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

        run_started_at = None
        if data.get('run_started_at'):
            try:
                run_started_at = datetime.fromisoformat(data['run_started_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        actor = data.get('actor', {}) or {}
        triggering_actor = data.get('triggering_actor', {}) or {}

        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            workflow_id=data.get('workflow_id', 0),
            head_branch=data.get('head_branch', ''),
            head_sha=data.get('head_sha', '')[:7] if data.get('head_sha') else '',
            status=data.get('status', ''),
            conclusion=data.get('conclusion'),
            event=data.get('event', ''),
            run_number=data.get('run_number', 0),
            run_attempt=data.get('run_attempt', 1),
            html_url=data.get('html_url', ''),
            created_at=created_at,
            updated_at=updated_at,
            run_started_at=run_started_at,
            actor_login=actor.get('login', ''),
            actor_avatar_url=actor.get('avatar_url', ''),
            triggering_actor_login=triggering_actor.get('login', '')
        )

    def _format_relative_time(self) -> str:
        """Format relative time for display."""
        if not self.created_at:
            return ""

        now = datetime.now(self.created_at.tzinfo) if self.created_at.tzinfo else datetime.now()
        diff = now - self.created_at

        seconds = diff.total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days}d ago"
        else:
            return self.created_at.strftime('%Y-%m-%d')

    def get_status_icon(self) -> str:
        """Get status icon for display."""
        if self.status == "completed":
            if self.conclusion == "success":
                return "✓"
            elif self.conclusion == "failure":
                return "✗"
            elif self.conclusion == "cancelled":
                return "⊘"
            elif self.conclusion == "skipped":
                return "⊘"
            else:
                return "?"
        elif self.status == "in_progress":
            return "●"
        elif self.status == "queued":
            return "○"
        else:
            return "?"

    def get_status_text(self) -> str:
        """Get status text for display."""
        if self.status == "completed":
            return self.conclusion or "completed"
        return self.status.replace("_", " ")

    def format_display(self) -> str:
        """Format workflow run for display in list."""
        icon = self.get_status_icon()
        time_str = self._format_relative_time()
        return f"{icon} {self.name} #{self.run_number} - {self.head_branch} ({self.event}) - {time_str}"


@dataclass
class WorkflowJob:
    """GitHub Actions workflow job."""
    id: int
    run_id: int
    name: str
    status: str  # 'queued', 'in_progress', 'completed'
    conclusion: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    html_url: str
    runner_name: Optional[str]
    steps: list  # List of step dicts

    @classmethod
    def from_github_api(cls, data: dict) -> "WorkflowJob":
        """Create a WorkflowJob from GitHub API response."""
        started_at = None
        if data.get('started_at'):
            try:
                started_at = datetime.fromisoformat(data['started_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        completed_at = None
        if data.get('completed_at'):
            try:
                completed_at = datetime.fromisoformat(data['completed_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data.get('id', 0),
            run_id=data.get('run_id', 0),
            name=data.get('name', ''),
            status=data.get('status', ''),
            conclusion=data.get('conclusion'),
            started_at=started_at,
            completed_at=completed_at,
            html_url=data.get('html_url', ''),
            runner_name=data.get('runner_name'),
            steps=data.get('steps', [])
        )

    def get_status_icon(self) -> str:
        """Get status icon for display."""
        if self.status == "completed":
            if self.conclusion == "success":
                return "✓"
            elif self.conclusion == "failure":
                return "✗"
            elif self.conclusion == "cancelled":
                return "⊘"
            elif self.conclusion == "skipped":
                return "⊘"
            else:
                return "?"
        elif self.status == "in_progress":
            return "●"
        elif self.status == "queued":
            return "○"
        else:
            return "?"

    def get_duration(self) -> str:
        """Get job duration as string."""
        if not self.started_at:
            return ""
        end = self.completed_at or datetime.now(self.started_at.tzinfo)
        diff = end - self.started_at
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            mins = seconds // 60
            secs = seconds % 60
            return f"{mins}m {secs}s"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}h {mins}m"

    def format_display(self) -> str:
        """Format job for display."""
        icon = self.get_status_icon()
        duration = self.get_duration()
        if duration:
            return f"{icon} {self.name} ({duration})"
        return f"{icon} {self.name}"
