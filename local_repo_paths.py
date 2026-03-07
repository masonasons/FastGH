"""Helpers for finding existing local clones for a GitHub repository."""

from __future__ import annotations

import json
import os
import platform
import re
from typing import Iterable


_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?(?:[#/\s]|$)", re.IGNORECASE)


def normalize_full_name(value: str) -> str:
    """Normalize owner/repo identifiers for case-insensitive matching."""
    return (value or "").strip().lower()


def github_full_name_from_remote_url(url: str) -> str:
    """Extract owner/repo from a git remote URL if it points to github.com."""
    if not url:
        return ""
    match = _GITHUB_REMOTE_RE.search(url.strip())
    if not match:
        return ""
    owner = match.group("owner").strip()
    repo = match.group("repo").strip()
    return normalize_full_name(f"{owner}/{repo}")


def github_full_name_from_git_config(repo_path: str) -> str:
    """Read .git/config and return owner/repo for github.com remotes."""
    cfg_path = os.path.join(repo_path, ".git", "config")
    if not os.path.isfile(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as handle:
            contents = handle.read()
    except OSError:
        return ""

    for match in _GITHUB_REMOTE_RE.finditer(contents):
        owner = match.group("owner").strip()
        repo = match.group("repo").strip()
        return normalize_full_name(f"{owner}/{repo}")
    return ""


def _dedupe_existing_paths(paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for path in paths:
        if not path:
            continue
        expanded = os.path.abspath(os.path.expanduser(path))
        if expanded in seen or not os.path.isdir(expanded):
            continue
        seen.add(expanded)
        out.append(expanded)
    return out


def _looks_like_git_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


def _github_desktop_state_file() -> str:
    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Darwin":
        return os.path.join(home, "Library", "Application Support", "GitHub Desktop", "state.json")
    if system == "Windows":
        appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(appdata, "GitHub Desktop", "state.json")
    return os.path.join(home, ".config", "GitHub Desktop", "state.json")


def github_desktop_clone_roots() -> list[str]:
    """Read GitHub Desktop state.json and return known default clone roots."""
    state_file = _github_desktop_state_file()
    if not os.path.isfile(state_file):
        return []
    try:
        with open(state_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []

    paths = []
    for key in ("cloningPath", "defaultClonePath", "clonePath"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            paths.append(value.strip())
    return _dedupe_existing_paths(paths)


def build_repo_search_roots(primary_git_path: str) -> list[str]:
    """Build ordered roots to check for existing clones."""
    defaults = [
        primary_git_path,
        os.path.join("~", "Documents", "GitHub"),
        os.path.join("~", "GitHub"),
        os.path.join("~", "git"),
    ]
    return _dedupe_existing_paths(defaults + github_desktop_clone_roots())


def find_existing_repo_path(full_name: str, repo_name: str, owner: str, roots: Iterable[str]) -> str:
    """Find a local repo path that already matches the target GitHub full_name."""
    wanted = normalize_full_name(full_name)
    if not wanted:
        return ""

    repo_name = (repo_name or "").strip()
    owner = (owner or "").strip()
    candidate_rel_paths = []
    if owner and repo_name:
        candidate_rel_paths.append(os.path.join(owner, repo_name))
    if repo_name:
        candidate_rel_paths.append(repo_name)

    for root in _dedupe_existing_paths(roots):
        # First pass: cheap and likely locations.
        for rel in candidate_rel_paths:
            candidate = os.path.join(root, rel)
            if not _looks_like_git_repo(candidate):
                continue
            detected = github_full_name_from_git_config(candidate)
            if detected == wanted:
                return candidate

        # Second pass: shallow scan by repo name under one folder depth.
        if not repo_name:
            continue
        direct = os.path.join(root, repo_name)
        nested = os.path.join(root, "*", repo_name)
        for glob_pattern in (direct, nested):
            # Avoid importing glob just for two fixed patterns.
            if "*" not in glob_pattern:
                candidates = [glob_pattern]
            else:
                parent = root
                try:
                    entries = [os.path.join(parent, d) for d in os.listdir(parent)]
                except OSError:
                    entries = []
                candidates = [os.path.join(entry, repo_name) for entry in entries if os.path.isdir(entry)]

            for candidate in candidates:
                if not _looks_like_git_repo(candidate):
                    continue
                detected = github_full_name_from_git_config(candidate)
                if detected == wanted:
                    return candidate
    return ""
