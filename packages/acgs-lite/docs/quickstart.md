# Quickstart

## Install

```bash
pip install acgs-lite
```

## Create a Constitution

**YAML (recommended):**

```yaml
# rules.yaml
rules:
  - id: no-pii-leak
    keywords: ["ssn", "social security", "date of birth"]
    severity: critical
    action: block
    description: Prevent PII from appearing in agent output
```

**Code:**

```python
from acgs_lite import ConstitutionBuilder, Severity

constitution = (
    ConstitutionBuilder()
    .add_rule(id="no-pii", keywords=["ssn", "password"], severity=Severity.CRITICAL)
    .add_rule(id="polite", keywords=["stupid", "idiot"], severity=Severity.MEDIUM)
    .build()
)
```

## Govern an Agent

```python
from acgs_lite import Constitution, GovernedAgent

constitution = Constitution.from_yaml("rules.yaml")
agent = GovernedAgent(my_agent, constitution=constitution)
result = agent.run("process this request")
```

!!! warning "Violations raise exceptions"
    `GovernanceEngine.validate()` raises `ConstitutionalViolationError` on violations.
    Catch the exception to inspect details.

## Check the Audit Trail

```python
from acgs_lite import AuditLog
log = AuditLog()
for entry in log.entries:
    print(entry.timestamp, entry.action, entry.result)
```

## Run a Compliance Assessment

```bash
acgs assess --jurisdiction european_union --domain healthcare
acgs report --markdown
```

## Use Built-in Templates

```python
from acgs_lite import Constitution
general = Constitution.from_template("general")
gitlab = Constitution.from_template("gitlab")
merged = Constitution.merge(general, gitlab)
```

!!! tip "Next"
    See [Integrations](integrations.md) for platform-specific setup.
