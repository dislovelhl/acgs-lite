# AI Workspace

Repo-local AI workspace bootstrap for **Claude Code**, **Codex CLI**, and **Gemini CLI**.
This document is the source of truth for agent-facing tooling in this repository.

## Workspace Layout

| Tool | Repo-local entry | Purpose |
| --- | --- | --- |
| Claude Code | `.claude/` | permissions, rules, commands, evals |
| Codex CLI | `.codex/config.toml` | MCP server wiring and repo-local Codex config |
| Gemini CLI | `.gemini/` | repo-local prompts, policies, launcher, and shared workspace metadata |

## Claude Code

Key files:
- `.claude/settings.json` — permissions and hooks
- `.claude/rules/*.md` — always-on repo rules
- `.claude/commands/test-and-verify.sh` — repo verification command
- `.claude/evals/` — eval definitions and dashboard

Recommended commands:

```bash
bash .claude/commands/test-and-verify.sh --quick
bash .claude/commands/test-and-verify.sh
```

## Codex CLI

Key files:
- `.codex/config.toml` — repo-local Codex configuration
- `scripts/codex-doctor.sh` — readiness checks
- `.agents/skills/acgs-codex-bootstrap/` — Codex workspace bootstrap skill
- `.agents/skills/package-health-governance/` — package-health workflow skill

Recommended command:

```bash
make codex-doctor
make gemini-doctor
```

Notes:
- The repo ships a minimal repo-local Codex config in `.codex/config.toml`.
- `make codex-doctor` is a local workspace sanity check. It validates the active skills,
  `AGENTS.md`, `PLANS.md`, and the repo-local Codex config without running a broad lint or test
  sweep.

## Gemini CLI

Key files:
- `.gemini/settings.json` — repo-local Gemini workspace metadata
- `.gemini/settings.local.json.example` — example local override template
- `.gemini/policies/acgs-governance.toml` — governance policy guidance
- `.gemini/commands/acgs/*.toml` — reusable repo-local Gemini prompts, including `eval-review`
- `.gemini/run-gemini.sh` — launcher that exports workspace context, supports diagnostics, and then execs Gemini

Run Gemini with repo-local context:

```bash
bash .gemini/run-gemini.sh
bash .gemini/run-gemini.sh --workspace-info
bash .gemini/run-gemini.sh --doctor
```

Available repo-local Gemini prompts include:
- `constitutional-check`
- `maci-validate`
- `release-readiness`
- `eval-review`

Create local overrides by copying:

```bash
cp .gemini/settings.local.json.example .gemini/settings.local.json
```

The real `.gemini/settings.local.json` file is intentionally gitignored.
Use `GEMINI_BIN=/path/to/gemini` to override binary detection when needed.

## Verification Commands

Use the narrowest meaningful command first:

```bash
# Workspace bootstrap checks
python3 - <<'PY'
import json, tomllib
from pathlib import Path
json.loads(Path('.claude/settings.json').read_text())
json.loads(Path('.gemini/settings.json').read_text())
tomllib.loads(Path('.codex/config.toml').read_text())
print('workspace config parse OK')
PY

# Repo-local Codex readiness
make codex-doctor

# Repo-local Gemini readiness
make gemini-doctor GEMINI_BIN=/path/to/gemini

# Gemini workspace diagnostics
bash .gemini/run-gemini.sh --workspace-info

# Claude verification
bash .claude/commands/test-and-verify.sh --quick
```

## Worktree Isolation

For parallel or risky work, prefer a dedicated worktree instead of editing in the shared checkout.
The canonical ACGS workflow is documented in [`docs/worktree-isolation.md`](worktree-isolation.md).
Use worktrees together with package-health gates to keep both edits and verification scoped.

## Context Compaction and Project Memory

For long-running work, handoffs, or context resets, preserve the right task state instead of
re-reading the whole repository. Use:
- [`docs/context-compaction.md`](context-compaction.md) for carry-forward rules during compaction
  and handoff
- [`docs/project-memory.md`](project-memory.md) for durable workspace memory and `claude-mem`
  guidance

## Docs Index and Sub-Agent Execution

Use [`docs/README.md`](README.md) as the tracked index for workflow/reference docs added to this
repository.

For delegated implementation or review work, use
[`docs/subagent-execution.md`](subagent-execution.md) together with `docs/worktree-isolation.md`
and `docs/context-compaction.md`.

## Repo Guidance Layering

To decide where new shared guidance should live, use
[`docs/repo-guidance-layering.md`](repo-guidance-layering.md). It explains the division of labor
between `AGENTS.md`, `CLAUDE.md`, `.claude/rules/`, package-local `AGENTS.md`, `docs/`, and
`.claude/evals/`.

## Related Workflow Docs

Common companions to this workspace guide:
- [`docs/README.md`](README.md) — docs index for the workflow/reference set
- [`docs/testing-spec.md`](testing-spec.md) — repository testing model
- [`docs/worktree-isolation.md`](worktree-isolation.md) — parallel-task isolation
- [`docs/context-compaction.md`](context-compaction.md) — carry-forward and handoff rules
- [`docs/project-memory.md`](project-memory.md) — durable workspace memory guidance
- [`docs/subagent-execution.md`](subagent-execution.md) — delegated implementation/review workflow
- [`docs/repo-guidance-layering.md`](repo-guidance-layering.md) — where new guidance should live

## Operating Principles

- Read `AGENTS.md` before broad changes. Use `CLAUDE.md` only as a compatibility summary for tools
  that still load it.
- Keep the constitutional hash `608508a9bd224290` consistent across docs and config.
- Respect MACI separation of powers in prompts, commands, and implementation guidance.
- Prefer deterministic, code-based verification over open-ended judgment when possible.
