# Repo Guidance Layering

This guide adapts the useful idea behind system-prompt layering from the inspected Claude CLI
workspace, but applies it to ACGS as a **documentation placement model**. It explains where shared
repository guidance should live so both humans and coding agents can find the right level of detail
quickly.

This is **not** a claim about literal runtime prompt assembly in ACGS. It is a practical content
layering model for this repository.

> Part of the ACGS workflow docs. Start at [`README.md`](README.md) for the full workflow/reference set.

## The short version

| Location | Put this here | Do not put this here |
| --- | --- | --- |
| `AGENTS.md` | canonical repo guide: navigation, structure, commands, conventions, where-to-look, forbidden patterns | long deep dives, repeated walkthroughs, large architecture essays |
| `CLAUDE.md` | compatibility summary for tools that still load it | primary repo rules or a second full guide |
| `.claude/rules/` | always-on guardrails that should apply every session | one-off notes, project history, long architecture rationale |
| `docs/` | durable long-form reference, workflows, plans, architecture, strategy, subsystem guides | short duplicated summaries already covered by AGENTS/CLAUDE |
| package/subdir `AGENTS.md` | local rules and navigation for one package/subsystem | repo-wide policy duplicated from the root |
| `.claude/evals/` | success criteria and deterministic graders | broad narrative docs |

## Mental model

Think of the repository guidance stack like this:

1. **Find the area and the rules** → `AGENTS.md`
2. **Apply hard guardrails** → `.claude/rules/`
3. **Read the deep reference** → `docs/`
4. **Use local package nuance** → package/subdir `AGENTS.md`
5. **Check compatibility summaries only if needed** → `CLAUDE.md`
6. **Define success before coding** → `.claude/evals/`

Each layer should stay focused. When layers blur together, guidance becomes harder to maintain and
agents start re-reading too much noise.

## What belongs in `AGENTS.md`

Use `AGENTS.md` for fast orientation.

Good fits:
- repository structure,
- canonical namespaces,
- high-level conventions,
- where to look for common tasks,
- dangerous anti-patterns,
- and the index of package-level guides.

Bad fits:
- long command walkthroughs,
- subsystem implementation details that belong in `docs/`,
- repeated verification scripts already described elsewhere.

If a reader should be able to scan it quickly at the start of a session, it probably belongs here.

## What belongs in `CLAUDE.md`

Use `CLAUDE.md` only as a small compatibility layer for tools that still read it.

Good fits:
- a pointer back to `AGENTS.md`,
- a very short command summary,
- and brief verification reminders.

Bad fits:
- primary repo rules,
- detailed workflow guidance,
- architecture deep dives,
- or any content that would become stale if duplicated from `AGENTS.md`.

If the content matters for everyday work in this repo, it should usually live in `AGENTS.md` or
`docs/`, not only in `CLAUDE.md`.

## What belongs in `.claude/rules/`

Use `.claude/rules/` for compact, always-on guardrails.

Good fits:
- testing rules,
- security rules,
- code style rules,
- git workflow rules.

These should be short, prescriptive, and stable.

Do not turn `.claude/rules/` into a dumping ground for architecture notes or release history.

## What belongs in `docs/`

Use `docs/` for durable deep reference.

Good fits:
- architecture docs,
- workflow guides,
- test plans,
- AI workspace docs,
- deployment/process docs,
- and subsystem-level explanations that are too large for `AGENTS.md`.

Examples already present in ACGS:
- `docs/ai-workspace.md`
- `docs/worktree-isolation.md`
- `docs/context-compaction.md`
- `docs/project-memory.md`
- `docs/testing-spec.md`

If the document is something you would want to link repeatedly instead of repeating inline, it
belongs in `docs/`.

## What belongs in package or subdirectory `AGENTS.md`

Use local `AGENTS.md` files when a subsystem has rules that should not pollute the whole repo.

Good fits:
- canonical local imports,
- package-specific testing guidance,
- local architecture boundaries,
- optional dependency patterns,
- and subsystem anti-patterns.

Rule of thumb:
- if it applies to the whole repo, keep it at the root;
- if it applies to one package, move it to that package's `AGENTS.md`.

## What belongs in `.claude/evals/`

Use evals for **success criteria**, not general explanation.

Good fits:
- capability checks,
- regression graders,
- deterministic bash commands,
- release gates for a specific change.

If the question is “how do we know this work is done?”, that belongs in an eval.

## How to choose where a new note goes

Ask these questions in order:

### 1. Is it a hard rule that should apply every session?

Put it in `.claude/rules/`.

### 2. Is it fast orientation or repo navigation?

Put it in `AGENTS.md`.

### 3. Is it shared repo guidance for coding or verification?

Put it in `AGENTS.md` unless it is too detailed, then put it in `docs/`.

### 4. Is it a long-lived reference or detailed workflow?

Put it in `docs/`.

### 5. Is it only true for one package/subsystem?

Put it in that package's `AGENTS.md`.

### 6. Is it the definition of done for one task/change?

Put it in `.claude/evals/`.

## Anti-patterns

Avoid these documentation mistakes:
- putting long architecture essays in `AGENTS.md`,
- duplicating the same rule in root docs and every package doc,
- using `CLAUDE.md` as a changelog,
- treating `CLAUDE.md` as a second canonical repo guide,
- storing one-task acceptance criteria in general docs instead of evals,
- or hiding durable workflow guidance only in local memory instead of tracked docs.

## Recommended read order for new sessions

For most ACGS tasks:

1. `AGENTS.md`
2. this docs index or linked `docs/*.md`
3. relevant package `AGENTS.md`
4. `CLAUDE.md` only if a tool still loads it
5. relevant `.claude/evals/*.md`

That gives a good balance of speed, safety, and depth.

## Related docs

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`ai-workspace.md`](ai-workspace.md) — repo-local operator workflow and entry points
- [`testing-spec.md`](testing-spec.md) — example of a long-form tracked workflow doc
- [`worktree-isolation.md`](worktree-isolation.md) — example of task-specific workflow guidance
- [`context-compaction.md`](context-compaction.md) — example of active-session workflow guidance
- [`project-memory.md`](project-memory.md) — example of durable memory guidance
- [`subagent-execution.md`](subagent-execution.md) — example of delegated-work execution guidance
