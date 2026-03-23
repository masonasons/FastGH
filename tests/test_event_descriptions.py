"""Tests for models/event.py — get_action_description, format_display,
get_web_url, get_actor_url, and _format_relative_time.

Complements test_event_activity_metadata.py which covers IssuesEvent
(assigned, milestoned, pinned) and PullRequestEvent (review_requested,
synchronize).
"""

import pytest
from datetime import datetime, timezone, timedelta

from models.event import Event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(event_type: str, payload: dict = None, repo: str = "owner/repo",
          actor: str = "alice", created_at: str = "2026-03-01T12:00:00Z") -> Event:
    return Event.from_api({
        "id": "1",
        "type": event_type,
        "actor": {"id": 1, "login": actor, "avatar_url": ""},
        "repo": {"id": 1, "name": repo, "url": ""},
        "payload": payload or {},
        "public": True,
        "created_at": created_at,
    })


def _make_aged(event_type: str, seconds_ago: int) -> Event:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _make(event_type, created_at=iso)


# ---------------------------------------------------------------------------
# _format_relative_time
# ---------------------------------------------------------------------------


def test_relative_time_just_now():
    e = _make_aged("PushEvent", 20)
    assert e._format_relative_time() == "Just now"


def test_relative_time_minutes():
    e = _make_aged("PushEvent", 120)  # 2 minutes
    assert e._format_relative_time() == "2m ago"


def test_relative_time_hours():
    e = _make_aged("PushEvent", 4 * 3600)  # 4 hours
    assert e._format_relative_time() == "4h ago"


def test_relative_time_days():
    e = _make_aged("PushEvent", 3 * 86400)  # 3 days
    assert e._format_relative_time() == "3d ago"


def test_relative_time_months():
    e = _make_aged("PushEvent", 60 * 86400)  # ~2 months
    assert e._format_relative_time() == "2mo ago"


def test_relative_time_years():
    e = _make_aged("PushEvent", 400 * 86400)
    assert e._format_relative_time() == "1y ago"


def test_relative_time_no_created_at():
    e = _make("PushEvent", created_at=None)
    assert e._format_relative_time() == "Unknown"


def test_relative_time_invalid_created_at():
    # from_api silently sets created_at=None on bad input
    e = Event.from_api({
        "id": "x", "type": "PushEvent",
        "actor": {"id": 1, "login": "a", "avatar_url": ""},
        "repo": {"id": 1, "name": "o/r", "url": ""},
        "payload": {}, "public": True,
        "created_at": "not-a-date",
    })
    assert e._format_relative_time() == "Unknown"


# ---------------------------------------------------------------------------
# get_action_description — WatchEvent
# ---------------------------------------------------------------------------


def test_watch_event_returns_starred():
    assert _make("WatchEvent").get_action_description() == "starred"


# ---------------------------------------------------------------------------
# get_action_description — ForkEvent
# ---------------------------------------------------------------------------


def test_fork_event_with_fork_name():
    e = _make("ForkEvent", {"forkee": {"full_name": "bob/repo"}})
    assert e.get_action_description() == "forked to bob/repo"


def test_fork_event_without_fork_name():
    assert _make("ForkEvent").get_action_description() == "forked"


def test_fork_event_empty_forkee():
    e = _make("ForkEvent", {"forkee": {}})
    assert e.get_action_description() == "forked"


# ---------------------------------------------------------------------------
# get_action_description — CreateEvent
# ---------------------------------------------------------------------------


def test_create_event_repository():
    e = _make("CreateEvent", {"ref_type": "repository", "ref": ""})
    assert e.get_action_description() == "created repository"


def test_create_event_branch():
    e = _make("CreateEvent", {"ref_type": "branch", "ref": "main"})
    assert e.get_action_description() == "created branch main"


def test_create_event_tag():
    e = _make("CreateEvent", {"ref_type": "tag", "ref": "v1.0"})
    assert e.get_action_description() == "created tag v1.0"


