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
    MUTED_REPOS_KEY,
    USER_FILTERS_KEY,
    filter_feed,
    is_event_visible,
    load_muted_repos,
    load_user_filters,
    load_visible_types,
    save_muted_repos,
    save_user_filters,
    save_visible_types,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_type: str, repo: str = "owner/repo", actor: str = "alice") -> Event:
    return Event.from_api(
        {
            "id": "1",
            "type": event_type,
            "actor": {"id": 1, "login": actor, "avatar_url": ""},
            "repo": {"id": 1, "name": repo, "url": ""},
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


# ---------------------------------------------------------------------------
# load_muted_repos — baseline
# ---------------------------------------------------------------------------


def test_load_muted_repos_absent_key_returns_none():
    assert load_muted_repos({}) is None


def test_load_muted_repos_empty_list_returns_empty_set():
    assert load_muted_repos({MUTED_REPOS_KEY: []}) == set()


def test_load_muted_repos_single_repo():
    assert load_muted_repos({MUTED_REPOS_KEY: ["owner/repo"]}) == {"owner/repo"}


def test_load_muted_repos_multiple_repos():
    result = load_muted_repos({MUTED_REPOS_KEY: ["alice/foo", "bob/bar"]})
    assert result == {"alice/foo", "bob/bar"}


# ---------------------------------------------------------------------------
# load_muted_repos — corrupt / invalid stored data
# ---------------------------------------------------------------------------


def test_load_muted_repos_string_value_returns_none():
    assert load_muted_repos({MUTED_REPOS_KEY: "owner/repo"}) is None


def test_load_muted_repos_dict_value_returns_none():
    assert load_muted_repos({MUTED_REPOS_KEY: {"owner/repo": True}}) is None


def test_load_muted_repos_none_value_returns_none():
    assert load_muted_repos({MUTED_REPOS_KEY: None}) is None


def test_load_muted_repos_integer_value_returns_none():
    assert load_muted_repos({MUTED_REPOS_KEY: 42}) is None


def test_load_muted_repos_list_drops_non_string_items():
    result = load_muted_repos({MUTED_REPOS_KEY: [42, None, "owner/repo", 3.14]})
    assert result == {"owner/repo"}


def test_load_muted_repos_list_all_non_strings_returns_empty_set():
    result = load_muted_repos({MUTED_REPOS_KEY: [1, 2, None]})
    assert result == set()


# ---------------------------------------------------------------------------
# save_muted_repos
# ---------------------------------------------------------------------------


def test_save_muted_repos_writes_sorted_list():
    prefs = {}
    save_muted_repos(prefs, {"charlie/z", "alice/a", "bob/m"})
    assert prefs[MUTED_REPOS_KEY] == ["alice/a", "bob/m", "charlie/z"]


def test_save_muted_repos_empty_set_writes_empty_list():
    prefs = {}
    save_muted_repos(prefs, set())
    assert prefs[MUTED_REPOS_KEY] == []


def test_save_muted_repos_uses_correct_key():
    prefs = {}
    save_muted_repos(prefs, {"owner/repo"})
    assert MUTED_REPOS_KEY in prefs


def test_save_muted_repos_overwrites_existing():
    prefs = {MUTED_REPOS_KEY: ["old/repo"]}
    save_muted_repos(prefs, {"new/repo"})
    assert prefs[MUTED_REPOS_KEY] == ["new/repo"]


def test_save_muted_repos_key_present_after_empty_save():
    prefs = {}
    save_muted_repos(prefs, set())
    assert MUTED_REPOS_KEY in prefs
    assert load_muted_repos(prefs) == set()


# ---------------------------------------------------------------------------
# filter_feed — muted repos
# ---------------------------------------------------------------------------


def test_filter_feed_muted_repos_none_passes_all():
    events = [_make_event("PushEvent", "alice/foo"), _make_event("ForkEvent", "bob/bar")]
    assert len(filter_feed(events, None, None)) == 2


def test_filter_feed_muted_repos_empty_set_passes_all():
    events = [_make_event("PushEvent", "alice/foo"), _make_event("ForkEvent", "bob/bar")]
    assert len(filter_feed(events, None, set())) == 2


def test_filter_feed_muted_repo_hides_matching_events():
    events = [
        _make_event("PushEvent", "alice/foo"),
        _make_event("ForkEvent", "bob/bar"),
    ]
    result = filter_feed(events, None, {"alice/foo"})
    assert len(result) == 1
    assert result[0].repo.name == "bob/bar"


def test_filter_feed_muted_repo_hides_all_event_types_from_that_repo():
    events = [_make_event(t, "noisy/repo") for t in ["PushEvent", "ForkEvent", "WatchEvent"]]
    result = filter_feed(events, None, {"noisy/repo"})
    assert result == []


def test_filter_feed_non_muted_repo_events_pass_through():
    events = [_make_event("PushEvent", "safe/repo")]
    result = filter_feed(events, None, {"other/repo"})
    assert len(result) == 1


def test_filter_feed_muted_repos_and_visible_types_both_applied():
    events = [
        _make_event("PushEvent", "alice/foo"),   # wrong repo
        _make_event("ForkEvent", "bob/bar"),     # wrong type
        _make_event("PushEvent", "bob/bar"),     # passes both
    ]
    result = filter_feed(events, {"PushEvent"}, {"alice/foo"})
    assert len(result) == 1
    assert result[0].repo.name == "bob/bar"
    assert result[0].type == "PushEvent"


def test_filter_feed_muted_repo_beats_visible_type():
    # Even if the event type is in visible, muted repo blocks it
    events = [_make_event("PushEvent", "muted/repo")]
    result = filter_feed(events, {"PushEvent"}, {"muted/repo"})
    assert result == []


def test_filter_feed_multiple_muted_repos():
    events = [
        _make_event("PushEvent", "muted/one"),
        _make_event("PushEvent", "muted/two"),
        _make_event("PushEvent", "allowed/repo"),
    ]
    result = filter_feed(events, None, {"muted/one", "muted/two"})
    assert len(result) == 1
    assert result[0].repo.name == "allowed/repo"


def test_filter_feed_muted_repos_preserves_order():
    events = [
        _make_event("PushEvent", "keep/a"),
        _make_event("PushEvent", "muted/x"),
        _make_event("PushEvent", "keep/b"),
    ]
    result = filter_feed(events, None, {"muted/x"})
    assert [e.repo.name for e in result] == ["keep/a", "keep/b"]


def test_filter_feed_does_not_mutate_original_with_muted_repos():
    events = [_make_event("PushEvent", "muted/repo"), _make_event("ForkEvent", "safe/repo")]
    original_len = len(events)
    filter_feed(events, None, {"muted/repo"})
    assert len(events) == original_len


# ---------------------------------------------------------------------------
# Muted repos roundtrips
# ---------------------------------------------------------------------------


def test_muted_repos_roundtrip_single():
    prefs = {}
    save_muted_repos(prefs, {"owner/repo"})
    assert load_muted_repos(prefs) == {"owner/repo"}


def test_muted_repos_roundtrip_multiple():
    original = {"alice/foo", "bob/bar", "charlie/baz"}
    prefs = {}
    save_muted_repos(prefs, original)
    assert load_muted_repos(prefs) == original


def test_muted_repos_roundtrip_empty_returns_empty_not_none():
    prefs = {}
    save_muted_repos(prefs, set())
    result = load_muted_repos(prefs)
    assert result is not None
    assert result == set()


# ---------------------------------------------------------------------------
# Muted repos account isolation
# ---------------------------------------------------------------------------


def test_muted_repos_different_prefs_give_different_sets():
    prefs_a = {MUTED_REPOS_KEY: ["alice/foo"]}
    prefs_b = {MUTED_REPOS_KEY: ["bob/bar"]}
    assert load_muted_repos(prefs_a) != load_muted_repos(prefs_b)


def test_saving_muted_repos_for_b_does_not_affect_a():
    prefs_a = {MUTED_REPOS_KEY: ["alice/foo"]}
    prefs_b = {}
    save_muted_repos(prefs_b, {"bob/bar"})
    assert load_muted_repos(prefs_a) == {"alice/foo"}


def test_muted_repos_key_value():
    assert MUTED_REPOS_KEY == "feed_muted_repos"


# ---------------------------------------------------------------------------
# load_user_filters — baseline
# ---------------------------------------------------------------------------


def test_load_user_filters_absent_key_returns_none():
    assert load_user_filters({}) is None


def test_load_user_filters_empty_dict_returns_empty_dict():
    assert load_user_filters({USER_FILTERS_KEY: {}}) == {}


def test_load_user_filters_single_user_all_types():
    result = load_user_filters({USER_FILTERS_KEY: {"alice": ["PushEvent"]}})
    assert result == {"alice": {"PushEvent"}}


def test_load_user_filters_multiple_users():
    result = load_user_filters({
        USER_FILTERS_KEY: {"alice": ["PushEvent"], "bob": ["ForkEvent", "WatchEvent"]}
    })
    assert result == {"alice": {"PushEvent"}, "bob": {"ForkEvent", "WatchEvent"}}


def test_load_user_filters_empty_list_means_muted():
    result = load_user_filters({USER_FILTERS_KEY: {"alice": []}})
    assert result == {"alice": set()}


# ---------------------------------------------------------------------------
# load_user_filters — corrupt / invalid stored data
# ---------------------------------------------------------------------------


def test_load_user_filters_non_dict_top_level_returns_none():
    assert load_user_filters({USER_FILTERS_KEY: ["alice"]}) is None


def test_load_user_filters_string_top_level_returns_none():
    assert load_user_filters({USER_FILTERS_KEY: "alice"}) is None


def test_load_user_filters_none_top_level_returns_none():
    assert load_user_filters({USER_FILTERS_KEY: None}) is None


def test_load_user_filters_integer_top_level_returns_none():
    assert load_user_filters({USER_FILTERS_KEY: 42}) is None


def test_load_user_filters_accepts_mapping_not_just_dict():
    # Config wraps stored dicts as a MutableMapping subclass — must be accepted.
    from collections.abc import MutableMapping

    class FakeConfig(MutableMapping):
        def __init__(self, data):
            self._d = data
        def __getitem__(self, k): return self._d[k]
        def __setitem__(self, k, v): self._d[k] = v
        def __delitem__(self, k): del self._d[k]
        def __iter__(self): return iter(self._d)
        def __len__(self): return len(self._d)

    raw = FakeConfig({"alice": ["PushEvent"]})
    prefs = {USER_FILTERS_KEY: raw}
    result = load_user_filters(prefs)
    assert result == {"alice": {"PushEvent"}}


def test_load_user_filters_invalid_username_key_skipped():
    result = load_user_filters({USER_FILTERS_KEY: {42: ["PushEvent"], "alice": ["ForkEvent"]}})
    assert result == {"alice": {"ForkEvent"}}


def test_load_user_filters_invalid_types_list_entry_skipped():
    result = load_user_filters({USER_FILTERS_KEY: {"alice": "PushEvent", "bob": ["ForkEvent"]}})
    assert result == {"bob": {"ForkEvent"}}


def test_load_user_filters_non_string_types_dropped():
    result = load_user_filters({USER_FILTERS_KEY: {"alice": [42, None, "PushEvent"]}})
    assert result == {"alice": {"PushEvent"}}


# ---------------------------------------------------------------------------
# save_user_filters
# ---------------------------------------------------------------------------


def test_save_user_filters_writes_sorted_lists():
    prefs = {}
    save_user_filters(prefs, {"alice": {"WatchEvent", "ForkEvent", "PushEvent"}})
    assert prefs[USER_FILTERS_KEY] == {"alice": ["ForkEvent", "PushEvent", "WatchEvent"]}


def test_save_user_filters_empty_set_means_muted():
    prefs = {}
    save_user_filters(prefs, {"alice": set()})
    assert prefs[USER_FILTERS_KEY] == {"alice": []}


def test_save_user_filters_multiple_users():
    prefs = {}
    save_user_filters(prefs, {"alice": {"PushEvent"}, "bob": set()})
    assert prefs[USER_FILTERS_KEY]["alice"] == ["PushEvent"]
    assert prefs[USER_FILTERS_KEY]["bob"] == []


def test_save_user_filters_uses_correct_key():
    prefs = {}
    save_user_filters(prefs, {"alice": {"PushEvent"}})
    assert USER_FILTERS_KEY in prefs


def test_save_user_filters_overwrites_existing():
    prefs = {USER_FILTERS_KEY: {"old": ["PushEvent"]}}
    save_user_filters(prefs, {"new": {"ForkEvent"}})
    assert "old" not in prefs[USER_FILTERS_KEY]
    assert prefs[USER_FILTERS_KEY]["new"] == ["ForkEvent"]


def test_save_user_filters_empty_dict():
    prefs = {}
    save_user_filters(prefs, {})
    assert prefs[USER_FILTERS_KEY] == {}


# ---------------------------------------------------------------------------
# filter_feed — user filters
# ---------------------------------------------------------------------------


def test_filter_feed_user_filters_none_uses_global():
    events = [_make_event("PushEvent", actor="alice"), _make_event("ForkEvent", actor="alice")]
    result = filter_feed(events, {"PushEvent"}, None, None)
    assert len(result) == 1
    assert result[0].type == "PushEvent"


def test_filter_feed_user_filter_overrides_global_for_that_actor():
    # Global hides ForkEvent, but alice has a rule allowing it
    events = [_make_event("ForkEvent", actor="alice")]
    result = filter_feed(events, {"PushEvent"}, None, {"alice": {"ForkEvent"}})
    assert len(result) == 1


def test_filter_feed_user_filter_empty_set_mutes_user():
    events = [_make_event("PushEvent", actor="alice"), _make_event("PushEvent", actor="bob")]
    result = filter_feed(events, {"PushEvent"}, None, {"alice": set()})
    assert len(result) == 1
    assert result[0].actor.login == "bob"


def test_filter_feed_user_filter_does_not_affect_other_actors():
    events = [
        _make_event("ForkEvent", actor="alice"),
        _make_event("ForkEvent", actor="bob"),
    ]
    # alice has a rule (PushEvent only), bob uses global (all)
    result = filter_feed(events, None, None, {"alice": {"PushEvent"}})
    assert len(result) == 1
    assert result[0].actor.login == "bob"


def test_filter_feed_user_filter_type_in_rule_passes():
    events = [_make_event("PushEvent", actor="alice")]
    result = filter_feed(events, None, None, {"alice": {"PushEvent", "ForkEvent"}})
    assert len(result) == 1


def test_filter_feed_user_filter_type_not_in_rule_hidden():
    events = [_make_event("WatchEvent", actor="alice")]
    result = filter_feed(events, None, None, {"alice": {"PushEvent"}})
    assert result == []


def test_filter_feed_muted_repo_beats_user_filter():
    # Even if actor has a permissive user rule, muted repo wins
    events = [_make_event("PushEvent", repo="muted/repo", actor="alice")]
    result = filter_feed(events, None, {"muted/repo"}, {"alice": set(ALL_EVENT_TYPES)})
    assert result == []


def test_filter_feed_all_three_filters_interact():
    events = [
        _make_event("PushEvent", repo="muted/repo", actor="alice"),  # blocked by repo
        _make_event("ForkEvent", repo="safe/repo", actor="alice"),   # alice rule: PushEvent only → hidden
        _make_event("PushEvent", repo="safe/repo", actor="alice"),   # alice rule: passes
        _make_event("ForkEvent", repo="safe/repo", actor="bob"),     # global: PushEvent only → hidden
        _make_event("PushEvent", repo="safe/repo", actor="bob"),     # global: passes
    ]
    result = filter_feed(events, {"PushEvent"}, {"muted/repo"}, {"alice": {"PushEvent"}})
    assert len(result) == 2
    assert all(e.type == "PushEvent" for e in result)


def test_filter_feed_user_filters_empty_dict_uses_global():
    events = [_make_event("ForkEvent", actor="alice")]
    result = filter_feed(events, {"PushEvent"}, None, {})
    assert result == []


def test_filter_feed_user_filter_matches_case_insensitive_actor():
    # API may return actor login in any case; stored key is lowercase
    events = [_make_event("PushEvent", actor="Alice")]
    result = filter_feed(events, None, None, {"alice": set()})
    assert result == []


def test_filter_feed_user_filter_mixed_case_actor_types_respected():
    events = [
        _make_event("PushEvent", actor="Alice"),
        _make_event("ForkEvent", actor="Alice"),
    ]
    result = filter_feed(events, None, None, {"alice": {"PushEvent"}})
    assert len(result) == 1
    assert result[0].type == "PushEvent"


def test_filter_feed_muted_repo_matches_case_insensitive():
    # Stored repo names are lowercased; API may return mixed case
    events = [_make_event("PushEvent", repo="Owner/Repo")]
    result = filter_feed(events, None, {"owner/repo"}, None)
    assert result == []


# ---------------------------------------------------------------------------
# User filters roundtrips
# ---------------------------------------------------------------------------


def test_user_filters_roundtrip_single_user():
    prefs = {}
    save_user_filters(prefs, {"alice": {"PushEvent", "ForkEvent"}})
    result = load_user_filters(prefs)
    assert result == {"alice": {"PushEvent", "ForkEvent"}}


def test_user_filters_roundtrip_muted_user():
    prefs = {}
    save_user_filters(prefs, {"alice": set()})
    result = load_user_filters(prefs)
    assert result == {"alice": set()}


def test_user_filters_roundtrip_multiple_users():
    original = {"alice": {"PushEvent"}, "bob": set(), "charlie": set(ALL_EVENT_TYPES)}
    prefs = {}
    save_user_filters(prefs, original)
    assert load_user_filters(prefs) == original


def test_user_filters_roundtrip_empty_dict():
    prefs = {}
    save_user_filters(prefs, {})
    result = load_user_filters(prefs)
    assert result == {}


# ---------------------------------------------------------------------------
# User filters account isolation
# ---------------------------------------------------------------------------


def test_user_filters_different_prefs_independent():
    prefs_a = {USER_FILTERS_KEY: {"alice": ["PushEvent"]}}
    prefs_b = {USER_FILTERS_KEY: {"bob": []}}
    assert load_user_filters(prefs_a) != load_user_filters(prefs_b)


def test_saving_user_filters_for_b_does_not_affect_a():
    prefs_a = {USER_FILTERS_KEY: {"alice": ["PushEvent"]}}
    prefs_b = {}
    save_user_filters(prefs_b, {"bob": set()})
    assert load_user_filters(prefs_a) == {"alice": {"PushEvent"}}


def test_user_filters_key_value():
    assert USER_FILTERS_KEY == "feed_user_filters"
