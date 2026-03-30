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
- `scripts/codex-mcp-acgs-governance.sh` — governance MCP launcher
- `scripts/codex-mcp-acgs-agent-bus.sh` — agent-bus MCP launcher

Recommended command:

```bash
make codex-doctor
make gemini-doctor
```

Notes:
- The repo already ships Codex configuration.
- `make codex-doctor` validates config presence and MCP wiring, but it currently ends with `make lint`, so it can fail on unrelated repo lint issues. Treat that as a repository baseline issue, not a workspace-config parsing failure.

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

## Operating Principles

- Read `AGENTS.md` and `CLAUDE.md` before broad changes.
- Keep the constitutional hash `608508a9bd224290` consistent across docs and config.
- Respect MACI separation of powers in prompts, commands, and implementation guidance.
- Prefer deterministic, code-based verification over open-ended judgment when possible.
