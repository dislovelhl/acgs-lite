# MACI Enforcement

> Scope: `packages/enhanced_agent_bus/maci/` — role enforcement, registry, validation strategy,
> and supporting models.

## Structure

- `enforcer.py`: core MACI enforcement
- `models.py`: roles and supporting data models
- `registry.py`: agent-to-role mapping
- `config_loader.py`: configuration loading
- `role_matrix_validator.py`: matrix/permission validation
- `strategy.py`: enforcement strategy helpers
- `utils.py`: supporting utilities

## Where to Look

| Task | Location |
| ---- | -------- |
| Change role enforcement | `enforcer.py` |
| Update role/model definitions | `models.py` |
| Registry behavior | `registry.py` |
| Config loading | `config_loader.py` |
| Matrix validation | `role_matrix_validator.py` |

## Conventions

- Preserve the core rule: proposers do not validate their own output.
- Keep role/permission changes explicit and reviewable.
- Log or surface enforcement outcomes consistently with the surrounding governance flow.

## Anti-Patterns

- Do not bypass the enforcer for approval decisions.
- Do not introduce overlapping proposer/validator semantics without explicit review.
