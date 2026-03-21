# Constitutional Amendment Engine

> Scope: `packages/enhanced_agent_bus/constitutional/` — constitutional lifecycle, invariants,
> review, activation, rollback, and storage.

## Structure

- `proposal_engine.py`: proposal creation and validation
- `council.py`: review/evaluation logic
- `review_api.py`: review-facing API surface
- `activation_saga.py`: activation workflow
- `rollback_engine.py`: rollback safety path
- `invariants.py`, `invariant_guard.py`: invariant enforcement
- `opa_updater.py`: policy/runtime propagation
- `storage.py`, `storage/`, `storage_infra/`: persistence and storage helpers
- `version_history.py`, `version_model.py`, `amendment_model.py`: core models/history

## Where to Look

| Task | Location |
| ---- | -------- |
| Add amendment fields/types | `amendment_model.py`, `version_model.py` |
| Change proposal validation | `proposal_engine.py` |
| Modify review flow | `council.py`, `review_api.py`, `hitl_integration.py` |
| Activation/rollback behavior | `activation_saga.py`, `rollback_engine.py` |
| Invariant enforcement | `invariants.py`, `invariant_guard.py` |
| Storage/backend work | `storage.py`, `storage/`, `storage_infra/` |

## Conventions

- Constitutional changes go through proposal, review, activation, and verification stages.
- Keep version history append-only.
- Preserve independent review and HITL gates for constitutional changes.

## Anti-Patterns

- Do not bypass council/review paths for amendment approval.
- Do not mutate storage schemas without updating the matching storage layer.
- Do not push runtime policy changes outside the controlled updater/rollback path.
