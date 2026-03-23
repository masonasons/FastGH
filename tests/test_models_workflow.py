"""Tests for models/workflow.py — Workflow, WorkflowRun parsing and display."""

import pytest
from datetime import datetime, timezone, timedelta

from models.workflow import Workflow, WorkflowRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workflow_data(**overrides) -> dict:
    base = {
        "id": 1,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "state": "active",
        "html_url": "https://github.com/owner/repo/actions/workflows/ci.yml",
        "badge_url": "https://github.com/owner/repo/actions/workflows/ci.yml/badge.svg",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _run_data(**overrides) -> dict:
    base = {
        "id": 100,
        "name": "CI",
        "workflow_id": 1,
        "head_branch": "main",
        "head_sha": "abcdef1234567890",
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "run_number": 42,
        "run_attempt": 1,
        "html_url": "https://github.com/owner/repo/actions/runs/100",
        "created_at": "2026-03-01T10:00:00Z",
        "updated_at": "2026-03-01T10:05:00Z",
        "run_started_at": "2026-03-01T10:01:00Z",
        "actor": {"login": "alice", "avatar_url": ""},
        "triggering_actor": {"login": "alice"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Workflow.from_github_api
# ---------------------------------------------------------------------------


def test_workflow_from_api_id():
    w = Workflow.from_github_api(_workflow_data(id=99))
    assert w.id == 99


def test_workflow_from_api_name():
    w = Workflow.from_github_api(_workflow_data(name="Deploy"))
    assert w.name == "Deploy"


def test_workflow_from_api_path():
    w = Workflow.from_github_api(_workflow_data(path=".github/workflows/deploy.yml"))
    assert w.path == ".github/workflows/deploy.yml"


def test_workflow_from_api_state():
    w = Workflow.from_github_api(_workflow_data(state="disabled_manually"))
    assert w.state == "disabled_manually"


def test_workflow_from_api_html_url():
    url = "https://github.com/x/y/actions/workflows/ci.yml"
    w = Workflow.from_github_api(_workflow_data(html_url=url))
    assert w.html_url == url


def test_workflow_from_api_created_at_parsed():
    w = Workflow.from_github_api(_workflow_data(created_at="2025-06-15T08:00:00Z"))
    assert w.created_at is not None
    assert w.created_at.year == 2025
    assert w.created_at.month == 6


def test_workflow_from_api_updated_at_parsed():
    w = Workflow.from_github_api(_workflow_data(updated_at="2026-02-10T09:30:00Z"))
    assert w.updated_at is not None
    assert w.updated_at.year == 2026


def test_workflow_from_api_invalid_date_gives_none():
    w = Workflow.from_github_api(_workflow_data(created_at="bad-date"))
    assert w.created_at is None


def test_workflow_from_api_missing_fields_use_defaults():
    w = Workflow.from_github_api({})
    assert w.id == 0
    assert w.name == ""
    assert w.state == ""
    assert w.created_at is None
    assert w.updated_at is None


# ---------------------------------------------------------------------------
# Workflow.format_display
# ---------------------------------------------------------------------------


def test_workflow_format_display_active():
    w = Workflow.from_github_api(_workflow_data(name="CI", state="active"))
    assert w.format_display() == "✓ CI"


def test_workflow_format_display_inactive():
    w = Workflow.from_github_api(_workflow_data(name="Deploy", state="disabled_manually"))
    assert w.format_display() == "○ Deploy"


def test_workflow_format_display_other_state():
    w = Workflow.from_github_api(_workflow_data(name="Test", state="disabled_inactivity"))
    assert w.format_display() == "○ Test"


# ---------------------------------------------------------------------------
# WorkflowRun.from_github_api
# ---------------------------------------------------------------------------


def test_run_from_api_id():
    r = WorkflowRun.from_github_api(_run_data(id=777))
    assert r.id == 777


def test_run_from_api_name():
    r = WorkflowRun.from_github_api(_run_data(name="Deploy"))
    assert r.name == "Deploy"


def test_run_from_api_head_sha_truncated_to_7():
    r = WorkflowRun.from_github_api(_run_data(head_sha="abcdef1234567890"))
    assert r.head_sha == "abcdef1"


def test_run_from_api_head_sha_missing():
    r = WorkflowRun.from_github_api(_run_data(head_sha=None))
    assert r.head_sha == ""


def test_run_from_api_status():
    r = WorkflowRun.from_github_api(_run_data(status="in_progress"))
    assert r.status == "in_progress"


def test_run_from_api_conclusion():
    r = WorkflowRun.from_github_api(_run_data(conclusion="failure"))
    assert r.conclusion == "failure"


def test_run_from_api_conclusion_none():
    r = WorkflowRun.from_github_api(_run_data(conclusion=None))
    assert r.conclusion is None


def test_run_from_api_event():
    r = WorkflowRun.from_github_api(_run_data(event="pull_request"))
    assert r.event == "pull_request"


def test_run_from_api_run_number():
    r = WorkflowRun.from_github_api(_run_data(run_number=99))
    assert r.run_number == 99


def test_run_from_api_actor_login():
    r = WorkflowRun.from_github_api(_run_data(actor={"login": "bob", "avatar_url": ""}))
    assert r.actor_login == "bob"


def test_run_from_api_triggering_actor_login():
    r = WorkflowRun.from_github_api(_run_data(triggering_actor={"login": "carol"}))
    assert r.triggering_actor_login == "carol"


def test_run_from_api_actor_none_safe():
    data = _run_data()
    data["actor"] = None
    r = WorkflowRun.from_github_api(data)
    assert r.actor_login == ""


def test_run_from_api_created_at_parsed():
    r = WorkflowRun.from_github_api(_run_data(created_at="2026-03-01T10:00:00Z"))
    assert r.created_at is not None
    assert r.created_at.year == 2026


def test_run_from_api_run_started_at_parsed():
    r = WorkflowRun.from_github_api(_run_data(run_started_at="2026-03-01T10:01:00Z"))
    assert r.run_started_at is not None


def test_run_from_api_run_started_at_missing_gives_none():
    data = _run_data()
    data.pop("run_started_at")
    r = WorkflowRun.from_github_api(data)
    assert r.run_started_at is None


def test_run_from_api_missing_fields_use_defaults():
    r = WorkflowRun.from_github_api({})
    assert r.id == 0
    assert r.name == ""
    assert r.status == ""
    assert r.conclusion is None
    assert r.created_at is None


# ---------------------------------------------------------------------------
# WorkflowRun.get_status_icon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status,conclusion,expected", [
    ("completed", "success", "✓"),
    ("completed", "failure", "✗"),
    ("completed", "cancelled", "⊘"),
    ("completed", "skipped", "⊘"),
    ("completed", "neutral", "?"),
    ("completed", None, "?"),
    ("in_progress", None, "●"),
    ("queued", None, "○"),
    ("unknown_status", None, "?"),
])
def test_get_status_icon(status, conclusion, expected):
    r = WorkflowRun.from_github_api(_run_data(status=status, conclusion=conclusion))
    assert r.get_status_icon() == expected


# ---------------------------------------------------------------------------
# WorkflowRun.get_status_text
# ---------------------------------------------------------------------------


def test_get_status_text_completed_success():
    r = WorkflowRun.from_github_api(_run_data(status="completed", conclusion="success"))
    assert r.get_status_text() == "success"


def test_get_status_text_completed_failure():
    r = WorkflowRun.from_github_api(_run_data(status="completed", conclusion="failure"))
    assert r.get_status_text() == "failure"


def test_get_status_text_completed_no_conclusion():
    r = WorkflowRun.from_github_api(_run_data(status="completed", conclusion=None))
    assert r.get_status_text() == "completed"


def test_get_status_text_in_progress():
    r = WorkflowRun.from_github_api(_run_data(status="in_progress", conclusion=None))
    assert r.get_status_text() == "in progress"


def test_get_status_text_queued():
    r = WorkflowRun.from_github_api(_run_data(status="queued", conclusion=None))
    assert r.get_status_text() == "queued"


# ---------------------------------------------------------------------------
# WorkflowRun.format_display
# ---------------------------------------------------------------------------


def test_format_display_contains_name():
    r = WorkflowRun.from_github_api(_run_data(name="CI"))
    assert "CI" in r.format_display()


def test_format_display_contains_run_number():
    r = WorkflowRun.from_github_api(_run_data(run_number=42))
    assert "#42" in r.format_display()


def test_format_display_contains_branch():
    r = WorkflowRun.from_github_api(_run_data(head_branch="feature/x"))
    assert "feature/x" in r.format_display()


def test_format_display_contains_event():
    r = WorkflowRun.from_github_api(_run_data(event="push"))
    assert "push" in r.format_display()


def test_format_display_success_icon():
    r = WorkflowRun.from_github_api(_run_data(status="completed", conclusion="success"))
    assert r.format_display().startswith("✓")


def test_format_display_failure_icon():
    r = WorkflowRun.from_github_api(_run_data(status="completed", conclusion="failure"))
    assert r.format_display().startswith("✗")


# ---------------------------------------------------------------------------
# WorkflowRun._format_relative_time
# ---------------------------------------------------------------------------


def _run_aged(seconds: int) -> WorkflowRun:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return WorkflowRun.from_github_api(_run_data(created_at=iso))


def test_run_relative_time_just_now():
    r = _run_aged(30)
    assert r._format_relative_time() == "just now"


def test_run_relative_time_minutes():
    r = _run_aged(90)
    assert r._format_relative_time() == "1m ago"


def test_run_relative_time_hours():
    r = _run_aged(7200)
    assert r._format_relative_time() == "2h ago"


def test_run_relative_time_days():
    r = _run_aged(3 * 86400)
    assert r._format_relative_time() == "3d ago"


def test_run_relative_time_old_returns_date():
    r = _run_aged(8 * 86400)  # > 1 week
    result = r._format_relative_time()
    # Should be a formatted date like "2026-02-XX"
    assert "-" in result
    assert "ago" not in result


def test_run_relative_time_no_created_at():
    r = WorkflowRun.from_github_api(_run_data(created_at=None))
    assert r._format_relative_time() == ""
