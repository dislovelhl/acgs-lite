# Project Memory and Durable Workspace Memory

This guide adapts the best parts of the external Claude CLI memory model for ACGS and combines them
with the local `claude-mem` workflow already available in this workspace.

> Part of the ACGS workflow docs. Start at [`README.md`](README.md) for the full workflow/reference set.

## Principle

Store only facts that are worth remembering across sessions.

Good memory candidates:
- recurring workflow rules,
- stable project context not obvious from code,
- validated user/team preferences,
- pointers to external systems or dashboards,
- and high-value discoveries that repeatedly save time.

Bad memory candidates:
- facts easily rediscovered from the repo,
- stale hypotheses,
- transient logs,
- or code structure that should be read from source instead of recalled from memory.

## Two memory layers

### 1. File-based project memory

Use repository-adjacent Claude memory files under:

```text
~/.claude/projects/<path-encoded>/memory/
```

Typical layout:

```text
~/.claude/projects/<path-encoded>/memory/
├── MEMORY.md
├── feedback_testing.md
├── project_governance_workflow.md
└── reference_deploy_urls.md
```

`MEMORY.md` should be the human-readable entrypoint index. Keep it short and link out to focused
files.

Those filenames are examples, not tracked files in this repository.

### 2. claude-mem durable search memory

The local `claude-mem` tool is available for cross-session retrieval, history search, and saving
higher-value observations.

Use it when you need:
- recall across many sessions,
- timeline context,
- searchable discoveries,
- or memory that should not live only in a single Markdown file.

See the `claude-mem` skill for the operational details.

## Recommended memory categories

Adapted for ACGS, these categories work well:

| Type | Use for | Example |
| --- | --- | --- |
| user | stable operator preferences | "Prefer package-health gates before full-suite runs" |
| feedback | validated workflow corrections | "Always call out baseline debt vs new failures" |
| project | durable repo context | "Constitutional hash is `608508a9bd224290`" |
| reference | external pointers | "Primary deploy status lives in Render dashboard X" |

## What belongs in `MEMORY.md`

`MEMORY.md` should be an index, not a dump.

Recommended format:

```markdown
- Governance workflow (`project_governance_workflow.md`) — package-health and eval-first reminders
- Testing feedback (`feedback_testing.md`) — import mode, baseline debt, verification habits
- External references (`reference_deploy_urls.md`) — dashboards, endpoints, service links
```

Keep entries brief enough that a later session can decide relevance quickly.

## Durable memory rules for ACGS

### Save these

- stable deploy/ops references not obvious from code,
- repeated gotchas that waste time when rediscovered,
- user-confirmed workflow preferences,
- package-specific verification shortcuts,
- and architecture facts that are easy to violate accidentally.

### Do not save these

- secrets, tokens, credentials, or sensitive logs,
- temporary branches or one-off experiment noise,
- speculative debugging theories,
- stale file/function names without verification,
- or anything that should instead be recorded in a tracked repo doc.

## Drift prevention

Memory can go stale. Before trusting a remembered fact:
- verify file paths still exist,
- verify function/class names still exist,
- verify dashboards/URLs are still current,
- and prefer source-of-truth repo docs when available.

For ACGS specifically:
- re-check the constitutional hash in tracked docs/config,
- re-check package-health commands in `Makefile`,
- re-check package paths against `AGENTS.md` and the nearest scoped package guide.

## How to use memory with compaction

Use memory for facts that should survive beyond one session.
Use compaction carry-forward for the current task's transient working state.

Examples:
- “`make health-bus-governance` is the best fast gate for governance-core work” → durable memory
- “Current branch has one failing targeted test after a local edit” → compaction/handoff state

See [`docs/context-compaction.md`](context-compaction.md).

## When to update tracked docs instead of memory

Prefer a tracked repo doc when the fact is:
- shared across contributors,
- likely to affect future code changes,
- part of an official workflow,
- or important enough to review in git history.

Use memory when the fact is useful but too personal, too operational, or too cross-session to fit
cleanly in tracked project docs.

## Quick operational pointers

### Search existing durable memory

Use the local `claude-mem` workflow when you need recall across sessions.

### Refresh project memory files

If you update project memory files under `~/.claude/projects/`, make sure `MEMORY.md` stays aligned
with the specific files it indexes.

### Privacy and safety

Never store:
- API keys
- passwords
- tokens
- secret URLs
- raw credential material

Memory is for durable context, not sensitive material.

## Related docs

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`context-compaction.md`](context-compaction.md) — session-state carry-forward versus durable memory
- [`repo-guidance-layering.md`](repo-guidance-layering.md) — when a fact belongs in tracked docs instead of memory
- [`ai-workspace.md`](ai-workspace.md) — workspace-level operator guidance around memory and tooling