def test_create_event_unknown_ref_type():
    e = _make("CreateEvent", {"ref_type": "something", "ref": ""})
    assert e.get_action_description() == "created something"


# ---------------------------------------------------------------------------
# get_action_description — DeleteEvent
# ---------------------------------------------------------------------------


def test_delete_event_branch():
    e = _make("DeleteEvent", {"ref_type": "branch", "ref": "old-branch"})
    assert e.get_action_description() == "deleted branch old-branch"


def test_delete_event_tag():
    e = _make("DeleteEvent", {"ref_type": "tag", "ref": "v0.9"})
    assert e.get_action_description() == "deleted tag v0.9"


# ---------------------------------------------------------------------------
# get_action_description — PushEvent
# ---------------------------------------------------------------------------


def test_push_event_single_commit():
    e = _make("PushEvent", {"size": 1, "ref": "refs/heads/main"})
    assert e.get_action_description() == "pushed 1 commit to main"


def test_push_event_multiple_commits():
    e = _make("PushEvent", {"size": 3, "ref": "refs/heads/develop"})
    assert e.get_action_description() == "pushed 3 commits to develop"


def test_push_event_force_push_size_zero():
    e = _make("PushEvent", {"size": 0, "distinct_size": 0, "commits": [], "ref": "refs/heads/main"})
    assert e.get_action_description() == "force pushed to main"


def test_push_event_uses_distinct_size_fallback():
    e = _make("PushEvent", {"size": 0, "distinct_size": 2, "ref": "refs/heads/main"})
    assert e.get_action_description() == "pushed 2 commits to main"


def test_push_event_uses_commits_array_fallback():
    e = _make("PushEvent", {"size": 0, "distinct_size": 0,
                             "commits": [{}, {}], "ref": "refs/heads/main"})
    assert e.get_action_description() == "pushed 2 commits to main"


def test_push_event_strips_refs_heads_prefix():
    e = _make("PushEvent", {"size": 1, "ref": "refs/heads/feature/x"})
    assert "feature/x" in e.get_action_description()


# ---------------------------------------------------------------------------
# get_action_description — DiscussionEvent
# ---------------------------------------------------------------------------


def test_discussion_event_with_title():
    e = _make("DiscussionEvent", {
        "action": "created",
        "discussion": {"number": 5, "title": "How to use"},
    })
    assert e.get_action_description() == "created discussion #5: How to use"


def test_discussion_event_without_title():
    e = _make("DiscussionEvent", {
        "action": "answered",
        "discussion": {"number": 5, "title": ""},
    })
    assert e.get_action_description() == "answered discussion #5"


def test_discussion_event_title_truncated_at_50():
    long_title = "A" * 60
    e = _make("DiscussionEvent", {
        "action": "created",
        "discussion": {"number": 1, "title": long_title},
    })
    desc = e.get_action_description()
    assert "A" * 50 in desc
    assert "A" * 51 not in desc


# ---------------------------------------------------------------------------
# get_action_description — DiscussionCommentEvent
# ---------------------------------------------------------------------------


def test_discussion_comment_created_with_title():
    e = _make("DiscussionCommentEvent", {
        "action": "created",
        "discussion": {"number": 3, "title": "Help"},
        "comment": {},
    })
    assert e.get_action_description() == "commented on discussion #3: Help"


def test_discussion_comment_reply_with_in_reply_to_id():
    e = _make("DiscussionCommentEvent", {
        "action": "created",
        "discussion": {"number": 3, "title": "Help"},
        "comment": {"in_reply_to_id": 99},
    })
    assert e.get_action_description() == "replied in discussion #3: Help"


def test_discussion_comment_reply_without_title():
    e = _make("DiscussionCommentEvent", {
        "action": "created",
        "discussion": {"number": 3, "title": ""},
        "comment": {"in_reply_to_id": 99},
    })
    assert e.get_action_description() == "replied in discussion #3"


def test_discussion_comment_edited():
    e = _make("DiscussionCommentEvent", {
        "action": "edited",
        "discussion": {"number": 3, "title": "Help"},
        "comment": {},
    })
    assert e.get_action_description() == "commented on discussion #3: Help"


