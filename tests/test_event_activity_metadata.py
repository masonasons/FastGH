from models.event import Event


def _make_event(event_type: str, payload: dict) -> Event:
    return Event.from_api(
        {
            "id": "evt-1",
            "type": event_type,
            "actor": {"id": 1, "login": "alice", "avatar_url": ""},
            "repo": {"id": 10, "name": "owner/repo", "url": ""},
            "payload": payload,
            "public": True,
            "created_at": "2026-02-16T11:15:00Z",
        }
    )


def test_issue_assigned_shows_assignee_login():
    event = _make_event(
        "IssuesEvent",
        {
            "action": "assigned",
            "issue": {"number": 8360, "title": "Audio bug"},
            "assignee": {"login": "meshanuvarma-spec"},
        },
    )
    assert event.get_action_description() == "assigned meshanuvarma-spec to issue #8360: Audio bug"


def test_issue_milestoned_shows_milestone_title():
    event = _make_event(
        "IssuesEvent",
        {
            "action": "milestoned",
            "issue": {"number": 8360, "title": "Audio bug"},
            "milestone": {"title": "v1.2"},
        },
    )
    assert event.get_action_description() == "milestoned issue #8360 [v1.2]: Audio bug"


def test_issue_pinned_uses_human_wording():
    event = _make_event(
        "IssuesEvent",
        {"action": "pinned", "issue": {"number": 8360, "title": "Audio bug"}},
    )
    assert event.get_action_description() == "pinned issue #8360: Audio bug"


def test_pr_review_requested_shows_reviewer_name():
    event = _make_event(
        "PullRequestEvent",
        {
            "action": "review_requested",
            "pull_request": {"number": 101, "title": "Improve docs"},
            "requested_reviewer": {"login": "bob"},
        },
    )
    assert event.get_action_description() == "requested review from bob on PR #101: Improve docs"


def test_pr_review_requested_shows_team_name():
    event = _make_event(
        "PullRequestEvent",
        {
            "action": "review_requested",
            "pull_request": {"number": 102, "title": "Improve docs"},
            "requested_team": {"name": "core-team"},
        },
    )
    assert event.get_action_description() == "requested review from team core-team on PR #102: Improve docs"


def test_pr_synchronize_uses_human_wording():
    event = _make_event(
        "PullRequestEvent",
        {"action": "synchronize", "pull_request": {"number": 103, "title": "Improve docs"}},
    )
    assert event.get_action_description() == "updated PR #103 with new commits: Improve docs"
