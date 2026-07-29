"""Tests for models/release.py — ReleaseAsset and Release."""

import pytest
from datetime import datetime, timezone, timedelta

from models.release import Release, ReleaseAsset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _asset_data(**overrides) -> dict:
    base = {
        "id": 1,
        "name": "app-windows.zip",
        "label": "Windows installer",
        "content_type": "application/zip",
        "size": 10 * 1024 * 1024,  # 10 MB
        "download_count": 42,
        "browser_download_url": "https://github.com/owner/repo/releases/download/v1.0/app.zip",
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": "2026-01-01T12:05:00Z",
    }
    base.update(overrides)
    return base


def _release_data(**overrides) -> dict:
    base = {
        "id": 100,
        "tag_name": "v1.0.0",
        "name": "Version 1.0.0",
        "body": "Release notes here",
        "draft": False,
        "prerelease": False,
        "created_at": "2026-01-01T10:00:00Z",
        "published_at": "2026-01-01T11:00:00Z",
        "html_url": "https://github.com/owner/repo/releases/tag/v1.0.0",
        "tarball_url": "https://api.github.com/repos/owner/repo/tarball/v1.0.0",
        "zipball_url": "https://api.github.com/repos/owner/repo/zipball/v1.0.0",
        "author": {"login": "alice"},
        "assets": [],
    }
    base.update(overrides)
    return base


def _release_aged(seconds: int) -> Release:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return Release.from_github_api(_release_data(published_at=iso, created_at=iso))


# ---------------------------------------------------------------------------
# ReleaseAsset.from_github_api
# ---------------------------------------------------------------------------


def test_asset_from_api_id():
    a = ReleaseAsset.from_github_api(_asset_data(id=99))
    assert a.id == 99


def test_asset_from_api_name():
    a = ReleaseAsset.from_github_api(_asset_data(name="app-macos.dmg"))
    assert a.name == "app-macos.dmg"


def test_asset_from_api_label():
    a = ReleaseAsset.from_github_api(_asset_data(label="macOS disk image"))
    assert a.label == "macOS disk image"


def test_asset_from_api_label_none():
    a = ReleaseAsset.from_github_api(_asset_data(label=None))
    assert a.label is None


def test_asset_from_api_content_type():
    a = ReleaseAsset.from_github_api(_asset_data(content_type="application/octet-stream"))
    assert a.content_type == "application/octet-stream"


def test_asset_from_api_size():
    a = ReleaseAsset.from_github_api(_asset_data(size=2048))
    assert a.size == 2048


def test_asset_from_api_download_count():
    a = ReleaseAsset.from_github_api(_asset_data(download_count=100))
    assert a.download_count == 100


def test_asset_from_api_browser_download_url():
    url = "https://github.com/x/y/releases/download/v1/file.zip"
    a = ReleaseAsset.from_github_api(_asset_data(browser_download_url=url))
    assert a.browser_download_url == url


def test_asset_from_api_created_at_parsed():
    a = ReleaseAsset.from_github_api(_asset_data(created_at="2026-03-01T08:00:00Z"))
    assert a.created_at is not None
    assert a.created_at.year == 2026


def test_asset_from_api_invalid_created_at():
    a = ReleaseAsset.from_github_api(_asset_data(created_at="bad"))
    assert a.created_at is None


def test_asset_from_api_invalid_updated_at():
    a = ReleaseAsset.from_github_api(_asset_data(updated_at="bad"))
    assert a.updated_at is None


def test_asset_from_api_missing_fields():
    a = ReleaseAsset.from_github_api({})
    assert a.id == 0
    assert a.name == ""
    assert a.size == 0
    assert a.download_count == 0
    assert a.created_at is None


# ---------------------------------------------------------------------------
# ReleaseAsset.format_size
# ---------------------------------------------------------------------------


def test_asset_format_size_bytes():
    a = ReleaseAsset.from_github_api(_asset_data(size=500))
    assert a.format_size() == "500 B"


def test_asset_format_size_exactly_1023_bytes():
    a = ReleaseAsset.from_github_api(_asset_data(size=1023))
    assert a.format_size() == "1023 B"


def test_asset_format_size_kilobytes():
    a = ReleaseAsset.from_github_api(_asset_data(size=2048))
    assert a.format_size() == "2.0 KB"


def test_asset_format_size_megabytes():
    a = ReleaseAsset.from_github_api(_asset_data(size=5 * 1024 * 1024))
    assert a.format_size() == "5.0 MB"


def test_asset_format_size_gigabytes():
    a = ReleaseAsset.from_github_api(_asset_data(size=2 * 1024 * 1024 * 1024))
    assert a.format_size() == "2.00 GB"


