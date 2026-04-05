"""Tests for models/issue.py — User, Label, Comment, Issue, PullRequest."""

import pytest
from datetime import datetime, timezone, timedelta

from models.issue import Comment, Issue, Label, PullRequest, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_data(**overrides) -> dict:
    base = {"login": "alice", "id": 1, "avatar_url": "https://example.com/avatar.png"}
    base.update(overrides)
    return base


def _label_data(**overrides) -> dict:
    base = {"name": "bug", "color": "d73a4a", "description": "Something broken"}
    base.update(overrides)
    return base


def _comment_data(**overrides) -> dict:
    base = {
        "id": 10,
        "body": "Looks good!",
        "user": _user_data(),
        "created_at": "2026-01-01T10:00:00Z",
        "updated_at": "2026-01-01T10:05:00Z",
        "html_url": "https://github.com/owner/repo/issues/1#issuecomment-10",
    }
    base.update(overrides)
    return base


def _issue_data(**overrides) -> dict:
    base = {
        "id": 100,
        "number": 1,
        "title": "Fix the bug",
        "body": "Details here",
        "state": "open",
        "user": _user_data(),
        "labels": [],
        "assignees": [],
        "comments": 3,
        "created_at": "2026-01-01T09:00:00Z",
        "updated_at": "2026-01-02T09:00:00Z",
        "closed_at": None,
        "html_url": "https://github.com/owner/repo/issues/1",
    }
    base.update(overrides)
    return base


