# Sub-Agent Execution Guide

This guide adapts the strongest remaining workflow pattern from the inspected Claude CLI workspace:
sub-agent delegation should be structured, evidence-based, and verification-first. It is rewritten
for ACGS and aligned with this repository's existing `/do` and planning commands.

## Why this matters in ACGS

Sub-agents are useful here because ACGS is a large, mixed-language, multi-package repository. But
sub-agents become dangerous when they:
- wander across too many files,
- report conclusions without evidence,
- skip verification,
- or leave work mixed together in one checkout.

Use them as scoped workers, not as unverifiable narrators.

## Core rule

A sub-agent is only done when it returns:
- objective completed,
- files touched,
- commands run,
- verification result,
- and any remaining risks or unknowns.

## When to use sub-agents

Good uses:
- fact gathering across docs/examples,
- package-scoped implementation,
- targeted verification,
- anti-pattern review,
- code quality review,
- and independent plan execution phases.

Bad uses:
- cross-cutting repo-wide refactors in one pass,
- vague “go fix everything” delegation,
- or tasks where no evidence can be returned.

## Scope limits

Follow the repo guidance in `AGENTS.md` and the local package guide:
- keep each sub-agent scoped to **<10 files**,
- prefer one subsystem per sub-agent,
- and create a dedicated worktree for risky or parallel tasks.

If the scope grows beyond that, split the work into multiple sub-agents.

## Preferred execution model

### 1. Discovery sub-agent

Use for:
- locating files,
- reading docs,
- extracting signatures/patterns,
- or identifying affected tests.

Required output:
- files read,
- exact commands/greps used,
- short findings list with paths.

### 2. Implementation sub-agent

Use for:
- making the scoped code/doc change.

Required output:
- files changed,
- what changed,
- why this matches existing repo patterns.

### 3. Verification sub-agent

Use for:
- package-health checks,
- targeted pytest runs,
- lint/typecheck commands,
- or frontend checks.

Required output:
- exact verification command,
- PASS/FAIL,
- whether failure is baseline debt or newly introduced.

### 4. Review sub-agent

Use for:
- anti-pattern scan,
- code quality review,
- or security-sensitive spot checks.

Required output:
- findings with file paths,
- severity,
- recommended follow-up.

## Evidence requirements

Every sub-agent report should include evidence, not just conclusions.

Minimum evidence set:

```text
OBJECTIVE
- <what the sub-agent was asked to do>

FILES
- read: <paths>
- changed: <paths>

COMMANDS
- <exact command>
- <exact command>

RESULT
- PASS|FAIL|PARTIAL

VERIFICATION
- <command>
- <outcome>
- baseline vs new: <summary>

RISKS
- <remaining risk or unknown>
```

If a report lacks evidence, treat it as incomplete and re-check manually or redeploy the sub-agent.

## Worktree rule

For parallel or risky work, put the sub-agent in a dedicated worktree.

See [`worktree-isolation.md`](worktree-isolation.md).

Typical flow:

```bash
mkdir -p .claude/worktrees
git worktree add .claude/worktrees/fix-governance-gate -b worktree/fix-governance-gate
```

This keeps one sub-agent's edits from contaminating another's.

## Verification rule

Sub-agents must not stop at “implemented”. They must run the narrowest meaningful verification.

Preferred order:
1. package-health target (`make health-*`)
2. targeted pytest with `--import-mode=importlib`
3. `bash .claude/commands/test-and-verify.sh --quick`
4. broader repo checks only when needed

Examples:

```bash
make health-bus-governance
python -m pytest packages/enhanced_agent_bus/tests/test_governance_core.py -v --import-mode=importlib
bash .claude/commands/test-and-verify.sh --quick
```

## Handoff rule

A good sub-agent handoff includes:
- scope completed,
- file list,
- exact verification state,
- baseline debt vs new failures,
- and the next recommended command.

Example:

```text
Completed: governance-core docs update
Changed: docs/testing-spec.md, docs/test-plans/01-governance-core.md
Verified: make health-bus-governance not run yet; file-content checks passed
Baseline vs new: unknown for package tests because not run in this step
Next: make health-bus-governance
```

## Failure modes to avoid

- conclusions without file/command evidence,
- expanding to unrelated files,
- skipping verification,
- committing before verification,
- using destructive git commands,
- or merging work from multiple sub-agents without a clear audit trail.

## Relationship to existing ACGS commands

This guide complements:
- `.claude/commands/do.md`
- `.claude/commands/make-plan.md`
- `docs/worktree-isolation.md`
- `docs/context-compaction.md`

Those files define the workflow mechanics; this guide defines the quality bar for sub-agent outputs.

## See also

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`worktree-isolation.md`](worktree-isolation.md) — isolation model for risky or parallel delegated work
- [`context-compaction.md`](context-compaction.md) — what a good delegated handoff should preserve
- [`testing-spec.md`](testing-spec.md) — verification expectations for delegated implementation
- [`test-plans/01-governance-core.md`](test-plans/01-governance-core.md) — example of a subsystem-specific verification slice
