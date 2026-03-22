"""Tests for models/feed_filter.py — feed filter preferences logic.

All tests are pure Python (no wx).  account_prefs is a plain dict because
load_visible_types only calls .get() and save_visible_types only uses
dict-style assignment, both of which work on plain dicts.
"""

import pytest
from models.event import Event
from models.feed_filter import (
    ALL_EVENT_TYPES,
    CONFIG_KEY,
    FILTER_GROUPS,
    filter_feed,
    is_event_visible,
    load_visible_types,
    save_visible_types,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str) -> Event:
    return Event.from_api(
        {
            "id": "1",
            "type": event_type,
            "actor": {"id": 1, "login": "alice", "avatar_url": ""},
            "repo": {"id": 1, "name": "owner/repo", "url": ""},
            "payload": {},
            "public": True,
            "created_at": None,
        }
    )


_sentinel = object()


def _prefs(hidden_key_value=_sentinel) -> dict:
    """Return a plain dict acting as account prefs."""
    if hidden_key_value is _sentinel:
        return {}
    return {CONFIG_KEY: hidden_key_value}


# ---------------------------------------------------------------------------
# load_visible_types — baseline behaviour
# ---------------------------------------------------------------------------


def test_load_visible_types_absent_key_returns_none():
    assert load_visible_types({}) is None


def test_load_visible_types_empty_list_returns_empty_set():
    assert load_visible_types({CONFIG_KEY: []}) == set()


def test_load_visible_types_single_type():
    assert load_visible_types({CONFIG_KEY: ["PushEvent"]}) == {"PushEvent"}


def test_load_visible_types_multiple_types():
    result = load_visible_types({CONFIG_KEY: ["PushEvent", "ForkEvent"]})
    assert result == {"PushEvent", "ForkEvent"}


def test_load_visible_types_all_known_types():
    result = load_visible_types({CONFIG_KEY: ALL_EVENT_TYPES})
    assert result == set(ALL_EVENT_TYPES)


# ---------------------------------------------------------------------------
# load_visible_types — corrupt / invalid stored data
# ---------------------------------------------------------------------------


def test_load_visible_types_string_value_returns_none():
    assert load_visible_types({CONFIG_KEY: "PushEvent"}) is None


def test_load_visible_types_dict_value_returns_none():
    assert load_visible_types({CONFIG_KEY: {"PushEvent": True}}) is None


def test_load_visible_types_none_value_returns_none():
    assert load_visible_types({CONFIG_KEY: None}) is None


def test_load_visible_types_integer_value_returns_none():
    assert load_visible_types({CONFIG_KEY: 42}) is None


def test_load_visible_types_boolean_value_returns_none():
    assert load_visible_types({CONFIG_KEY: True}) is None


def test_load_visible_types_list_drops_non_string_items():
    result = load_visible_types({CONFIG_KEY: [42, None, "PushEvent", 3.14]})
    assert result == {"PushEvent"}


def test_load_visible_types_list_all_non_strings_returns_empty_set():
    result = load_visible_types({CONFIG_KEY: [1, 2, None]})
    assert result == set()


def test_load_visible_types_unknown_future_type_kept_in_set():
    # Forward-compat: an unknown type the user somehow added stays in the set
    result = load_visible_types({CONFIG_KEY: ["UnknownFutureEvent2099"]})
    assert "UnknownFutureEvent2099" in result


# ---------------------------------------------------------------------------
# save_visible_types
# ---------------------------------------------------------------------------


def test_save_visible_types_writes_sorted_list():
    prefs = {}
    save_visible_types(prefs, {"ForkEvent", "PushEvent", "WatchEvent"})
    assert prefs[CONFIG_KEY] == ["ForkEvent", "PushEvent", "WatchEvent"]


def test_save_visible_types_empty_set_writes_empty_list():
    prefs = {}
    save_visible_types(prefs, set())
    assert prefs[CONFIG_KEY] == []


def test_save_visible_types_all_types_roundtrip():
    prefs = {}
    save_visible_types(prefs, set(ALL_EVENT_TYPES))
    assert sorted(prefs[CONFIG_KEY]) == sorted(ALL_EVENT_TYPES)


