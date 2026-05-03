# Governance Engine

> **Stability: stable.** `GovernanceEngine`, `ValidationResult`, and
> `BatchValidationResult` are part of the **stable** API surface
> (`acgs_lite.stability("GovernanceEngine") == "stable"`). Behaviour and
> attribute layout are semver-protected: breaking changes only on major
> version bumps.

`GovernanceEngine` is the low-level synchronous validator. It applies a
`Constitution` to actions, returns structured `ValidationResult` objects, and
optionally records each decision into an `AuditLog`. Use it directly when you
want fine-grained control; for the wrapped agent ergonomics use
[`GovernedAgent`](governed_agent.md).

## Class Reference

::: acgs_lite.GovernanceEngine
    options:
      members:
        - __init__
        - validate
        - validate_batch
        - validate_batch_report
      show_source: true

::: acgs_lite.ValidationResult

::: acgs_lite.BatchValidationResult

## Constructor

`GovernanceEngine(constitution, *, audit_log=None, custom_validators=None,
strict=True, disable_gc=False, audit_mode=None, warmup=True, freeze_gc=True)`

- `constitution` — required `Constitution` instance.
- `audit_log` — optional `AuditLog`. When provided, the engine switches to
  `audit_mode="full"` and records every decision. When `None`, the engine
  defaults to `audit_mode="fast"` and uses a non-recording fast path.
- `strict` — when `True` (default), the first CRITICAL violation raises
  `ConstitutionalViolationError`. When `False`, violations are collected and
  returned in the result.
- `audit_mode` — `"fast"` or `"full"`. Passing `"fast"` together with
  `audit_log` raises `ValueError`.

## `validate(action, *, agent_id="anonymous", context=None, audit_metadata=None, strict=None) -> ValidationResult`

Validates a single action string. Pass `strict=False` per call to override
the instance-level setting without mutating shared state.

## `validate_batch(actions, *, agent_id="anonymous") -> list[ValidationResult]`

Validates a list of action strings. Always non-strict — never raises;
violations are captured per-result. Returns one `ValidationResult` per input
in the same order.

## `validate_batch_report(actions, *, agent_id="anonymous") -> BatchValidationResult`

Validates a batch and returns aggregate statistics. Accepts plain action
strings or `(action, context_dict)` tuples. Never raises — useful for
orchestrators that need a one-shot summary across many actions.

## `ValidationResult` fields

Verified from `acgs_lite.engine.models.ValidationResult`:

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `valid` | `bool` | True if no CRITICAL violations were collected |
| `constitutional_hash` | `str` | Hash of the constitution that produced this result |
| `violations` | `list[Violation]` | Per-rule violation records (id, text, severity, matched content, category) |
| `warnings` | `list[Violation]` | Non-blocking findings (rules with `WARN` workflow action) |
| `rules_checked` | `int` | Number of rules evaluated for this action |
| `latency_ms` | `float` | Wall-clock time spent in `validate()` |
| `request_id` | `str` | Per-call identifier |
| `timestamp` | `str` | ISO-8601 timestamp |
| `action` | `str` | Echo of the input action string |
| `agent_id` | `str` | Echo of the `agent_id` argument |
| `action_taken` | `ViolationAction \| None` | The workflow action dispatched (e.g. `BLOCK`, `WARN`, `ESCALATE`) |
| `notifications` | `list[NotificationEvent]` | Notification events emitted by workflow dispatch |
| `review_requests` | `list[ReviewRequest]` | Pending human-review requests |
| `escalations` | `list[EscalationRequest]` | Escalation events |
| `incident_alerts` | `list[IncidentAlert]` | Critical incident alerts |

## `BatchValidationResult` fields

Verified from `acgs_lite.engine.batch.BatchValidationResult`:

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `results` | `tuple[ValidationResult, ...]` | Per-action results, same order as input |
| `total` | `int` | Total number of actions validated |
| `allowed` | `int` | Count that passed all rules |
| `denied` | `int` | Count blocked by CRITICAL/HIGH violations |
| `escalated` | `int` | Count with MEDIUM/LOW violations (warn-only) |
| `compliance_rate` | `float` | `allowed / total` |
| `critical_rule_ids` | `tuple[str, ...]` | Rule IDs that triggered at least one CRITICAL violation |
| `summary` | `str` | One-line human-readable summary |

`BatchValidationResult.to_dict()` returns a JSON-serialisable view.

## Examples

### Single-action validation

```python
from acgs_lite import Constitution, GovernanceEngine

constitution = Constitution.from_template("general")
engine = GovernanceEngine(constitution, strict=False)

result = engine.validate("summarise this document", agent_id="agent-42")

if not result.valid:
    for v in result.violations:
        print(f"{v.rule_id} [{v.severity}]: {v.rule_text}")
```

### Strict mode

When `strict=True` (default), the first CRITICAL violation raises
`ConstitutionalViolationError`:

```python
from acgs_lite import GovernanceEngine, ConstitutionalViolationError

engine = GovernanceEngine(constitution, strict=True)
try:
    engine.validate("delete production database")
except ConstitutionalViolationError as exc:
    print(f"Blocked by rule {exc.rule_id}")
```

### Per-call strict override

```python
# Engine default is strict=True; relax for this single call only.
result = engine.validate("inspect logs", strict=False)
```

### Batch validation (per-action results)

```python
results = engine.validate_batch([
    "read public docs",
    "delete production database",
    "send a customer email",
])
for r in results:
    print(r.action, r.valid)
```

### Batch validation with aggregate report

```python
report = engine.validate_batch_report([
    "read public docs",
    "delete production database",
    "send a customer email",
])
print(report.summary)
print(f"compliance: {report.compliance_rate:.0%} "
      f"({report.allowed}/{report.total})")
print("critical rule ids:", report.critical_rule_ids)
```

### Pairing with an `AuditLog`

```python
from acgs_lite import AuditLog, Constitution, GovernanceEngine

audit = AuditLog()
engine = GovernanceEngine(constitution, audit_log=audit, strict=False)

engine.validate("send a customer email", agent_id="agent-1")
print(len(audit.entries))
```

## Common exceptions

- `ConstitutionalViolationError` (raised by `validate()` only when
  `strict=True` and a CRITICAL violation matches). Carries `rule_id`,
  `severity`, and the offending `action`.
- `ValueError` from the constructor when an inconsistent `audit_mode` /
  `audit_log` combination is passed (`audit_mode="fast"` with a non-`None`
  `audit_log`).

## Related

- [`Constitution`](constitution.md) — the rule container the engine validates against.
- [`GovernedAgent`](governed_agent.md) — high-level wrapper that composes `GovernanceEngine` with retries and MACI.
- [`AuditLog`](audit.md) — tamper-evident decision log.
- [Constitution Lifecycle HTTP API](lifecycle.md) — bundle-aware activation surface (beta).
