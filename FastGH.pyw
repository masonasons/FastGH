"""FastGH - A fast GitHub client."""

import sys
sys.dont_write_bytecode = True

import platform
import os

# On Windows, redirect stderr to errors.log
if platform.system() != "Darwin":
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        f = open(os.path.join(app_dir, "errors.log"), "a")
        sys.stderr = f
    except:
        pass

import wx

# Create wx.App first
wx_app = wx.App(redirect=False)

# Prevent multiple instances
instance_checker = wx.SingleInstanceChecker("FastGH-" + wx.GetUserId())
if instance_checker.IsAnotherRunning():
    wx.MessageBox("Another instance of FastGH is already running.", "FastGH", wx.OK | wx.ICON_WARNING)
    sys.exit(1)

# Import and initialize application
import application
from application import get_app
from GUI import main, theme

# Load application (initializes accounts, preferences)
fastgh_app = get_app()
fastgh_app.load()

# Create main window
main.create_window()

# Apply theme
theme.apply_theme(main.window)

# Show window
if fastgh_app.prefs.window_shown:
    main.window.Show()

# Start main loop
wx_app.MainLoop()