def test_discussion_comment_deleted():
    e = _make("DiscussionCommentEvent", {
        "action": "deleted",
        "discussion": {"number": 3, "title": "Help"},
        "comment": {},
    })
    assert e.get_action_description() == "deleted comment on discussion #3: Help"


def test_discussion_comment_deleted_without_title():
    e = _make("DiscussionCommentEvent", {
        "action": "deleted",
        "discussion": {"number": 3, "title": ""},
        "comment": {},
    })
    assert e.get_action_description() == "deleted comment on discussion #3"


def test_discussion_comment_created_no_title_no_reply():
    e = _make("DiscussionCommentEvent", {
        "action": "created",
        "discussion": {"number": 4, "title": ""},
        "comment": {},
    })
    assert e.get_action_description() == "commented on discussion #4"


def test_discussion_comment_uses_reply_to_id_field():
    # Some API payloads use reply_to_id instead of in_reply_to_id
    e = _make("DiscussionCommentEvent", {
        "action": "created",
        "discussion": {"number": 5, "title": "Help"},
        "comment": {"reply_to_id": 77},
    })
    assert e.get_action_description() == "replied in discussion #5: Help"


# ---------------------------------------------------------------------------
# get_action_description — IssuesEvent (branches not in metadata tests)
# ---------------------------------------------------------------------------


def test_issues_event_opened_with_title():
    e = _make("IssuesEvent", {"action": "opened", "issue": {"number": 1, "title": "Bug"}})
    assert e.get_action_description() == "opened issue #1: Bug"


def test_issues_event_closed():
    e = _make("IssuesEvent", {"action": "closed", "issue": {"number": 2, "title": "Done"}})
    assert e.get_action_description() == "closed issue #2: Done"


def test_issues_event_unlabeled():
    e = _make("IssuesEvent", {
        "action": "unlabeled",
        "issue": {"number": 5, "title": "X"},
        "label": {"name": "bug"},
    })
    assert e.get_action_description() == "unlabeled issue #5 [bug]: X"


def test_issues_event_unassigned():
    e = _make("IssuesEvent", {
        "action": "unassigned",
        "issue": {"number": 6, "title": "Y"},
        "assignee": {"login": "carol"},
    })
    assert e.get_action_description() == "unassigned carol from issue #6: Y"


def test_issues_event_demilestoned():
    e = _make("IssuesEvent", {
        "action": "demilestoned",
        "issue": {"number": 7, "title": "Z"},
        "milestone": {"title": "v2.0"},
    })
    assert e.get_action_description() == "demilestoned issue #7 [v2.0]: Z"


def test_issues_event_unpinned():
    e = _make("IssuesEvent", {"action": "unpinned", "issue": {"number": 8, "title": "W"}})
    assert e.get_action_description() == "unpinned issue #8: W"


def test_issues_event_locked():
    e = _make("IssuesEvent", {"action": "locked", "issue": {"number": 9, "title": "V"}})
    assert e.get_action_description() == "locked issue #9: V"


def test_issues_event_unlocked():
    e = _make("IssuesEvent", {"action": "unlocked", "issue": {"number": 10, "title": "U"}})
    assert e.get_action_description() == "unlocked issue #10: U"


def test_issues_event_transferred():
    e = _make("IssuesEvent", {"action": "transferred", "issue": {"number": 11, "title": "T"}})
    assert e.get_action_description() == "transferred issue #11: T"


def test_issues_event_generic_action():
    e = _make("IssuesEvent", {"action": "converted_to_discussion", "issue": {"number": 12, "title": "S"}})
    assert e.get_action_description() == "converted_to_discussion issue #12: S"


def test_issues_event_no_title():
    e = _make("IssuesEvent", {"action": "opened", "issue": {"number": 1, "title": ""}})
    assert e.get_action_description() == "opened issue #1"


