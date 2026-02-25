# Raywonder Project Sync

This folder links this project to the shared private `.GITHUB` automation repo.

## Purpose
- Keep this project aligned with shared Raywonder governance/workflow tooling.
- Provide per-OS entrypoints for humans and agents.
- Keep machine-specific values local-only in `.local/`.

## Entrypoints
- Windows: `windows/sync-from-dotgithub.bat`
- macOS: `macos/sync-from-dotgithub.sh`
- WSL/Linux: `wsl/sync-from-dotgithub.sh`

## Local-only files
- `.local/*` is intentionally ignored by git.

## Layout helpers
- `LAYOUT_STANDARD.md` defines the OS/app/server folder standard.
- `apply-layout.sh` and `apply-layout.bat` create the standard starter folders in the repo root.
