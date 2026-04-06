# Context Compaction and Carry-Forward Rules

This guide adapts the best parts of the external Claude CLI documentation on context compaction, but
rewrites them for ACGS workflows. The goal is not to copy another tool's runtime behavior. The goal
is to preserve the **right state** when a session gets long, a task is handed off, or context must
be compacted manually.

> Part of the ACGS workflow docs. Start at [`README.md`](README.md) for the full workflow/reference set.

## Why this matters in ACGS

ACGS work often spans:
- multi-package Python + TypeScript changes,
- governance/security decisions that must stay fail-closed,
- baseline test debt that must be distinguished from newly introduced failures,
- and eval-first workflows where success criteria exist before code changes.

If that state is lost during compaction, later work becomes slower and less safe.

## What to carry forward

Always carry forward the following items.

### 1. Current task and acceptance criteria

Record:
- the exact task being solved,
- the package/subsystem in scope,
- the active eval file(s),
- and the definition of done.

Example:

```text
Task: harden message processor failure sinks in enhanced_agent_bus
Scope: packages/enhanced_agent_bus/
Eval: .claude/evals/message-processor-architecture-hardening.md
Done when: targeted suites pass and docs exist
```

### 2. Files changed or intended to change

Record both:
- files already modified,
- files intentionally reserved for next edits.

This prevents drift and duplicate exploration.

### 3. Verification state

Always carry forward the exact verification status:
- commands run,
- whether they passed or failed,
- whether failure is new or baseline,
- and the highest-signal next verification command.

Example:

```text
Ran: make health-bus-governance
Status: failed
New or baseline: baseline debt in test_environment_check.py, no evidence current change caused it
Next: rerun targeted pytest for test_governance_core.py after fixing lint issue
```

### 4. Key errors and evidence

Preserve exact commands, stack traces, file paths, and failure summaries. Do not compress them into
vague prose like “tests were broken”.

### 5. Architectural constraints

Carry forward any discovered rule that should constrain later edits, for example:
- `--import-mode=importlib` is required,
- `middlewares/` is canonical, not `middleware/`,
- fail-closed behavior cannot be relaxed,
- package-health targets are the preferred fast gate.

### 6. Baseline debt vs new failures

This is mandatory in ACGS.

Every handoff or compaction summary should explicitly state:
- what is confirmed baseline debt,
- what is newly introduced,
- what is still unknown.

If unknown, say unknown — do not guess.

## Carry-forward template

Use this compact template during handoff or manual context compression:

```text
TASK
- <one-sentence task>

SCOPE
- <package/path>

EVALS
- <eval path(s)>

FILES
- changed: <file list>
- next: <file list>

VERIFICATION
- ran: <command>
- result: PASS|FAIL
- baseline vs new: <summary>
- next: <command>

CONSTRAINTS
- <repo rule or architecture fact>
- <repo rule or architecture fact>

OPEN QUESTIONS
- <only if truly unresolved>
```

## When to compact

Prefer compaction at logical boundaries:
- after a verification loop,
- after finishing one subsystem,
- before switching packages,
- before asking a second agent to continue,
- or before a long planning/review phase.

Do **not** compact in the middle of an unresolved failure investigation unless the failure evidence
has already been captured.

## What not to carry forward

Do not preserve noise such as:
- broad repository file listings,
- speculative explanations already disproven,
- repeated copies of unchanged docs,
- or low-signal command output without an associated conclusion.

## Relationship to verification

Compaction is not a substitute for verification. It is a state-preservation tool.

Before ending a session, the carry-forward summary should point to the narrowest next check, for
example:

```bash
make health-bus-governance
python -m pytest packages/enhanced_agent_bus/tests/test_governance_core.py -v --import-mode=importlib
bash .claude/commands/test-and-verify.sh --quick
```

## Relationship to project memory

Use compaction for **session state**.
Use project memory for **durable facts that should survive across sessions**.

See [`docs/project-memory.md`](project-memory.md).

## Related docs

- [`README.md`](README.md) — docs index for the workflow/reference set
- [`project-memory.md`](project-memory.md) — durable facts that should outlive one session
- [`subagent-execution.md`](subagent-execution.md) — evidence and handoff quality for delegated work
- [`testing-spec.md`](testing-spec.md) — verification expectations to preserve across compaction
