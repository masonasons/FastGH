"""Repository auto-sync helpers (auto pull/push per configured repo)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class RepoSyncResult:
    """Outcome for one repository sync run."""

    repo: str
    ok: bool
    message: str


class RepoSyncManager:
    """Manage per-repository auto sync preferences and git operations."""

    PREF_CONFIGS = "repo_sync_configs"
    PREF_ENABLED = "repo_sync_enabled"
    PREF_INTERVAL = "repo_sync_interval_minutes"
    PREF_USE_GITHUB_TOOLS = "repo_sync_use_github_tools"
    PREF_GITHUB_TOOLS_PATH = "repo_sync_github_tools_path"
    PREF_GIT_LFS_ENABLED = "git_lfs_enabled"

    def __init__(self, prefs: Any):
        self.prefs = prefs
        self._ensure_defaults()

    def _ensure_defaults(self):
        if self.prefs.get(self.PREF_CONFIGS) is None:
            self._set_pref(self.PREF_CONFIGS, {})
        if self.prefs.get(self.PREF_ENABLED) is None:
            self._set_pref(self.PREF_ENABLED, False)
        if self.prefs.get(self.PREF_INTERVAL) is None:
            self._set_pref(self.PREF_INTERVAL, 0)
        if self.prefs.get(self.PREF_USE_GITHUB_TOOLS) is None:
            self._set_pref(self.PREF_USE_GITHUB_TOOLS, True)
        if self.prefs.get(self.PREF_GITHUB_TOOLS_PATH) is None:
            if platform.system() == "Windows":
                default_tools = os.path.join(os.path.expanduser("~"), "dev", "apps", ".GITHUB")
            else:
                default_tools = os.path.expanduser("~/DEV/APPS/.GITHUB")
            self._set_pref(self.PREF_GITHUB_TOOLS_PATH, default_tools)

    def _set_pref(self, key: str, value: Any):
        setattr(self.prefs, key, value)

    def _configs(self) -> dict:
        data = self.prefs.get(self.PREF_CONFIGS, {})
        if hasattr(data, "_data"):
            return dict(data._data)
        return dict(data)

    def _save_configs(self, configs: dict):
        self._set_pref(self.PREF_CONFIGS, configs)

    def get_repo_config(self, full_name: str, default_path: str = "") -> dict:
        configs = self._configs()
        config = configs.get(full_name, {})
        return {
            "enabled": bool(config.get("enabled", False)),
            "auto_pull": bool(config.get("auto_pull", True)),
            "auto_push": bool(config.get("auto_push", False)),
            "path": config.get("path", default_path) or default_path,
        }

    def set_repo_config(
        self,
        full_name: str,
        enabled: bool,
        auto_pull: bool,
        auto_push: bool,
        path: str,
    ):
        configs = self._configs()
        configs[full_name] = {
            "enabled": bool(enabled),
            "auto_pull": bool(auto_pull),
            "auto_push": bool(auto_push),
            "path": path,
        }
        self._save_configs(configs)

    def get_enabled_repos(self) -> list[tuple[str, dict]]:
        configs = self._configs()
        return [(repo, cfg) for repo, cfg in configs.items() if cfg.get("enabled")]

    def sync_all_enabled(self) -> list[RepoSyncResult]:
        if not self.prefs.get(self.PREF_ENABLED, False):
            return []
        results = []
        for repo, cfg in self.get_enabled_repos():
            results.append(self.sync_one(repo, cfg))
        return results

    def sync_one(self, full_name: str, cfg: dict | None = None) -> RepoSyncResult:
        cfg = cfg or self.get_repo_config(full_name)
        repo_path = cfg.get("path", "")
        if not repo_path:
            return RepoSyncResult(full_name, False, "No local path configured.")
        if not os.path.isdir(repo_path):
            return RepoSyncResult(full_name, False, f"Missing path: {repo_path}")
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return RepoSyncResult(full_name, False, f"Not a git repo: {repo_path}")

        try:
            self._maybe_run_repo_update(repo_path)
            self._run_git(repo_path, ["fetch", "--all", "--prune"])
            if cfg.get("auto_pull", True):
                self._run_git(repo_path, ["pull", "--ff-only"])
                self._run_lfs_sync(repo_path)
            push_message = "push disabled"
            if cfg.get("auto_push", False):
                push_message = self._maybe_push(repo_path)
            return RepoSyncResult(full_name, True, f"sync complete ({push_message})")
        except RuntimeError as exc:
            return RepoSyncResult(full_name, False, str(exc))

    def run_repo_update(self, repo_path: str):
        """Run external repo update helper for one repository path when configured."""
        self._maybe_run_repo_update(repo_path)

    def _maybe_run_repo_update(self, repo_path: str):
        if not self.prefs.get(self.PREF_USE_GITHUB_TOOLS, True):
            return

        tools_path = self.prefs.get(self.PREF_GITHUB_TOOLS_PATH, "")
        if not tools_path or not os.path.isdir(tools_path):
            return

        if platform.system() == "Windows":
            batch = os.path.join(tools_path, "raywonder-repo-bootstrap", "run-repo-update.bat")
            if os.path.isfile(batch):
                self._run_external(["cmd", "/c", batch, repo_path], tools_path)
            return

        script = os.path.join(tools_path, "raywonder-repo-bootstrap", "scripts", "pull_and_fix_repo.ps1")
        if not os.path.isfile(script):
            return

        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            return

        self._run_external([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-RepoRoot", repo_path], tools_path)

    def _run_external(self, cmd: list[str], cwd: str):
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Repo bootstrap failed: {' '.join(cmd)}\n{err}")

    def _run_git(self, repo_path: str, args: list[str]) -> str:
        cmd = ["git"] + args
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{' '.join(cmd)} failed for {repo_path}\n{err}")
        return (result.stdout or "").strip()

    def _run_git_allow_fail(self, repo_path: str, args: list[str]) -> tuple[bool, str]:
        cmd = ["git"] + args
        creationflags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            creationflags=creationflags,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output

    def _run_lfs_sync(self, repo_path: str):
        if not self.prefs.get(self.PREF_GIT_LFS_ENABLED, True):
            return

        ok, _ = self._run_git_allow_fail(repo_path, ["lfs", "version"])
        if not ok:
            return

        self._run_git(repo_path, ["lfs", "install", "--local"])
        # Pull includes fetch + checkout of LFS objects.
        self._run_git(repo_path, ["lfs", "pull"])

    def _has_uncommitted_changes(self, repo_path: str) -> bool:
        status = self._run_git(repo_path, ["status", "--porcelain"])
        return bool(status.strip())

    def _current_branch(self, repo_path: str) -> str:
        return self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def _has_upstream(self, repo_path: str) -> bool:
        try:
            self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
            return True
        except RuntimeError:
            return False

    def _ahead_count(self, repo_path: str) -> int:
        raw = self._run_git(repo_path, ["rev-list", "--count", "@{u}..HEAD"]).strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    def _maybe_push(self, repo_path: str) -> str:
        if self._has_uncommitted_changes(repo_path):
            return "skipped push (dirty working tree)"

        branch = self._current_branch(repo_path)
        if not branch or branch == "HEAD":
            return "skipped push (detached HEAD)"

        if not self._has_upstream(repo_path):
            self._run_git(repo_path, ["push", "-u", "origin", branch])
            return "pushed (set upstream)"

        ahead = self._ahead_count(repo_path)
        if ahead <= 0:
            return "push not needed"

        self._run_git(repo_path, ["push"])
        return f"pushed ({ahead} commit(s) ahead)"