def test_save_visible_types_uses_correct_key():
    prefs = {}
    save_visible_types(prefs, {"PushEvent"})
    assert CONFIG_KEY in prefs


def test_save_visible_types_overwrites_existing_value():
    prefs = {CONFIG_KEY: ["PushEvent"]}
    save_visible_types(prefs, {"ForkEvent"})
    assert prefs[CONFIG_KEY] == ["ForkEvent"]


def test_save_visible_types_key_present_after_empty_set_save():
    # Empty set save must write the key so a subsequent load returns set(), not None
    prefs = {}
    save_visible_types(prefs, set())
    assert CONFIG_KEY in prefs
    assert load_visible_types(prefs) == set()


# ---------------------------------------------------------------------------
# is_event_visible
# ---------------------------------------------------------------------------


def test_is_event_visible_none_visible_always_true():
    event = _make_event("PushEvent")
    assert is_event_visible(event, None) is True


def test_is_event_visible_empty_set_always_false():
    event = _make_event("PushEvent")
    assert is_event_visible(event, set()) is False


def test_is_event_visible_type_in_set_returns_true():
    event = _make_event("PushEvent")
    assert is_event_visible(event, {"PushEvent", "ForkEvent"}) is True


def test_is_event_visible_type_not_in_set_returns_false():
    event = _make_event("ForkEvent")
    assert is_event_visible(event, {"PushEvent"}) is False


def test_is_event_visible_unknown_type_with_none_returns_true():
    event = _make_event("NewUnknownEvent2099")
    assert is_event_visible(event, None) is True


def test_is_event_visible_unknown_type_not_in_set_returns_false():
    event = _make_event("NewUnknownEvent2099")
    assert is_event_visible(event, {"PushEvent"}) is False


def test_is_event_visible_unknown_type_in_set_returns_true():
    event = _make_event("NewUnknownEvent2099")
    assert is_event_visible(event, {"NewUnknownEvent2099"}) is True


# ---------------------------------------------------------------------------
# filter_feed
# ---------------------------------------------------------------------------


def test_filter_feed_empty_feed_returns_empty_list():
    assert filter_feed([], {"PushEvent"}) == []


def test_filter_feed_none_visible_returns_all_events():
    events = [_make_event("PushEvent"), _make_event("ForkEvent"), _make_event("WatchEvent")]
    result = filter_feed(events, None)
    assert len(result) == 3


def test_filter_feed_empty_visible_set_returns_empty_list():
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    assert filter_feed(events, set()) == []


def test_filter_feed_hides_non_visible_type():
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    result = filter_feed(events, {"ForkEvent"})
    assert len(result) == 1
    assert result[0].type == "ForkEvent"


def test_filter_feed_keeps_matching_type():
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    result = filter_feed(events, {"PushEvent", "ForkEvent"})
    assert len(result) == 2


def test_filter_feed_preserves_order():
    types = ["ForkEvent", "PushEvent", "WatchEvent"]
    events = [_make_event(t) for t in types]
    result = filter_feed(events, {"ForkEvent", "WatchEvent"})
    assert [e.type for e in result] == ["ForkEvent", "WatchEvent"]


def test_filter_feed_does_not_mutate_original_list():
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    original_len = len(events)
    filter_feed(events, {"ForkEvent"})
    assert len(events) == original_len


def test_filter_feed_returns_new_list_not_same_object():
    events = [_make_event("PushEvent")]
    result = filter_feed(events, None)
    assert result is not events


def test_filter_feed_multiple_events_of_hidden_type_all_removed():
    events = [_make_event("PushEvent")] * 3 + [_make_event("ForkEvent")]
    result = filter_feed(events, {"ForkEvent"})
    assert len(result) == 1
    assert result[0].type == "ForkEvent"


def test_filter_feed_multiple_events_of_visible_type_all_kept():
    events = [_make_event("PushEvent")] * 4
    result = filter_feed(events, {"PushEvent"})
    assert len(result) == 4


# ---------------------------------------------------------------------------
# Realistic scenarios
# ---------------------------------------------------------------------------


