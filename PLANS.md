# ACGS Plans

## Purpose

Active coordination artifact for all agents (Claude Code, Codex, subagents) working on this repo.
**Read this first. Update this last.** Keep entries concrete: objective, state, next step, blockers.

## Active Work

| Agent | MACI Role | Scope | Status | Next Step | Blockers |
|-------|-----------|-------|--------|-----------|----------|
| Claude Code | Validator | Governance sweep: lint, tests, .gitignore, PLANS.md | done | PR `fix/p0-security-hardening` to main | — |
| Claude Code (worktree) | Proposer | `src/core/cli/` — platform CLI | stalled | Needs type annotation fixes (26 mypy errors) before merge | Worktree `agent-a56ce594` |
| Codex CLI | Proposer | `PLANS.md`, `autoresearch/program.md`, `autoresearch/setup_run.py`, `autoresearch/log_run.py` | done | — | — |

> **Hotspot ownership**: Claim `proposal_engine.py`, `api_gateway/main.py`, or `builder.py` here
> before touching them. One agent at a time — wait or use a worktree if claimed.

## Decision Log

- `make codex-doctor` is the first fast readiness check (verifies AGENTS.md + PLANS.md + .codex/config + lint).
- `make test-quick` for fast validation; `make test` is the full gate required before merge to `main`.
- Codex: `--sandbox workspace-write --ask-for-approval on-request` for interactive sessions; `--full-auto` only for scoped non-destructive tasks.
- Feature branches only — never commit directly to `main`.
- Conventional commits enforced: `feat/fix/refactor/test/chore/perf/ci` (100% compliance in this repo).
- `--import-mode=importlib` required on every pytest invocation.
- Autoresearch loops run on `autoresearch/<tag>` branches, never on feature branches.

## Outcomes & Retrospective

Record after each completed work unit: what changed, test result, and recurring issues to watch.

| Date | Agent | Outcome | Regressions |
|------|-------|---------|-------------|
| 2026-03-19 | Claude Code | Dev agent governance framework added to AGENTS.md + PLANS.md | None |
| 2026-03-19 | Codex CLI | Tightened autoresearch loop discipline: setup helper now reports scoped comparables and blocks dirty branch switches; logger now honors scope, legacy statuses, and justified tie-keeps; program.md updated to match helper behavior | None in helper verification (`py_compile`, `--help`, dry-run setup, synthetic logger checks) |
| 2026-03-19 | Claude Code | Governance sweep: fixed broken test imports (circuit breaker, PQC registry), resolved 44+ ruff violations (ruff exclude fix, per-file-ignores, zip strict=, import sort), added P0 env scenario test, updated .gitignore (9 ephemeral dirs), updated stale export expectations | 51 pre-existing failures (OPA fail-closed, PQC, Redis, MCP, licensing) — not introduced by this sweep |

## Surprises & Discoveries

- `.codex-readiness-unit-test/` directory present (untracked) — readiness test harness, do not delete.
- Autoresearch skill-evolve loop completed: `review=8.2`, `plan=8.6`, `orchestrate=8.0`, `build=8.2` on opus judge.
- Note missing scripts, broken targets, or ambiguous instructions here as soon as discovered.
