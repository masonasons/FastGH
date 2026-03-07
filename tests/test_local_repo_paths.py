import json
import os

from local_repo_paths import (
    find_existing_repo_path,
    github_full_name_from_git_config,
    github_full_name_from_remote_url,
)


def _write_git_config(repo_path: str, remote_url: str):
    git_dir = os.path.join(repo_path, ".git")
    os.makedirs(git_dir, exist_ok=True)
    cfg_path = os.path.join(git_dir, "config")
    with open(cfg_path, "w", encoding="utf-8") as handle:
        handle.write(
            "[remote \"origin\"]\n"
            f"\turl = {remote_url}\n"
            "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        )


def test_remote_url_normalization_handles_https_and_ssh():
    assert github_full_name_from_remote_url("https://github.com/Raywonder/FastGH.git") == "raywonder/fastgh"
    assert github_full_name_from_remote_url("git@github.com:Raywonder/FastGH.git") == "raywonder/fastgh"
    assert github_full_name_from_remote_url("ssh://git@github.com/Raywonder/FastGH.git") == "raywonder/fastgh"


def test_github_full_name_from_git_config_reads_origin(tmp_path):
    repo = tmp_path / "FastGH"
    _write_git_config(str(repo), "git@github.com:Raywonder/FastGH.git")
    assert github_full_name_from_git_config(str(repo)) == "raywonder/fastgh"


def test_find_existing_repo_path_prefers_matching_remote(tmp_path):
    root = tmp_path / "git"
    right_repo = root / "Raywonder" / "FastGH"
    wrong_repo = root / "FastGH"
    _write_git_config(str(wrong_repo), "git@github.com:someone/FastGH.git")
    _write_git_config(str(right_repo), "git@github.com:Raywonder/FastGH.git")

    found = find_existing_repo_path(
        full_name="Raywonder/FastGH",
        repo_name="FastGH",
        owner="Raywonder",
        roots=[str(root)],
    )
    assert found == str(right_repo)