def test_asset_format_size_fractional_gb():
    a = ReleaseAsset.from_github_api(_asset_data(size=int(1.5 * 1024 * 1024 * 1024)))
    assert a.format_size() == "1.50 GB"


# ---------------------------------------------------------------------------
# ReleaseAsset.format_display
# ---------------------------------------------------------------------------


def test_asset_format_display_plural_downloads():
    a = ReleaseAsset.from_github_api(_asset_data(name="app.zip", size=1024, download_count=42))
    display = a.format_display()
    assert "app.zip" in display
    assert "42 downloads" in display


def test_asset_format_display_singular_download():
    a = ReleaseAsset.from_github_api(_asset_data(name="app.zip", size=1024, download_count=1))
    assert "1 download" in a.format_display()
    assert "1 downloads" not in a.format_display()


def test_asset_format_display_zero_downloads():
    a = ReleaseAsset.from_github_api(_asset_data(name="app.zip", size=1024, download_count=0))
    assert "0 downloads" in a.format_display()


# ---------------------------------------------------------------------------
# Release.from_github_api
# ---------------------------------------------------------------------------


def test_release_from_api_id():
    r = Release.from_github_api(_release_data(id=55))
    assert r.id == 55


def test_release_from_api_tag_name():
    r = Release.from_github_api(_release_data(tag_name="v2.0.0"))
    assert r.tag_name == "v2.0.0"


def test_release_from_api_name():
    r = Release.from_github_api(_release_data(name="Version 2"))
    assert r.name == "Version 2"


def test_release_from_api_name_falls_back_to_tag_when_empty():
    r = Release.from_github_api(_release_data(name="", tag_name="v1.5"))
    assert r.name == "v1.5"


def test_release_from_api_name_falls_back_to_tag_when_none():
    r = Release.from_github_api(_release_data(name=None, tag_name="v1.5"))
    assert r.name == "v1.5"


def test_release_from_api_body():
    r = Release.from_github_api(_release_data(body="Changelog text"))
    assert r.body == "Changelog text"


def test_release_from_api_body_none_becomes_empty():
    r = Release.from_github_api(_release_data(body=None))
    assert r.body == ""


def test_release_from_api_draft_true():
    r = Release.from_github_api(_release_data(draft=True))
    assert r.draft is True


def test_release_from_api_prerelease_true():
    r = Release.from_github_api(_release_data(prerelease=True))
    assert r.prerelease is True


def test_release_from_api_author_login():
    r = Release.from_github_api(_release_data(author={"login": "bob"}))
    assert r.author_login == "bob"


def test_release_from_api_author_none():
    r = Release.from_github_api(_release_data(author=None))
    assert r.author_login == ""


def test_release_from_api_assets_parsed():
    r = Release.from_github_api(_release_data(assets=[
        _asset_data(name="windows.zip"),
        _asset_data(name="macos.dmg"),
    ]))
    assert len(r.assets) == 2
    assert r.assets[0].name == "windows.zip"


def test_release_from_api_no_assets():
    r = Release.from_github_api(_release_data(assets=[]))
    assert r.assets == []


def test_release_from_api_published_at_parsed():
    r = Release.from_github_api(_release_data(published_at="2026-02-01T10:00:00Z"))
    assert r.published_at is not None


def test_release_from_api_invalid_published_at():
    r = Release.from_github_api(_release_data(published_at="bad"))
    assert r.published_at is None


def test_release_from_api_invalid_created_at():
    r = Release.from_github_api(_release_data(created_at="bad"))
    assert r.created_at is None


# ---------------------------------------------------------------------------
# Release.get_status_label
# ---------------------------------------------------------------------------


def test_status_label_normal_release():
    r = Release.from_github_api(_release_data(draft=False, prerelease=False))
    assert r.get_status_label() == "Release"


def test_status_label_draft():
    r = Release.from_github_api(_release_data(draft=True, prerelease=False))
    assert r.get_status_label() == "Draft"


def test_status_label_prerelease():
    r = Release.from_github_api(_release_data(draft=False, prerelease=True))
    assert r.get_status_label() == "Pre-release"


def test_status_label_draft_and_prerelease():
    r = Release.from_github_api(_release_data(draft=True, prerelease=True))
    label = r.get_status_label()
    assert "Draft" in label
    assert "Pre-release" in label


# ---------------------------------------------------------------------------
# Release._format_relative_time
# ---------------------------------------------------------------------------


def test_release_relative_time_just_now():
    assert _release_aged(30)._format_relative_time() == "just now"


