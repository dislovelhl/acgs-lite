# ACGS Docs Index

This index highlights the most useful tracked documentation for active engineering work in ACGS.
It is intentionally biased toward operator and coding-agent workflows rather than strategy or paper
content.

> Part of the ACGS workflow docs. Start here when you need the tracked workflow/reference set.

## Start Here

| Doc | Use when |
| --- | --- |
| [`ai-workspace.md`](ai-workspace.md) | You need the repo-local Claude/Codex/Gemini workspace setup and operator workflow |
| [`repo-guidance-layering.md`](repo-guidance-layering.md) | You are deciding where new shared guidance should live |
| [`testing-spec.md`](testing-spec.md) | You want the repository testing model, layers, and standard commands |
| [`test-plans/01-governance-core.md`](test-plans/01-governance-core.md) | You are working on governance-core or message-processor changes |

## Workflow Guides

| Doc | Focus |
| --- | --- |
| [`worktree-isolation.md`](worktree-isolation.md) | Safe parallel work with dedicated git worktrees |
| [`context-compaction.md`](context-compaction.md) | Carry-forward rules for handoff and context compression |
| [`project-memory.md`](project-memory.md) | Durable project memory, `MEMORY.md`, and `claude-mem` usage |
| [`subagent-execution.md`](subagent-execution.md) | How to delegate to sub-agents safely with evidence and verification |

## Architecture and Project Reference

| Doc | Focus |
| --- | --- |
| [`ai-workspace.md`](ai-workspace.md) | Repo-local AI tooling layout and verification commands |
| [`brand-architecture.md`](brand-architecture.md) | Branding/system framing |
| [`GITLAB.md`](GITLAB.md) | GitLab-specific integration/reference material |
| [`ORIGIN.md`](ORIGIN.md) | Repository background and lineage |

## Strategy, Research, and Launch

These docs are valuable, but not usually the first stop for implementation sessions:
- [`strategy/`](strategy/)
- [`launch/`](launch/)
- [`papers/`](papers/)
- [`generated/`](generated/)

## Recommended Read Order for Coding Work

For most engineering tasks:
1. root `AGENTS.md`
2. this index
3. relevant package/subdirectory `AGENTS.md`
4. the specific workflow doc(s) above
5. root `CLAUDE.md` only if a tool still reads it
6. the relevant eval under `.claude/evals/`

## Maintenance Rule

When a new tracked workflow or operator doc is added under `docs/`, update this index so later
sessions can discover it quickly.

## Related docs

- [`ai-workspace.md`](ai-workspace.md) — repo-local tooling and operator workflow
- [`repo-guidance-layering.md`](repo-guidance-layering.md) — where new shared guidance should live
- [`subagent-execution.md`](subagent-execution.md) — delegated implementation/review workflow
