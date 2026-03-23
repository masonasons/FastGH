"""Tests for models/notification.py — Notification and NotificationSubject."""

import pytest
from datetime import datetime, timezone, timedelta

from models.notification import Notification, NotificationSubject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _subject_data(**overrides) -> dict:
    base = {
        "title": "Fix the bug",
        "url": "https://api.github.com/repos/owner/repo/issues/42",
        "type": "Issue",
        "latest_comment_url": "https://api.github.com/repos/owner/repo/issues/comments/999",
    }
    base.update(overrides)
    return base


def _notif_data(**overrides) -> dict:
    base = {
        "id": "12345",
        "unread": True,
        "reason": "mention",
        "subject": _subject_data(),
        "repository": {
            "full_name": "owner/repo",
            "name": "repo",
            "owner": {"login": "owner"},
        },
        "updated_at": "2026-03-20T10:00:00Z",
        "last_read_at": "2026-03-19T08:00:00Z",
        "url": "https://api.github.com/notifications/threads/12345",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# NotificationSubject.from_api
# ---------------------------------------------------------------------------


def test_subject_from_api_title():
    s = NotificationSubject.from_api(_subject_data(title="My issue"))
    assert s.title == "My issue"


def test_subject_from_api_url():
    url = "https://api.github.com/repos/x/y/issues/1"
    s = NotificationSubject.from_api(_subject_data(url=url))
    assert s.url == url


def test_subject_from_api_type():
    s = NotificationSubject.from_api(_subject_data(type="PullRequest"))
    assert s.type == "PullRequest"


def test_subject_from_api_latest_comment_url():
    url = "https://api.github.com/repos/x/y/issues/comments/5"
    s = NotificationSubject.from_api(_subject_data(latest_comment_url=url))
    assert s.latest_comment_url == url


def test_subject_from_api_latest_comment_url_none():
    s = NotificationSubject.from_api(_subject_data(latest_comment_url=None))
    assert s.latest_comment_url is None


def test_subject_from_api_empty_dict():
    s = NotificationSubject.from_api({})
    assert s.title == ""
    assert s.url == ""
    assert s.type == ""
    assert s.latest_comment_url is None


# ---------------------------------------------------------------------------
# Notification.from_api — field mapping
# ---------------------------------------------------------------------------


def test_notification_from_api_id():
    n = Notification.from_api(_notif_data(id="99"))
    assert n.id == "99"


def test_notification_from_api_unread_true():
    n = Notification.from_api(_notif_data(unread=True))
    assert n.unread is True


def test_notification_from_api_unread_false():
    n = Notification.from_api(_notif_data(unread=False))
    assert n.unread is False


def test_notification_from_api_reason():
    n = Notification.from_api(_notif_data(reason="assign"))
    assert n.reason == "assign"


def test_notification_from_api_repository_fields():
    n = Notification.from_api(_notif_data())
    assert n.repository_full_name == "owner/repo"
    assert n.repository_name == "repo"
    assert n.repository_owner == "owner"


def test_notification_from_api_url():
    url = "https://api.github.com/notifications/threads/5"
    n = Notification.from_api(_notif_data(url=url))
    assert n.url == url


# ---------------------------------------------------------------------------
# Notification.from_api — datetime parsing
# ---------------------------------------------------------------------------


def test_notification_from_api_updated_at_parsed():
    n = Notification.from_api(_notif_data(updated_at="2026-01-15T12:30:00Z"))
    assert n.updated_at is not None
    assert n.updated_at.year == 2026
    assert n.updated_at.month == 1
    assert n.updated_at.day == 15


def test_notification_from_api_last_read_at_parsed():
    n = Notification.from_api(_notif_data(last_read_at="2026-01-14T09:00:00Z"))
    assert n.last_read_at is not None
    assert n.last_read_at.year == 2026


def test_notification_from_api_updated_at_none_when_absent():
    n = Notification.from_api(_notif_data(updated_at=None))
    assert n.updated_at is None


def test_notification_from_api_last_read_at_none_when_absent():
    n = Notification.from_api(_notif_data(last_read_at=None))
    assert n.last_read_at is None


def test_notification_from_api_invalid_datetime_gives_none():
    n = Notification.from_api(_notif_data(updated_at="not-a-date"))
    assert n.updated_at is None


def test_notification_from_api_missing_repository_uses_defaults():
    data = _notif_data()
    del data["repository"]
    n = Notification.from_api(data)
    assert n.repository_full_name == ""
    assert n.repository_name == ""
    assert n.repository_owner == ""


# ---------------------------------------------------------------------------
# get_reason_display
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason,expected", [
    ("assign", "You were assigned"),
    ("author", "You created the thread"),
    ("comment", "You commented"),
    ("ci_activity", "CI activity"),
    ("invitation", "You were invited"),
    ("manual", "You subscribed manually"),
    ("mention", "You were @mentioned"),
    ("review_requested", "Review requested"),
    ("security_alert", "Security alert"),
    ("state_change", "State changed"),
    ("subscribed", "You're watching the repo"),
    ("team_mention", "Your team was @mentioned"),
])
def test_get_reason_display_known(reason, expected):
    n = Notification.from_api(_notif_data(reason=reason))
    assert n.get_reason_display() == expected


