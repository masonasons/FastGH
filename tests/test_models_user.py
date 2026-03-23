"""Tests for models/user.py — UserProfile parsing and display."""

import pytest
from datetime import datetime, timezone, timedelta

from models.user import UserProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_data(**overrides) -> dict:
    base = {
        "id": 1,
        "login": "alice",
        "name": "Alice Smith",
        "avatar_url": "https://avatars.githubusercontent.com/u/1",
        "html_url": "https://github.com/alice",
        "bio": "Open source developer",
        "company": "Acme Corp",
        "location": "New York",
        "email": "alice@example.com",
        "blog": "https://alice.dev",
        "twitter_username": "alice_dev",
        "public_repos": 30,
        "public_gists": 5,
        "followers": 100,
        "following": 50,
        "created_at": "2018-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "type": "User",
    }
    base.update(overrides)
    return base


def _profile_aged(seconds: int) -> UserProfile:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return UserProfile.from_github_api(_profile_data(created_at=iso))


# ---------------------------------------------------------------------------
# UserProfile.from_github_api
# ---------------------------------------------------------------------------


def test_profile_from_api_id():
    p = UserProfile.from_github_api(_profile_data(id=42))
    assert p.id == 42


def test_profile_from_api_login():
    p = UserProfile.from_github_api(_profile_data(login="bob"))
    assert p.login == "bob"


def test_profile_from_api_name():
    p = UserProfile.from_github_api(_profile_data(name="Bob Jones"))
    assert p.name == "Bob Jones"


def test_profile_from_api_name_none():
    p = UserProfile.from_github_api(_profile_data(name=None))
    assert p.name is None


def test_profile_from_api_bio():
    p = UserProfile.from_github_api(_profile_data(bio="Python enthusiast"))
    assert p.bio == "Python enthusiast"


def test_profile_from_api_bio_none():
    p = UserProfile.from_github_api(_profile_data(bio=None))
    assert p.bio is None


def test_profile_from_api_company():
    p = UserProfile.from_github_api(_profile_data(company="BigCo"))
    assert p.company == "BigCo"


def test_profile_from_api_location():
    p = UserProfile.from_github_api(_profile_data(location="London"))
    assert p.location == "London"


def test_profile_from_api_email():
    p = UserProfile.from_github_api(_profile_data(email="bob@example.com"))
    assert p.email == "bob@example.com"


def test_profile_from_api_blog():
    p = UserProfile.from_github_api(_profile_data(blog="https://bob.io"))
    assert p.blog == "https://bob.io"


def test_profile_from_api_twitter_username():
    p = UserProfile.from_github_api(_profile_data(twitter_username="bobdev"))
    assert p.twitter_username == "bobdev"


def test_profile_from_api_public_repos():
    p = UserProfile.from_github_api(_profile_data(public_repos=15))
    assert p.public_repos == 15


def test_profile_from_api_followers():
    p = UserProfile.from_github_api(_profile_data(followers=200))
    assert p.followers == 200


def test_profile_from_api_following():
    p = UserProfile.from_github_api(_profile_data(following=75))
    assert p.following == 75


def test_profile_from_api_type_user():
    p = UserProfile.from_github_api(_profile_data(type="User"))
    assert p.type == "User"


def test_profile_from_api_type_organization():
    p = UserProfile.from_github_api(_profile_data(type="Organization"))
    assert p.type == "Organization"


def test_profile_from_api_created_at_parsed():
    p = UserProfile.from_github_api(_profile_data(created_at="2020-06-15T12:00:00Z"))
    assert p.created_at is not None
    assert p.created_at.year == 2020
    assert p.created_at.month == 6


def test_profile_from_api_updated_at_parsed():
    p = UserProfile.from_github_api(_profile_data(updated_at="2026-01-01T00:00:00Z"))
    assert p.updated_at is not None


def test_profile_from_api_invalid_created_at():
    p = UserProfile.from_github_api(_profile_data(created_at="not-a-date"))
    assert p.created_at is None


def test_profile_from_api_invalid_updated_at():
    p = UserProfile.from_github_api(_profile_data(updated_at="not-a-date"))
    assert p.updated_at is None


