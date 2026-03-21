# acgs-lite API Reference

> Constitutional AI governance for any agent. Wrap any LLM agent in enforceable rules, audit
> trails, and separation of powers — in 5 lines of code.

**Version**: 0.2.0 | **License**: Apache-2.0 | **Python**: 3.10+ | **Constitutional Hash**: `cdd01ef066bc6cf2`

---

## Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Public API Reference](#4-public-api-reference)
5. [Constitution Module](#5-constitution-module)
6. [Engine](#6-engine)
7. [MACI Enforcement](#7-maci-enforcement)
8. [Governed Wrappers](#8-governed-wrappers)
9. [Audit](#9-audit)
10. [Compliance Frameworks](#10-compliance-frameworks)
11. [EU AI Act](#11-eu-ai-act)
12. [Integrations](#12-integrations)
13. [Rust Extension](#13-rust-extension)
14. [Error Reference](#14-error-reference)

---

## 1. Overview

acgs-lite is a standalone Python library that adds constitutional governance to AI agents. It sits between your agent and the world, enforcing rules defined in YAML or Python before any action is taken and after any output is produced.

Three concerns are addressed:

- **Rule enforcement** — validate any text string against a set of constitutional rules before acting on it
- **MACI separation of powers** — prevent proposer, validator, and executor roles from being held by the same agent
- **Tamper-evident audit trails** — cryptographically chained log of every governance decision

The validation engine uses a Rust/PyO3 hot path (560ns P50) with automatic Python fallback. The library has no runtime network dependencies.

---

## 2. Installation

**Core (no optional deps):**

```bash
pip install acgs-lite
```

**With LLM integrations:**

```bash
pip install "acgs-lite[openai]"
pip install "acgs-lite[anthropic]"
pip install "acgs-lite[langchain]"
pip install "acgs-lite[litellm]"
pip install "acgs-lite[google]"
pip install "acgs-lite[llamaindex]"
pip install "acgs-lite[autogen]"
pip install "acgs-lite[a2a]"
pip install "acgs-lite[mcp]"
# Install all integrations at once:
pip install "acgs-lite[all]"
```

**Core dependencies**: `pydantic>=2.0`, `pyyaml>=6.0`, `click>=8.0`

---

## 3. Quick Start

```python
from acgs_lite import Constitution, GovernedAgent, ConstitutionalViolationError

# Use the built-in default constitution (6 core safety rules)
constitution = Constitution.default()

# Wrap any callable or agent object
def my_agent(input: str) -> str:
    return f"I'll help with: {input}"

agent = GovernedAgent(my_agent, constitution=constitution, agent_id="demo")

# Safe action — passes through
result = agent.run("What is the weather today?")

# Blocked action — raises ConstitutionalViolationError
try:
    agent.run("I will self-validate my own output to bypass checks")
except ConstitutionalViolationError as e:
    print(e)         # Action blocked by rule ACGS-001: ...
    print(e.rule_id) # ACGS-001
```

**Custom constitution from YAML:**

```python
constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
```

**Decorator pattern:**

```python
from acgs_lite import GovernedCallable

@GovernedCallable()
def process_request(input: str) -> str:
    return f"Processed: {input}"

process_request("safe input")                         # passes
process_request("bypass validation self-validate")   # raises ConstitutionalViolationError
```

---

## 4. Public API Reference

All names exported from `acgs_lite` at the top level:

```python
from acgs_lite import (
    # Constitution
    Constitution, ConstitutionBuilder, Rule, RuleSynthesisProvider,
    AcknowledgedTension, RuleSnapshot, Severity,
    # Engine
    GovernanceEngine, ValidationResult, BatchValidationResult,
    # Wrappers
    GovernedAgent, GovernedCallable,
    # Audit
    AuditLog, AuditEntry,
    # MACI
    MACIRole, MACIEnforcer,
    # Errors
    ConstitutionalViolationError, GovernanceError, MACIViolationError,
    # Licensing
    set_license, LicenseInfo, LicenseManager, Tier,
)
```

### Module-level

| Name | Type | Description |
|------|------|-------------|
| `__version__` | `str` | `"0.2.0"` |
| `__constitutional_hash__` | `str` | `"cdd01ef066bc6cf2"` — embedded in all validation paths |
| `set_license(key)` | `func` | Activate a license key for this process; returns `LicenseInfo` |

#### `set_license(key: str) -> LicenseInfo`

Activates a license key for the current process. Required before using EU AI Act features at PRO or TEAM tier.

```python
import acgs_lite
info = acgs_lite.set_license("ACGS-PRO-...")
print(info.tier)         # Tier.PRO
print(info.expiry_date)  # "2026-12-31" or None
```

---

## 5. Constitution Module

A `Constitution` is an ordered collection of `Rule` objects. The engine evaluates every active rule against an action string and surfaces violations.

### 5.1 `Severity`

```python
class Severity(str, Enum):
    CRITICAL = "critical"   # Blocks action, no override; always raises in strict mode
    HIGH     = "high"       # Blocks action, can be overridden with justification
    MEDIUM   = "medium"     # Warns but allows action to proceed
    LOW      = "low"        # Informational only
```

**`Severity.blocks() -> bool`** — returns `True` for `CRITICAL` and `HIGH`.

### 5.2 `Rule`

Pydantic `BaseModel`. All fields except `id` and `text` are optional.

```python
from acgs_lite import Rule, Severity

rule = Rule(
    id="PII-001",                          # required, 1-50 chars
    text="No PII in agent outputs",        # required, 1-1000 chars
    severity=Severity.CRITICAL,            # default: HIGH
    keywords=["ssn", "social security", "date of birth"],
    patterns=[r"\b\d{3}-\d{2}-\d{4}\b"],  # validated regex
    category="privacy",
    subcategory="pii-exposure",
    depends_on=["ACGS-002"],              # rule IDs this rule depends on
    enabled=True,
    workflow_action="block_and_notify",   # "block"|"block_and_notify"|"require_human_review"|"escalate_to_senior"|"warn"
    hardcoded=False,
    tags=["gdpr", "hipaa", "eu-ai-act"],
    priority=10,                          # higher = evaluated first within same severity
    condition={"env": "production"},      # activation condition (see below)
    deprecated=False,
    replaced_by="",
    valid_from="2025-01-01",             # ISO-8601, empty = unbounded
    valid_until="2026-12-31",
    embedding=[0.1, 0.9, 0.3],           # optional vector for semantic search
    provenance=["GDPR-Art-5"],
    metadata={"owner": "security-team"},
)
```

**Rule methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `matches` | `(text: str) -> bool` | Returns `True` if `text` triggers this rule. Context-aware: positive-verb actions ("audit…", "test…") are not flagged even if they contain governance keywords. |
| `matches_with_signals` | `(text_lower: str, has_neg: bool, has_pos: bool) -> bool` | Fast match using pre-computed action-level signals. Amortised per `validate()` call. |
| `match_detail` | `(text: str) -> dict` | Returns structured match info: `matched`, `rule_id`, `severity`, `category`, `workflow_action`, `trigger_type` ("keyword"\|"pattern"\|`None`), `trigger_value`, `positive_context`. |
| `condition_matches` | `(context: dict) -> bool` | Returns `True` if the rule's activation `condition` is satisfied by `context`. Empty condition always returns `True`. |
| `is_valid_at` | `(timestamp: str) -> bool` | Returns `True` if the rule is temporally active at an ISO-8601 timestamp. `valid_until` is inclusive. |
| `cosine_similarity` | `(other: Rule) -> float \| None` | Cosine similarity between stored `embedding` vectors. Returns `None` if either embedding is missing. |
| `explain` | `() -> dict` | Human-readable explanation for compliance dashboards: `rule_id`, `summary`, `what_it_protects`, `how_it_detects`, `when_triggered`, `severity_label`, `dependencies`. |
| `impact_score` | `() -> dict` | Normalized 0.0-1.0 impact score for prioritization: `rule_id`, `score`, `severity_weight`, `detection_breadth`, `config_richness`, `blocking`, `classification`. |
| `from_description` | `classmethod(description, *, rule_id, llm_provider, default_severity)` | Synthesize a rule from natural-language policy text. Falls back to deterministic heuristics when `llm_provider` is `None`. |

**Activation conditions (`condition` field):**

```python
# Scalar equality
condition={"env": "production"}

# Operator dict
condition={"env": {"op": "in", "value": ["prod", "staging"]}}

# Supported ops: "equals", "not_equals", "contains", "in", "not_in"
```

Pass matching context to `engine.validate()`:

```python
engine.validate("action text", context={"env": "production"})
```

### 5.3 `Constitution`

Pydantic `BaseModel`. Computes a SHA-256 content hash on construction and caches active rules.

```python
from acgs_lite import Constitution

# Load from YAML file
constitution = Constitution.from_yaml("rules.yaml")

# Load from YAML string
constitution = Constitution.from_yaml_str(yaml_content)

# Load from dict
constitution = Constitution.from_dict(data)

# Create from Rule objects
constitution = Constitution.from_rules([rule1, rule2], name="my-policy")

# Built-in default (6 core ACGS safety rules)
constitution = Constitution.default()

# Domain template
constitution = Constitution.from_template("gitlab")
# domains: "gitlab" | "healthcare" | "finance" | "security" | "general"
```

**Properties and methods:**

| Member | Type | Description |
|--------|------|-------------|
| `name` | `str` | Constitution name, default `"default"` |
| `version` | `str` | SemVer string, default `"1.0.0"` |
| `rules` | `list[Rule]` | All rules (enabled and disabled) |
| `description` | `str` | Human-readable description |
| `metadata` | `dict` | Arbitrary metadata |
| `permission_ceiling` | `str` | `"standard"` \| `"strict"` \| `"permissive"` |
| `version_name` | `str` | Optional label, e.g. `"release-2026-03"` |
| `hash` | `property str` | SHA-256 content hash (first 16 hex chars) |
| `hash_versioned` | `property str` | `"sha256:v1:<hash>"` |
| `active_rules()` | `-> list[Rule]` | Enabled rules only (cached) |
| `active_non_deprecated()` | `-> list[Rule]` | Enabled, non-deprecated rules for enforcement |
| `active_rules_at(timestamp)` | `-> list[Rule]` | Rules active at an ISO-8601 timestamp |
| `active_rules_for_context(context)` | `-> list[Rule]` | Enabled rules whose `condition` matches context |
| `deprecated_rules()` | `-> list[Rule]` | Rules with `deprecated=True` |
| `to_yaml()` | `-> str` | Serialize to YAML string (round-trippable) |
| `validate_rules()` | `-> list[str]` | Validate rule syntax and semantics; returns list of error strings |
| `merge_constitutions(other, strategy)` | `-> Constitution` | Merge two constitutions; `strategy`: `"union"` (default) or `"intersect"` |
| `__len__()` | `int` | Number of rules |

### 5.4 YAML Format

```yaml
name: my-policy
version: 1.2.0
description: Policy for production AI agents
permission_ceiling: strict   # standard | strict | permissive
version_name: release-2026-03

rules:
  - id: SEC-001
    text: Agents must not expose credentials in outputs
    severity: critical          # critical | high | medium | low
    category: security
    subcategory: credential-exposure
    keywords:
      - api_key
      - secret key
      - private key
    patterns:
      - '(?i)(sk-[a-zA-Z0-9]{20,})'
      - '\b\d{3}-\d{2}-\d{4}\b'
    workflow_action: block_and_notify
    tags: [gdpr, pci-dss, eu-ai-act]
    depends_on: [ACGS-002]
    priority: 100
    hardcoded: false
    enabled: true
    condition:
      env: production
    valid_from: "2025-01-01"
    valid_until: "2026-12-31"
    metadata:
      owner: security-team

  - id: AUDIT-001
    text: All data exports must be logged
    severity: high
    category: audit
    keywords: [export, download, extract]
    workflow_action: require_human_review
```

### 5.5 `ConstitutionBuilder`

Fluent builder for constructing constitutions programmatically.

```python
from acgs_lite import ConstitutionBuilder

constitution = (
    ConstitutionBuilder("my-policy")
    .add_rule(Rule(id="R1", text="No PII", severity=Severity.CRITICAL, keywords=["ssn"]))
    .add_rule(Rule(id="R2", text="Audit required", severity=Severity.HIGH))
    .build()
)
```

### 5.6 `RuleSnapshot` and `AcknowledgedTension`

`RuleSnapshot` captures a point-in-time version of a rule for constitutional history tracking (stored in `constitution.rule_history`).

`AcknowledgedTension` records a known rule conflict that has been explicitly reviewed:

```python
from acgs_lite import AcknowledgedTension

# Frozen dataclass: rule_id (required), rationale (optional)
tension = AcknowledgedTension(rule_id="R1", rationale="Intentional override for pilot program")
```

### 5.7 `RuleSynthesisProvider`

Protocol for plugging in LLM-backed rule synthesis:

```python
from collections.abc import Mapping
from typing import Any

class MyLLMProvider:
    def generate_rule(self, description: str, *, rule_id: str) -> Mapping[str, Any]:
        # Call your LLM, return a dict with at minimum: id, text, severity, keywords
        ...

rule = Rule.from_description(
    "Agents must not share patient health records",
    rule_id="HIPAA-001",
    llm_provider=MyLLMProvider(),
)
```

---

## 6. Engine

### 6.1 `GovernanceEngine`

Core validation engine. Inherits `BatchValidationMixin`.

```python
from acgs_lite import GovernanceEngine, Constitution, AuditLog

constitution = Constitution.from_yaml("rules.yaml")
audit_log = AuditLog()  # optional; omit for maximum performance

engine = GovernanceEngine(
    constitution,
    audit_log=audit_log,      # None = use internal fast log (default)
    custom_validators=None,   # list[CustomValidator] | None
    strict=True,              # True = raise on CRITICAL/HIGH violations
    disable_gc=False,         # True = disable GC after engine init (reduces p99 latency)
)
```

**`GovernanceEngine.__init__` parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `constitution` | `Constitution` | required | The governing constitution |
| `audit_log` | `AuditLog \| None` | `None` | Pass an `AuditLog()` for tamper-evident chaining; omit for the fast internal log |
| `custom_validators` | `list[CustomValidator] \| None` | `None` | Additional validator callables |
| `strict` | `bool` | `True` | If `True`, raises `ConstitutionalViolationError` on any blocking violation |
| `disable_gc` | `bool` | `False` | Disable Python GC after init to reduce p99 latency spikes |

**`CustomValidator` type:** `Callable[[str, dict[str, Any]], list[Violation]]`

#### `validate()`

```python
result: ValidationResult = engine.validate(
    action,               # str — the action text to check
    *,
    agent_id="anonymous", # str — identifies the agent for audit records
    context=None,         # dict[str, Any] | None — optional context
)
```

Returns `ValidationResult`. Raises `ConstitutionalViolationError` in strict mode when blocking violations are found.

**Context keys with governance significance:**

| Key | Effect |
|-----|--------|
| `"action_detail"` | Additional text scanned against all rules (same pass as `action`) |
| `"action_description"` | Additional text scanned against all rules |
| Any other key | Passed to rule `condition_matches()` for conditional rules (e.g., `{"env": "production"}`) |

#### `validate_batch()`

```python
results: list[ValidationResult] = engine.validate_batch(
    actions,              # list[str]
    *,
    agent_id="anonymous",
)
```

Validates multiple actions without raising in strict mode. Returns one `ValidationResult` per action.

#### `validate_batch_report()`

```python
report: BatchValidationResult = engine.validate_batch_report(
    actions,              # list[str | tuple[str, dict]]
    *,
    agent_id="anonymous",
)
```

Accepts plain strings or `(action, context_dict)` tuples. Never raises. Returns aggregate statistics.

```python
report = engine.validate_batch_report([
    "deploy to staging",
    ("deploy to production", {"environment": "prod"}),
    "auto-approve merge request",
])
print(report.compliance_rate)   # 0.666...
print(report.critical_rule_ids) # ('ACGS-004',)
print(report.summary)           # "FAIL: 1/3 actions blocked, ..."
print(report.to_dict())         # JSON-compatible dict
```

#### `stats` property

```python
stats: dict = engine.stats
# {
#   "total_validations": int,
#   "compliance_rate": float,   # 0.0–1.0
#   "rules_count": int,
#   "constitutional_hash": str,
#   "avg_latency_ms": float,
# }
```

Note: `compliance_rate` and `avg_latency_ms` are only accurate when `AuditLog()` was passed at construction. With the default fast log, `compliance_rate` is always `1.0`.

### 6.2 `ValidationResult`

`@dataclass(slots=True)` — result of a single `validate()` call.

```python
@dataclass(slots=True)
class ValidationResult:
    valid: bool                # True if no blocking violations
    constitutional_hash: str   # Hash of the constitution used
    violations: list[Violation]
    rules_checked: int
    latency_ms: float
    request_id: str
    timestamp: str
    action: str
    agent_id: str
```

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `blocking_violations` | `list[Violation]` | Violations that block execution (CRITICAL or HIGH) |
| `warnings` | `list[Violation]` | Non-blocking violations (MEDIUM or LOW) |

**Methods:**

| Method | Return | Description |
|--------|--------|-------------|
| `to_dict()` | `dict` | JSON-serializable representation |

### 6.3 `Violation`

`NamedTuple` — a single rule match.

```python
class Violation(NamedTuple):
    rule_id: str
    rule_text: str
    severity: Severity
    matched_content: str
    category: str
```

### 6.4 `BatchValidationResult`

`@dataclass(frozen=True)` — aggregate result from `validate_batch_report()`.

```python
@dataclass(frozen=True)
class BatchValidationResult:
    results: tuple             # tuple[ValidationResult, ...] — per-action results in input order
    total: int
    allowed: int
    denied: int                # count blocked by CRITICAL/HIGH violations
    escalated: int             # count with MEDIUM/LOW violations only
    compliance_rate: float     # allowed / total
    critical_rule_ids: tuple   # tuple[str, ...] — rule IDs with at least one critical violation
    summary: str               # human-readable one-liner
```

**`to_dict() -> dict`** — JSON-compatible serialization.

---

## 7. MACI Enforcement

MACI (Multi-Agent Constitutional Integrity) enforces separation of powers: an agent that proposes an action cannot validate it, and a validator cannot execute. This prevents any single agent from having unchecked authority.

### 7.1 `MACIRole`

```python
class MACIRole(str, Enum):
    PROPOSER  = "proposer"   # Suggests governance actions: propose, draft, suggest, amend
    VALIDATOR = "validator"  # Verifies compliance: validate, review, audit, verify
    EXECUTOR  = "executor"   # Executes approved actions: execute, deploy, apply, run
    OBSERVER  = "observer"   # Read-only: read, query, export, observe
```

Unassigned agents are treated as `OBSERVER`.

**Role permission matrix:**

| Role | Allowed | Denied |
|------|---------|--------|
| PROPOSER | propose, draft, suggest, amend | validate, execute, approve |
| VALIDATOR | validate, review, audit, verify | propose, execute, deploy |
| EXECUTOR | execute, deploy, apply, run | validate, propose, approve |
| OBSERVER | read, query, export, observe | propose, validate, execute, deploy, approve |

### 7.2 `MACIEnforcer`

```python
from acgs_lite import MACIEnforcer, MACIRole, MACIViolationError

enforcer = MACIEnforcer(audit_log=None)  # audit_log defaults to a new AuditLog()

# Assign roles
enforcer.assign_role("planner",  MACIRole.PROPOSER)
enforcer.assign_role("reviewer", MACIRole.VALIDATOR)
enforcer.assign_role("deployer", MACIRole.EXECUTOR)

# Check role permission — raises MACIViolationError on violation
enforcer.check("planner",  "propose")    # True
enforcer.check("reviewer", "validate")  # True

try:
    enforcer.check("planner", "validate")  # raises — PROPOSER cannot validate
except MACIViolationError as e:
    print(e.actor_role)          # "proposer"
    print(e.attempted_action)    # "validate"

# Enforce the golden rule: agents never validate their own output
try:
    enforcer.check_no_self_validation("agent-x", "agent-x")  # same ID = violation
except MACIViolationError as e:
    print(e)
```

**`MACIEnforcer` methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `assign_role` | `(agent_id: str, role: MACIRole) -> None` | Assign a role; records to audit log |
| `get_role` | `(agent_id: str) -> MACIRole \| None` | Return the assigned role, or `None` |
| `check` | `(agent_id: str, action: str) -> bool` | Verify action is permitted; raises `MACIViolationError` if not |
| `check_no_self_validation` | `(proposer_id: str, validator_id: str) -> bool` | Verify the two IDs differ; raises if they match |
| `role_assignments` | `property dict[str, str]` | Current agent → role mapping |
| `summary` | `() -> dict` | Enforcement summary: `agents`, `roles`, `checks_total`, `checks_denied`, `separation_integrity` |

### 7.3 `ActionRiskTier`

Classify an action's risk tier for downstream routing without inspecting rule details:

```python
from acgs_lite.maci import ActionRiskTier

class ActionRiskTier(str, Enum):
    LOW      = "low"       # Auto-approve
    MEDIUM   = "medium"    # Notify supervisor
    HIGH     = "high"      # Human review queue
    CRITICAL = "critical"  # Immediate governance lead escalation
```

Each tier has an `escalation_path` property returning the recommended routing string.

### 7.4 `recommend_escalation()`

```python
from acgs_lite.maci import recommend_escalation

result = recommend_escalation(
    severity="critical",
    context_risk_score=0.8,   # 0.0–1.0
    action_risk_tier="high",
)
# Returns:
# {
#   "tier": "tier_4_block",
#   "sla": "immediate",
#   "requires_human": True,
#   "rationale": "critical severity + high-risk context/action",
# }
```

Five escalation tiers: `tier_0_auto`, `tier_1_notify`, `tier_2_review`, `tier_3_urgent`, `tier_4_block`.

### 7.5 Attaching MACI to `GovernedAgent`

```python
agent = GovernedAgent(
    my_agent,
    constitution=constitution,
    agent_id="planner",
    maci_role=MACIRole.PROPOSER,  # automatically calls enforcer.assign_role()
)
```

---

## 8. Governed Wrappers

High-level wrappers that combine engine validation, MACI enforcement, and audit logging behind a single interface.

### 8.1 `GovernedAgent`

Wraps any agent object or callable with constitutional governance.

```python
from acgs_lite import GovernedAgent, Constitution, MACIRole

agent = GovernedAgent(
    my_agent,
    constitution=Constitution.default(),  # None = use default
    agent_id="my-agent",
    strict=True,
    validate_output=True,                 # validate string outputs as well as inputs
    maci_role=MACIRole.PROPOSER,          # optional; assigns role to agent_id
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `Any` | required | Any object with a `.run()` method or a callable |
| `constitution` | `Constitution \| None` | `None` | Uses `Constitution.default()` if `None` |
| `agent_id` | `str` | `"default"` | Identifies this agent in audit records |
| `strict` | `bool` | `True` | Raise on blocking violations |
| `validate_output` | `bool` | `True` | Validate string outputs through the constitution |
| `maci_role` | `MACIRole \| None` | `None` | Assign a MACI role at construction time |

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `run` | `(input: str, **kwargs) -> Any` | Validate input → run agent → validate output (if `validate_output=True` and result is `str`) |
| `arun` | `async (input: str, **kwargs) -> Any` | Async variant; detects async agents automatically |
| `stats` | `property dict` | Combines `engine.stats` with `agent_id` and `audit_chain_valid` |

**`run()` execution order:**

1. Validate `input` against constitution
2. Call `agent.run(input, **kwargs)` (or `agent(input, **kwargs)` for bare callables)
3. If `validate_output=True` and result is `str`, validate result with `agent_id="{agent_id}:output"`
4. Return result

**Supported wrapped types:**

- Object with `.run(input: str, **kwargs) -> Any`
- Object with `.arun(input: str, **kwargs) -> Any` (for `arun()`)
- Any `Callable` accepting `(str, **kwargs)`

### 8.2 `GovernedCallable`

Class decorator for governing individual functions.

```python
from acgs_lite import GovernedCallable, Constitution

@GovernedCallable(
    constitution=Constitution.default(),  # None = default
    agent_id="my-callable",
    strict=True,
)
def process_data(input: str) -> str:
    return f"Processed: {input}"

# Works for sync and async functions:
@GovernedCallable()
async def async_processor(input: str) -> str:
    return f"Async: {input}"
```

**Behavior:** All positional `str` arguments are validated on entry. String return values are validated on exit with `agent_id="{agent_id}:output"`.

---

## 9. Audit

### 9.1 `AuditEntry`

`@dataclass` — a single audit log record.

```python
@dataclass
class AuditEntry:
    id: str
    type: str              # "validation" | "override" | "maci_check" | "maci_assign"
    agent_id: str = ""
    action: str = ""
    valid: bool = True
    violations: list[str] = field(default_factory=list)
    constitutional_hash: str = ""
    latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)
    timestamp: str = ...   # auto-set to UTC ISO-8601 at creation

    @property
    def entry_hash(self) -> str: ...  # SHA-256 of canonical JSON (first 16 hex chars)

    def to_dict(self) -> dict: ...
```

### 9.2 `AuditLog`

Tamper-evident audit log. Each entry's chain hash includes the previous entry's hash. Tampering with any entry invalidates `verify_chain()`.

```python
from acgs_lite import AuditLog, AuditEntry

log = AuditLog(max_entries=10000)  # default max; oldest entries trimmed when exceeded
```

**Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `record` | `(entry: AuditEntry) -> str` | Append entry; returns chain hash for this position |
| `verify_chain` | `() -> bool` | Returns `True` if no entries have been tampered with |
| `query` | `(*, agent_id, entry_type, valid, limit=100) -> list[AuditEntry]` | Filter entries; all filter args are optional |
| `export_json` | `(path: str \| Path) -> None` | Write JSON file; creates parent directories |
| `export_dicts` | `() -> list[dict]` | Return all entries as JSON-compatible dicts |
| `entries` | `property list[AuditEntry]` | Copy of all entries |
| `compliance_rate` | `property float` | Fraction of entries where `valid=True` |
| `__len__` | `int` | Number of entries |

**Usage with engine:**

```python
audit_log = AuditLog()
engine = GovernanceEngine(constitution, audit_log=audit_log)

engine.validate("some action", agent_id="bot-1")

# Inspect decisions
violations = audit_log.query(valid=False)
print(audit_log.compliance_rate)  # e.g. 0.95
print(audit_log.verify_chain())   # True if untampered

# Export for compliance archival
audit_log.export_json("/var/log/governance/audit-2026-03.json")
```

**Performance note:** Passing `AuditLog()` explicitly to `GovernanceEngine` enables SHA-256 chain hashing per entry (~50µs overhead). Without it, the engine uses an internal fast log that counts calls but does not chain-hash. Use the fast path in latency-sensitive production systems; pass `AuditLog()` where tamper-evidence is required.

---

## 10. Compliance Frameworks

`acgs_lite.compliance` maps acgs-lite's governance features to eight regulatory frameworks. Import from `acgs_lite.compliance`.

### 10.1 Supported Frameworks

| Class | Framework | Coverage area |
|-------|-----------|---------------|
| `NISTAIRMFFramework` | NIST AI RMF | GOVERN/MAP/MEASURE/MANAGE functions |
| `ISO42001Framework` | ISO/IEC 42001 | AI Management System standard |
| `GDPRFramework` | GDPR | Automated decisions, data subject rights |
| `SOC2AIFramework` | SOC 2 + AI | Trust Service Criteria with AI controls |
| `HIPAAAIFramework` | HIPAA + AI | PHI protection in healthcare AI |
| `USFairLendingFramework` | US Fair Lending | ECOA + FCRA + fair lending for credit AI |
| `NYCLL144Framework` | NYC LL 144 | Automated Employment Decision Tools law |
| `OECDAIFramework` | OECD AI Principles | Baseline principles (46 countries) |

### 10.2 Core Types

```python
from acgs_lite.compliance import (
    ChecklistItem, ChecklistStatus,
    ComplianceFramework, FrameworkAssessment,
    MultiFrameworkReport, MultiFrameworkAssessor,
)
```

**`ChecklistStatus`** (enum): `PASS`, `FAIL`, `PARTIAL`, `NOT_APPLICABLE`, `UNKNOWN`

**`ChecklistItem`** (dataclass): `id`, `description`, `status: ChecklistStatus`, `notes: str`

**`FrameworkAssessment`** (dataclass): `framework_id`, `framework_name`, `items: list[ChecklistItem]`, `score: float`, `gaps: list[str]`

**`MultiFrameworkReport`** (dataclass): `assessments: list[FrameworkAssessment]`, `overall_score: float`, `cross_framework_gaps: list[str]`, `system_id: str`

### 10.3 Usage

```python
from acgs_lite.compliance import MultiFrameworkAssessor

assessor = MultiFrameworkAssessor()

report = assessor.assess({
    "system_id":    "my-hiring-system",
    "jurisdiction": "united_states",
    "domain":       "employment",
})

print(report.overall_score)                        # e.g. 0.72
print(report.cross_framework_gaps)                 # ["Missing bias audit procedure", ...]

for assessment in report.assessments:
    print(f"{assessment.framework_name}: {assessment.score:.0%}")
    for item in assessment.items:
        if item.status != ChecklistStatus.PASS:
            print(f"  {item.id}: {item.description} — {item.status.value}")
```

Each framework auto-populates checklist items that acgs-lite's governance controls satisfy (audit trails, rule enforcement, MACI separation), computing coverage and surfacing gaps that require additional controls outside the library.

---

## 11. EU AI Act

`acgs_lite.eu_ai_act` provides Article 12, 13, 14 compliance helpers for high-risk AI systems. **High-risk provisions apply from 2026-08-02.**

License requirement: PRO tier for `Article12Logger`, `RiskClassifier`, `ComplianceChecklist`; TEAM tier for `TransparencyDisclosure`, `HumanOversightGateway`.

```python
import acgs_lite
acgs_lite.set_license("ACGS-PRO-...")   # required before instantiating gated classes
```

### 11.1 Risk Classification

```python
from acgs_lite.eu_ai_act import RiskClassifier, SystemDescription, RiskLevel

classifier = RiskClassifier()

result = classifier.classify(SystemDescription(
    system_id="hiring-screener",
    purpose="Automated first-pass CV screening",
    domain="employment",          # triggers Annex III high-risk classification
    autonomy_level=3,             # 1 (human-in-loop) to 5 (full autonomy)
    human_oversight=True,
    employment=True,
))

print(result.level)                          # RiskLevel.HIGH_RISK
print(result.requires_article12_logging)     # True
```

**`RiskLevel`** values: `MINIMAL_RISK`, `LIMITED_RISK`, `HIGH_RISK`, `UNACCEPTABLE_RISK`

### 11.2 Article 12 — Record-Keeping (PRO+)

Log every LLM call for audit trail continuity under Article 12:

```python
from acgs_lite.eu_ai_act import Article12Logger, Article12Record

logger = Article12Logger(system_id="hiring-screener")

response = logger.log_call(
    operation="screen_candidate",
    call=lambda: llm.complete(prompt),
    input_text=prompt,
)
```

### 11.3 Article 13 — Transparency (TEAM+)

Generate the required transparency disclosure document:

```python
from acgs_lite.eu_ai_act import TransparencyDisclosure

disclosure = TransparencyDisclosure(
    system_id="hiring-screener",
    system_name="CV Screening System",
    provider="Acme Corp",
    intended_purpose="Automated first-pass CV screening",
    capabilities=["Text classification", "Ranking"],
    limitations=["English only", "Not validated for creative roles"],
    human_oversight_measures=["All rejections reviewed by HR within 24h"],
    contact_email="ai-compliance@acme.com",
)
```

### 11.4 Article 14 — Human Oversight (TEAM+)

Gate high-impact AI decisions on human review:

```python
from acgs_lite.eu_ai_act import HumanOversightGateway, OversightOutcome

gateway = HumanOversightGateway(system_id="hiring-screener")
decision = gateway.submit(
    action="final_reject",
    output=ai_output,
    impact_score=0.9,   # 0.0–1.0; high scores route to human review
)

if decision.outcome == OversightOutcome.APPROVED:
    proceed()
elif decision.outcome == OversightOutcome.PENDING_REVIEW:
    queue_for_hr()
```

### 11.5 Compliance Checklist (PRO+)

Track Annex IV documentation requirements:

```python
from acgs_lite.eu_ai_act import ComplianceChecklist

checklist = ComplianceChecklist(system_id="hiring-screener")
checklist.auto_populate_acgs_lite()  # marks items satisfied by acgs-lite controls

print(checklist.compliance_score)   # 0.55 — items auto-populated by acgs-lite
print(checklist.is_gate_clear)      # False — remaining items need manual completion
```

### 11.6 License Check

```python
from acgs_lite.eu_ai_act import check_license

info = check_license()
# {
#   "tier": "PRO",
#   "expiry": "2026-12-31",
#   "pro_features": True,
#   "team_features": False,
#   "enterprise_features": False,
#   "available_classes": ["Article12Logger", "RiskClassifier", "ComplianceChecklist"],
# }
```

---

## 12. Integrations

All integrations follow the same pattern: drop-in replacement for the underlying client, with constitution and `agent_id` injected at construction. Input validation raises in strict mode; output validation logs warnings but does not block.

Install the extra before importing the integration module.

### OpenAI (`acgs_lite.integrations.openai`)

```bash
pip install "acgs-lite[openai]"
```

```python
from acgs_lite.integrations.openai import GovernedOpenAI

client = GovernedOpenAI(
    api_key=None,               # reads OPENAI_API_KEY from env
    constitution=constitution,  # None = default
    agent_id="openai-agent",
    strict=True,
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)

print(client.stats)  # governance statistics
```

Async: `await client.chat.completions.acreate(**kwargs)`

### Anthropic (`acgs_lite.integrations.anthropic`)

```bash
pip install "acgs-lite[anthropic]"
```

```python
from acgs_lite.integrations.anthropic import GovernedAnthropic

client = GovernedAnthropic(constitution=constitution, agent_id="claude-agent")
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
```

### LangChain (`acgs_lite.integrations.langchain`)

```bash
pip install "acgs-lite[langchain]"
```

```python
from acgs_lite.integrations.langchain import GovernedLangChain

# Wraps any LangChain Runnable
governed_chain = GovernedLangChain(chain, constitution=constitution)
result = governed_chain.invoke({"input": "process this"})
```

### LiteLLM (`acgs_lite.integrations.litellm`)

```bash
pip install "acgs-lite[litellm]"
```

```python
from acgs_lite.integrations.litellm import GovernedLiteLLM

client = GovernedLiteLLM(constitution=constitution)
response = client.completion(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)
```

### Google GenAI (`acgs_lite.integrations.google_genai`)

```bash
pip install "acgs-lite[google]"
```

```python
from acgs_lite.integrations.google_genai import GovernedGoogleGenAI

client = GovernedGoogleGenAI(constitution=constitution)
response = client.generate_content("Hello, world")
```

### LlamaIndex (`acgs_lite.integrations.llamaindex`)

```bash
pip install "acgs-lite[llamaindex]"
```

```python
from acgs_lite.integrations.llamaindex import GovernedLlamaIndex

engine = GovernedLlamaIndex(query_engine, constitution=constitution)
response = engine.query("What does this document say?")
```

### AutoGen (`acgs_lite.integrations.autogen`)

```bash
pip install "acgs-lite[autogen]"
```

```python
from acgs_lite.integrations.autogen import GovernedAutoGenAgent

agent = GovernedAutoGenAgent(base_agent, constitution=constitution)
```

### A2A (`acgs_lite.integrations.a2a`)

```bash
pip install "acgs-lite[a2a]"
```

Wraps A2A (Agent-to-Agent) protocol messages with constitutional validation before routing.

```python
from acgs_lite.integrations.a2a import GovernedA2AClient

client = GovernedA2AClient(constitution=constitution)
```

### MCP Server (`acgs_lite.integrations.mcp_server`)

```bash
pip install "acgs-lite[mcp]"
```

Exposes the governance engine as an MCP (Model Context Protocol) server so external tools can call `validate` over the wire.

```python
from acgs_lite.integrations.mcp_server import GovernanceMCPServer

server = GovernanceMCPServer(constitution=constitution)
server.serve()
```

### GitLab CI/CD (`acgs_lite.integrations.gitlab`)

Gate merge requests and pipeline stages against a constitution. No extra dependencies needed.

```python
from acgs_lite.integrations.gitlab import GitLabGovernanceGate

gate = GitLabGovernanceGate(constitution=Constitution.from_template("gitlab"))
gate.check_merge_request(mr_title, mr_description)  # raises on violation
```

### Cloud Logging (`acgs_lite.integrations.cloud_logging`)

```bash
pip install "acgs-lite[google-cloud]"
```

Streams audit log entries to Google Cloud Logging.

---

## 13. Rust Extension

The Rust/PyO3 extension (`acgs_lite_rust`) provides a dual-automaton validator: Aho-Corasick for keyword scanning + pre-compiled anchor dispatch for regex patterns. It is automatically used when present; the engine falls back to Python transparently.

**Performance:** 560ns P50 validation latency (warmed, Rust path). Python fallback: ~5-15µs depending on rule count.

**Build:**

```bash
cd packages/acgs-lite/rust
maturin develop --release   # build and install into current venv
cargo test                  # run Rust unit tests
cargo bench                 # run criterion benchmarks
cargo clippy                # lint
cargo audit                 # security audit
```

**Rust extension modules:**

| Module | Description |
|--------|-------------|
| `validator.rs` | Core rule validation logic |
| `severity.rs` | Severity enum with ordering |
| `verbs.rs` | Positive/negative action verb parsing |
| `result.rs` | Validation result types |
| `context.rs` | Governance context struct |
| `hash.rs` | Constitutional hash computation |

**When to build the Rust extension:**

- Latency requirement below 5µs P50
- High-throughput batch validation (>10,000 calls/second)
- Production deployments where p99 spikes from GC are unacceptable (combine with `disable_gc=True`)

**Verify extension is active:**

```python
from acgs_lite.engine.rust import _HAS_RUST
print(_HAS_RUST)  # True if acgs_lite_rust is importable
```

---

## 14. Error Reference

All errors inherit from `GovernanceError` which inherits from `Exception`.

### `GovernanceError`

Base class for all acgs-lite governance failures.

```python
class GovernanceError(Exception):
    rule_id: str | None   # rule that caused the failure, if applicable
```

### `ConstitutionalViolationError`

Raised by `GovernanceEngine.validate()` in strict mode when a blocking violation is found.

```python
class ConstitutionalViolationError(GovernanceError):
    rule_id: str    # ID of the violated rule
    severity: str   # "critical" | "high"
    action: str     # first 200 chars of the violating action text
```

```python
try:
    engine.validate("bypass audit logging", agent_id="bot")
except ConstitutionalViolationError as e:
    print(e)           # "Action blocked by rule ACGS-002: ..."
    print(e.rule_id)   # "ACGS-002"
    print(e.severity)  # "high"
    print(e.action)    # "bypass audit logging"
```

### `MACIViolationError`

Raised when MACI separation of powers is violated.

```python
class MACIViolationError(GovernanceError):
    rule_id: str = "MACI"     # always "MACI"
    actor_role: str           # the role that attempted the forbidden action
    attempted_action: str     # the action that was denied
```

```python
try:
    enforcer.check("planner", "validate")
except MACIViolationError as e:
    print(e.actor_role)         # "proposer"
    print(e.attempted_action)   # "validate"
```

### `LicenseError`

Raised when a PRO or TEAM tier feature is accessed without the required license.

```python
from acgs_lite.licensing import LicenseError

try:
    logger = Article12Logger(system_id="my-system")  # requires PRO+
except LicenseError as e:
    print(e)  # "Article 12 logging requires PRO tier or higher"
```

---

## Appendix: Default Constitution Rules

The six rules bundled in `Constitution.default()`:

| ID | Severity | Category | Description |
|----|----------|----------|-------------|
| `ACGS-001` | CRITICAL | integrity | Agents must not modify their own validation logic |
| `ACGS-002` | HIGH | audit | All actions must produce an audit trail entry |
| `ACGS-003` | CRITICAL | access | Agents must not access data outside their authorized scope |
| `ACGS-004` | CRITICAL | maci | Proposers cannot validate their own proposals (MACI) |
| `ACGS-005` | HIGH | integrity | All governance changes require constitutional hash verification |
| `ACGS-006` | CRITICAL | data-protection | Agents must not expose sensitive data in responses (credentials, SSNs) |

All six are tagged `eu-ai-act`. ACGS-006 additionally matches OpenAI API key patterns (`sk-...`), GitHub tokens (`ghp_...`), and SSN patterns via regex.