def test_filter_feed_only_pr_events_visible():
    pr_types = ["PullRequestEvent", "PullRequestReviewEvent",
                "PullRequestReviewCommentEvent", "PullRequestReviewThreadEvent"]
    all_events = [_make_event(t) for t in ALL_EVENT_TYPES]
    result = filter_feed(all_events, set(pr_types))
    assert all(e.type in pr_types for e in result)
    assert len(result) == len(pr_types)


def test_filter_feed_partial_filter_correct_count():
    # One event per type, hide 5 → 14 visible
    all_events = [_make_event(t) for t in ALL_EVENT_TYPES]
    hidden = {"PushEvent", "ForkEvent", "WatchEvent", "GollumEvent", "MemberEvent"}
    visible = set(ALL_EVENT_TYPES) - hidden
    result = filter_feed(all_events, visible)
    assert len(result) == len(ALL_EVENT_TYPES) - len(hidden)


def test_filter_feed_unknown_type_hidden_when_filter_configured():
    # Whitelist model: unknown types not in visible set are hidden
    events = [_make_event("NewGitHubEvent2099"), _make_event("PushEvent")]
    result = filter_feed(events, {"PushEvent"})
    assert len(result) == 1
    assert result[0].type == "PushEvent"


# ---------------------------------------------------------------------------
# Constants integrity
# ---------------------------------------------------------------------------


def test_config_key_value():
    assert CONFIG_KEY == "feed_visible_event_types"


def test_all_event_types_has_no_duplicates():
    assert len(ALL_EVENT_TYPES) == len(set(ALL_EVENT_TYPES))


def test_filter_groups_cover_all_event_types_exactly_once():
    covered = []
    for _label, types in FILTER_GROUPS:
        covered.extend(types)
    assert sorted(covered) == sorted(ALL_EVENT_TYPES)


def test_filter_groups_has_no_duplicates_within_or_across_groups():
    covered = []
    for _label, types in FILTER_GROUPS:
        covered.extend(types)
    assert len(covered) == len(set(covered))


# ---------------------------------------------------------------------------
# Account isolation
# ---------------------------------------------------------------------------


def test_different_prefs_give_different_visible_sets():
    prefs_a = {CONFIG_KEY: ["PushEvent"]}
    prefs_b = {CONFIG_KEY: ["ForkEvent"]}
    assert load_visible_types(prefs_a) != load_visible_types(prefs_b)


def test_filter_feed_with_account_a_prefs_hides_push():
    prefs_a = {CONFIG_KEY: ["ForkEvent"]}
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    visible = load_visible_types(prefs_a)
    result = filter_feed(events, visible)
    assert all(e.type == "ForkEvent" for e in result)


def test_filter_feed_with_account_b_prefs_hides_fork():
    prefs_b = {CONFIG_KEY: ["PushEvent"]}
    events = [_make_event("PushEvent"), _make_event("ForkEvent")]
    visible = load_visible_types(prefs_b)
    result = filter_feed(events, visible)
    assert all(e.type == "PushEvent" for e in result)


def test_saving_account_b_prefs_does_not_affect_account_a_prefs():
    prefs_a = {CONFIG_KEY: ["PushEvent"]}
    prefs_b = {}
    save_visible_types(prefs_b, {"ForkEvent"})
    assert load_visible_types(prefs_a) == {"PushEvent"}


# ---------------------------------------------------------------------------
# Roundtrips
# ---------------------------------------------------------------------------


def test_roundtrip_single_type():
    prefs = {}
    save_visible_types(prefs, {"PushEvent"})
    assert load_visible_types(prefs) == {"PushEvent"}


def test_roundtrip_empty_set_returns_empty_set_not_none():
    prefs = {}
    save_visible_types(prefs, set())
    result = load_visible_types(prefs)
    assert result is not None
    assert result == set()


def test_roundtrip_partial_set_preserved():
    original = {"PushEvent", "ForkEvent", "WatchEvent"}
    prefs = {}
    save_visible_types(prefs, original)
    assert load_visible_types(prefs) == original


def test_roundtrip_all_types():
    prefs = {}
    save_visible_types(prefs, set(ALL_EVENT_TYPES))
    assert load_visible_types(prefs) == set(ALL_EVENT_TYPES)