@pytest.mark.parametrize("action,extra,expected_fragment", [
    ("labeled",     {"label": {"name": "bug"}},                  "labeled issue #1 [bug]"),
    ("unlabeled",   {"label": {"name": "bug"}},                  "unlabeled issue #1 [bug]"),
    ("assigned",    {"assignee": {"login": "dev"}},              "assigned dev to issue #1"),
    ("unassigned",  {"assignee": {"login": "dev"}},              "unassigned dev from issue #1"),
    ("milestoned",  {"milestone": {"title": "v1"}},              "milestoned issue #1 [v1]"),
    ("demilestoned",{"milestone": {"title": "v1"}},              "demilestoned issue #1 [v1]"),
    ("pinned",      {},                                           "pinned issue #1"),
    ("unpinned",    {},                                           "unpinned issue #1"),
    ("locked",      {},                                           "locked issue #1"),
    ("unlocked",    {},                                           "unlocked issue #1"),
    ("transferred", {},                                           "transferred issue #1"),
])
def test_issues_event_no_title_variants(action, extra, expected_fragment):
    payload = {"action": action, "issue": {"number": 1, "title": ""}, **extra}
    e = _make("IssuesEvent", payload)
    result = e.get_action_description()
    assert result == expected_fragment


# ---------------------------------------------------------------------------
# get_action_description — IssueCommentEvent
# ---------------------------------------------------------------------------


def test_issue_comment_created():
    e = _make("IssueCommentEvent", {
        "action": "created",
        "issue": {"number": 3, "title": "Bug report"},
    })
    assert e.get_action_description() == "commented on issue #3: Bug report"


def test_issue_comment_edited():
    e = _make("IssueCommentEvent", {
        "action": "edited",
        "issue": {"number": 3, "title": "Bug report"},
    })
    assert e.get_action_description() == "commented on issue #3: Bug report"


def test_issue_comment_deleted():
    e = _make("IssueCommentEvent", {
        "action": "deleted",
        "issue": {"number": 3, "title": "Bug report"},
    })
    assert e.get_action_description() == "deleted comment on issue #3: Bug report"


def test_issue_comment_no_title():
    e = _make("IssueCommentEvent", {
        "action": "created",
        "issue": {"number": 4, "title": ""},
    })
    assert e.get_action_description() == "commented on issue #4"


# ---------------------------------------------------------------------------
# get_action_description — PullRequestEvent
# ---------------------------------------------------------------------------


def test_pr_opened():
    e = _make("PullRequestEvent", {"action": "opened", "pull_request": {"number": 1, "title": "Fix"}})
    assert e.get_action_description() == "opened PR #1: Fix"


def test_pr_reopened():
    e = _make("PullRequestEvent", {"action": "reopened", "pull_request": {"number": 2, "title": "Fix"}})
    assert e.get_action_description() == "reopened PR #2: Fix"


def test_pr_closed_not_merged():
    e = _make("PullRequestEvent", {
        "action": "closed",
        "pull_request": {"number": 3, "title": "Fix", "merged": False},
    })
    assert e.get_action_description() == "closed PR #3: Fix"


def test_pr_merged():
    e = _make("PullRequestEvent", {
        "action": "closed",
        "pull_request": {"number": 4, "title": "Merge me", "merged": True},
    })
    assert e.get_action_description() == "merged PR #4: Merge me"


def test_pr_labeled():
    e = _make("PullRequestEvent", {
        "action": "labeled",
        "pull_request": {"number": 5, "title": "Work"},
        "label": {"name": "enhancement"},
    })
    assert e.get_action_description() == "labeled PR #5 [enhancement]: Work"


def test_pr_unlabeled():
    e = _make("PullRequestEvent", {
        "action": "unlabeled",
        "pull_request": {"number": 6, "title": "Work"},
        "label": {"name": "bug"},
    })
    assert e.get_action_description() == "unlabeled PR #6 [bug]: Work"


def test_pr_assigned():
    e = _make("PullRequestEvent", {
        "action": "assigned",
        "pull_request": {"number": 7, "title": "Review"},
        "assignee": {"login": "dev"},
    })
    assert e.get_action_description() == "assigned dev to PR #7: Review"


