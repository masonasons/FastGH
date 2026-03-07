"""Repository auto-sync helpers (auto pull/push per configured repo)."""

from __future__ import annotations

import os
import platform
import re
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
    _REPO_PROVIDER_RE = re.compile(r"(?:(?P<scheme>https?)://|git@|ssh://git@)(?P<host>[^/:]+)")
    _OS_HINTS = ("windows", "mac", "macos", "osx", "linux", "ubuntu", "ios", "android")

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
        return self.sync_path(
            repo_path=repo_path,
            repo_label=full_name,
            auto_pull=bool(cfg.get("auto_pull", True)),
            auto_push=bool(cfg.get("auto_push", False)),
        )

    def sync_path(
        self,
        repo_path: str,
        repo_label: str = "external",
        auto_pull: bool = True,
        auto_push: bool = False,
    ) -> RepoSyncResult:
        """Sync any local git repository path, including external/non-GitHub remotes."""
        if not repo_path:
            return RepoSyncResult(repo_label, False, "No local path configured.")
        if not os.path.isdir(repo_path):
            return RepoSyncResult(repo_label, False, f"Missing path: {repo_path}")
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            return RepoSyncResult(repo_label, False, f"Not a git repo: {repo_path}")

        try:
            self._maybe_run_repo_update(repo_path)
            self._run_git(repo_path, ["fetch", "--all", "--prune"])
            incoming_count = self._incoming_count(repo_path)
            os_hints = self._detect_cross_os_hints(repo_path) if incoming_count > 0 else []
            if auto_pull:
                self._run_git(repo_path, ["pull", "--ff-only"])
                self._run_lfs_sync(repo_path)
            push_message = "push disabled"
            if auto_push:
                push_message = self._maybe_push(repo_path)
            provider = self._remote_provider_name(repo_path)
            remote_note = ""
            if incoming_count > 0:
                remote_note = f"; incoming={incoming_count}"
                if os_hints:
                    remote_note += f"; os-hints={','.join(os_hints)}"
            return RepoSyncResult(repo_label, True, f"sync complete ({push_message}; remote={provider}{remote_note})")
        except RuntimeError as exc:
            return RepoSyncResult(repo_label, False, str(exc))

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

    def _remote_provider_name(self, repo_path: str) -> str:
        ok, url = self._run_git_allow_fail(repo_path, ["config", "--get", "remote.origin.url"])
        if not ok or not url.strip():
            return "unknown"
        host = self._remote_host(url.strip())
        if not host:
            return "unknown"
        if host.endswith("github.com"):
            return "github"
        if host.endswith("gitlab.com"):
            return "gitlab"
        return host

    def _remote_host(self, remote_url: str) -> str:
        match = self._REPO_PROVIDER_RE.search(remote_url.strip())
        if not match:
            return ""
        return (match.group("host") or "").lower()

    def _incoming_count(self, repo_path: str) -> int:
        if not self._has_upstream(repo_path):
            return 0
        raw = self._run_git(repo_path, ["rev-list", "--count", "HEAD..@{u}"]).strip()
        try:
            return int(raw)
        except ValueError:
            return 0

    def _detect_cross_os_hints(self, repo_path: str) -> list[str]:
        if not self._has_upstream(repo_path):
            return []
        ok, output = self._run_git_allow_fail(repo_path, ["log", "--max-count=25", "--format=%s%n%b", "HEAD..@{u}"])
        if not ok:
            return []
        text = output.lower()
        hints: list[str] = []
        for marker in self._OS_HINTS:
            if marker in text and marker not in hints:
                hints.append(marker)
        return hints
