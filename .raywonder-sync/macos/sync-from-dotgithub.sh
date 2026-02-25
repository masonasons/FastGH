#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TOOLS1="$HOME/DEV/APPS/.GITHUB/raywonder-repo-bootstrap"
TOOLS2="$HOME/dev/apps/.GITHUB/raywonder-repo-bootstrap"
TOOLS=""

if [[ -x "$TOOLS1/run-repo-bootstrap.bat" || -f "$TOOLS1/run-repo-bootstrap.bat" ]]; then
  TOOLS="$TOOLS1"
elif [[ -x "$TOOLS2/run-repo-bootstrap.bat" || -f "$TOOLS2/run-repo-bootstrap.bat" ]]; then
  TOOLS="$TOOLS2"
fi

if [[ -z "$TOOLS" ]]; then
  echo "Could not find raywonder-repo-bootstrap tooling."
  exit 1
fi

# On macOS call PowerShell updater directly if available; otherwise do report-only.
PS_SCRIPT="$TOOLS/scripts/pull_and_fix_repo.ps1"
if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoProfile -ExecutionPolicy Bypass -File "$PS_SCRIPT" -RepoRoot "$REPO_ROOT"
else
  echo "pwsh not found; skipping PowerShell repo update."
fi
