"""Tests for models/workflow.py — Workflow, WorkflowRun parsing and display."""

import pytest
from datetime import datetime, timezone, timedelta

from models.workflow import Workflow, WorkflowJob, WorkflowRun, Artifact


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


# ---------------------------------------------------------------------------
# WorkflowRun invalid datetime paths
# ---------------------------------------------------------------------------


def test_run_invalid_created_at_gives_none():
    r = WorkflowRun.from_github_api(_run_data(created_at="bad"))
    assert r.created_at is None


def test_run_invalid_updated_at_gives_none():
    r = WorkflowRun.from_github_api(_run_data(updated_at="bad"))
    assert r.updated_at is None


def test_run_invalid_run_started_at_gives_none():
    r = WorkflowRun.from_github_api(_run_data(run_started_at="bad"))
    assert r.run_started_at is None


# ---------------------------------------------------------------------------
# Workflow invalid datetime paths
# ---------------------------------------------------------------------------


def test_workflow_invalid_updated_at_gives_none():
    w = Workflow.from_github_api(_workflow_data(updated_at="bad"))
    assert w.updated_at is None


# ---------------------------------------------------------------------------
# WorkflowJob.from_github_api
# ---------------------------------------------------------------------------


def _job_data(**overrides) -> dict:
    base = {
        "id": 1,
        "run_id": 100,
        "name": "build",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-03-01T10:00:00Z",
        "completed_at": "2026-03-01T10:05:00Z",
        "html_url": "https://github.com/owner/repo/actions/runs/100/jobs/1",
        "runner_name": "ubuntu-latest",
        "steps": [],
    }
    base.update(overrides)
    return base


def test_job_from_api_id():
    j = WorkflowJob.from_github_api(_job_data(id=42))
    assert j.id == 42


def test_job_from_api_name():
    j = WorkflowJob.from_github_api(_job_data(name="test"))
    assert j.name == "test"


def test_job_from_api_status():
    j = WorkflowJob.from_github_api(_job_data(status="in_progress"))
    assert j.status == "in_progress"


def test_job_from_api_conclusion():
    j = WorkflowJob.from_github_api(_job_data(conclusion="failure"))
    assert j.conclusion == "failure"


def test_job_from_api_started_at_parsed():
    j = WorkflowJob.from_github_api(_job_data(started_at="2026-03-01T10:00:00Z"))
    assert j.started_at is not None
    assert j.started_at.year == 2026


def test_job_from_api_completed_at_parsed():
    j = WorkflowJob.from_github_api(_job_data(completed_at="2026-03-01T10:05:00Z"))
    assert j.completed_at is not None


def test_job_from_api_invalid_started_at_gives_none():
    j = WorkflowJob.from_github_api(_job_data(started_at="bad"))
    assert j.started_at is None


def test_job_from_api_invalid_completed_at_gives_none():
    j = WorkflowJob.from_github_api(_job_data(completed_at="bad"))
    assert j.completed_at is None


def test_job_from_api_runner_name():
    j = WorkflowJob.from_github_api(_job_data(runner_name="ubuntu-22.04"))
    assert j.runner_name == "ubuntu-22.04"


def test_job_from_api_steps():
    steps = [{"name": "Checkout", "status": "completed", "conclusion": "success"}]
    j = WorkflowJob.from_github_api(_job_data(steps=steps))
    assert j.steps == steps


def test_job_from_api_missing_fields_use_defaults():
    j = WorkflowJob.from_github_api({})
    assert j.id == 0
    assert j.name == ""
    assert j.status == ""
    assert j.conclusion is None
    assert j.started_at is None
    assert j.completed_at is None
    assert j.steps == []


# ---------------------------------------------------------------------------
# WorkflowJob.get_status_icon
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
    ("waiting", None, "?"),
])
def test_job_get_status_icon(status, conclusion, expected):
    j = WorkflowJob.from_github_api(_job_data(status=status, conclusion=conclusion))
    assert j.get_status_icon() == expected


# ---------------------------------------------------------------------------
# WorkflowJob.get_duration
# ---------------------------------------------------------------------------


