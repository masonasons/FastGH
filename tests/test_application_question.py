"""Tests for application.py question() dialog behavior.

wx is stubbed so these run without a GUI. We verify the return-value
mapping of wx dialog results to the 1/2 convention used throughout
the app, including the Escape-key path (wx.ID_CANCEL treated as No).
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub wx before importing application
# ---------------------------------------------------------------------------
if "wx" not in sys.modules:
    _wx = types.ModuleType("wx")
    for _name in [
        "YES_NO", "NO_DEFAULT", "ICON_QUESTION", "OK", "CANCEL", "YES", "NO",
        "ID_YES", "ID_NO", "ID_CANCEL", "ID_OK",
        "VERTICAL", "HORIZONTAL", "ALL", "EXPAND", "RIGHT", "ALIGN_CENTER",
        "ICON_INFORMATION", "ICON_ERROR", "NOT_FOUND", "EVT_BUTTON",
        "EVT_CLOSE", "EVT_MENU", "EVT_TIMER",
    ]:
        setattr(_wx, _name, MagicMock())
    for _cls in ["Dialog", "Frame", "Panel", "App", "Window", "Timer",
                 "Menu", "MenuItem", "MenuBar", "SystemTray", "TaskBarIcon",
                 "Icon", "Bitmap", "NullBitmap", "NullIcon"]:
        setattr(_wx, _cls, type(_cls, (), {"__init__": lambda self, *a, **kw: None}))
    for _name in [
        "MessageDialog", "BoxSizer", "StaticText", "Button", "CheckBox",
        "Notebook", "ScrolledWindow", "StaticBox", "StaticBoxSizer",
        "TheClipboard", "TextDataObject", "CallAfter", "MessageBox",
        "GetApp", "PySimpleApp",
    ]:
        setattr(_wx, _name, MagicMock())
    sys.modules["wx"] = _wx

import wx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    """Create a minimal app-like object exposing only question()."""
    # Import here so wx stub is already in place
    import application
    app = object.__new__(application.Application)
    # Minimal attributes question() needs
    app._platform = "Windows"
    return app


def _mock_dialog(return_value):
    """Return a context-managed mock for wx.MessageDialog that returns return_value from ShowModal."""
    dlg = MagicMock()
    dlg.ShowModal.return_value = return_value
    dlg.Destroy.return_value = None
    dialog_cls = MagicMock(return_value=dlg)
    return dialog_cls, dlg


# ---------------------------------------------------------------------------
# question() return values
# ---------------------------------------------------------------------------


def test_question_returns_1_when_yes_clicked():
    app = _make_app()
    dialog_cls, dlg = _mock_dialog(wx.ID_YES)
    with patch("wx.MessageDialog", dialog_cls), \
         patch("platform.system", return_value="Windows"):
        result = app.question("Title", "Text?")
    assert result == 1


def test_question_returns_2_when_no_clicked():
    app = _make_app()
    dialog_cls, dlg = _mock_dialog(wx.ID_NO)
    with patch("wx.MessageDialog", dialog_cls), \
         patch("platform.system", return_value="Windows"):
        result = app.question("Title", "Text?")
    assert result == 2


def test_question_returns_2_when_escape_pressed():
    """Escape yields wx.ID_CANCEL; that must be treated as No (return 2)."""
    app = _make_app()
    dialog_cls, dlg = _mock_dialog(wx.ID_CANCEL)
    with patch("wx.MessageDialog", dialog_cls), \
         patch("platform.system", return_value="Windows"):
        result = app.question("Title", "Text?")
    assert result == 2


# ---------------------------------------------------------------------------
# question() dialog style — Yes must be default, NO_DEFAULT must NOT be set
# ---------------------------------------------------------------------------


def test_question_does_not_set_no_default_flag():
    """wx.NO_DEFAULT must never appear in the style — Yes is always default."""
    app = _make_app()
    captured_style = []

    def fake_dialog(parent, text, title, style):
        captured_style.append(style)
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_YES
        return dlg

    with patch("wx.MessageDialog", side_effect=fake_dialog), \
         patch("platform.system", return_value="Windows"):
        app.question("T", "Q?")

    style = captured_style[0]
    # NO_DEFAULT is a MagicMock; using & on two MagicMocks gives another MagicMock
    # so we verify by checking the style does NOT include NO_DEFAULT via identity.
    # The real assertion: style should equal YES_NO | ICON_QUESTION, nothing more.
    assert style == (wx.YES_NO | wx.ICON_QUESTION)


def test_question_includes_yes_no_and_icon():
    app = _make_app()
    captured_style = []

    def fake_dialog(parent, text, title, style):
        captured_style.append(style)
        dlg = MagicMock()
        dlg.ShowModal.return_value = wx.ID_YES
        return dlg

    with patch("wx.MessageDialog", side_effect=fake_dialog), \
         patch("platform.system", return_value="Windows"):
        app.question("T", "Q?")

    style = captured_style[0]
    assert style == (wx.YES_NO | wx.ICON_QUESTION)


# ---------------------------------------------------------------------------
# question() cleans up the dialog regardless of result
# ---------------------------------------------------------------------------


def test_question_destroys_dialog_after_yes():
    app = _make_app()
    dialog_cls, dlg = _mock_dialog(wx.ID_YES)
    with patch("wx.MessageDialog", dialog_cls), \
         patch("platform.system", return_value="Windows"):
        app.question("T", "Q?")
    dlg.Destroy.assert_called_once()


def test_question_destroys_dialog_after_escape():
    app = _make_app()
    dialog_cls, dlg = _mock_dialog(wx.ID_CANCEL)
    with patch("wx.MessageDialog", dialog_cls), \
         patch("platform.system", return_value="Windows"):
        app.question("T", "Q?")
    dlg.Destroy.assert_called_once()


# ---------------------------------------------------------------------------
# question_from_thread() — same mapping, called via CallAfter
# ---------------------------------------------------------------------------


def test_question_from_thread_returns_1_for_yes():
    import application
    app = object.__new__(application.Application)

    app.question = MagicMock(return_value=1)

    # question_from_thread uses wx.CallAfter + threading.Event.
    # We call it synchronously by patching CallAfter to invoke immediately.
    def immediate_call_after(fn, *args, **kwargs):
        fn(*args, **kwargs)

    with patch("wx.CallAfter", side_effect=immediate_call_after):
        result = app.question_from_thread("T", "Q?")

    assert result == 1


def test_question_from_thread_returns_2_for_no():
    import application
    app = object.__new__(application.Application)
    app.question = MagicMock(return_value=2)

    def immediate_call_after(fn, *args, **kwargs):
        fn(*args, **kwargs)

    with patch("wx.CallAfter", side_effect=immediate_call_after):
        result = app.question_from_thread("T", "Q?")

    assert result == 2


def test_question_from_thread_returns_2_for_escape():
    """Escape in dialog → question() returns 2 → question_from_thread returns 2."""
    import application
    app = object.__new__(application.Application)
    app.question = MagicMock(return_value=2)  # simulates Escape path

    def immediate_call_after(fn, *args, **kwargs):
        fn(*args, **kwargs)

    with patch("wx.CallAfter", side_effect=immediate_call_after):
        result = app.question_from_thread("T", "Q?")

    assert result == 2
