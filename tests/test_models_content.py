"""Tests for models/content.py — ContentItem parsing and display helpers."""

import pytest
from models.content import ContentItem


def _file_data(**overrides) -> dict:
    base = {
        "name": "README.md",
        "path": "README.md",
        "sha": "abc123",
        "size": 512,
        "type": "file",
        "download_url": "https://raw.githubusercontent.com/owner/repo/main/README.md",
        "html_url": "https://github.com/owner/repo/blob/main/README.md",
        "content": None,
        "encoding": None,
    }
    base.update(overrides)
    return base


def _dir_data(**overrides) -> dict:
    base = {
        "name": "src",
        "path": "src",
        "sha": "def456",
        "size": 0,
        "type": "dir",
        "download_url": None,
        "html_url": "https://github.com/owner/repo/tree/main/src",
        "content": None,
        "encoding": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# from_github_api — field mapping
# ---------------------------------------------------------------------------


def test_from_api_file_name():
    item = ContentItem.from_github_api(_file_data(name="main.py"))
    assert item.name == "main.py"


def test_from_api_file_path():
    item = ContentItem.from_github_api(_file_data(path="src/main.py"))
    assert item.path == "src/main.py"


def test_from_api_file_sha():
    item = ContentItem.from_github_api(_file_data(sha="deadbeef"))
    assert item.sha == "deadbeef"


def test_from_api_file_size():
    item = ContentItem.from_github_api(_file_data(size=2048))
    assert item.size == 2048


def test_from_api_file_type():
    item = ContentItem.from_github_api(_file_data(type="file"))
    assert item.type == "file"


def test_from_api_dir_type():
    item = ContentItem.from_github_api(_dir_data())
    assert item.type == "dir"


def test_from_api_download_url_present():
    url = "https://raw.githubusercontent.com/x/y/main/f.py"
    item = ContentItem.from_github_api(_file_data(download_url=url))
    assert item.download_url == url


def test_from_api_download_url_none_for_dir():
    item = ContentItem.from_github_api(_dir_data(download_url=None))
    assert item.download_url is None


def test_from_api_html_url():
    url = "https://github.com/owner/repo/blob/main/f.py"
    item = ContentItem.from_github_api(_file_data(html_url=url))
    assert item.html_url == url


def test_from_api_content_and_encoding():
    item = ContentItem.from_github_api(_file_data(content="SGVsbG8=", encoding="base64"))
    assert item.content == "SGVsbG8="
    assert item.encoding == "base64"


def test_from_api_missing_fields_use_defaults():
    item = ContentItem.from_github_api({})
    assert item.name == ""
    assert item.path == ""
    assert item.sha == ""
    assert item.size == 0
    assert item.type == "file"
    assert item.download_url is None
    assert item.html_url == ""
    assert item.content is None
    assert item.encoding is None


# ---------------------------------------------------------------------------
# get_display_name
# ---------------------------------------------------------------------------


def test_get_display_name_file_returns_name():
    item = ContentItem.from_github_api(_file_data(name="setup.py"))
    assert item.get_display_name() == "setup.py"


def test_get_display_name_dir_returns_bracketed_name():
    item = ContentItem.from_github_api(_dir_data(name="src"))
    assert item.get_display_name() == "[src]"


def test_get_display_name_symlink_returns_name():
    item = ContentItem.from_github_api(_file_data(name="link", type="symlink"))
    assert item.get_display_name() == "link"


# ---------------------------------------------------------------------------
# get_size_str
# ---------------------------------------------------------------------------


def test_get_size_str_dir_returns_empty():
    item = ContentItem.from_github_api(_dir_data())
    assert item.get_size_str() == ""


def test_get_size_str_zero_bytes():
    item = ContentItem.from_github_api(_file_data(size=0))
    assert item.get_size_str() == "0 B"


def test_get_size_str_small_bytes():
    item = ContentItem.from_github_api(_file_data(size=500))
    assert item.get_size_str() == "500 B"


def test_get_size_str_exactly_1023_bytes():
    item = ContentItem.from_github_api(_file_data(size=1023))
    assert item.get_size_str() == "1023 B"


def test_get_size_str_exactly_1024_is_kb():
    item = ContentItem.from_github_api(_file_data(size=1024))
    assert item.get_size_str() == "1.0 KB"


def test_get_size_str_kilobytes():
    item = ContentItem.from_github_api(_file_data(size=2048))
    assert item.get_size_str() == "2.0 KB"


def test_get_size_str_fractional_kb():
    item = ContentItem.from_github_api(_file_data(size=1536))  # 1.5 KB
    assert item.get_size_str() == "1.5 KB"


def test_get_size_str_exactly_1mb():
    item = ContentItem.from_github_api(_file_data(size=1024 * 1024))
    assert item.get_size_str() == "1.0 MB"


def test_get_size_str_megabytes():
    item = ContentItem.from_github_api(_file_data(size=5 * 1024 * 1024))
    assert item.get_size_str() == "5.0 MB"


def test_get_size_str_fractional_mb():
    item = ContentItem.from_github_api(_file_data(size=int(2.5 * 1024 * 1024)))
    assert item.get_size_str() == "2.5 MB"
