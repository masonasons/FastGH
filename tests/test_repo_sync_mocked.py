"""Mock tests for repo_sync.py — RepoSyncManager logic with subprocess mocked."""

import platform
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from repo_sync import RepoSyncManager, RepoSyncResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePrefs(dict):
    """Plain dict that supports .get() and attribute set/get via __setattr__."""

    def __setattr__(self, name, value):
        self[name] = value

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _mgr(prefs_data=None) -> tuple[RepoSyncManager, _FakePrefs]:
    prefs = _FakePrefs(prefs_data or {})
    mgr = RepoSyncManager(prefs)
    return mgr, prefs


# ---------------------------------------------------------------------------
# _ensure_defaults
# ---------------------------------------------------------------------------


def test_ensure_defaults_sets_configs_key():
    mgr, prefs = _mgr()
    assert prefs.get(RepoSyncManager.PREF_CONFIGS) is not None


def test_ensure_defaults_sets_enabled_false():
    mgr, prefs = _mgr()
    assert prefs.get(RepoSyncManager.PREF_ENABLED) is False


def test_ensure_defaults_sets_interval_zero():
    mgr, prefs = _mgr()
    assert prefs.get(RepoSyncManager.PREF_INTERVAL) == 0


def test_ensure_defaults_sets_use_github_tools_true():
    mgr, prefs = _mgr()
    assert prefs.get(RepoSyncManager.PREF_USE_GITHUB_TOOLS) is True


def test_ensure_defaults_does_not_overwrite_existing():
    mgr, prefs = _mgr({RepoSyncManager.PREF_ENABLED: True, RepoSyncManager.PREF_INTERVAL: 15})
    assert prefs.get(RepoSyncManager.PREF_ENABLED) is True
    assert prefs.get(RepoSyncManager.PREF_INTERVAL) == 15


# ---------------------------------------------------------------------------
# get_repo_config / set_repo_config
# ---------------------------------------------------------------------------


def test_get_repo_config_returns_defaults_for_unknown_repo():
    mgr, _ = _mgr()
    cfg = mgr.get_repo_config("owner/repo")
    assert cfg["enabled"] is False
    assert cfg["auto_pull"] is True
    assert cfg["auto_push"] is False
    assert cfg["path"] == ""


def test_get_repo_config_uses_provided_default_path():
    mgr, _ = _mgr()
    cfg = mgr.get_repo_config("owner/repo", default_path="/home/user/repo")
    assert cfg["path"] == "/home/user/repo"


def test_set_repo_config_persists():
    mgr, _ = _mgr()
    mgr.set_repo_config("owner/repo", enabled=True, auto_pull=True, auto_push=False, path="/tmp/r")
    cfg = mgr.get_repo_config("owner/repo")
    assert cfg["enabled"] is True
    assert cfg["path"] == "/tmp/r"


def test_set_repo_config_overwrite():
    mgr, _ = _mgr()
    mgr.set_repo_config("owner/repo", enabled=True, auto_pull=True, auto_push=False, path="/a")
    mgr.set_repo_config("owner/repo", enabled=False, auto_pull=False, auto_push=True, path="/b")
    cfg = mgr.get_repo_config("owner/repo")
    assert cfg["enabled"] is False
    assert cfg["auto_push"] is True
    assert cfg["path"] == "/b"


def test_set_repo_config_multiple_repos_independent():
    mgr, _ = _mgr()
    mgr.set_repo_config("a/repo1", enabled=True, auto_pull=True, auto_push=False, path="/r1")
    mgr.set_repo_config("b/repo2", enabled=False, auto_pull=True, auto_push=True, path="/r2")
    assert mgr.get_repo_config("a/repo1")["path"] == "/r1"
    assert mgr.get_repo_config("b/repo2")["path"] == "/r2"


# ---------------------------------------------------------------------------
# get_enabled_repos
# ---------------------------------------------------------------------------


def test_get_enabled_repos_empty_when_none_enabled():
    mgr, _ = _mgr()
    mgr.set_repo_config("a/r", enabled=False, auto_pull=True, auto_push=False, path="/x")
    assert mgr.get_enabled_repos() == []


def test_get_enabled_repos_returns_enabled_only():
    mgr, _ = _mgr()
    mgr.set_repo_config("a/r1", enabled=True, auto_pull=True, auto_push=False, path="/r1")
    mgr.set_repo_config("b/r2", enabled=False, auto_pull=True, auto_push=False, path="/r2")
    enabled = mgr.get_enabled_repos()
    assert len(enabled) == 1
    assert enabled[0][0] == "a/r1"


def test_get_enabled_repos_returns_all_enabled():
    mgr, _ = _mgr()
    mgr.set_repo_config("a/r1", enabled=True, auto_pull=True, auto_push=False, path="/r1")
    mgr.set_repo_config("b/r2", enabled=True, auto_pull=True, auto_push=False, path="/r2")
    assert len(mgr.get_enabled_repos()) == 2


