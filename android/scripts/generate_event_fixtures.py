"""Generate feed-description fixtures from the desktop app's Event model.

The Android EventDescriber is a port of models/event.py; EventParityTest checks
it against this fixture so both apps describe the feed identically. Re-run after
changing models/event.py:

    python android/scripts/generate_event_fixtures.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from models.event import Event  # noqa: E402

OUT = ROOT / "android" / "app" / "src" / "test" / "resources" / "event_parity.json"

ISSUE = {"number": 7, "title": "Crash when opening settings on a very long title that gets cut off"}
PR = {"number": 12, "title": "Add dark mode"}
LABEL = {"name": "bug"}
USER = {"login": "bob"}
MILESTONE = {"title": "v2.0"}


def issue_like(kind, item_key, item, extra_actions):
    cases = []
    for action in ["opened", "closed", "reopened", "pinned", "unpinned", "locked",
                   "unlocked", "transferred", *extra_actions]:
        cases.append((kind, {"action": action, item_key: item}))
    for item_variant in (item, {"number": item["number"]}):
        cases += [
            (kind, {"action": "labeled", item_key: item_variant, "label": LABEL}),
            (kind, {"action": "unlabeled", item_key: item_variant, "label": LABEL}),
            (kind, {"action": "labeled", item_key: item_variant}),
            (kind, {"action": "assigned", item_key: item_variant, "assignee": USER}),
            (kind, {"action": "unassigned", item_key: item_variant, "assignee": USER}),
            (kind, {"action": "milestoned", item_key: item_variant, "milestone": MILESTONE}),
            (kind, {"action": "demilestoned", item_key: item_variant, "milestone": MILESTONE}),
            (kind, {"action": "opened", item_key: item_variant}),
        ]
    return cases


CASES = [
    ("WatchEvent", {"action": "started"}),
    ("ForkEvent", {"forkee": {"full_name": "bob/repo", "html_url": "https://github.com/bob/repo"}}),
    ("ForkEvent", {}),
    ("CreateEvent", {"ref_type": "repository"}),
    ("CreateEvent", {"ref_type": "branch", "ref": "feature/x"}),
    ("CreateEvent", {"ref_type": "tag", "ref": "v1.0"}),
    ("CreateEvent", {"ref_type": "branch"}),
    ("DeleteEvent", {"ref_type": "branch", "ref": "old"}),
    ("DiscussionEvent", {"action": "created", "discussion": {"number": 3, "title": "Ideas"}}),
    ("DiscussionEvent", {"action": "answered", "discussion": {"number": 3,
                         "html_url": "https://github.com/owner/repo/discussions/3"}}),
    ("DiscussionEvent", {"action": "created", "discussion": {}}),
    ("DiscussionCommentEvent", {"action": "created", "discussion": {"number": 3, "title": "Ideas"},
                                "comment": {"html_url": "https://github.com/owner/repo/discussions/3#c1"}}),
    ("DiscussionCommentEvent", {"action": "created", "discussion": {"number": 3, "title": "Ideas"},
                                "comment": {"in_reply_to_id": 99}}),
    ("DiscussionCommentEvent", {"action": "edited", "discussion": {"number": 3},
                                "comment": {"reply_to_id": 5}}),
    ("DiscussionCommentEvent", {"action": "created", "discussion": {"number": 3},
                                "comment": {"in_reply_to_id": None}}),
    ("DiscussionCommentEvent", {"action": "deleted", "discussion": {"number": 3, "title": "Ideas"}}),
    ("DiscussionCommentEvent", {"action": "deleted", "discussion": {"number": 4}}),
    ("PushEvent", {"size": 3, "ref": "refs/heads/main", "before": "aaaaaaaaaa", "head": "bbbbbbbbbb"}),
    ("PushEvent", {"size": 1, "ref": "refs/heads/dev"}),
    ("PushEvent", {"size": 0, "distinct_size": 2, "ref": "refs/heads/main"}),
    ("PushEvent", {"size": 0, "commits": [{}, {}, {}, {}], "ref": "refs/heads/main"}),
    ("PushEvent", {"size": 0, "ref": "refs/heads/main"}),
    *issue_like("IssuesEvent", "issue", ISSUE, []),
    ("IssueCommentEvent", {"action": "created", "issue": ISSUE,
                           "comment": {"html_url": "https://github.com/owner/repo/issues/7#c"}}),
    ("IssueCommentEvent", {"action": "edited", "issue": {"number": 7}}),
    ("IssueCommentEvent", {"action": "deleted", "issue": ISSUE}),
    ("IssueCommentEvent", {"action": "deleted", "issue": {"number": 8}}),
    *issue_like("PullRequestEvent", "pull_request", PR,
                ["ready_for_review", "converted_to_draft", "synchronize", "edited"]),
    ("PullRequestEvent", {"action": "closed", "pull_request": {**PR, "merged": True}}),
    ("PullRequestEvent", {"action": "closed", "pull_request": {"number": 12, "merged": True}}),
    ("PullRequestEvent", {"action": "review_requested", "pull_request": PR, "requested_reviewer": USER}),
    ("PullRequestEvent", {"action": "review_requested", "pull_request": PR, "requested_team": {"name": "core"}}),
    ("PullRequestEvent", {"action": "review_requested", "pull_request": {"number": 12}}),
    ("PullRequestEvent", {"action": "review_request_removed", "pull_request": PR, "requested_reviewer": USER}),
    ("PullRequestEvent", {"action": "review_request_removed", "pull_request": {"number": 12},
                          "requested_team": {"name": "core"}}),
    ("PullRequestEvent", {"action": "review_request_removed", "pull_request": PR}),
    ("PullRequestReviewEvent", {"pull_request": PR, "review": {"state": "approved"}}),
    ("PullRequestReviewEvent", {"pull_request": {"number": 12}, "review": {"state": "changes_requested"}}),
    ("PullRequestReviewEvent", {"pull_request": PR, "review": {"state": "commented"}}),
    ("PullRequestReviewCommentEvent", {"pull_request": PR,
                                       "comment": {"html_url": "https://github.com/owner/repo/pull/12#r1"}}),
    ("PullRequestReviewCommentEvent", {"pull_request": {"number": 12}}),
    ("PullRequestReviewThreadEvent", {"action": "resolved", "pull_request": PR,
                                      "thread": {"html_url": "https://github.com/owner/repo/pull/12#t"}}),
    ("PullRequestReviewThreadEvent", {"action": "unresolved", "pull_request": {"number": 12}}),
    ("PullRequestReviewThreadEvent", {"action": "other", "pull_request": PR}),
    ("ReleaseEvent", {"action": "published", "release": {"tag_name": "v1.2",
                      "html_url": "https://github.com/owner/repo/releases/tag/v1.2"}}),
    ("ReleaseEvent", {"action": "edited", "release": {"tag_name": "v1.2"}}),
    ("CommitCommentEvent", {"comment": {"html_url": "https://github.com/owner/repo/commit/abc#c"}}),
    ("GollumEvent", {"pages": [{"action": "created", "title": "Home"}]}),
    ("GollumEvent", {"pages": []}),
    ("MemberEvent", {"action": "added", "member": USER}),
    ("PublicEvent", {}),
    ("SponsorshipEvent", {}),
    ("SomeFutureEvent", {}),
]


def main():
    fixtures = []
    for event_type, payload in CASES:
        event = Event.from_api({
            "id": "1", "type": event_type,
            "actor": {"login": "alice"}, "repo": {"name": "owner/repo"},
            "payload": payload, "created_at": "2026-03-01T12:00:00Z",
        })
        fixtures.append({
            "type": event_type,
            "payload": payload,
            "description": event.get_action_description(),
            "webUrl": event.get_web_url(),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fixtures, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {len(fixtures)} cases to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
