# validate-tasks-down-with-codex

## Overview
Runs Codex readiness validation after a subagent completes work.

**Event Type:** `SubagentStop`
**Template:** `subagent_stop_test_runner`
**Command:** `make codex-doctor`

## How It Works

1. Claude Code emits `SubagentStop` when a subagent finishes.
2. The hook checks that `make` is available and that the repo has a `Makefile`.
3. The hook runs `make codex-doctor`.
4. Any failure is swallowed so workflow continues silently.

## Safety Notes

- The hook is non-destructive.
- It exits cleanly if `make` or `Makefile` is unavailable.
- Validation is silent and should not block the session.

## Manual Installation

Add the `SubagentStop` entry from [hook.json](hook.json) to your Claude Code settings file:

- Project: `.claude/settings.json`
- User: `~/.claude/settings.json`

## Recommended Use

Use this when you want Codex to validate completed tasks automatically before you continue.