def _pr_data(**overrides) -> dict:
    base = {
        "id": 200,
        "number": 5,
        "title": "Add feature",
        "body": "Description",
        "state": "open",
        "user": _user_data(),
        "labels": [],
        "assignees": [],
        "head": {"ref": "feature/x"},
        "base": {"ref": "main"},
        "merged": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "merged_by": None,
        "merged_at": None,
        "comments": 2,
        "commits": 3,
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
        "created_at": "2026-02-01T09:00:00Z",
        "updated_at": "2026-02-02T09:00:00Z",
        "closed_at": None,
        "html_url": "https://github.com/owner/repo/pull/5",
        "draft": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# User (from issue.py)
# ---------------------------------------------------------------------------


def test_user_from_api_login():
    u = User.from_github_api(_user_data(login="bob"))
    assert u.login == "bob"


def test_user_from_api_id():
    u = User.from_github_api(_user_data(id=42))
    assert u.id == 42


def test_user_from_api_avatar_url():
    u = User.from_github_api(_user_data(avatar_url="https://x.com/img.png"))
    assert u.avatar_url == "https://x.com/img.png"


def test_user_from_api_empty_dict_returns_unknown():
    u = User.from_github_api({})
    assert u.login == "unknown"
    assert u.id == 0


def test_user_from_api_none_returns_unknown():
    u = User.from_github_api(None)
    assert u.login == "unknown"


def test_user_from_api_missing_login_defaults():
    u = User.from_github_api({"id": 5})
    assert u.login == "unknown"


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------


def test_label_from_api_name():
    l = Label.from_github_api(_label_data(name="enhancement"))
    assert l.name == "enhancement"


def test_label_from_api_color():
    l = Label.from_github_api(_label_data(color="0075ca"))
    assert l.color == "0075ca"


def test_label_from_api_description():
    l = Label.from_github_api(_label_data(description="New feature request"))
    assert l.description == "New feature request"


def test_label_from_api_missing_fields():
    l = Label.from_github_api({})
    assert l.name == ""
    assert l.color == ""
    assert l.description == ""


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


def test_comment_from_api_id():
    c = Comment.from_github_api(_comment_data(id=99))
    assert c.id == 99


def test_comment_from_api_body():
    c = Comment.from_github_api(_comment_data(body="LGTM"))
    assert c.body == "LGTM"


def test_comment_from_api_html_url():
    url = "https://github.com/x/y/issues/1#issuecomment-5"
    c = Comment.from_github_api(_comment_data(html_url=url))
    assert c.html_url == url


def test_comment_from_api_created_at_parsed():
    c = Comment.from_github_api(_comment_data(created_at="2026-03-15T08:00:00Z"))
    assert c.created_at is not None
    assert c.created_at.year == 2026
    assert c.created_at.month == 3


def test_comment_from_api_updated_at_parsed():
    c = Comment.from_github_api(_comment_data(updated_at="2026-03-16T10:00:00Z"))
    assert c.updated_at is not None


def test_comment_from_api_invalid_created_at():
    c = Comment.from_github_api(_comment_data(created_at="bad"))
    assert c.created_at is None


def test_comment_from_api_invalid_updated_at():
    c = Comment.from_github_api(_comment_data(updated_at="bad"))
    assert c.updated_at is None


def test_comment_from_api_user():
    c = Comment.from_github_api(_comment_data(user={"login": "bob", "id": 2, "avatar_url": ""}))
    assert c.user.login == "bob"


# ---------------------------------------------------------------------------
# Issue.from_github_api
# ---------------------------------------------------------------------------


def test_issue_from_api_number():
    i = Issue.from_github_api(_issue_data(number=42))
    assert i.number == 42


def test_issue_from_api_title():
    i = Issue.from_github_api(_issue_data(title="Memory leak"))
    assert i.title == "Memory leak"


def test_issue_from_api_state_open():
    i = Issue.from_github_api(_issue_data(state="open"))
    assert i.state == "open"


def test_issue_from_api_state_closed():
    i = Issue.from_github_api(_issue_data(state="closed"))
    assert i.state == "closed"


def test_issue_from_api_body():
    i = Issue.from_github_api(_issue_data(body="Steps to reproduce"))
    assert i.body == "Steps to reproduce"


def test_issue_from_api_body_none():
    i = Issue.from_github_api(_issue_data(body=None))
    assert i.body is None


def test_issue_from_api_labels_parsed():
    i = Issue.from_github_api(_issue_data(labels=[
        {"name": "bug", "color": "red", "description": ""},
        {"name": "help wanted", "color": "green", "description": ""},
    ]))
    assert len(i.labels) == 2
    assert i.labels[0].name == "bug"
    assert i.labels[1].name == "help wanted"


def test_issue_from_api_no_labels():
    i = Issue.from_github_api(_issue_data(labels=[]))
    assert i.labels == []


def test_issue_from_api_assignees_parsed():
    i = Issue.from_github_api(_issue_data(assignees=[
        {"login": "alice", "id": 1, "avatar_url": ""},
        {"login": "bob", "id": 2, "avatar_url": ""},
    ]))
    assert len(i.assignees) == 2
    assert i.assignees[0].login == "alice"


def test_issue_from_api_comments_count():
    i = Issue.from_github_api(_issue_data(comments=7))
    assert i.comments_count == 7


def test_issue_from_api_created_at_parsed():
    i = Issue.from_github_api(_issue_data(created_at="2026-01-15T12:00:00Z"))
    assert i.created_at is not None
    assert i.created_at.year == 2026


def test_issue_from_api_closed_at_parsed():
    i = Issue.from_github_api(_issue_data(
        state="closed", closed_at="2026-01-20T15:00:00Z"
    ))
    assert i.closed_at is not None


def test_issue_from_api_closed_at_none():
    i = Issue.from_github_api(_issue_data(closed_at=None))
    assert i.closed_at is None


def test_issue_from_api_invalid_created_at():
    i = Issue.from_github_api(_issue_data(created_at="bad"))
    assert i.created_at is None


def test_issue_from_api_invalid_updated_at():
    i = Issue.from_github_api(_issue_data(updated_at="bad"))
    assert i.updated_at is None


def test_issue_from_api_invalid_closed_at():
    i = Issue.from_github_api(_issue_data(closed_at="bad"))
    assert i.closed_at is None


def test_issue_from_api_not_a_pr():
    i = Issue.from_github_api(_issue_data())
    assert i.is_pull_request is False


def test_issue_from_api_is_pr_when_pull_request_key_present():
    data = _issue_data()
    data["pull_request"] = {"url": "https://api.github.com/repos/x/y/pulls/1"}
    i = Issue.from_github_api(data)
    assert i.is_pull_request is True


# ---------------------------------------------------------------------------
# Issue.format_display
# ---------------------------------------------------------------------------


def test_issue_format_display_open():
    i = Issue.from_github_api(_issue_data(state="open", title="Bug", number=3))
    assert "[Open]" in i.format_display()
    assert "#3" in i.format_display()
    assert "Bug" in i.format_display()


def test_issue_format_display_closed():
    i = Issue.from_github_api(_issue_data(state="closed", title="Fixed", number=4))
    assert "[Closed]" in i.format_display()


def test_issue_format_display_with_labels():
    i = Issue.from_github_api(_issue_data(labels=[
        {"name": "bug", "color": "", "description": ""},
        {"name": "urgent", "color": "", "description": ""},
    ]))
    display = i.format_display()
    assert "bug" in display
    assert "urgent" in display


def test_issue_format_display_no_labels_has_no_brackets():
    i = Issue.from_github_api(_issue_data(labels=[]))
    # labels_part should be empty, no extra brackets
    assert i.format_display().count("[") == 1  # only the state icon


def test_issue_format_display_contains_user():
    i = Issue.from_github_api(_issue_data(user={"login": "carol", "id": 3, "avatar_url": ""}))
    assert "carol" in i.format_display()


# ---------------------------------------------------------------------------
# Issue._format_relative_time — singular and plural
# ---------------------------------------------------------------------------


def _dt_ago(seconds: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def test_issue_relative_time_just_now():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(30)) == "just now"


def test_issue_relative_time_1_minute():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(90)) == "1 minute ago"


