"""Repository content model for FastGH."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ContentItem:
    """Represents a file or directory in a repository."""
    name: str
    path: str
    sha: str
    size: int
    type: str  # 'file', 'dir', 'symlink', 'submodule'
    download_url: Optional[str]
    html_url: str
    content: Optional[str] = None  # Base64 encoded content for files
    encoding: Optional[str] = None  # Usually 'base64'

    @classmethod
    def from_github_api(cls, data: dict) -> "ContentItem":
        """Create a ContentItem from GitHub API response."""
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            sha=data.get("sha", ""),
            size=data.get("size", 0),
            type=data.get("type", "file"),
            download_url=data.get("download_url"),
            html_url=data.get("html_url", ""),
            content=data.get("content"),
            encoding=data.get("encoding")
        )

    def get_display_name(self) -> str:
        """Get display name with folder indicator."""
        if self.type == "dir":
            return f"[{self.name}]"
        return self.name

    def get_size_str(self) -> str:
        """Get human-readable file size."""
        if self.type == "dir":
            return ""
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        else:
            return f"{self.size / (1024 * 1024):.1f} MB"
