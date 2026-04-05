"""Feed filter logic for FastGH activity feed.

All filter logic lives here as pure Python with no wx dependency so it
can be tested without a display and reused from both GUI/main.py and
GUI/options.py.

NOTE: account_prefs is a Config object (MutableMapping) that wraps any
stored dict value in another Config.  load_user_filters must therefore
accept any Mapping, not just plain dict.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# All known event type strings.  Includes PullRequestReviewThreadEvent even
# though it is currently absent from Event.EVENT_TYPES in models/event.py
# because GitHub does emit it in the received-events stream.
ALL_EVENT_TYPES: list[str] = [
    "CommitCommentEvent",
    "CreateEvent",
    "DeleteEvent",
    "DiscussionCommentEvent",
    "DiscussionEvent",
    "ForkEvent",
    "GollumEvent",
    "IssueCommentEvent",
    "IssuesEvent",
    "MemberEvent",
    "PublicEvent",
    "PullRequestEvent",
    "PullRequestReviewCommentEvent",
    "PullRequestReviewEvent",
    "PullRequestReviewThreadEvent",
    "PushEvent",
    "ReleaseEvent",
    "SponsorshipEvent",
    "WatchEvent",
]

# Per event-type, the individual actions exposed for granular filtering.
# Event types absent from this dict (or with empty list) are treated as
# atomic — a single checkbox, no sub-actions.
#
# Action source per type:
#   PullRequestEvent          payload["action"]  ("merged" is synthetic:
#                               action=="closed" + pull_request.merged==True)
#   IssuesEvent               payload["action"]
#   IssueCommentEvent         payload["action"]
#   PullRequestReviewEvent    payload["review"]["state"]   (not payload["action"])
#   PullRequestReviewCommentEvent  payload["action"]
#   PullRequestReviewThreadEvent   payload["action"]
#   CreateEvent / DeleteEvent payload["ref_type"]
#   ReleaseEvent              payload["action"]
#   DiscussionEvent           payload["action"]
#   DiscussionCommentEvent    payload["action"]
#   MemberEvent               payload["action"]
#   SponsorshipEvent          payload["action"]
EVENT_TYPE_ACTIONS: dict = {
    "PullRequestEvent": [
        "opened", "closed", "merged", "reopened",
        "labeled", "unlabeled", "assigned", "unassigned",
        "locked", "unlocked",
    ],
    "IssuesEvent": [
        "opened", "closed", "reopened",
        "labeled", "unlabeled", "assigned", "unassigned",
        "locked", "unlocked",
    ],
    "IssueCommentEvent": ["created", "edited", "deleted"],
    "PullRequestReviewEvent": ["approved", "changes_requested", "commented"],
    "PullRequestReviewCommentEvent": ["created", "edited", "deleted"],
    "PullRequestReviewThreadEvent": ["resolved", "unresolved"],
    "CreateEvent": ["branch", "tag", "repository"],
    "DeleteEvent": ["branch", "tag"],
    "ReleaseEvent": ["published", "created", "edited", "deleted", "prereleased"],
    "DiscussionEvent": ["created", "answered", "category_changed", "labeled", "unlabeled"],
    "DiscussionCommentEvent": ["created", "edited", "deleted"],
    "MemberEvent": ["added", "removed"],
    "SponsorshipEvent": ["created", "cancelled"],
}

# Ordered display groups used to build the UI checklist.
# Note: wx StaticBox labels require "&&" to render a literal "&".
FILTER_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Pull Requests && Reviews",
        [
            "PullRequestEvent",
            "PullRequestReviewEvent",
            "PullRequestReviewCommentEvent",
            "PullRequestReviewThreadEvent",
        ],
    ),
    (
        "Issues",
        [
            "IssuesEvent",
            "IssueCommentEvent",
        ],
    ),
    (
        "Code",
        [
            "PushEvent",
            "CommitCommentEvent",
            "CreateEvent",
            "DeleteEvent",
        ],
    ),
    (
        "Collaboration",
        [
            "ForkEvent",
            "WatchEvent",
            "MemberEvent",
            "GollumEvent",
        ],
    ),
    (
        "Releases && Discussions",
        [
            "ReleaseEvent",
            "DiscussionEvent",
            "DiscussionCommentEvent",
            "SponsorshipEvent",
            "PublicEvent",
        ],
    ),
]

# Key written to each account's config JSON.
CONFIG_KEY = "feed_visible_event_types"
MUTED_REPOS_KEY = "feed_muted_repos"
USER_FILTERS_KEY = "feed_user_filters"

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def load_visible_types(account_prefs) -> Optional[set[str]]:
    """Return the set of event type strings that are visible for this account.

    account_prefs is a Config-like object (any MutableMapping, or plain dict).

    Return values:
      None        — key is absent; caller should treat as "show everything"
                    (new account / user has never opened Feed Filters)
      set()       — key is present but empty; user explicitly hid everything
      {str, ...}  — key is present with one or more types; show only these

    Invalid stored values (not a list, list contains non-strings, etc.) are
    treated as "never configured" and return None so the feed degrades
    gracefully rather than hiding events unexpectedly.
    """
    raw = account_prefs.get(CONFIG_KEY, None)

    if raw is None:
        return None

    if not isinstance(raw, list):
        return None

    # Keep only string entries; silently drop ints, None, etc.
    result: set[str] = {item for item in raw if isinstance(item, str)}

    # If every entry was non-string the list is effectively empty, which is
    # a valid "show nothing" state (distinct from the absent-key case).
    return result


def save_visible_types(account_prefs, visible: set[str]) -> None:
    """Persist the visible event type set to the account config.

    Stores a sorted list for deterministic JSON output.
    After this call the key is always present — even for an empty set —
    so subsequent loads correctly return set() rather than None.
    """
    account_prefs[CONFIG_KEY] = sorted(visible)


def load_muted_repos(account_prefs) -> Optional[set[str]]:
    """Return the set of muted repo full-names (owner/repo) for this account.

    Return values:
      None        — key is absent; no repos are muted (new account)
      set()       — key is present but empty; explicitly configured with nothing muted
      {str, ...}  — one or more repos are muted

    Invalid stored values return None (safe fallback — mute nothing).
    """
    raw = account_prefs.get(MUTED_REPOS_KEY, None)

    if raw is None:
        return None

    if not isinstance(raw, list):
        return None

    return {item for item in raw if isinstance(item, str)}


def save_muted_repos(account_prefs, muted: set[str]) -> None:
    """Persist the muted repo set to the account config as a sorted list."""
    account_prefs[MUTED_REPOS_KEY] = sorted(muted)


def load_user_filters(account_prefs) -> Optional[dict]:
    """Return per-user filter rules as {username: set[str]}.

    Return values:
      None        — key is absent; no per-user rules configured
      {}          — key is present but no users configured
      {user: set} — one or more user rules; empty set means mute that user

    Invalid top-level value returns None.  Invalid per-user entries are
    silently skipped so one bad entry does not wipe the whole config.
    """
    raw = account_prefs.get(USER_FILTERS_KEY, None)

    if raw is None:
        return None

    if not isinstance(raw, Mapping):
        return None

    result: dict = {}
    for username, types in raw.items():
        if not isinstance(username, str):
            continue
        if not isinstance(types, list):
            continue
        result[username] = {t for t in types if isinstance(t, str)}
    return result


def save_user_filters(account_prefs, user_filters: dict) -> None:
    """Persist user filter rules.  Each type list is stored sorted."""
    account_prefs[USER_FILTERS_KEY] = {
        username: sorted(types) for username, types in user_filters.items()
    }


def _get_event_action(event) -> str:
    """Extract the filterable action string for an event.

    Returns an empty string for event types that have no sub-action filtering.
    For PullRequestEvent a closed+merged PR is reported as "merged" (synthetic).
    For CreateEvent/DeleteEvent the ref_type (branch/tag/repository) is used.
    For PullRequestReviewEvent the review state is used instead of "submitted".
    """
    t = event.type
    if t not in EVENT_TYPE_ACTIONS:
        return ""
    payload = event.payload or {}

    if t == "PullRequestEvent":
        action = payload.get("action", "")
        if action == "closed":
            pr = payload.get("pull_request") or {}
            if pr.get("merged"):
                return "merged"
        return action

    if t in ("CreateEvent", "DeleteEvent"):
        return payload.get("ref_type", "")

    if t == "PullRequestReviewEvent":
        review = payload.get("review") or {}
        return review.get("state", "")

    return payload.get("action", "")


def _is_event_in_visible(event, visible: set) -> bool:
    """Return True if the event passes a visible-types filter set.

    For event types with known sub-actions the key is "Type:action".
    For types without sub-actions the key is the plain "Type" string.
    """
    t = event.type
    if t in EVENT_TYPE_ACTIONS:
        action = _get_event_action(event)
        if action:
            return f"{t}:{action}" in visible
    return t in visible


def is_event_visible(event, visible: Optional[set[str]]) -> bool:
    """Return True if *event* should appear in the feed.

    event   — a models.event.Event instance
    visible — None means "unconfigured, show all"
              a set means "show only these type(:action) keys"
    """
    if visible is None:
        return True
    return _is_event_in_visible(event, visible)


def filter_feed(
    events,
    visible: Optional[set[str]],
    muted_repos: Optional[set[str]] = None,
    user_filters: Optional[dict] = None,
) -> list:
    """Return a new list containing only the visible events.

    Filters are applied in order:
      1. Muted repos (blacklist) — events from a muted repo are always hidden.
      2. Per-user override — if the actor has a rule, that rule's type/action
         set is used instead of the global visible set (empty = mute user).
      3. Global visible types (whitelist) — applied to actors without a rule.

    The visible set may contain plain "EventType" strings (backward compat) or
    granular "EventType:action" strings (current format).  Both are handled by
    _is_event_in_visible.

    Does not mutate the input iterable.
    """
    result = []
    for e in events:
        if muted_repos and e.repo.name.lower() in muted_repos:
            continue

        if user_filters:
            login = e.actor.login.lower()
            vis = user_filters[login] if login in user_filters else visible
        else:
            vis = visible

        if vis is not None and not _is_event_in_visible(e, vis):
            continue

        result.append(e)
    return result
