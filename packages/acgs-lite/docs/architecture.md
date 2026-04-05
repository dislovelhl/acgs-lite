# Architecture

## Package Structure

```
src/acgs_lite/
  constitution/     # Constitution models, loading, templates, export
    rule.py         # Rule and Severity definitions
    constitution.py # Constitution class, builder, merge/diff
    filtering.py    # Rule filtering and matching
    rendering.py    # Human-readable rule rendering
    regulatory.py   # Regulatory framework mappings
    ...
  engine/           # Validation engine
    core.py         # GovernanceEngine -- deterministic validation
    batch.py        # Batch validation for bulk operations
  compliance/       # Multi-framework compliance assessment
  integrations/     # External platform adapters
    anthropic.py    # GovernedAnthropic
    openai.py       # GovernedOpenAI
    langchain.py    # GovernanceRunnable
    litellm.py      # GovernedLiteLLM
    mcp_server.py   # MCP Server integration
    google_genai.py # GovernedGenAI
    llamaindex.py   # GovernedQueryEngine
    autogen.py      # GovernedModelClient
    crewai.py       # GovernedCrew
    a2a.py          # A2A protocol adapter
    gitlab.py       # GitLab CI/CD governance bot
  maci/             # MACI enforcement subsystem
  audit.py          # Tamper-evident audit trail
  governed.py       # GovernedAgent / GovernedCallable wrappers
  maci.py           # MACIEnforcer, MACIRole definitions
  middleware.py     # GovernanceASGIMiddleware
  cli.py            # Click-based CLI
  server.py         # FastAPI wrapper
  fail_closed.py    # Fail-closed decorator
  errors.py         # Exception hierarchy
```

## Core Concepts

### Constitution

A **Constitution** is an immutable set of rules that define what an AI agent can and
cannot do. Rules are defined in YAML or code and validated at runtime.

```
Constitution
  rules: list[Rule]
  hash: str          # SHA-256 of rule content for integrity verification
  metadata: dict     # Framework, version, author info
```

### GovernanceEngine

The **GovernanceEngine** is a deterministic validator. Given a constitution and an
input/output pair, it returns a pass/fail result with violation details.

```
Input/Output --> GovernanceEngine --> ValidationResult
                      |                    |
                 Constitution         violations[]
                                      severity
                                      matched_rules[]
```

### GovernedAgent

**GovernedAgent** wraps any callable (function, LLM client, agent) with governance
checks on inputs and outputs.

```
User Request --> GovernedAgent --> Validate Input --> Call Agent --> Validate Output --> Response
                     |                                                    |
                Constitution                                        AuditLog
```

### MACI Roles

MACI (Monitor-Approve-Control-Inspect) enforces structural separation of powers:

| Role | Can | Cannot |
|---|---|---|
| **Proposer** | Generate actions | Execute or validate |
| **Validator** | Check against constitution | Propose or execute |
| **Executor** | Carry out approved actions | Propose or validate |
| **Observer** | Record audit trail | Modify decisions |

### Audit Trail

Every governance decision produces an `AuditEntry` chained via SHA-256 hashes:

```
Entry_1 --> hash --> Entry_2 --> hash --> Entry_3
  |                    |                    |
  timestamp            timestamp            timestamp
  action               action               action
  result               result               result
  rule_ids             rule_ids             rule_ids
```

## Integration Pattern

All integrations follow the same pattern:

1. Accept a `Constitution` at init time
2. Wrap the underlying client's methods
3. Validate inputs before calling the real method
4. Validate outputs before returning
5. Log to the audit trail

```python
class GovernedClient:
    def __init__(self, constitution: Constitution):
        self._engine = GovernanceEngine(constitution)
        self._audit = AuditLog()

    def call(self, input: str) -> str:
        self._engine.validate(input)       # Raises on violation
        result = self._real_client(input)
        self._engine.validate(result)      # Raises on violation
        self._audit.record(input, result)
        return result
```

## Fail-Closed Design

All governance paths default to deny on error. The `@fail_closed` decorator ensures
that any unexpected exception in a governance check results in a denial rather than
an accidental approval.

```python
from acgs_lite import fail_closed

@fail_closed
def check_permission(action: str, constitution: Constitution) -> bool:
    # If this raises, the decorator returns False (deny)
    return engine.validate(action).valid
```
