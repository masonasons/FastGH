"""Mock tests for github_api.py — GitHubAccount API methods.

wx is not available in CI, so we stub it out before importing the module.
All network calls are mocked via unittest.mock.MagicMock on _session.
"""

import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Stub wx before github_api is imported so the top-level `import wx` succeeds
# ---------------------------------------------------------------------------

_wx_stub = types.ModuleType("wx")
for _attr in [
    "Dialog", "Panel", "BoxSizer", "StaticText", "Button", "VERTICAL",
    "HORIZONTAL", "ALL", "EXPAND", "RIGHT", "ALIGN_CENTER", "OK", "CANCEL",
    "YES_NO", "YES", "NO", "NO_DEFAULT", "ID_OK", "ID_CANCEL",
    "ICON_QUESTION", "ICON_INFORMATION", "ICON_ERROR",
    "NOT_FOUND", "EVT_BUTTON", "TheClipboard", "TextDataObject",
    "CallAfter", "MessageBox", "MessageDialog",
]:
    setattr(_wx_stub, _attr, MagicMock())

sys.modules.setdefault("wx", _wx_stub)

# Now import the real module
import github_api
from github_api import GitHubAccount, GITHUB_API_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_account() -> GitHubAccount:
    """Create a GitHubAccount without calling __init__ (avoids wx/config/network)."""
    acc = object.__new__(GitHubAccount)
    acc.app = None
    acc.index = 0
    acc.ready = False
    acc.me = {"login": "alice", "name": "Alice Smith"}
    acc._last_error = ""
    acc._session = MagicMock()
    return acc


