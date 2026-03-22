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


# ── PullRequestReviewThreadEvent: action descriptions ──────────────────────

def test_pr_review_thread_resolved_with_title():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {"action": "resolved", "pull_request": {"number": 42, "title": "Fix the thing"}},
    )
    assert event.get_action_description() == "resolved review thread on PR #42: Fix the thing"


def test_pr_review_thread_unresolved_with_title():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {"action": "unresolved", "pull_request": {"number": 42, "title": "Fix the thing"}},
    )
    assert event.get_action_description() == "unresolved review thread on PR #42: Fix the thing"


def test_pr_review_thread_resolved_no_title():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {"action": "resolved", "pull_request": {"number": 7, "title": ""}},
    )
    assert event.get_action_description() == "resolved review thread on PR #7"


def test_pr_review_thread_unknown_action_falls_back():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {"action": "locked", "pull_request": {"number": 99, "title": "Something"}},
    )
    assert event.get_action_description() == "locked review thread on PR #99: Something"


def test_pr_review_thread_in_event_types_dict():
    assert "PullRequestReviewThreadEvent" in Event.EVENT_TYPES


# ── PullRequestReviewThreadEvent: web URLs ─────────────────────────────────

def test_pr_review_thread_web_url_uses_thread_html_url():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {
            "action": "resolved",
            "thread": {"html_url": "https://github.com/owner/repo/pull/42#discussion_r123"},
            "pull_request": {"number": 42},
        },
    )
    assert event.get_web_url() == "https://github.com/owner/repo/pull/42#discussion_r123"


def test_pr_review_thread_web_url_falls_back_to_pr_number():
    event = _make_event(
        "PullRequestReviewThreadEvent",
        {
            "action": "resolved",
            "thread": {},
            "pull_request": {"number": 42},
        },
    )
    assert event.get_web_url() == "https://github.com/owner/repo/pull/42"


# ── PullRequestReviewCommentEvent: web URL uses comment html_url ───────────

def test_pr_review_comment_web_url_uses_comment_html_url():
    event = _make_event(
        "PullRequestReviewCommentEvent",
        {
            "comment": {"html_url": "https://github.com/owner/repo/pull/10#pullrequestreview-456"},
            "pull_request": {"number": 10},
        },
    )
    assert event.get_web_url() == "https://github.com/owner/repo/pull/10#pullrequestreview-456"


def test_pr_review_comment_web_url_falls_back_to_pr_number():
    event = _make_event(
        "PullRequestReviewCommentEvent",
        {
            "comment": {},
            "pull_request": {"number": 10},
        },
    )
    assert event.get_web_url() == "https://github.com/owner/repo/pull/10"
