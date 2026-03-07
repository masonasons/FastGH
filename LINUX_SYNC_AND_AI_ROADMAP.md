# FastGH Linux + Server Sync + AI Roadmap

## Scope
- Build a Linux desktop FastGH release with parity for core repo workflows.
- Add server-hosted sync mode so repos can continue syncing even without GitHub.
- Keep FastGH as an accessible replacement for GitHub Desktop.
- Add optional commit/PR/release summaries via local and remote AI providers.

## Phase 1: Linux Client Parity
- Add Linux build target in `build.py` and CI artifacts (`.AppImage` and `.tar.gz`).
- Validate keyboard navigation and screen-reader compatibility on Orca.
- Keep existing Git clone/pull/sync paths and repo auto-sync settings behavior.
- Add Linux startup checks for `git`, `git-lfs`, and optional `gh`.

## Phase 2: Server-Hosted Sync Engine
- Add `Repo Host` settings section:
  - `mode`: `github`, `self-hosted-git`, `hybrid`.
  - `primary remote`, `fallback remote`, auth credentials/token reference.
- Add sync policy options:
  - Auto fetch interval.
  - Auto pull strategy (`ff-only`, `rebase`, `merge`).
  - Auto push strategy (`never`, `ahead-only`, `force-disabled`).
- Add conflict policy:
  - Pause and notify.
  - Auto-create recovery branch.
  - Auto-open issue/PR in configured forge.

## Phase 3: Non-GitHub Forge Support
- Provider abstraction for GitHub, GitLab, Gitea, Forgejo, and bare git remotes.
- Keep `owner/repo` canonical identity plus `provider/host` metadata.
- Add UI for provider-specific auth and endpoint setup.
- Keep external-local-repo sync path as provider-agnostic fallback.

## Phase 4: Accessibility Completion
- Standardize list item text for screen readers (sentence-style labels).
- Ensure all dialogs have deterministic focus order and initial focus.
- Add explicit keyboard shortcuts and announce them in tooltips/help.
- Add accessibility smoke tests for:
  - Main lists.
  - Commit/PR/release dialogs.
  - Sync status and error summaries.

## Phase 5: AI Summary Providers
- Add Summary Provider settings:
  - `Manual only` (default).
  - `GitHub Copilot` (if available via token/API endpoint).
  - `Ollama local`.
  - `OpenAI/compatible remote`.
- Summary use-cases:
  - Commit bundle summary before push.
  - PR summary draft.
  - Changelog/release note generation.
- Controls:
  - Per-repo enable/disable.
  - Prompt templates.
  - Maximum context size and privacy guardrails.

## Security + Safety Baseline
- Never store raw secrets in repo config; use OS keychain/credential store.
- Redact tokens, keys, and private URLs from logs and exported diagnostics.
- Require explicit user confirmation before auto-merge or destructive operations.
- Keep AI summarization opt-in and auditable.

## Immediate Next Tasks
1. Add Linux build output support to `build.py`.
2. Add provider metadata model (`provider`, `host`, `remoteUrl`) for sync entries.
3. Add `Repo Host` settings tab and migration logic.
4. Add summary provider interface with a local Ollama adapter first.