def test_pr_unassigned():
    e = _make("PullRequestEvent", {
        "action": "unassigned",
        "pull_request": {"number": 8, "title": "Review"},
        "assignee": {"login": "dev"},
    })
    assert e.get_action_description() == "unassigned dev from PR #8: Review"


def test_pr_milestoned():
    e = _make("PullRequestEvent", {
        "action": "milestoned",
        "pull_request": {"number": 9, "title": "Feat"},
        "milestone": {"title": "v3.0"},
    })
    assert e.get_action_description() == "milestoned PR #9 [v3.0]: Feat"


def test_pr_demilestoned():
    e = _make("PullRequestEvent", {
        "action": "demilestoned",
        "pull_request": {"number": 10, "title": "Feat"},
        "milestone": {"title": "v3.0"},
    })
    assert e.get_action_description() == "demilestoned PR #10 [v3.0]: Feat"


def test_pr_locked():
    e = _make("PullRequestEvent", {
        "action": "locked",
        "pull_request": {"number": 11, "title": "Old"},
    })
    assert e.get_action_description() == "locked PR #11: Old"


def test_pr_unlocked():
    e = _make("PullRequestEvent", {
        "action": "unlocked",
        "pull_request": {"number": 12, "title": "Old"},
    })
    assert e.get_action_description() == "unlocked PR #12: Old"


def test_pr_review_request_removed_reviewer():
    e = _make("PullRequestEvent", {
        "action": "review_request_removed",
        "pull_request": {"number": 13, "title": "Fix"},
        "requested_reviewer": {"login": "bob"},
    })
    assert e.get_action_description() == "removed review request for bob on PR #13: Fix"


def test_pr_review_request_removed_team():
    e = _make("PullRequestEvent", {
        "action": "review_request_removed",
        "pull_request": {"number": 14, "title": "Fix"},
        "requested_team": {"name": "backend"},
    })
    assert e.get_action_description() == "removed review request for team backend on PR #14: Fix"


def test_pr_review_request_removed_no_reviewer():
    e = _make("PullRequestEvent", {
        "action": "review_request_removed",
        "pull_request": {"number": 15, "title": "Fix"},
    })
    assert e.get_action_description() == "removed review request on PR #15: Fix"


def test_pr_ready_for_review():
    e = _make("PullRequestEvent", {
        "action": "ready_for_review",
        "pull_request": {"number": 16, "title": "Draft done"},
    })
    assert e.get_action_description() == "marked PR #16 ready for review: Draft done"


def test_pr_converted_to_draft():
    e = _make("PullRequestEvent", {
        "action": "converted_to_draft",
        "pull_request": {"number": 17, "title": "WIP"},
    })
    assert e.get_action_description() == "converted PR #17 to draft: WIP"


def test_pr_generic_action():
    e = _make("PullRequestEvent", {
        "action": "auto_merge_enabled",
        "pull_request": {"number": 18, "title": "Main"},
    })
    assert e.get_action_description() == "auto_merge_enabled PR #18: Main"


def test_pr_no_title():
    e = _make("PullRequestEvent", {"action": "opened", "pull_request": {"number": 1, "title": ""}})
    assert e.get_action_description() == "opened PR #1"


