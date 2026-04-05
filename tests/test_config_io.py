"""Mock/integration tests for config.py — file I/O and path logic.

Uses tmp_path fixtures so no real config dirs are touched.
"""

import json
import os
import platform
import pytest

import config as cfg_module
from config import Config, get_config_home, is_portable_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_config(tmp_path, name="FastGH", data=None):
    """Create a Config pointed at tmp_path, skipping disk load."""
    return Config(name=name, autosave=False, save_on_exit=False, _data=data if data is not None else {})


# ---------------------------------------------------------------------------
# Config._load — reads JSON from disk
# ---------------------------------------------------------------------------


def test_load_reads_existing_file(tmp_path, monkeypatch):
    payload = {"key": "value", "num": 42}
    conf_dir = tmp_path / "FastGH"
    conf_dir.mkdir()
    (conf_dir / "config.json").write_text(json.dumps(payload))

    monkeypatch.setattr(cfg_module, "get_config_home", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "_portable_checked", False)
    monkeypatch.setattr(cfg_module, "_portable_path", None)
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH", autosave=False, save_on_exit=False)
    assert c["key"] == "value"
    assert c["num"] == 42


def test_load_missing_file_yields_empty_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "get_config_home", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH", autosave=False, save_on_exit=False)
    assert len(c) == 0


def test_load_invalid_json_yields_empty_config(tmp_path, monkeypatch, capsys):
    conf_dir = tmp_path / "FastGH"
    conf_dir.mkdir()
    (conf_dir / "config.json").write_text("{bad json")

    monkeypatch.setattr(cfg_module, "get_config_home", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH", autosave=False, save_on_exit=False)
    assert len(c) == 0
    captured = capsys.readouterr()
    assert "Error loading config" in captured.out


# ---------------------------------------------------------------------------
# Config.save — writes JSON to disk
# ---------------------------------------------------------------------------


def test_save_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "get_config_home", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH", autosave=False, save_on_exit=False, _data={"x": 1})
    # Override the config_file path directly via the _user_config_home attribute
    c._user_config_home = str(tmp_path)
    c.save()

    conf_path = tmp_path / "FastGH" / "config.json"
    assert conf_path.exists()
    loaded = json.loads(conf_path.read_text())
    assert loaded["x"] == 1


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "get_config_home", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    data = {"foo": "bar", "nested": {"a": 1}}
    c = Config(name="FastGH", autosave=False, save_on_exit=False, _data=data)
    c._user_config_home = str(tmp_path)
    c.save()

    conf_path = tmp_path / "FastGH" / "config.json"
    loaded = json.loads(conf_path.read_text())
    assert loaded["foo"] == "bar"
    assert loaded["nested"]["a"] == 1


def test_save_creates_intermediate_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH/account0", autosave=False, save_on_exit=False, _data={"token": "abc"})
    c._user_config_home = str(tmp_path)
    c.save()

    conf_path = tmp_path / "FastGH" / "account0" / "config.json"
    assert conf_path.exists()
    assert json.loads(conf_path.read_text())["token"] == "abc"


def test_save_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    c = Config(name="FastGH", autosave=False, save_on_exit=False, _data={"v": 1})
    c._user_config_home = str(tmp_path)
    c.save()

    c._data["v"] = 99
    c.save()

    conf_path = tmp_path / "FastGH" / "config.json"
    loaded = json.loads(conf_path.read_text())
    assert loaded["v"] == 99


def test_child_save_delegates_to_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    class _FakeParent:
        def __init__(self):
            self.saved = 0
            self._user_config_home = str(tmp_path)
            self._name = "FastGH"
        def save(self):
            self.saved += 1

    parent = _FakeParent()
    child = Config("FastGH", autosave=False, save_on_exit=False, _parent=parent, _data={"x": 1})
    child.save()
    assert parent.saved == 1


# ---------------------------------------------------------------------------
# Config.config_file — path logic
# ---------------------------------------------------------------------------


def test_config_file_non_portable(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: None)

    c = Config(name="FastGH", autosave=False, save_on_exit=False, _data={})
    c._user_config_home = str(tmp_path)
    assert c.config_file == str(tmp_path / "FastGH" / "config.json")


def test_config_file_portable_main(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: True)
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "_portable_path", str(tmp_path))

    c = Config(name="FastGH", autosave=False, save_on_exit=False, _data={})
    c._user_config_home = str(tmp_path)
    assert c.config_file == str(tmp_path / "config.json")


