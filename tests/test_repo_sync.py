from repo_sync import RepoSyncManager


class DummyPrefs(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


def test_repo_sync_defaults_are_initialized():
    prefs = DummyPrefs()
    mgr = RepoSyncManager(prefs)
    assert mgr.prefs.repo_sync_enabled is False
    assert mgr.prefs.repo_sync_interval_minutes == 0
    assert isinstance(mgr.prefs.repo_sync_configs, dict)
    assert mgr.prefs.repo_sync_use_github_tools is True


def test_repo_sync_config_roundtrip():
    prefs = DummyPrefs()
    mgr = RepoSyncManager(prefs)

    mgr.set_repo_config(
        "Raywonder/FastGH",
        enabled=True,
        auto_pull=True,
        auto_push=False,
        path="/tmp/FastGH",
    )

    cfg = mgr.get_repo_config("Raywonder/FastGH")
    assert cfg["enabled"] is True
    assert cfg["auto_pull"] is True
    assert cfg["auto_push"] is False
    assert cfg["path"] == "/tmp/FastGH"

    enabled = mgr.get_enabled_repos()
    assert len(enabled) == 1
    assert enabled[0][0] == "Raywonder/FastGH"