@pytest.mark.parametrize("action,extra,expected_fragment", [
    ("reopened",     {},                                           "reopened PR #1"),
    ("closed",       {"pull_request": {"number": 1, "title": "", "merged": False}}, "closed PR #1"),
    ("closed",       {"pull_request": {"number": 1, "title": "", "merged": True}},  "merged PR #1"),
    ("labeled",      {"label": {"name": "bug"}},                  "labeled PR #1 [bug]"),
    ("unlabeled",    {"label": {"name": "bug"}},                  "unlabeled PR #1 [bug]"),
    ("assigned",     {"assignee": {"login": "dev"}},              "assigned dev to PR #1"),
    ("unassigned",   {"assignee": {"login": "dev"}},              "unassigned dev from PR #1"),
    ("milestoned",   {"milestone": {"title": "v1"}},              "milestoned PR #1 [v1]"),
    ("demilestoned", {"milestone": {"title": "v1"}},              "demilestoned PR #1 [v1]"),
    ("locked",       {},                                           "locked PR #1"),
    ("unlocked",     {},                                           "unlocked PR #1"),
    ("ready_for_review",    {},                                   "marked PR #1 ready for review"),
    ("converted_to_draft",  {},                                   "converted PR #1 to draft"),
    ("synchronize",         {},                                   "updated PR #1 with new commits"),
    ("review_request_removed", {},                                "removed review request on PR #1"),
    ("review_request_removed", {"requested_reviewer": {"login": "bob"}},
                                                                  "removed review request for bob on PR #1"),
    ("review_request_removed", {"requested_team": {"name": "eng"}},
                                                                  "removed review request for team eng on PR #1"),
    ("review_requested", {},                                      "requested review on PR #1"),
    ("review_requested", {"requested_reviewer": {"login": "bob"}},
                                                                  "requested review from bob on PR #1"),
    ("review_requested", {"requested_team": {"name": "eng"}},
                                                                  "requested review from team eng on PR #1"),
])
def test_pr_no_title_variants(action, extra, expected_fragment):
    base_pr = {"number": 1, "title": ""}
    payload = {"action": action, "pull_request": base_pr, **extra}
    # For closed tests the pull_request key is in extra — merge properly
    if "pull_request" in extra:
        payload["pull_request"] = extra["pull_request"]
    e = _make("PullRequestEvent", payload)
    assert e.get_action_description() == expected_fragment


# ---------------------------------------------------------------------------
# get_action_description — PullRequestReviewEvent
# ---------------------------------------------------------------------------


def test_pr_review_approved():
    e = _make("PullRequestReviewEvent", {
        "action": "submitted",
        "pull_request": {"number": 20, "title": "Nice PR"},
        "review": {"state": "approved"},
    })
    assert e.get_action_description() == "approved PR #20: Nice PR"


def test_pr_review_changes_requested():
    e = _make("PullRequestReviewEvent", {
        "action": "submitted",
        "pull_request": {"number": 21, "title": "Needs work"},
        "review": {"state": "changes_requested"},
    })
    assert e.get_action_description() == "requested changes on PR #21: Needs work"


def test_pr_review_commented():
    e = _make("PullRequestReviewEvent", {
        "action": "submitted",
        "pull_request": {"number": 22, "title": "Looks OK"},
        "review": {"state": "commented"},
    })
    assert e.get_action_description() == "reviewed PR #22: Looks OK"


def test_pr_review_no_title():
    e = _make("PullRequestReviewEvent", {
        "pull_request": {"number": 23, "title": ""},
        "review": {"state": "approved"},
    })
    assert e.get_action_description() == "approved PR #23"


def test_pr_review_changes_requested_no_title():
    e = _make("PullRequestReviewEvent", {
        "pull_request": {"number": 24, "title": ""},
        "review": {"state": "changes_requested"},
    })
    assert e.get_action_description() == "requested changes on PR #24"


def test_pr_review_commented_no_title():
    e = _make("PullRequestReviewEvent", {
        "pull_request": {"number": 25, "title": ""},
        "review": {"state": "commented"},
    })
    assert e.get_action_description() == "reviewed PR #25"


# ---------------------------------------------------------------------------
# get_action_description — PullRequestReviewCommentEvent
# ---------------------------------------------------------------------------


def test_pr_review_comment_with_title():
    e = _make("PullRequestReviewCommentEvent", {
        "pull_request": {"number": 30, "title": "Refactor"},
    })
    assert e.get_action_description() == "commented on PR #30: Refactor"


def test_pr_review_comment_no_title():
    e = _make("PullRequestReviewCommentEvent", {
        "pull_request": {"number": 31, "title": ""},
    })
    assert e.get_action_description() == "commented on PR #31"


