# MACI — Separation of Powers

MACI (Multi-Agent Constitutional Intelligence) enforces that no agent validates its own output. Every governance action flows through three distinct roles: **Proposer → Validator → Executor**.

## Role Reference

::: acgs_lite.maci.roles.MACIRole

::: acgs_lite.maci.enforcer.MACIEnforcer
    options:
      members:
        - assign_role
        - get_role
        - check
        - check_no_self_validation
        - summary

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
from acgs_lite.maci import MACIEnforcer, MACIRole

enforcer = MACIEnforcer()
enforcer.assign_role(agent_a, MACIRole.PROPOSER)   # Proposes
enforcer.assign_role(agent_b, MACIRole.VALIDATOR)  # Validates
enforcer.assign_role(agent_c, MACIRole.EXECUTOR)   # Executes
```

### Validate separation

```python
# Raises MACIViolationError if the same agent proposes and validates
enforcer.check_no_self_validation(agent_a, agent_b)
```
