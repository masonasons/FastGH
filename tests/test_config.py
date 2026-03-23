"""Tests for config.py — Config class in-memory behaviour.

All tests use _data= to bypass file I/O so no files are read or written.
"""

import pytest
from collections.abc import MutableMapping

from config import Config


def _cfg(data=None) -> Config:
    """Create a Config backed by in-memory data only (no file I/O)."""
    return Config("FastGH", autosave=False, save_on_exit=False, _data=data if data is not None else {})


# ---------------------------------------------------------------------------
# MutableMapping contract
# ---------------------------------------------------------------------------


def test_config_is_mutable_mapping():
    assert isinstance(_cfg(), MutableMapping)


def test_config_len_empty():
    assert len(_cfg()) == 0


def test_config_len_reflects_stored_keys():
    c = _cfg({"a": 1, "b": 2})
    assert len(c) == 2


def test_config_iter_yields_keys():
    c = _cfg({"x": 10, "y": 20})
    assert set(c) == {"x", "y"}


def test_config_contains_existing_key():
    c = _cfg({"key": "val"})
    assert "key" in c


def test_config_contains_missing_key():
    c = _cfg()
    assert "missing" not in c


# ---------------------------------------------------------------------------
# __getitem__ / __setitem__ / __delitem__
# ---------------------------------------------------------------------------


def test_config_getitem_returns_value():
    c = _cfg({"name": "FastGH"})
    assert c["name"] == "FastGH"


def test_config_getitem_missing_key_raises_key_error():
    c = _cfg()
    with pytest.raises(KeyError):
        _ = c["nope"]


def test_config_setitem_stores_value():
    c = _cfg()
    c["foo"] = 42
    assert c["foo"] == 42


def test_config_setitem_overwrites_existing():
    c = _cfg({"k": 1})
    c["k"] = 99
    assert c["k"] == 99


def test_config_delitem_removes_key():
    c = _cfg({"remove_me": True})
    del c["remove_me"]
    assert "remove_me" not in c


def test_config_delitem_missing_raises_key_error():
    c = _cfg()
    with pytest.raises(KeyError):
        del c["ghost"]


# ---------------------------------------------------------------------------
# dict-wrapping behaviour (the bug that caused real issues)
# ---------------------------------------------------------------------------


def test_config_setitem_dict_value_is_wrapped_as_config():
    c = _cfg()
    c["nested"] = {"a": 1}
    assert isinstance(c["nested"], Config)


def test_config_wrapped_dict_is_mutable_mapping():
    c = _cfg()
    c["nested"] = {"a": 1}
    assert isinstance(c["nested"], MutableMapping)


def test_config_wrapped_dict_is_not_plain_dict():
    c = _cfg()
    c["nested"] = {"a": 1}
    assert not isinstance(c["nested"], dict)


def test_config_wrapped_dict_values_accessible():
    c = _cfg()
    c["nested"] = {"key": "value"}
    assert c["nested"]["key"] == "value"


def test_config_non_dict_value_not_wrapped():
    c = _cfg()
    c["items"] = [1, 2, 3]
    assert isinstance(c["items"], list)


def test_config_integer_not_wrapped():
    c = _cfg()
    c["count"] = 7
    assert c["count"] == 7
    assert type(c["count"]) is int


def test_config_string_not_wrapped():
    c = _cfg()
    c["label"] = "hello"
    assert type(c["label"]) is str


# ---------------------------------------------------------------------------
# .get() method
# ---------------------------------------------------------------------------


def test_config_get_existing_key():
    c = _cfg({"token": "abc"})
    assert c.get("token") == "abc"


def test_config_get_missing_key_returns_none():
    c = _cfg()
    assert c.get("missing") is None


def test_config_get_missing_key_with_default():
    c = _cfg()
    assert c.get("missing", "default") == "default"


def test_config_get_does_not_modify_config():
    c = _cfg()
    c.get("missing", "x")
    assert "missing" not in c


# ---------------------------------------------------------------------------
# Attribute access (__getattr__ / __setattr__ / __delattr__)
# ---------------------------------------------------------------------------


def test_config_attribute_read_existing_key():
    c = _cfg({"theme": "dark"})
    assert c.theme == "dark"


def test_config_attribute_read_missing_raises_attribute_error():
    c = _cfg()
    with pytest.raises(AttributeError):
        _ = c.nonexistent


def test_config_attribute_set_stores_as_key():
    c = _cfg()
    c.foo = "bar"
    assert c["foo"] == "bar"


def test_config_attribute_del_removes_key():
    c = _cfg({"tmp": 1})
    del c.tmp
    assert "tmp" not in c


def test_config_private_attr_not_routed_to_data():
    c = _cfg()
    # _name is set in __init__ via super().__setattr__, not via __setitem__
    assert c._name == "FastGH"


def test_config_private_attr_access_raises_attribute_error_if_missing():
    c = _cfg()
    with pytest.raises(AttributeError):
        _ = c._no_such_private


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


def test_config_repr_matches_data_repr():
    data = {"a": 1, "b": 2}
    c = _cfg(data)
    assert repr(c) == repr(data)


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_config_close_returns_true_first_call(monkeypatch):
    c = _cfg()
    monkeypatch.setattr(c, "save", lambda: None)
    assert c.close() is True


def test_config_close_returns_false_second_call(monkeypatch):
    c = _cfg()
    monkeypatch.setattr(c, "save", lambda: None)
    c.close()
    assert c.close() is False


def test_config_close_sets_closed_flag(monkeypatch):
    c = _cfg()
    monkeypatch.setattr(c, "save", lambda: None)
    c.close()
    assert c._closed is True


# ---------------------------------------------------------------------------
# Child Config (save delegates to parent)
# ---------------------------------------------------------------------------


def test_config_child_save_delegates_to_parent():
    # Config.__setattr__ routes any non-underscore attribute to _data, which
    # means we can't monkeypatch parent.save in the normal way.
    # Use a plain fake parent object instead.
    saved = []

    class _FakeParent:
        def save(self):
            saved.append(1)

    child = Config("FastGH", _parent=_FakeParent(), _data={"x": 1})
    child.save()
    assert len(saved) == 1


def test_config_child_inherits_name_from_parent():
    parent = _cfg()
    child = Config("FastGH", _parent=parent, _data={})
    assert child._name == "FastGH"