# ---------------------------------------------------------------------------
# get_action_description — ReleaseEvent
# ---------------------------------------------------------------------------


def test_release_event_published():
    e = _make("ReleaseEvent", {"action": "published", "release": {"tag_name": "v1.2.3"}})
    assert e.get_action_description() == "released v1.2.3"


def test_release_event_other_action():
    e = _make("ReleaseEvent", {"action": "created", "release": {"tag_name": "v2.0.0"}})
    assert e.get_action_description() == "created release v2.0.0"


# ---------------------------------------------------------------------------
# get_action_description — CommitCommentEvent
# ---------------------------------------------------------------------------


def test_commit_comment_event():
    assert _make("CommitCommentEvent").get_action_description() == "commented on a commit"


# ---------------------------------------------------------------------------
# get_action_description — GollumEvent (wiki)
# ---------------------------------------------------------------------------


def test_gollum_event_with_page():
    e = _make("GollumEvent", {"pages": [{"action": "created", "title": "Home"}]})
    assert e.get_action_description() == "created wiki page: Home"


def test_gollum_event_edited_page():
    e = _make("GollumEvent", {"pages": [{"action": "edited", "title": "Setup"}]})
    assert e.get_action_description() == "edited wiki page: Setup"


def test_gollum_event_no_pages():
    assert _make("GollumEvent", {"pages": []}).get_action_description() == "updated wiki"


def test_gollum_event_empty_payload():
    assert _make("GollumEvent").get_action_description() == "updated wiki"


# ---------------------------------------------------------------------------
# get_action_description — MemberEvent
# ---------------------------------------------------------------------------


def test_member_event_added():
    e = _make("MemberEvent", {"action": "added", "member": {"login": "newdev"}})
    assert e.get_action_description() == "added newdev as collaborator"


def test_member_event_removed():
    e = _make("MemberEvent", {"action": "removed", "member": {"login": "olddev"}})
    assert e.get_action_description() == "removed olddev as collaborator"


# ---------------------------------------------------------------------------
# get_action_description — PublicEvent
# ---------------------------------------------------------------------------


def test_public_event():
    assert _make("PublicEvent").get_action_description() == "made repository public"


# ---------------------------------------------------------------------------
# get_action_description — unknown event type fallback
# ---------------------------------------------------------------------------


def test_unknown_event_type_falls_back_to_event_types_dict():
    e = _make("WatchEvent")
    assert e.get_action_description() == "starred"


def test_completely_unknown_event_returns_type_string():
    e = _make("NewFutureEvent2099")
    assert e.get_action_description() == "NewFutureEvent2099"


# ---------------------------------------------------------------------------
# format_display
# ---------------------------------------------------------------------------


def test_format_display_contains_actor():
    e = _make("PushEvent", {"size": 1, "ref": "refs/heads/main"}, actor="bob")
    assert "bob" in e.format_display()


def test_format_display_contains_repo():
    e = _make("PushEvent", {"size": 1, "ref": "refs/heads/main"}, repo="org/proj")
    assert "org/proj" in e.format_display()


def test_format_display_contains_action():
    e = _make("WatchEvent")
    assert "starred" in e.format_display()


def test_format_display_contains_timestamp():
    e = _make("WatchEvent", created_at="2026-03-01T12:00:00Z")
    assert "2026" in e.format_display()


def test_format_display_no_timestamp_shows_unknown():
    e = _make("WatchEvent", created_at=None)
    assert "Unknown" in e.format_display()


# ---------------------------------------------------------------------------
# get_web_url
# ---------------------------------------------------------------------------


