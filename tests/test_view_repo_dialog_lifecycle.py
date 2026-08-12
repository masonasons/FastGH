"""Regression tests for the repository dialog's modal lifecycle."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def test_close_ends_modal_loop_before_caller_destroys_dialog(monkeypatch):
    """Closing must unwind ShowModal; direct Destroy corrupts Cocoa state."""
    wx_stub = types.ModuleType("wx")
    wx_stub.Dialog = type("Dialog", (), {})
    wx_stub.ID_CANCEL = 123

    application_stub = types.ModuleType("application")
    application_stub.get_app = MagicMock()

    theme_stub = types.ModuleType("GUI.theme")
    theme_stub.apply_theme = MagicMock()

    monkeypatch.setitem(sys.modules, "wx", wx_stub)
    monkeypatch.setitem(sys.modules, "application", application_stub)
    monkeypatch.setitem(sys.modules, "GUI.theme", theme_stub)

    view_path = Path(__file__).parents[1] / "GUI" / "view.py"
    spec = importlib.util.spec_from_file_location("GUI._view_lifecycle_test", view_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dialog = MagicMock()
    module.ViewRepoDialog.on_close(dialog, None)

    dialog.EndModal.assert_called_once_with(wx_stub.ID_CANCEL)
    dialog.Destroy.assert_not_called()