def test_issue_relative_time_plural_minutes():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(180)) == "3 minutes ago"


def test_issue_relative_time_1_hour():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(3700)) == "1 hour ago"


def test_issue_relative_time_plural_hours():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(7400)) == "2 hours ago"


def test_issue_relative_time_1_day():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(86500)) == "1 day ago"


def test_issue_relative_time_plural_days():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(3 * 86400)) == "3 days ago"


def test_issue_relative_time_1_month():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(35 * 86400)) == "1 month ago"


def test_issue_relative_time_plural_months():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(70 * 86400)) == "2 months ago"


def test_issue_relative_time_1_year():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(400 * 86400)) == "1 year ago"


def test_issue_relative_time_plural_years():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(_dt_ago(800 * 86400)) == "2 years ago"


def test_issue_relative_time_none():
    i = Issue.from_github_api(_issue_data())
    assert i._format_relative_time(None) == "Unknown"


# ---------------------------------------------------------------------------
# PullRequest.from_github_api
# ---------------------------------------------------------------------------


def test_pr_from_api_number():
    pr = PullRequest.from_github_api(_pr_data(number=10))
    assert pr.number == 10


def test_pr_from_api_title():
    pr = PullRequest.from_github_api(_pr_data(title="Refactor auth"))
    assert pr.title == "Refactor auth"


def test_pr_from_api_head_ref():
    pr = PullRequest.from_github_api(_pr_data(head={"ref": "feature/login"}))
    assert pr.head_ref == "feature/login"


def test_pr_from_api_base_ref():
    pr = PullRequest.from_github_api(_pr_data(base={"ref": "develop"}))
    assert pr.base_ref == "develop"


def test_pr_from_api_missing_head_base():
    data = _pr_data()
    del data["head"]
    del data["base"]
    pr = PullRequest.from_github_api(data)
    assert pr.head_ref == ""
    assert pr.base_ref == ""


