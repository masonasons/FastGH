"""Feed filter logic for FastGH activity feed.

All filter logic lives here as pure Python with no wx dependency so it
can be tested without a display and reused from both GUI/main.py and
GUI/options.py.
"""

from __future__ import annotations

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


def is_event_visible(event, visible: Optional[set[str]]) -> bool:
    """Return True if *event* should appear in the feed.

    event   — a models.event.Event instance (only .type is read)
    visible — None means "unconfigured, show all"
              a set means "show only these types"
    """
    if visible is None:
        return True
    return event.type in visible


def filter_feed(events, visible: Optional[set[str]]) -> list:
    """Return a new list containing only the visible events.

    Does not mutate the input iterable.
    If visible is None every event passes through (copy semantics preserved).
    """
    if visible is None:
        return list(events)
    return [e for e in events if e.type in visible]