def test_get_web_url_issues_event():
    e = _make("IssuesEvent", {"issue": {"number": 42}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/issues/42"


def test_get_web_url_issues_event_no_number():
    e = _make("IssuesEvent", {"issue": {}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_issue_comment_uses_comment_html_url():
    url = "https://github.com/owner/repo/issues/5#issuecomment-123"
    e = _make("IssueCommentEvent", {"comment": {"html_url": url}, "issue": {"number": 5}})
    assert e.get_web_url() == url


def test_get_web_url_issue_comment_falls_back_to_issue_number():
    e = _make("IssueCommentEvent", {"comment": {}, "issue": {"number": 5}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/issues/5"


def test_get_web_url_discussion_event_uses_html_url():
    url = "https://github.com/owner/repo/discussions/3"
    e = _make("DiscussionEvent", {"discussion": {"html_url": url, "number": 3}})
    assert e.get_web_url() == url


def test_get_web_url_discussion_event_falls_back_to_number():
    e = _make("DiscussionEvent", {"discussion": {"number": 7}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/discussions/7"


def test_get_web_url_discussion_comment_uses_comment_html_url():
    url = "https://github.com/owner/repo/discussions/3#discussioncomment-99"
    e = _make("DiscussionCommentEvent", {"comment": {"html_url": url}})
    assert e.get_web_url() == url


def test_get_web_url_discussion_comment_falls_back_to_discussion_html_url():
    url = "https://github.com/owner/repo/discussions/3"
    e = _make("DiscussionCommentEvent", {"comment": {}, "discussion": {"html_url": url}})
    assert e.get_web_url() == url


def test_get_web_url_discussion_comment_falls_back_to_number():
    e = _make("DiscussionCommentEvent",
              {"comment": {}, "discussion": {"number": 3}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/discussions/3"


def test_get_web_url_pr_event():
    e = _make("PullRequestEvent", {"pull_request": {"number": 10}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/pull/10"


def test_get_web_url_pr_review_event():
    e = _make("PullRequestReviewEvent", {"pull_request": {"number": 11}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/pull/11"


def test_get_web_url_pr_review_comment_event():
    e = _make("PullRequestReviewCommentEvent", {"pull_request": {"number": 12}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/pull/12"


def test_get_web_url_push_event_compare():
    e = _make("PushEvent", {
        "before": "abc1234567",
        "head": "def7654321",
    }, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/compare/abc1234...def7654"


def test_get_web_url_push_event_missing_shas():
    e = _make("PushEvent", {}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_release_event_uses_html_url():
    url = "https://github.com/owner/repo/releases/tag/v1.0"
    e = _make("ReleaseEvent", {"release": {"html_url": url}})
    assert e.get_web_url() == url


def test_get_web_url_release_event_no_html_url():
    e = _make("ReleaseEvent", {"release": {}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_fork_event_uses_forkee_html_url():
    url = "https://github.com/bob/repo"
    e = _make("ForkEvent", {"forkee": {"html_url": url}})
    assert e.get_web_url() == url


def test_get_web_url_fork_event_no_forkee_html_url():
    e = _make("ForkEvent", {"forkee": {}}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_commit_comment_uses_html_url():
    url = "https://github.com/owner/repo/commit/abc#commitcomment-1"
    e = _make("CommitCommentEvent", {"comment": {"html_url": url}})
    assert e.get_web_url() == url


def test_get_web_url_create_branch():
    e = _make("CreateEvent", {"ref_type": "branch", "ref": "feature/x"}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/tree/feature/x"


def test_get_web_url_create_tag():
    e = _make("CreateEvent", {"ref_type": "tag", "ref": "v2.0"}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo/releases/tag/v2.0"


def test_get_web_url_create_repository():
    e = _make("CreateEvent", {"ref_type": "repository", "ref": ""}, repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_watch_event_returns_base():
    e = _make("WatchEvent", repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


def test_get_web_url_unknown_type_returns_base():
    e = _make("NewFutureEvent2099", repo="owner/repo")
    assert e.get_web_url() == "https://github.com/owner/repo"


# ---------------------------------------------------------------------------
# get_actor_url
# ---------------------------------------------------------------------------


def test_get_actor_url():
    e = _make("WatchEvent", actor="alice")
    assert e.get_actor_url() == "https://github.com/alice"


def test_get_actor_url_different_actor():
    e = _make("WatchEvent", actor="org-name")
    assert e.get_actor_url() == "https://github.com/org-name"
