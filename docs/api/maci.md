# MACI — Separation of Powers

MACI (Multi-Agent Constitutional Intelligence) enforces that no agent validates its own output. Every governance action flows through three distinct roles: **Proposer → Validator → Executor**.

## Role Reference

::: acgs_lite.maci.roles.Role

::: acgs_lite.maci.roles.MACIConfig

::: acgs_lite.maci.enforcement.MACIEnforcer
    options:
      members:
        - assign_role
        - validate_separation
        - enforce

## Design Constraints

| Constraint | Rule |
|------------|------|
| Self-validation | ❌ Proposer cannot be Validator |
| Self-execution | ❌ Proposer cannot be Executor |
| Role assignment | Must happen before any governance action |
| Constitutional hash | All paths embed `608508a9bd224290` |

## Examples

### Assign roles

```python
from acgs_lite.maci import MACIEnforcer, Role

enforcer = MACIEnforcer()
enforcer.assign_role(agent_a, Role.LEGISLATIVE)   # Proposes
enforcer.assign_role(agent_b, Role.JUDICIAL)       # Validates
enforcer.assign_role(agent_c, Role.EXECUTIVE)      # Executes
```

### Validate separation

```python
# Raises MACIViolationError if same agent holds conflicting roles
enforcer.validate_separation()
```
