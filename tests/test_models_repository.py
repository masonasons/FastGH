"""Tests for models/repository.py — Repository parsing and display."""

import pytest
from datetime import datetime, timezone, timedelta

from models.repository import Repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_data(**overrides) -> dict:
    base = {
        "id": 1,
        "name": "MyRepo",
        "full_name": "owner/MyRepo",
        "description": "A great project",
        "owner": {"login": "owner"},
        "stargazers_count": 100,
        "forks_count": 10,
        "open_issues_count": 5,
        "language": "Python",
        "updated_at": "2026-01-10T10:00:00Z",
        "pushed_at": "2026-01-15T12:00:00Z",
        "url": "https://api.github.com/repos/owner/MyRepo",
        "html_url": "https://github.com/owner/MyRepo",
        "private": False,
    }
    base.update(overrides)
    return base


def _repo_aged(seconds: int) -> Repository:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return Repository.from_github_api(_repo_data(pushed_at=iso))


# ---------------------------------------------------------------------------
# Repository.from_github_api
# ---------------------------------------------------------------------------


def test_repo_from_api_id():
    r = Repository.from_github_api(_repo_data(id=42))
    assert r.id == 42


def test_repo_from_api_name():
    r = Repository.from_github_api(_repo_data(name="FastGH"))
    assert r.name == "FastGH"


def test_repo_from_api_full_name():
    r = Repository.from_github_api(_repo_data(full_name="org/FastGH"))
    assert r.full_name == "org/FastGH"


def test_repo_from_api_description():
    r = Repository.from_github_api(_repo_data(description="A fast GitHub client"))
    assert r.description == "A fast GitHub client"


def test_repo_from_api_description_none():
    r = Repository.from_github_api(_repo_data(description=None))
    assert r.description is None


def test_repo_from_api_owner():
    r = Repository.from_github_api(_repo_data(owner={"login": "myorg"}))
    assert r.owner == "myorg"


def test_repo_from_api_stars():
    r = Repository.from_github_api(_repo_data(stargazers_count=500))
    assert r.stars == 500


def test_repo_from_api_forks():
    r = Repository.from_github_api(_repo_data(forks_count=25))
    assert r.forks == 25


def test_repo_from_api_open_issues():
    r = Repository.from_github_api(_repo_data(open_issues_count=3))
    assert r.open_issues == 3


def test_repo_from_api_language():
    r = Repository.from_github_api(_repo_data(language="Go"))
    assert r.language == "Go"


def test_repo_from_api_language_none():
    r = Repository.from_github_api(_repo_data(language=None))
    assert r.language is None


def test_repo_from_api_private_true():
    r = Repository.from_github_api(_repo_data(private=True))
    assert r.private is True


def test_repo_from_api_private_false():
    r = Repository.from_github_api(_repo_data(private=False))
    assert r.private is False


def test_repo_from_api_html_url():
    url = "https://github.com/x/y"
    r = Repository.from_github_api(_repo_data(html_url=url))
    assert r.html_url == url


def test_repo_from_api_updated_at_parsed():
    r = Repository.from_github_api(_repo_data(updated_at="2026-02-01T08:00:00Z"))
    assert r.updated_at is not None
    assert r.updated_at.year == 2026


def test_repo_from_api_pushed_at_parsed():
    r = Repository.from_github_api(_repo_data(pushed_at="2026-03-01T09:00:00Z"))
    assert r.pushed_at is not None


def test_repo_from_api_invalid_updated_at():
    r = Repository.from_github_api(_repo_data(updated_at="bad"))
    assert r.updated_at is None


def test_repo_from_api_invalid_pushed_at():
    r = Repository.from_github_api(_repo_data(pushed_at="bad"))
    assert r.pushed_at is None


def test_repo_from_api_missing_dates():
    data = _repo_data()
    data.pop("updated_at")
    data.pop("pushed_at")
    r = Repository.from_github_api(data)
    assert r.updated_at is None
    assert r.pushed_at is None


# ---------------------------------------------------------------------------
# Repository.format_display
# ---------------------------------------------------------------------------


def test_format_display_contains_full_name():
    r = Repository.from_github_api(_repo_data(full_name="org/proj"))
    assert "org/proj" in r.format_display()


def test_format_display_contains_description():
    r = Repository.from_github_api(_repo_data(description="A cool tool"))
    assert "A cool tool" in r.format_display()


def test_format_display_no_description_shows_fallback():
    r = Repository.from_github_api(_repo_data(description=None))
    assert "No description" in r.format_display()


def test_format_display_long_description_truncated():
    long_desc = "A" * 100
    r = Repository.from_github_api(_repo_data(description=long_desc))
    display = r.format_display()
    assert "..." in display
    # truncated to 77 chars + "..."
    assert "A" * 78 not in display