def test_config_file_portable_subaccount(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: True)
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: str(tmp_path))
    monkeypatch.setattr(cfg_module, "_portable_path", str(tmp_path))

    c = Config(name="FastGH/account0", autosave=False, save_on_exit=False, _data={})
    c._user_config_home = str(tmp_path)
    assert c.config_file == str(tmp_path / "account0" / "config.json")


# ---------------------------------------------------------------------------
# Config autosave — triggers save on __setitem__
# ---------------------------------------------------------------------------


def test_autosave_triggers_on_setitem(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    saves = []

    class _TrackingConfig(Config):
        def save(self):
            saves.append(1)

    c = _TrackingConfig(name="FastGH", autosave=True, save_on_exit=False, _data={})
    c["key"] = "val"
    assert len(saves) == 1


def test_autosave_triggers_on_delitem(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "is_portable_mode", lambda: False)

    saves = []

    class _TrackingConfig(Config):
        def save(self):
            saves.append(1)

    c = _TrackingConfig(name="FastGH", autosave=True, save_on_exit=False, _data={"k": 1})
    del c["k"]
    assert len(saves) == 1


# ---------------------------------------------------------------------------
# Config.close
# ---------------------------------------------------------------------------


def test_close_saves_and_returns_true(monkeypatch):
    saves = []

    class _TrackingConfig(Config):
        def save(self):
            saves.append(1)

    c = _TrackingConfig(name="FastGH", autosave=False, save_on_exit=False, _data={})
    result = c.close()
    assert result is True
    assert len(saves) == 1


def test_close_second_call_returns_false(monkeypatch):
    saves = []

    class _TrackingConfig(Config):
        def save(self):
            saves.append(1)

    c = _TrackingConfig(name="FastGH", autosave=False, save_on_exit=False, _data={})
    c.close()
    result = c.close()
    assert result is False
    assert len(saves) == 1  # second close did not save again


# ---------------------------------------------------------------------------
# is_portable_mode — detection logic
# ---------------------------------------------------------------------------


def test_portable_mode_detected_when_userdata_exists(tmp_path, monkeypatch):
    userdata = tmp_path / "userdata"
    userdata.mkdir()
    monkeypatch.setattr(cfg_module, "_portable_checked", False)
    monkeypatch.setattr(cfg_module, "_portable_path", None)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    # Force non-Darwin for this test
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    result = cfg_module.is_portable_mode()
    assert result is True
    assert cfg_module._portable_path == str(userdata)

    # Cleanup module state
    cfg_module._portable_checked = False
    cfg_module._portable_path = None


def test_portable_mode_not_detected_without_userdata(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "_portable_checked", False)
    monkeypatch.setattr(cfg_module, "_portable_path", None)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    result = cfg_module.is_portable_mode()
    assert result is False

    # Cleanup module state
    cfg_module._portable_checked = False
    cfg_module._portable_path = None


def test_portable_mode_false_on_macos(monkeypatch):
    monkeypatch.setattr(cfg_module, "_portable_checked", False)
    monkeypatch.setattr(cfg_module, "_portable_path", None)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    result = cfg_module.is_portable_mode()
    assert result is False

    cfg_module._portable_checked = False
    cfg_module._portable_path = None


def test_portable_mode_cached_after_first_check(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "_portable_checked", True)
    monkeypatch.setattr(cfg_module, "_portable_path", "/fake/userdata")

    # Even though userdata doesn't exist, cached result is used
    result = cfg_module.is_portable_mode()
    assert result is True

    cfg_module._portable_checked = False
    cfg_module._portable_path = None


# ---------------------------------------------------------------------------
# get_config_home — platform dispatch
# ---------------------------------------------------------------------------


def test_get_config_home_windows(monkeypatch):
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: None)
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")
    result = cfg_module.get_config_home()
    assert result == "C:\\Users\\test\\AppData\\Roaming"


def test_get_config_home_linux(monkeypatch):
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: None)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/user/.config")
    result = cfg_module.get_config_home()
    assert result == "/home/user/.config"


def test_get_config_home_portable_takes_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_module, "get_portable_path", lambda: str(tmp_path))
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = cfg_module.get_config_home()
    assert result == str(tmp_path)
