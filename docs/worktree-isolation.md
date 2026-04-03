# Worktree Isolation for ACGS

This guide adapts the best part of the external Claude CLI workspace docs: treat worktrees as the
primary safety mechanism for parallel agent work. It is intentionally rewritten for ACGS instead of
copying the original implementation.

> Part of the ACGS workflow docs. Start at [`README.md`](README.md) for the full workflow/reference set.

## Why worktrees matter here

ACGS is a multi-package repository with frequent parallel work across governance, security,
frontend, and worker code. A shared checkout creates three avoidable failure modes:

1. edit collisions in shared files,
2. mixed uncommitted state that is hard to attribute,
3. unsafe cleanup commands that destroy another agent's work.

Use a dedicated git worktree when the task is independent, risky, or likely to touch more than one
subsystem.

## Canonical location

Create human-managed worktrees under:

```text
.claude/worktrees/
```

Example layout:

```text
acgs/
├── .claude/
│   └── worktrees/
│       ├── fix-governance-gate/
│       └── docs-worktree-guide/
├── packages/
├── src/
└── workers/
```

Some internal tooling may create temporary worktree directories elsewhere for automation. For the
tracked team workflow, `.claude/worktrees/` is the canonical location.

## Standard creation flow

From the main repository root:

```bash
mkdir -p .claude/worktrees

git worktree add .claude/worktrees/fix-governance-gate -b worktree/fix-governance-gate
cd .claude/worktrees/fix-governance-gate
```

Recommended branch prefixes:
- `worktree/<slug>` for isolated parallel work
- `feature/<slug>` or `fix/<slug>` inside a dedicated worktree when you want a conventional branch
  name before opening a PR

Use short slugs tied to one task. Avoid reusing a dirty worktree for unrelated work.

## Safe day-to-day workflow

1. Start from repo root and read `AGENTS.md`.
2. Create one worktree per independent task.
3. Run the narrowest verification first (`make health-*`, package-scoped pytest, or
   `bash .claude/commands/test-and-verify.sh --quick`).
4. Stage only your files.
5. Clean up the worktree after merge or abandonment.

Selective staging example:

```bash
git status
git add packages/enhanced_agent_bus/message_processor.py \
        packages/enhanced_agent_bus/tests/test_governance_core.py
```

## Cleanup flow

When the worktree is no longer needed:

```bash
cd /home/martin/Documents/acgs-clean
git worktree remove .claude/worktrees/fix-governance-gate
# delete branch too only if it is fully merged / no longer needed
git branch -d worktree/fix-governance-gate
```

If the branch is not merged yet, keep the worktree or merge/cherry-pick the changes first.

## Multi-agent safety rules

### Allowed / preferred

- `git status`
- `git diff`
- `git add path/to/file ...`
- `git commit`
- `git pull --rebase origin <branch>`
- `git worktree add ...`
- `git worktree remove ...`

### Forbidden in a shared workspace unless explicitly approved

- `git stash`
- `git reset --hard`
- `git push --force`
- `git clean -f`
- `git add -A`
- `git add .`

The last two are especially dangerous in ACGS because they can silently stage another agent's
changes from the same checkout.

## When to prefer a worktree

Prefer a worktree when:
- you are debugging a risky failure in governance/security code,
- you need a clean branch for a docs or release workflow,
- another agent is already editing the same package,
- or you need to compare two implementation approaches side-by-side.

A plain shared checkout is acceptable only for small, low-risk, single-agent edits.

## Relationship to package-health verification

Worktree isolation and package-health checks complement each other:

```bash
make health-lite
make health-bus
make health-bus-governance
make health-gw
```

Use the worktree to isolate changes; use the health target to isolate verification.

## Practical handoff rule

When reporting work from a worktree, include:
- worktree path,
- branch name,
- files changed,
- exact verification command(s) run,
- whether anything remains intentionally unmerged.

That keeps parallel agents from stepping on each other during merge, cherry-pick, or cleanup.

## Related docs

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`subagent-execution.md`](subagent-execution.md) — how delegated workers should use worktrees
- [`context-compaction.md`](context-compaction.md) — what to preserve when handing off work from a worktree
- [`testing-spec.md`](testing-spec.md) — verification model to use inside isolated worktrees