# ---------------------------------------------------------------------------
# sync_all_enabled — disabled at top level
# ---------------------------------------------------------------------------


def test_sync_all_enabled_returns_empty_when_globally_disabled():
    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_ENABLED] = False
    mgr.set_repo_config("a/r", enabled=True, auto_pull=True, auto_push=False, path="/r")
    results = mgr.sync_all_enabled()
    assert results == []


def test_sync_all_enabled_calls_sync_one_per_enabled_repo(tmp_path):
    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_ENABLED] = True
    mgr.set_repo_config("a/r1", enabled=True, auto_pull=True, auto_push=False, path=str(tmp_path))
    mgr.set_repo_config("b/r2", enabled=True, auto_pull=True, auto_push=False, path=str(tmp_path))

    called = []
    original_sync = mgr.sync_one

    def fake_sync(repo, cfg=None):
        called.append(repo)
        return RepoSyncResult(repo, True, "ok")

    mgr.sync_one = fake_sync
    mgr.sync_all_enabled()
    assert sorted(called) == ["a/r1", "b/r2"]


# ---------------------------------------------------------------------------
# sync_one — error paths (no subprocess needed)
# ---------------------------------------------------------------------------


def test_sync_one_no_path_configured():
    mgr, _ = _mgr()
    result = mgr.sync_one("owner/repo", {"path": "", "auto_pull": True, "auto_push": False})
    assert result.ok is False
    assert "No local path" in result.message


def test_sync_one_path_not_a_directory(tmp_path):
    mgr, _ = _mgr()
    fake_path = str(tmp_path / "nonexistent")
    result = mgr.sync_one("owner/repo", {"path": fake_path, "auto_pull": True, "auto_push": False})
    assert result.ok is False
    assert "Missing path" in result.message


def test_sync_one_not_a_git_repo(tmp_path):
    mgr, _ = _mgr()
    # Directory exists but no .git inside
    result = mgr.sync_one("owner/repo", {"path": str(tmp_path), "auto_pull": True, "auto_push": False})
    assert result.ok is False
    assert "Not a git repo" in result.message


# ---------------------------------------------------------------------------
# sync_one — success paths (subprocess mocked)
# ---------------------------------------------------------------------------


def _make_ok_result(stdout="", stderr="", returncode=0):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_sync_one_auto_pull_calls_fetch_and_pull(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_USE_GITHUB_TOOLS] = False
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = False

    with patch("subprocess.run", return_value=_make_ok_result()) as mock_run:
        result = mgr.sync_one("owner/repo", {"path": str(tmp_path), "auto_pull": True, "auto_push": False})

    assert result.ok is True
    commands = [call_args[0][0] for call_args in mock_run.call_args_list]
    assert ["git", "fetch", "--all", "--prune"] in commands
    assert ["git", "pull", "--ff-only"] in commands


def test_sync_one_auto_pull_false_skips_pull(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_USE_GITHUB_TOOLS] = False
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = False

    with patch("subprocess.run", return_value=_make_ok_result()) as mock_run:
        result = mgr.sync_one("owner/repo", {"path": str(tmp_path), "auto_pull": False, "auto_push": False})

    assert result.ok is True
    commands = [call_args[0][0] for call_args in mock_run.call_args_list]
    assert ["git", "pull", "--ff-only"] not in commands


def test_sync_one_git_error_returns_failure(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_USE_GITHUB_TOOLS] = False

    failed = _make_ok_result(stderr="network error", returncode=1)

    with patch("subprocess.run", return_value=failed):
        result = mgr.sync_one("owner/repo", {"path": str(tmp_path), "auto_pull": True, "auto_push": False})

    assert result.ok is False
    assert "network error" in result.message or "failed" in result.message.lower()


def test_sync_one_result_contains_repo_name(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_USE_GITHUB_TOOLS] = False
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = False

    with patch("subprocess.run", return_value=_make_ok_result()):
        result = mgr.sync_one("owner/myrepo", {"path": str(tmp_path), "auto_pull": True, "auto_push": False})

    assert result.repo == "owner/myrepo"


# ---------------------------------------------------------------------------
# _run_git — low-level helper
# ---------------------------------------------------------------------------


def test_run_git_returns_stdout_on_success(tmp_path):
    mgr, _ = _mgr()
    with patch("subprocess.run", return_value=_make_ok_result(stdout="main\n")):
        output = mgr._run_git(str(tmp_path), ["rev-parse", "--abbrev-ref", "HEAD"])
    assert output == "main"


def test_run_git_raises_runtime_error_on_nonzero(tmp_path):
    mgr, _ = _mgr()
    with patch("subprocess.run", return_value=_make_ok_result(stderr="fatal: bad object", returncode=1)):
        with pytest.raises(RuntimeError, match="fatal: bad object"):
            mgr._run_git(str(tmp_path), ["log"])


