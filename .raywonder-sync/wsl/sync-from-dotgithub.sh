#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TOOLS1="/mnt/c/Users/$USER/git/raywonder/.github/raywonder-repo-bootstrap"
TOOLS2="/mnt/c/Users/$USER/dev/apps/.GITHUB/raywonder-repo-bootstrap"
TOOLS=""

if [[ -f "$TOOLS1/run-repo-update.bat" ]]; then
  TOOLS="$TOOLS1"
elif [[ -f "$TOOLS2/run-repo-update.bat" ]]; then
  TOOLS="$TOOLS2"
fi

if [[ -z "$TOOLS" ]]; then
  echo "Could not find raywonder-repo-bootstrap tooling."
  exit 1
fi

if command -v powershell.exe >/dev/null 2>&1; then
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$TOOLS/scripts/pull_and_fix_repo.ps1")" -RepoRoot "$(wslpath -w "$REPO_ROOT")"
else
  echo "powershell.exe not found in WSL PATH; skipping update."
fi
