"""Smoke tests — verify all major modules import cleanly and expose expected surfaces.

These do not test logic; they guard against import-time crashes, missing
constants, renamed exports, and obvious instantiation failures.
"""

import sys
import types

# ---------------------------------------------------------------------------
# Ensure wx is stubbed before any import that pulls in github_api or GUI code
# ---------------------------------------------------------------------------
if "wx" not in sys.modules:
    from unittest.mock import MagicMock
    _wx_stub = types.ModuleType("wx")
    # Scalar constants
    for _name in [
        "VERTICAL", "HORIZONTAL", "ALL", "EXPAND", "RIGHT", "ALIGN_CENTER",
        "OK", "CANCEL", "YES_NO", "YES", "NO", "NO_DEFAULT",
        "ID_OK", "ID_CANCEL", "ICON_QUESTION", "ICON_INFORMATION", "ICON_ERROR",
        "NOT_FOUND", "EVT_BUTTON",
    ]:
        setattr(_wx_stub, _name, MagicMock())
    # Classes that other classes may inherit from — must be real types
    for _cls_name in ["Dialog", "Panel", "Frame", "App", "Window"]:
        setattr(_wx_stub, _cls_name, type(_cls_name, (), {"__init__": lambda self, *a, **kw: None}))
    # Other callable/object stubs
    for _name in [
        "BoxSizer", "StaticText", "Button", "StaticBox", "StaticBoxSizer",
        "TheClipboard", "TextDataObject", "CallAfter", "MessageBox", "MessageDialog",
        "CheckBox", "Notebook", "ScrolledWindow",
    ]:
        setattr(_wx_stub, _name, MagicMock())
    sys.modules["wx"] = _wx_stub

import pytest


# ---------------------------------------------------------------------------
# Pure-Python models — no wx, no network
# ---------------------------------------------------------------------------


def test_import_models_repository():
    from models.repository import Repository
    assert hasattr(Repository, "from_github_api")


def test_import_models_issue():
    from models.issue import Issue, PullRequest, Comment
    assert hasattr(Issue, "from_github_api")
    assert hasattr(PullRequest, "from_github_api")
    assert hasattr(Comment, "from_github_api")


def test_import_models_user():
    from models.user import UserProfile
    assert hasattr(UserProfile, "from_github_api")


def test_import_models_release():
    from models.release import Release, ReleaseAsset
    assert hasattr(Release, "from_github_api")
    assert hasattr(ReleaseAsset, "from_github_api")


def test_import_models_notification():
    from models.notification import Notification, NotificationSubject
    assert hasattr(Notification, "from_api")


def test_import_models_event():
    from models.event import Event
    assert hasattr(Event, "from_api")
    assert hasattr(Event, "EVENT_TYPES")


def test_import_models_workflow():
    from models.workflow import Workflow, WorkflowRun, WorkflowJob
    assert hasattr(Workflow, "from_github_api")
    assert hasattr(WorkflowRun, "from_github_api")
    assert hasattr(WorkflowJob, "from_github_api")


def test_import_models_content():
    from models.content import ContentItem
    assert hasattr(ContentItem, "from_github_api")


def test_import_models_discussion():
    from models.discussion import Discussion, DiscussionComment
    assert hasattr(Discussion, "from_graphql")


# ---------------------------------------------------------------------------
# config module
# ---------------------------------------------------------------------------


def test_import_config():
    import config
    assert hasattr(config, "Config")
    assert hasattr(config, "is_portable_mode")
    assert hasattr(config, "get_config_home")


def test_config_instantiation_with_data():
    from config import Config
    c = Config("FastGH", autosave=False, save_on_exit=False, _data={"key": "val"})
    assert c["key"] == "val"


# ---------------------------------------------------------------------------
# repo_sync module
# ---------------------------------------------------------------------------


def test_import_repo_sync():
    from repo_sync import RepoSyncManager, RepoSyncResult
    assert hasattr(RepoSyncManager, "sync_one")
    assert hasattr(RepoSyncManager, "get_repo_config")


def test_repo_sync_manager_instantiation():
    from repo_sync import RepoSyncManager

    class _P(dict):
        def __setattr__(self, k, v): self[k] = v
        def __getattr__(self, k): return self.get(k)

    mgr = RepoSyncManager(_P())
    assert mgr is not None


# ---------------------------------------------------------------------------
# github_api module — import only (wx already stubbed above)
# ---------------------------------------------------------------------------


def test_import_github_api():
    import github_api
    assert hasattr(github_api, "GitHubAccount")
    assert hasattr(github_api, "GITHUB_API_URL")
    assert hasattr(github_api, "GITHUB_CLIENT_ID")


def test_github_api_url_is_string():
    from github_api import GITHUB_API_URL
    assert isinstance(GITHUB_API_URL, str)
    assert GITHUB_API_URL.startswith("https://")


# ---------------------------------------------------------------------------
# Event.EVENT_TYPES constant
# ---------------------------------------------------------------------------


def test_event_types_is_dict_with_string_keys():
    from models.event import Event
    assert isinstance(Event.EVENT_TYPES, dict)
    for k in Event.EVENT_TYPES:
        assert isinstance(k, str)
        assert k.endswith("Event")


# ---------------------------------------------------------------------------
# version module
# ---------------------------------------------------------------------------


def test_import_version():
    import version
    assert hasattr(version, "__version__") or hasattr(version, "VERSION") or len(dir(version)) > 0


# ---------------------------------------------------------------------------
# Models instantiate from empty dict without crashing
# ---------------------------------------------------------------------------


def test_repository_from_minimal_dict():
    from models.repository import Repository
    # Repository.from_github_api requires 'id' and other keys; test it accepts
    # a populated minimal dict without crashing.
    r = Repository.from_github_api({"id": 1, "name": "x", "full_name": "a/x",
                                    "owner": {"login": "a"}, "private": False,
                                    "url": "", "html_url": ""})
    assert r.name == "x"


def test_user_profile_from_empty_dict():
    from models.user import UserProfile
    p = UserProfile.from_github_api({})
    assert p.login == ""


def test_release_from_empty_dict():
    from models.release import Release
    r = Release.from_github_api({})
    assert r.tag_name == ""


def test_notification_from_api_minimal():
    from models.notification import Notification
    n = Notification.from_api({})
    assert hasattr(n, "id")


def test_event_from_api_minimal():
    from models.event import Event
    e = Event.from_api({})
    assert hasattr(e, "type")


def test_workflow_from_empty_dict():
    from models.workflow import Workflow
    w = Workflow.from_github_api({})
    assert w.name == ""


def test_content_item_from_empty_dict():
    from models.content import ContentItem
    c = ContentItem.from_github_api({})
    assert c.name == ""
