"""GitHub Release models."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReleaseAsset:
    """GitHub Release asset (downloadable file)."""
    id: int
    name: str
    label: Optional[str]
    content_type: str
    size: int
    download_count: int
    browser_download_url: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    @classmethod
    def from_github_api(cls, data: dict) -> "ReleaseAsset":
        """Create a ReleaseAsset from GitHub API response."""
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
            label=data.get('label'),
            content_type=data.get('content_type', ''),
            size=data.get('size', 0),
            download_count=data.get('download_count', 0),
            browser_download_url=data.get('browser_download_url', ''),
            created_at=created_at,
            updated_at=updated_at
        )

    def format_size(self) -> str:
        """Format file size for display."""
        size = self.size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    def format_display(self) -> str:
        """Format asset for display in list."""
        size_str = self.format_size()
        downloads = f"{self.download_count} downloads" if self.download_count != 1 else "1 download"
        return f"{self.name} ({size_str}, {downloads})"


@dataclass
class Release:
    """GitHub Release."""
    id: int
    tag_name: str
    name: str
    body: str
    draft: bool
    prerelease: bool
    created_at: Optional[datetime]
    published_at: Optional[datetime]
    html_url: str
    tarball_url: str
    zipball_url: str
    author_login: str
    assets: list[ReleaseAsset]

    @classmethod
    def from_github_api(cls, data: dict) -> "Release":
        """Create a Release from GitHub API response."""
        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        published_at = None
        if data.get('published_at'):
            try:
                published_at = datetime.fromisoformat(data['published_at'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        author = data.get('author', {}) or {}

        assets = []
        for asset_data in data.get('assets', []):
            assets.append(ReleaseAsset.from_github_api(asset_data))

        return cls(
            id=data.get('id', 0),
            tag_name=data.get('tag_name', ''),
            name=data.get('name', '') or data.get('tag_name', ''),
            body=data.get('body', '') or '',
            draft=data.get('draft', False),
            prerelease=data.get('prerelease', False),
            created_at=created_at,
            published_at=published_at,
            html_url=data.get('html_url', ''),
            tarball_url=data.get('tarball_url', ''),
            zipball_url=data.get('zipball_url', ''),
            author_login=author.get('login', ''),
            assets=assets
        )

    def _format_relative_time(self) -> str:
        """Format relative time for display."""
        dt = self.published_at or self.created_at
        if not dt:
            return ""

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt

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
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks}w ago"
        else:
            return dt.strftime('%Y-%m-%d')

    def get_status_label(self) -> str:
        """Get status label for display."""
        labels = []
        if self.draft:
            labels.append("Draft")
        if self.prerelease:
            labels.append("Pre-release")
        return ", ".join(labels) if labels else "Release"

    def format_display(self) -> str:
        """Format release for display in list."""
        time_str = self._format_relative_time()
        status = self.get_status_label()
        asset_count = len(self.assets)
        assets_str = f"{asset_count} assets" if asset_count != 1 else "1 asset"

        if self.name != self.tag_name:
            return f"{self.tag_name}: {self.name} - {status} ({assets_str}) - {time_str}"
        else:
            return f"{self.tag_name} - {status} ({assets_str}) - {time_str}"