def _response(status=200, json_data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.text = ""
    return r


def _repo_payload(**overrides):
    base = {
        "id": 1, "name": "MyRepo", "full_name": "alice/MyRepo",
        "description": "desc", "owner": {"login": "alice"},
        "stargazers_count": 5, "forks_count": 2, "open_issues_count": 1,
        "language": "Python", "updated_at": "2026-01-01T00:00:00Z",
        "pushed_at": "2026-01-01T00:00:00Z", "url": "", "html_url": "",
        "private": False,
    }
    base.update(overrides)
    return base


def _issue_payload(**overrides):
    base = {
        "id": 10, "number": 1, "title": "Bug", "body": "",
        "state": "open", "user": {"login": "alice"}, "labels": [],
        "assignees": [], "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z", "html_url": "",
        "comments": 0, "closed_at": None,
    }
    base.update(overrides)
    return base


def _comment_payload(**overrides):
    base = {
        "id": 99, "body": "A comment",
        "user": {"login": "alice"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "html_url": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# username / display_name properties
# ---------------------------------------------------------------------------


def test_username_returns_login():
    acc = _make_account()
    assert acc.username == "alice"


def test_username_empty_when_me_is_none():
    acc = _make_account()
    acc.me = None
    assert acc.username == ""


def test_display_name_returns_name():
    acc = _make_account()
    assert acc.display_name == "Alice Smith"


def test_display_name_falls_back_to_login_when_name_missing():
    acc = _make_account()
    acc.me = {"login": "alice"}
    assert acc.display_name == "alice"


def test_display_name_empty_when_me_is_none():
    acc = _make_account()
    acc.me = None
    assert acc.display_name == ""


# ---------------------------------------------------------------------------
# _set_last_error / get_last_error
# ---------------------------------------------------------------------------


def test_get_last_error_returns_empty_initially():
    acc = _make_account()
    assert acc.get_last_error() == ""


def test_set_last_error_stores_message():
    acc = _make_account()
    acc._set_last_error("something failed")
    assert acc.get_last_error() == "something failed"


def test_set_last_error_strips_whitespace():
    acc = _make_account()
    acc._set_last_error("  error  ")
    assert acc.get_last_error() == "error"


def test_set_last_error_no_args_clears():
    acc = _make_account()
    acc._set_last_error("old error")
    acc._set_last_error()
    assert acc.get_last_error() == ""


# ---------------------------------------------------------------------------
# get_repos
# ---------------------------------------------------------------------------


def test_get_repos_returns_list_on_success():
    acc = _make_account()
    acc._session.get.return_value = _response(200, [_repo_payload()])
    repos = acc.get_repos()
    assert len(repos) == 1
    assert repos[0].name == "MyRepo"


def test_get_repos_empty_on_error():
    acc = _make_account()
    acc._session.get.return_value = _response(401, {})
    repos = acc.get_repos()
    assert repos == []


def test_get_repos_stops_on_empty_page():
    acc = _make_account()
    # First call returns one repo, second call returns empty → stop pagination
    acc._session.get.side_effect = [
        _response(200, [_repo_payload()]),
        _response(200, []),
    ]
    repos = acc.get_repos(per_page=10)
    assert len(repos) == 1


def test_get_repos_paginates_when_full_page():
    acc = _make_account()
    page1 = [_repo_payload(id=i, name=f"repo{i}", full_name=f"alice/repo{i}") for i in range(2)]
    page2 = [_repo_payload(id=99, name="repo99", full_name="alice/repo99")]
    acc._session.get.side_effect = [
        _response(200, page1),
        _response(200, page2),
        _response(200, []),
    ]
    repos = acc.get_repos(per_page=2)
    assert len(repos) == 3


# ---------------------------------------------------------------------------
# get_repo
# ---------------------------------------------------------------------------


def test_get_repo_returns_repository_on_success():
    acc = _make_account()
    acc._session.get.return_value = _response(200, _repo_payload(name="FastGH"))
    repo = acc.get_repo("alice", "FastGH")
    assert repo is not None
    assert repo.name == "FastGH"


def test_get_repo_returns_none_on_404():
    acc = _make_account()
    acc._session.get.return_value = _response(404, {})
    repo = acc.get_repo("alice", "missing")
    assert repo is None


# ---------------------------------------------------------------------------
# get_issues
# ---------------------------------------------------------------------------


def test_get_issues_returns_issues():
    acc = _make_account()
    acc._session.get.return_value = _response(200, [_issue_payload(number=7)])
    issues = acc.get_issues("alice", "repo")
    assert len(issues) == 1
    assert issues[0].number == 7


def test_get_issues_skips_pull_requests():
    acc = _make_account()
    pr_item = _issue_payload(number=1)
    pr_item["pull_request"] = {"url": "..."}  # this marks it as a PR
    issue_item = _issue_payload(number=2)
    acc._session.get.return_value = _response(200, [pr_item, issue_item])
    issues = acc.get_issues("alice", "repo")
    assert len(issues) == 1
    assert issues[0].number == 2


def test_get_issues_empty_on_error():
    acc = _make_account()
    acc._session.get.return_value = _response(403, {})
    issues = acc.get_issues("alice", "repo")
    assert issues == []


# ---------------------------------------------------------------------------
# get_issue
# ---------------------------------------------------------------------------


def test_get_issue_returns_issue():
    acc = _make_account()
    acc._session.get.return_value = _response(200, _issue_payload(number=42))
    issue = acc.get_issue("alice", "repo", 42)
    assert issue is not None
    assert issue.number == 42


def test_get_issue_returns_none_on_404():
    acc = _make_account()
    acc._session.get.return_value = _response(404, {})
    assert acc.get_issue("alice", "repo", 99) is None


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------


def test_create_issue_returns_issue_on_201():
    acc = _make_account()
    acc._session.post.return_value = _response(201, _issue_payload(title="New bug"))
    issue = acc.create_issue("alice", "repo", "New bug")
    assert issue is not None
    assert issue.title == "New bug"


def test_create_issue_returns_none_on_error():
    acc = _make_account()
    acc._session.post.return_value = _response(422, {})
    assert acc.create_issue("alice", "repo", "title") is None


def test_create_issue_sends_labels():
    acc = _make_account()
    acc._session.post.return_value = _response(201, _issue_payload())
    acc.create_issue("alice", "repo", "title", labels=["bug", "help"])
    call_kwargs = acc._session.post.call_args[1]
    assert call_kwargs["json"]["labels"] == ["bug", "help"]


# ---------------------------------------------------------------------------
# update_issue / close / reopen
# ---------------------------------------------------------------------------


def test_update_issue_returns_issue_on_200():
    acc = _make_account()
    acc._session.patch.return_value = _response(200, _issue_payload(title="Updated"))
    issue = acc.update_issue("alice", "repo", 1, title="Updated")
    assert issue is not None


def test_update_issue_returns_none_on_error():
    acc = _make_account()
    acc._session.patch.return_value = _response(404, {})
    assert acc.update_issue("alice", "repo", 1, title="X") is None


def test_close_issue_returns_true_on_success():
    acc = _make_account()
    acc._session.patch.return_value = _response(200, _issue_payload(state="closed"))
    assert acc.close_issue("alice", "repo", 1) is True


def test_close_issue_returns_false_on_error():
    acc = _make_account()
    acc._session.patch.return_value = _response(404, {})
    assert acc.close_issue("alice", "repo", 99) is False


def test_reopen_issue_sends_open_state():
    acc = _make_account()
    acc._session.patch.return_value = _response(200, _issue_payload(state="open"))
    acc.reopen_issue("alice", "repo", 5)
    call_kwargs = acc._session.patch.call_args[1]
    assert call_kwargs["json"]["state"] == "open"


# ---------------------------------------------------------------------------
# get_issue_comments / create_issue_comment / delete_issue_comment
# ---------------------------------------------------------------------------


def test_get_issue_comments_returns_list():
    acc = _make_account()
    acc._session.get.return_value = _response(200, [_comment_payload(body="hello")])
    comments = acc.get_issue_comments("alice", "repo", 1)
    assert len(comments) == 1
    assert comments[0].body == "hello"


def test_get_issue_comments_empty_on_error():
    acc = _make_account()
    acc._session.get.return_value = _response(404, {})
    assert acc.get_issue_comments("alice", "repo", 1) == []


def test_create_issue_comment_returns_comment_on_201():
    acc = _make_account()
    acc._session.post.return_value = _response(201, _comment_payload(body="thanks"))
    comment = acc.create_issue_comment("alice", "repo", 1, "thanks")
    assert comment is not None
    assert comment.body == "thanks"


def test_create_issue_comment_returns_none_on_error():
    acc = _make_account()
    acc._session.post.return_value = _response(403, {})
    assert acc.create_issue_comment("alice", "repo", 1, "x") is None


def test_delete_issue_comment_returns_true_on_204():
    acc = _make_account()
    acc._session.delete.return_value = _response(204, {})
    assert acc.delete_issue_comment("alice", "repo", 777) is True


def test_delete_issue_comment_returns_false_on_404():
    acc = _make_account()
    acc._session.delete.return_value = _response(404, {})
    assert acc.delete_issue_comment("alice", "repo", 777) is False


# ---------------------------------------------------------------------------
# _graphql
# ---------------------------------------------------------------------------


def test_graphql_returns_data_on_success():
    acc = _make_account()
    acc._session.post.return_value = _response(200, {"data": {"viewer": {"login": "alice"}}})
    result = acc._graphql("{ viewer { login } }")
    assert result == {"viewer": {"login": "alice"}}


def test_graphql_returns_none_on_http_error():
    acc = _make_account()
    acc._session.post.return_value = _response(500, {})
    result = acc._graphql("{ viewer { login } }")
    assert result is None
    assert "500" in acc.get_last_error()


def test_graphql_returns_none_on_graphql_errors():
    acc = _make_account()
    acc._session.post.return_value = _response(200, {
        "errors": [{"message": "Field 'x' doesn't exist"}],
        "data": None,
    })
    result = acc._graphql("{ x }")
    assert result is None
    assert "Field 'x' doesn't exist" in acc.get_last_error()


def test_graphql_returns_none_when_data_is_none():
    acc = _make_account()
    acc._session.post.return_value = _response(200, {"data": None})
    result = acc._graphql("{ viewer { login } }")
    assert result is None


def test_graphql_clears_last_error_on_success():
    acc = _make_account()
    acc._set_last_error("previous error")
    acc._session.post.return_value = _response(200, {"data": {"ok": True}})
    acc._graphql("{ ok }")
    assert acc.get_last_error() == ""


def test_graphql_returns_none_on_exception():
    acc = _make_account()
    acc._session.post.side_effect = Exception("network down")
    result = acc._graphql("{ viewer { login } }")
    assert result is None
    assert "network down" in acc.get_last_error()


def test_get_repo_surfaces_fork_parent():
    acc = _make_account()
    acc._session.get.return_value = _response(200, _repo_payload(
        name="FastGH", fork=True,
        parent={"full_name": "masonasons/FastGH", "owner": {"login": "masonasons"}},
    ))
    repo = acc.get_repo("kellylford", "FastGH")
    assert repo is not None
    assert repo.is_fork is True
    assert repo.parent_full_name == "masonasons/FastGH"


# ---------------------------------------------------------------------------
# get_run_artifacts / download_artifact
# ---------------------------------------------------------------------------


def _artifact_payload(**overrides):
    base = {
        "id": 555,
        "name": "windows-build",
        "size_in_bytes": 1024,
        "archive_download_url": "https://api.github.com/repos/alice/MyRepo/actions/artifacts/555/zip",
        "expired": False,
        "created_at": "2026-03-01T10:00:00Z",
        "expires_at": "2026-05-30T10:00:00Z",
    }
    base.update(overrides)
    return base


def test_get_run_artifacts_returns_list():
    acc = _make_account()
    acc._session.get.return_value = _response(200, {"artifacts": [_artifact_payload()]})
    artifacts = acc.get_run_artifacts("alice", "MyRepo", 100)
    assert len(artifacts) == 1
    assert artifacts[0].name == "windows-build"
    assert artifacts[0].id == 555


def test_get_run_artifacts_empty_on_error():
    acc = _make_account()
    acc._session.get.return_value = _response(404, {})
    assert acc.get_run_artifacts("alice", "MyRepo", 100) == []


def test_get_run_artifacts_stops_on_empty_page():
    acc = _make_account()
    acc._session.get.side_effect = [
        _response(200, {"artifacts": [_artifact_payload()]}),
        _response(200, {"artifacts": []}),
    ]
    artifacts = acc.get_run_artifacts("alice", "MyRepo", 100, per_page=10)
    assert len(artifacts) == 1


def test_get_run_artifacts_paginates_when_full_page():
    acc = _make_account()
    page1 = [_artifact_payload(id=i, name=f"a{i}") for i in range(2)]
    page2 = [_artifact_payload(id=99, name="a99")]
    acc._session.get.side_effect = [
        _response(200, {"artifacts": page1}),
        _response(200, {"artifacts": page2}),
        _response(200, {"artifacts": []}),
    ]
    artifacts = acc.get_run_artifacts("alice", "MyRepo", 100, per_page=2)
    assert len(artifacts) == 3


def _stream_response(status=200, chunks=(b"PK\x03\x04", b"data"), content_length=None):
    r = MagicMock()
    r.status_code = status
    total = content_length if content_length is not None else sum(len(c) for c in chunks)
    r.headers = {"content-length": str(total)}
    r.iter_content.return_value = iter(chunks)
    return r


def test_download_artifact_writes_file(tmp_path):
    acc = _make_account()
    acc._session.get.return_value = _stream_response(chunks=[b"PK\x03\x04", b"zipbody"])
    dest = tmp_path / "windows-build.zip"
    ok = acc.download_artifact("alice", "MyRepo", 555, str(dest))
    assert ok is True
    assert dest.read_bytes() == b"PK\x03\x04zipbody"


def test_download_artifact_reports_progress(tmp_path):
    acc = _make_account()
    acc._session.get.return_value = _stream_response(chunks=[b"aaaa", b"bb"], content_length=6)
    seen = []
    dest = tmp_path / "art.zip"
    acc.download_artifact("alice", "MyRepo", 555, str(dest),
                          progress_callback=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (6, 6)


def test_download_artifact_false_on_http_error(tmp_path):
    acc = _make_account()
    acc._session.get.return_value = _stream_response(status=410)
    dest = tmp_path / "gone.zip"
    ok = acc.download_artifact("alice", "MyRepo", 555, str(dest))
    assert ok is False
    assert not dest.exists()