def test_profile_from_api_missing_fields_use_defaults():
    p = UserProfile.from_github_api({})
    assert p.id == 0
    assert p.login == ""
    assert p.name is None
    assert p.bio is None
    assert p.public_repos == 0
    assert p.followers == 0
    assert p.type == "User"
    assert p.created_at is None


# ---------------------------------------------------------------------------
# UserProfile.display_name
# ---------------------------------------------------------------------------


def test_display_name_uses_name_when_present():
    p = UserProfile.from_github_api(_profile_data(login="alice", name="Alice Smith"))
    assert p.display_name == "Alice Smith"


def test_display_name_falls_back_to_login_when_name_none():
    p = UserProfile.from_github_api(_profile_data(login="alice", name=None))
    assert p.display_name == "alice"


def test_display_name_falls_back_to_login_when_name_empty():
    p = UserProfile.from_github_api(_profile_data(login="alice", name=""))
    # empty string is falsy → falls back to login
    assert p.display_name == "alice"


# ---------------------------------------------------------------------------
# UserProfile.format_display
# ---------------------------------------------------------------------------


def test_format_display_login_only():
    p = UserProfile.from_github_api(_profile_data(login="alice", name=None, bio=None))
    assert p.format_display() == "alice"


def test_format_display_with_name():
    p = UserProfile.from_github_api(_profile_data(login="alice", name="Alice Smith", bio=None))
    display = p.format_display()
    assert "alice" in display
    assert "Alice Smith" in display


def test_format_display_with_bio():
    p = UserProfile.from_github_api(_profile_data(login="alice", bio="Python dev"))
    display = p.format_display()
    assert "Python dev" in display


def test_format_display_long_bio_truncated_at_50():
    long_bio = "X" * 60
    p = UserProfile.from_github_api(_profile_data(bio=long_bio))
    display = p.format_display()
    assert "X" * 50 in display
    assert "..." in display
    assert "X" * 51 not in display


def test_format_display_bio_with_newlines_replaced():
    p = UserProfile.from_github_api(_profile_data(bio="Line one\nLine two"))
    display = p.format_display()
    assert "\n" not in display


def test_format_display_exact_50_char_bio_not_truncated():
    bio = "B" * 50
    p = UserProfile.from_github_api(_profile_data(bio=bio))
    display = p.format_display()
    assert "..." not in display
    assert "B" * 50 in display


# ---------------------------------------------------------------------------
# UserProfile._format_relative_time — singular and plural
# ---------------------------------------------------------------------------


def test_user_relative_time_just_now():
    p = _profile_aged(20)
    assert p._format_relative_time(p.created_at) == "just now"


def test_user_relative_time_1_minute():
    p = _profile_aged(90)
    assert p._format_relative_time(p.created_at) == "1 minute ago"


def test_user_relative_time_plural_minutes():
    p = _profile_aged(180)
    assert p._format_relative_time(p.created_at) == "3 minutes ago"


def test_user_relative_time_1_hour():
    p = _profile_aged(3700)
    assert p._format_relative_time(p.created_at) == "1 hour ago"


def test_user_relative_time_plural_hours():
    p = _profile_aged(7400)
    assert p._format_relative_time(p.created_at) == "2 hours ago"


def test_user_relative_time_1_day():
    p = _profile_aged(86500)
    assert p._format_relative_time(p.created_at) == "1 day ago"


def test_user_relative_time_plural_days():
    p = _profile_aged(3 * 86400)
    assert p._format_relative_time(p.created_at) == "3 days ago"


def test_user_relative_time_1_month():
    p = _profile_aged(35 * 86400)
    assert p._format_relative_time(p.created_at) == "1 month ago"


def test_user_relative_time_plural_months():
    p = _profile_aged(70 * 86400)
    assert p._format_relative_time(p.created_at) == "2 months ago"


def test_user_relative_time_1_year():
    p = _profile_aged(400 * 86400)
    assert p._format_relative_time(p.created_at) == "1 year ago"


def test_user_relative_time_plural_years():
    p = _profile_aged(800 * 86400)
    assert p._format_relative_time(p.created_at) == "2 years ago"


def test_user_relative_time_none_returns_unknown():
    p = UserProfile.from_github_api(_profile_data())
    assert p._format_relative_time(None) == "Unknown"