def test_release_relative_time_minutes():
    assert _release_aged(120)._format_relative_time() == "2m ago"


def test_release_relative_time_hours():
    assert _release_aged(7200)._format_relative_time() == "2h ago"


def test_release_relative_time_days():
    assert _release_aged(3 * 86400)._format_relative_time() == "3d ago"


def test_release_relative_time_weeks():
    assert _release_aged(14 * 86400)._format_relative_time() == "2w ago"


def test_release_relative_time_old_returns_date():
    r = _release_aged(35 * 86400)  # > 30 days → date
    result = r._format_relative_time()
    assert "-" in result and "ago" not in result


def test_release_relative_time_no_dates():
    r = Release.from_github_api(_release_data(published_at=None, created_at=None))
    assert r._format_relative_time() == ""


def test_release_relative_time_falls_back_to_created_at():
    # published_at is None but created_at is set
    ts = datetime.now(timezone.utc) - timedelta(seconds=120)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    r = Release.from_github_api(_release_data(published_at=None, created_at=iso))
    assert r._format_relative_time() == "2m ago"


# ---------------------------------------------------------------------------
# Release.format_display
# ---------------------------------------------------------------------------


def test_release_format_display_name_differs_from_tag():
    r = Release.from_github_api(_release_data(tag_name="v1.0", name="Version 1.0"))
    display = r.format_display()
    assert "v1.0" in display
    assert "Version 1.0" in display
    assert ":" in display


def test_release_format_display_name_same_as_tag():
    r = Release.from_github_api(_release_data(tag_name="v1.0", name="v1.0"))
    display = r.format_display()
    assert "v1.0" in display
    # When name == tag_name, no colon separator
    assert ": v1.0" not in display


def test_release_format_display_contains_status():
    r = Release.from_github_api(_release_data(draft=True))
    assert "Draft" in r.format_display()


def test_release_format_display_asset_count_plural():
    r = Release.from_github_api(_release_data(assets=[_asset_data(), _asset_data()]))
    assert "2 assets" in r.format_display()


def test_release_format_display_asset_count_singular():
    r = Release.from_github_api(_release_data(assets=[_asset_data()]))
    assert "1 asset" in r.format_display()
    assert "1 assets" not in r.format_display()


def test_release_format_display_no_assets():
    r = Release.from_github_api(_release_data(assets=[]))
    assert "0 assets" in r.format_display()


def test_release_format_display_includes_download_total():
    r = Release.from_github_api(_release_data(assets=[
        _asset_data(download_count=40),
        _asset_data(download_count=2),
    ]))
    assert "42 downloads" in r.format_display()


def test_release_format_display_download_total_singular():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=1)]))
    display = r.format_display()
    assert "1 download" in display
    assert "1 downloads" not in display


def test_release_format_display_zero_downloads_with_assets():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=0)]))
    assert "0 downloads" in r.format_display()


def test_release_format_display_omits_downloads_when_no_assets():
    # Nothing to download, so the count would only add noise.
    r = Release.from_github_api(_release_data(assets=[]))
    assert "download" not in r.format_display()


# ---------------------------------------------------------------------------
# Release.total_downloads
# ---------------------------------------------------------------------------


def test_total_downloads_sums_assets():
    r = Release.from_github_api(_release_data(assets=[
        _asset_data(download_count=10),
        _asset_data(download_count=25),
        _asset_data(download_count=7),
    ]))
    assert r.total_downloads == 42


def test_total_downloads_single_asset():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=5)]))
    assert r.total_downloads == 5


def test_total_downloads_no_assets_is_zero():
    r = Release.from_github_api(_release_data(assets=[]))
    assert r.total_downloads == 0


def test_total_downloads_all_zero():
    r = Release.from_github_api(_release_data(assets=[
        _asset_data(download_count=0),
        _asset_data(download_count=0),
    ]))
    assert r.total_downloads == 0


def test_total_downloads_missing_count_treated_as_zero():
    # ReleaseAsset defaults download_count to 0 when the API omits it.
    r = Release.from_github_api(_release_data(assets=[{}, _asset_data(download_count=3)]))
    assert r.total_downloads == 3


# ---------------------------------------------------------------------------
# Release.format_downloads
# ---------------------------------------------------------------------------


def test_format_downloads_plural():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=42)]))
    assert r.format_downloads() == "42 downloads"


def test_format_downloads_singular():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=1)]))
    assert r.format_downloads() == "1 download"


def test_format_downloads_zero_is_plural():
    r = Release.from_github_api(_release_data(assets=[_asset_data(download_count=0)]))
    assert r.format_downloads() == "0 downloads"
