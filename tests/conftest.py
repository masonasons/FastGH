"""Pytest configuration — add project root to sys.path."""

import sys
import os

# Add the project root (parent of tests/) to sys.path so that
# top-level modules like config, repo_sync, github_api are importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
