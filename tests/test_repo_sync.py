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


def test_sync_path_requires_git_repo(tmp_path):
    prefs = DummyPrefs()
    mgr = RepoSyncManager(prefs)
    repo_dir = tmp_path / "external-repo"
    repo_dir.mkdir()

    result = mgr.sync_path(str(repo_dir), repo_label="external")
    assert result.ok is False
    assert "Not a git repo" in result.message


def test_remote_provider_detects_gitlab(monkeypatch):
    prefs = DummyPrefs()
    mgr = RepoSyncManager(prefs)

    def fake_run_git_allow_fail(repo_path, args):
        return True, "git@gitlab.com:group/project.git"

    monkeypatch.setattr(mgr, "_run_git_allow_fail", fake_run_git_allow_fail)
    assert mgr._remote_provider_name("/tmp/unused") == "gitlab"


def test_detect_cross_os_hints(monkeypatch):
    prefs = DummyPrefs()
    mgr = RepoSyncManager(prefs)

    monkeypatch.setattr(mgr, "_has_upstream", lambda _: True)
    monkeypatch.setattr(
        mgr,
        "_run_git_allow_fail",
        lambda repo_path, args: (True, "Fix windows path issue\nAlso verified on macOS and Linux"),
    )

    hints = mgr._detect_cross_os_hints("/tmp/unused")
    assert "windows" in hints
    assert "macos" in hints
    assert "linux" in hints