def _job_with_times(started_offset: int, duration_secs: int) -> WorkflowJob:
    """Create a job started `started_offset` seconds ago with given duration."""
    started = datetime.now(timezone.utc) - timedelta(seconds=started_offset + duration_secs)
    completed = started + timedelta(seconds=duration_secs)
    return WorkflowJob.from_github_api(_job_data(
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        completed_at=completed.strftime("%Y-%m-%dT%H:%M:%SZ"),
    ))


def test_job_duration_seconds():
    j = _job_with_times(60, 45)
    assert j.get_duration() == "45s"


def test_job_duration_minutes_and_seconds():
    j = _job_with_times(60, 125)  # 2m 5s
    assert j.get_duration() == "2m 5s"


def test_job_duration_hours_and_minutes():
    j = _job_with_times(60, 3900)  # 1h 5m
    assert j.get_duration() == "1h 5m"


def test_job_duration_no_started_at_returns_empty():
    j = WorkflowJob.from_github_api(_job_data(started_at=None, completed_at=None))
    assert j.get_duration() == ""


def test_job_duration_no_completed_at_uses_now():
    # Job still running — started 30s ago, no completed_at
    started = datetime.now(timezone.utc) - timedelta(seconds=30)
    j = WorkflowJob.from_github_api(_job_data(
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        completed_at=None,
    ))
    result = j.get_duration()
    assert result.endswith("s") or "m" in result  # some positive duration


# ---------------------------------------------------------------------------
# WorkflowJob.format_display
# ---------------------------------------------------------------------------


def test_job_format_display_with_duration():
    j = _job_with_times(60, 45)
    display = j.format_display()
    assert "build" in display
    assert "45s" in display
    assert display.startswith("✓")


def test_job_format_display_no_duration():
    j = WorkflowJob.from_github_api(_job_data(started_at=None, completed_at=None))
    display = j.format_display()
    assert "build" in display
    assert "(" not in display


# ---------------------------------------------------------------------------
# Artifact.from_github_api
# ---------------------------------------------------------------------------


def _artifact_data(**overrides) -> dict:
    base = {
        "id": 555,
        "name": "windows-build",
        "size_in_bytes": 2_500_000,
        "archive_download_url": "https://api.github.com/repos/owner/repo/actions/artifacts/555/zip",
        "expired": False,
        "created_at": "2026-03-01T10:00:00Z",
        "expires_at": "2026-05-30T10:00:00Z",
    }
    base.update(overrides)
    return base


def test_artifact_from_api_basic_fields():
    a = Artifact.from_github_api(_artifact_data())
    assert a.id == 555
    assert a.name == "windows-build"
    assert a.size_in_bytes == 2_500_000
    assert a.expired is False
    assert a.archive_download_url.endswith("/555/zip")


def test_artifact_from_api_parses_dates():
    a = Artifact.from_github_api(_artifact_data())
    assert a.created_at is not None and a.created_at.year == 2026
    assert a.expires_at is not None and a.expires_at.month == 5


def test_artifact_from_api_handles_missing_fields():
    a = Artifact.from_github_api({})
    assert a.id == 0
    assert a.name == ""
    assert a.size_in_bytes == 0
    assert a.expired is False
    assert a.created_at is None


def test_artifact_format_size_kb_mb():
    assert Artifact.from_github_api(_artifact_data(size_in_bytes=512)).format_size() == "512 B"
    assert Artifact.from_github_api(_artifact_data(size_in_bytes=2048)).format_size() == "2.0 KB"
    assert Artifact.from_github_api(_artifact_data(size_in_bytes=5 * 1024 * 1024)).format_size() == "5.0 MB"


def test_artifact_format_display_includes_name_and_size():
    display = Artifact.from_github_api(_artifact_data()).format_display()
    assert "windows-build" in display
    assert "MB" in display
    assert "expired" not in display


def test_artifact_format_display_marks_expired():
    display = Artifact.from_github_api(_artifact_data(expired=True)).format_display()
    assert "expired" in display
