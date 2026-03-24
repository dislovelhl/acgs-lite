# OPA Client

> Scope: `packages/enhanced_agent_bus/opa_client/` — OPA access, cache, and health handling.

## Structure

- `core.py`: core OPA client logic
- `cache.py`: response caching
- `health.py`: OPA health/readiness checks

## Where to Look

| Task | Location |
| ---- | -------- |
| Policy evaluation | `core.py` |
| Cache tuning | `cache.py` |
| Health checks | `health.py` |

## Conventions

- Preserve fail-closed behavior on policy evaluation failures.
- Keep caching bounded to valid policy-response windows.

## Anti-Patterns

- Do not fail open on OPA errors.
- Do not call OPA ad hoc from callers when a shared client path exists.