def test_run_git_allow_fail_returns_false_on_nonzero(tmp_path):
    mgr, _ = _mgr()
    with patch("subprocess.run", return_value=_make_ok_result(returncode=1, stderr="err")):
        ok, output = mgr._run_git_allow_fail(str(tmp_path), ["lfs", "version"])
    assert ok is False


def test_run_git_allow_fail_returns_true_on_success(tmp_path):
    mgr, _ = _mgr()
    with patch("subprocess.run", return_value=_make_ok_result(stdout="git-lfs/3.0", returncode=0)):
        ok, output = mgr._run_git_allow_fail(str(tmp_path), ["lfs", "version"])
    assert ok is True


# ---------------------------------------------------------------------------
# _maybe_push — push decision logic
# ---------------------------------------------------------------------------


def test_maybe_push_skips_when_dirty(tmp_path):
    mgr, _ = _mgr()
    with patch.object(mgr, "_has_uncommitted_changes", return_value=True):
        result = mgr._maybe_push(str(tmp_path))
    assert "dirty" in result


def test_maybe_push_skips_on_detached_head(tmp_path):
    mgr, _ = _mgr()
    with patch.object(mgr, "_has_uncommitted_changes", return_value=False), \
         patch.object(mgr, "_current_branch", return_value="HEAD"):
        result = mgr._maybe_push(str(tmp_path))
    assert "detached" in result


def test_maybe_push_push_not_needed_when_not_ahead(tmp_path):
    mgr, _ = _mgr()
    with patch.object(mgr, "_has_uncommitted_changes", return_value=False), \
         patch.object(mgr, "_current_branch", return_value="main"), \
         patch.object(mgr, "_has_upstream", return_value=True), \
         patch.object(mgr, "_ahead_count", return_value=0):
        result = mgr._maybe_push(str(tmp_path))
    assert "not needed" in result


def test_maybe_push_pushes_when_ahead(tmp_path):
    mgr, _ = _mgr()
    with patch.object(mgr, "_has_uncommitted_changes", return_value=False), \
         patch.object(mgr, "_current_branch", return_value="main"), \
         patch.object(mgr, "_has_upstream", return_value=True), \
         patch.object(mgr, "_ahead_count", return_value=3), \
         patch.object(mgr, "_run_git") as mock_git:
        result = mgr._maybe_push(str(tmp_path))
    mock_git.assert_called_once_with(str(tmp_path), ["push"])
    assert "3" in result


def test_maybe_push_sets_upstream_when_no_upstream(tmp_path):
    mgr, _ = _mgr()
    with patch.object(mgr, "_has_uncommitted_changes", return_value=False), \
         patch.object(mgr, "_current_branch", return_value="feature"), \
         patch.object(mgr, "_has_upstream", return_value=False), \
         patch.object(mgr, "_run_git") as mock_git:
        result = mgr._maybe_push(str(tmp_path))
    mock_git.assert_called_once_with(str(tmp_path), ["push", "-u", "origin", "feature"])
    assert "upstream" in result


# ---------------------------------------------------------------------------
# _run_lfs_sync — LFS helper
# ---------------------------------------------------------------------------


def test_lfs_sync_skipped_when_disabled(tmp_path):
    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = False
    with patch.object(mgr, "_run_git_allow_fail") as mock_allow, \
         patch.object(mgr, "_run_git") as mock_git:
        mgr._run_lfs_sync(str(tmp_path))
    mock_allow.assert_not_called()
    mock_git.assert_not_called()


def test_lfs_sync_skipped_when_lfs_not_installed(tmp_path):
    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = True
    with patch.object(mgr, "_run_git_allow_fail", return_value=(False, "")), \
         patch.object(mgr, "_run_git") as mock_git:
        mgr._run_lfs_sync(str(tmp_path))
    mock_git.assert_not_called()


def test_lfs_sync_runs_install_and_pull_when_lfs_available(tmp_path):
    mgr, prefs = _mgr()
    prefs[RepoSyncManager.PREF_GIT_LFS_ENABLED] = True
    git_calls = []
    with patch.object(mgr, "_run_git_allow_fail", return_value=(True, "git-lfs/3.0")), \
         patch.object(mgr, "_run_git", side_effect=lambda p, args: git_calls.append(args)):
        mgr._run_lfs_sync(str(tmp_path))
    assert ["lfs", "install", "--local"] in git_calls
    assert ["lfs", "pull"] in git_calls


# ---------------------------------------------------------------------------
# RepoSyncResult dataclass
# ---------------------------------------------------------------------------


def test_repo_sync_result_fields():
    r = RepoSyncResult(repo="owner/repo", ok=True, message="done")
    assert r.repo == "owner/repo"
    assert r.ok is True
    assert r.message == "done"


def test_repo_sync_result_failure():
    r = RepoSyncResult(repo="x/y", ok=False, message="error msg")
    assert r.ok is False