def test_get_reason_display_unknown_returns_raw():
    n = Notification.from_api(_notif_data(reason="some_future_reason"))
    assert n.get_reason_display() == "some_future_reason"


# ---------------------------------------------------------------------------
# _get_type_icon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("subject_type,expected_icon", [
    ("Issue", "Issue"),
    ("PullRequest", "PR"),
    ("Commit", "Commit"),
    ("Release", "Release"),
    ("Discussion", "Disc"),
    ("RepositoryVulnerabilityAlert", "Security"),
])
def test_get_type_icon_known_types(subject_type, expected_icon):
    n = Notification.from_api(_notif_data(subject=_subject_data(type=subject_type)))
    assert n._get_type_icon() == expected_icon


def test_get_type_icon_unknown_type_returns_raw():
    n = Notification.from_api(_notif_data(subject=_subject_data(type="SomeNewType")))
    assert n._get_type_icon() == "SomeNewType"


# ---------------------------------------------------------------------------
# format_display
# ---------------------------------------------------------------------------


def test_format_display_unread_has_filled_bullet():
    n = Notification.from_api(_notif_data(unread=True))
    assert n.format_display().startswith("● ")


def test_format_display_read_has_empty_bullet():
    n = Notification.from_api(_notif_data(unread=False))
    assert n.format_display().startswith("○ ")


def test_format_display_contains_subject_title():
    n = Notification.from_api(_notif_data(subject=_subject_data(title="My Important Issue")))
    assert "My Important Issue" in n.format_display()


def test_format_display_contains_repo_name():
    n = Notification.from_api(_notif_data())
    assert "owner/repo" in n.format_display()


def test_format_display_contains_reason():
    n = Notification.from_api(_notif_data(reason="mention"))
    assert "mentioned" in n.format_display().lower()


def test_format_display_no_timestamp_shows_unknown():
    n = Notification.from_api(_notif_data(updated_at=None))
    assert "Unknown" in n.format_display()


def test_format_display_with_timestamp_shows_date():
    n = Notification.from_api(_notif_data(updated_at="2026-03-20T10:00:00Z"))
    display = n.format_display()
    assert "2026" in display


# ---------------------------------------------------------------------------
# get_web_url
# ---------------------------------------------------------------------------


def test_get_web_url_issue_converts_api_to_web():
    n = Notification.from_api(_notif_data(subject=_subject_data(
        url="https://api.github.com/repos/owner/repo/issues/42"
    )))
    assert n.get_web_url() == "https://github.com/owner/repo/issues/42"


def test_get_web_url_pr_converts_pulls_to_pull():
    n = Notification.from_api(_notif_data(subject=_subject_data(
        url="https://api.github.com/repos/owner/repo/pulls/7"
    )))
    assert n.get_web_url() == "https://github.com/owner/repo/pull/7"


def test_get_web_url_no_subject_url_falls_back_to_repo():
    n = Notification.from_api(_notif_data(subject=_subject_data(url="")))
    assert n.get_web_url() == "https://github.com/owner/repo"


# ---------------------------------------------------------------------------
# _format_relative_time
# ---------------------------------------------------------------------------


def _notif_with_age(seconds: int) -> Notification:
    """Create a notification with updated_at set to `seconds` ago."""
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return Notification.from_api(_notif_data(updated_at=iso))


def test_format_relative_time_just_now():
    n = _notif_with_age(30)
    assert n._format_relative_time() == "Just now"


def test_format_relative_time_minutes():
    n = _notif_with_age(90)  # 1.5 minutes
    assert n._format_relative_time() == "1m ago"


def test_format_relative_time_hours():
    n = _notif_with_age(7200)  # 2 hours
    assert n._format_relative_time() == "2h ago"


def test_format_relative_time_days():
    n = _notif_with_age(3 * 86400)  # 3 days
    assert n._format_relative_time() == "3d ago"


def test_format_relative_time_months():
    n = _notif_with_age(45 * 86400)  # ~45 days → 1 month
    assert n._format_relative_time() == "1mo ago"


def test_format_relative_time_years():
    n = _notif_with_age(400 * 86400)  # >1 year
    assert n._format_relative_time() == "1y ago"


def test_format_relative_time_no_timestamp_returns_unknown():
    n = Notification.from_api(_notif_data(updated_at=None))
    assert n._format_relative_time() == "Unknown"
