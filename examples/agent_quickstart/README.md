# Agent Quickstart

A self-verifying ACGS-Lite demo designed for AI coding agents.

Run this single script to confirm ACGS-Lite is correctly installed and
all three core capabilities work end-to-end.

```bash
pip install acgs-lite
python examples/agent_quickstart/run.py
```

Exit code `0` = all assertions passed.
Exit code `1` = one or more assertions failed — investigate the output.

## What is verified

| Section | What it proves |
|---------|---------------|
| **1. Governed Callable** | Safe requests pass; PII and destructive operations are blocked |
| **1b. YAML constitution** | `constitution.yaml` loads correctly; rules enforced from file |
| **2. MACI Role Separation** | Proposer / Validator / Executor roles enforced; Golden Rule held |
| **3. Audit Trail** | Decisions recorded; chain integrity verified |

## Expected output

```
============================================================
  ACGS-Lite Agent Quickstart — Verification Suite
============================================================

============================================================
  Section 1: Governed Callable
============================================================

── 1a. Inline constitution ───────────────────────────────────
  ✅  safe request passes through
  ✅  Allowed:  Response to: What is the capital of France?
  🚫  Blocked:  no-pii — ...
  ✅  PII blocked by rule 'no-pii'
  🚫  Blocked:  no-destructive — ...
  ✅  destructive op blocked by 'no-destructive'

── 1b. YAML constitution (production pattern) ────────────────
  ✅  YAML loads 3 rules
  ✅  safe request passes via YAML constitution
  ✅  YAML load OK — rules: 3
  🚫  YAML block: no-pii — still enforced from file
  ✅  YAML PII rule enforced

============================================================
  Section 2: MACI Role Separation
============================================================
  ✅  Proposer can propose
  🚫  Blocked: Proposer CANNOT self-validate
  ...

── Golden Rule: no self-validation ──────────────────────────
  ✅  Golden Rule: proposer cannot validate own output

============================================================
  Section 3: Audit Trail
============================================================
  ✅  Audit log: 3 entries recorded
  ✅  Chain integrity: verified
  ✅  Violations in log: ['ev-002']
  ✅  verify_chain(tampered) returns bool: ...

============================================================
  ✅  All assertions passed — ACGS-Lite is correctly installed.
  Exit code: 0
```

## Agent prompt (copy-paste into Claude Code or Codex CLI)

```
TASK: Verify ACGS-Lite is correctly installed.

1. pip install acgs-lite
2. cd <repo-root>/packages/acgs-lite
3. python examples/agent_quickstart/run.py

Expected: all ✅ lines, exit code 0.
If any ❌ appears, report the failing assertion text.
Do NOT set strict=False to fix failures — investigate root cause.
```

## No API keys required

This example runs fully offline. No `OPENAI_API_KEY` or other credentials needed.