def test_pr_from_api_merged_true():
    pr = PullRequest.from_github_api(_pr_data(merged=True, state="closed"))
    assert pr.merged is True


def test_pr_from_api_merged_false():
    pr = PullRequest.from_github_api(_pr_data(merged=False))
    assert pr.merged is False


def test_pr_from_api_draft():
    pr = PullRequest.from_github_api(_pr_data(draft=True))
    assert pr.draft is True


def test_pr_from_api_merged_by():
    pr = PullRequest.from_github_api(_pr_data(
        merged_by={"login": "reviewer", "id": 5, "avatar_url": ""},
        merged=True,
        state="closed",
    ))
    assert pr.merged_by is not None
    assert pr.merged_by.login == "reviewer"


def test_pr_from_api_merged_by_none():
    pr = PullRequest.from_github_api(_pr_data(merged_by=None))
    assert pr.merged_by is None


def test_pr_from_api_merged_at_parsed():
    pr = PullRequest.from_github_api(_pr_data(merged_at="2026-02-15T14:00:00Z"))
    assert pr.merged_at is not None


def test_pr_from_api_stats():
    pr = PullRequest.from_github_api(_pr_data(additions=50, deletions=10, changed_files=5))
    assert pr.additions == 50
    assert pr.deletions == 10
    assert pr.changed_files == 5


def test_pr_from_api_invalid_created_at():
    pr = PullRequest.from_github_api(_pr_data(created_at="bad"))
    assert pr.created_at is None


def test_pr_from_api_invalid_merged_at():
    pr = PullRequest.from_github_api(_pr_data(merged_at="bad"))
    assert pr.merged_at is None


# ---------------------------------------------------------------------------
# PullRequest.format_display
# ---------------------------------------------------------------------------


def test_pr_format_display_open():
    pr = PullRequest.from_github_api(_pr_data(state="open", merged=False, draft=False))
    assert "[Open]" in pr.format_display()


def test_pr_format_display_draft():
    pr = PullRequest.from_github_api(_pr_data(state="open", draft=True, merged=False))
    assert "[Draft]" in pr.format_display()


def test_pr_format_display_merged():
    pr = PullRequest.from_github_api(_pr_data(state="closed", merged=True))
    assert "[Merged]" in pr.format_display()


def test_pr_format_display_closed_not_merged():
    pr = PullRequest.from_github_api(_pr_data(state="closed", merged=False))
    assert "[Closed]" in pr.format_display()


def test_pr_format_display_contains_branch_info():
    pr = PullRequest.from_github_api(_pr_data(
        head={"ref": "feat/x"}, base={"ref": "main"}
    ))
    display = pr.format_display()
    assert "feat/x" in display
    assert "main" in display


def test_pr_format_display_contains_title_and_user():
    pr = PullRequest.from_github_api(_pr_data(
        title="Big feature",
        user={"login": "dev", "id": 9, "avatar_url": ""},
    ))
    display = pr.format_display()
    assert "Big feature" in display
    assert "dev" in display


# ---------------------------------------------------------------------------
# PullRequest._format_relative_time (same logic as Issue)
# ---------------------------------------------------------------------------


def test_pr_relative_time_just_now():
    pr = PullRequest.from_github_api(_pr_data())
    assert pr._format_relative_time(_dt_ago(10)) == "just now"


def test_pr_relative_time_1_minute():
    pr = PullRequest.from_github_api(_pr_data())
    assert pr._format_relative_time(_dt_ago(90)) == "1 minute ago"


def test_pr_relative_time_plural_days():
    pr = PullRequest.from_github_api(_pr_data())
    assert pr._format_relative_time(_dt_ago(5 * 86400)) == "5 days ago"


def test_pr_relative_time_none():
    pr = PullRequest.from_github_api(_pr_data())
    assert pr._format_relative_time(None) == "Unknown"
