# Constitutional Amendment Engine

> Scope: `src/core/enhanced_agent_bus/constitutional/` — 31 files. Constitutional lifecycle: proposals, reviews, activation, rollback.

## STRUCTURE

```
constitutional/
├── proposal_engine.py       # Amendment proposal creation and validation
├── council.py               # Constitutional council evaluation
├── review_api.py            # FastAPI review endpoints (HTTP_403_FORBIDDEN for unauthorized)
├── activation_saga.py       # Distributed activation saga (multi-step, compensating)
├── rollback_engine.py       # Safe rollback of failed amendments
├── diff_engine.py           # Constitutional diff computation
├── version_model.py         # Version metadata (Pydantic)
├── version_history.py       # Immutable version history log
├── amendment_model.py       # Amendment data model
├── hitl_integration.py      # HITL review gates for constitutional changes
├── opa_updater.py           # Push amendments to OPA runtime
├── degradation_detector.py  # Detect governance degradation post-amendment
├── metrics_collector.py     # Amendment pipeline metrics
├── storage.py               # Amendment persistence (abstract)
├── storage/                 # Concrete storage backends
├── storage_infra/           # Storage infrastructure (migrations, schemas)
└── tests/                   # Constitutional amendment tests
```

## WHERE TO LOOK

| Task                         | Location                      |
| ---------------------------- | ----------------------------- |
| Create new amendment type    | `amendment_model.py`          |
| Change proposal validation   | `proposal_engine.py`          |
| Modify review workflow       | `review_api.py`, `council.py` |
| Add rollback safety check    | `rollback_engine.py`          |
| Update OPA policy deployment | `opa_updater.py`              |
| Storage backend changes      | `storage/`, `storage_infra/`  |

## CONVENTIONS

- Constitutional changes follow saga pattern: propose → review → activate → verify.
- `version_history.py` is append-only — **we NEVER rewrite history**.
- All amendments require HITL review via `hitl_integration.py` (no autonomous constitutional changes).
- `degradation_detector.py` runs post-activation to catch regressions.

## ANTI-PATTERNS

- Do not bypass `council.py` for amendment approval — MACI separation requires independent validation.
- Do not modify `storage_infra/` schemas without migration scripts.
- Do not push OPA updates directly — always via `opa_updater.py` with rollback capability.