def test_format_display_contains_stars():
    r = Repository.from_github_api(_repo_data(stargazers_count=42))
    assert "42" in r.format_display()


def test_format_display_contains_language():
    r = Repository.from_github_api(_repo_data(language="Rust"))
    assert "Rust" in r.format_display()


def test_format_display_no_language_shows_unknown():
    r = Repository.from_github_api(_repo_data(language=None))
    assert "Unknown" in r.format_display()


def test_format_display_no_pushed_at_shows_unknown():
    data = _repo_data()
    data["pushed_at"] = None
    r = Repository.from_github_api(data)
    assert "Unknown" in r.format_display()


# ---------------------------------------------------------------------------
# Repository.format_single_line
# ---------------------------------------------------------------------------


def test_format_single_line_contains_full_name():
    r = Repository.from_github_api(_repo_data(full_name="org/proj"))
    assert "org/proj" in r.format_single_line()


def test_format_single_line_contains_stars():
    r = Repository.from_github_api(_repo_data(stargazers_count=77))
    assert "77" in r.format_single_line()


def test_format_single_line_contains_language():
    r = Repository.from_github_api(_repo_data(language="TypeScript"))
    assert "TypeScript" in r.format_single_line()


def test_format_single_line_no_language_shows_unknown():
    r = Repository.from_github_api(_repo_data(language=None))
    assert "Unknown" in r.format_single_line()


def test_format_single_line_no_pushed_at_shows_unknown():
    data = _repo_data()
    data["pushed_at"] = None
    r = Repository.from_github_api(data)
    assert "Unknown" in r.format_single_line()


def test_format_single_line_with_pushed_at_shows_date():
    r = Repository.from_github_api(_repo_data(pushed_at="2026-03-01T10:00:00Z"))
    assert "2026" in r.format_single_line()


# ---------------------------------------------------------------------------
# Repository._format_relative_time — singular and plural
# ---------------------------------------------------------------------------


def test_repo_relative_time_just_now():
    assert _repo_aged(20)._format_relative_time() == "just now"


def test_repo_relative_time_1_minute():
    assert _repo_aged(90)._format_relative_time() == "1 minute ago"


def test_repo_relative_time_plural_minutes():
    assert _repo_aged(180)._format_relative_time() == "3 minutes ago"


def test_repo_relative_time_1_hour():
    assert _repo_aged(3700)._format_relative_time() == "1 hour ago"


def test_repo_relative_time_plural_hours():
    assert _repo_aged(7400)._format_relative_time() == "2 hours ago"


def test_repo_relative_time_1_day():
    assert _repo_aged(86500)._format_relative_time() == "1 day ago"


def test_repo_relative_time_plural_days():
    assert _repo_aged(3 * 86400)._format_relative_time() == "3 days ago"


def test_repo_relative_time_1_month():
    assert _repo_aged(35 * 86400)._format_relative_time() == "1 month ago"


def test_repo_relative_time_plural_months():
    assert _repo_aged(70 * 86400)._format_relative_time() == "2 months ago"


def test_repo_relative_time_1_year():
    assert _repo_aged(400 * 86400)._format_relative_time() == "1 year ago"


def test_repo_relative_time_plural_years():
    assert _repo_aged(800 * 86400)._format_relative_time() == "2 years ago"


def test_repo_relative_time_no_pushed_at():
    data = _repo_data()
    data["pushed_at"] = None
    r = Repository.from_github_api(data)
    assert r._format_relative_time() == "Unknown"


# ---------------------------------------------------------------------------
# Fork / upstream parent parsing
# ---------------------------------------------------------------------------


def test_repo_not_a_fork_by_default():
    r = Repository.from_github_api(_repo_data())
    assert r.is_fork is False
    assert r.parent_full_name is None


def test_repo_is_fork_flag_parsed():
    r = Repository.from_github_api(_repo_data(fork=True))
    assert r.is_fork is True


def test_repo_parent_full_name_parsed():
    r = Repository.from_github_api(_repo_data(
        fork=True,
        parent={"full_name": "upstream/MyRepo", "owner": {"login": "upstream"}},
    ))
    assert r.is_fork is True
    assert r.parent_full_name == "upstream/MyRepo"


def test_repo_parent_absent_gives_none():
    # A fork fetched from a list has `fork` but no `parent` object.
    r = Repository.from_github_api(_repo_data(fork=True))
    assert r.parent_full_name is None


def test_repo_parent_none_value_is_safe():
    r = Repository.from_github_api(_repo_data(fork=False, parent=None))
    assert r.parent_full_name is None
