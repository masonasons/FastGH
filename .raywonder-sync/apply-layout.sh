#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p \
  "$REPO_ROOT/apps/macos/mac-app" \
  "$REPO_ROOT/apps/windows/windows-app" \
  "$REPO_ROOT/servers/api" \
  "$REPO_ROOT/servers/signal" \
  "$REPO_ROOT/servers/windows"

touch \
  "$REPO_ROOT/apps/macos/mac-app/.gitkeep" \
  "$REPO_ROOT/apps/windows/windows-app/.gitkeep" \
  "$REPO_ROOT/servers/api/.gitkeep" \
  "$REPO_ROOT/servers/signal/.gitkeep" \
  "$REPO_ROOT/servers/windows/.gitkeep"

echo "Layout folders ensured in: $REPO_ROOT"
