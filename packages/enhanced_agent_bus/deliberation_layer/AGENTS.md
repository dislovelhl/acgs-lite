# Deliberation Layer

> Scope: `packages/enhanced_agent_bus/deliberation_layer/` — HITL, voting, guards, impact
> scoring, queues, and deliberation workflows.

## Structure

- `hitl_manager.py`: human approval orchestration
- `impact_scorer.py`: impact analysis
- `intent_classifier.py`: intent classification
- `voting_service.py`, `vote_collector.py`, `vote_consumer.py`, `vote_models.py`: voting flow
- `multi_approver.py`: multi-party approval chains
- `opa_guard.py`, `opa_guard_mixin.py`, `opa_guard_models.py`: policy guard layer
- `adaptive_router.py`, `integration.py`: orchestration and integration
- `deliberation_queue.py`, `timeout_checker.py`: queueing and timeout handling
- `workflows/`: workflow definitions

## Where to Look

| Task | Location |
| ---- | -------- |
| Add HITL step | `hitl_manager.py` |
| Change impact logic | `impact_scorer.py` |
| Modify voting behavior | `voting_service.py`, `vote_models.py` |
| Policy-guard flow | `opa_guard.py`, `opa_guard_mixin.py` |
| Queue/timeouts | `deliberation_queue.py`, `timeout_checker.py` |

## Conventions

- Preserve MACI boundaries between proposers and validators.
- Route policy evaluation through the guard layer, not ad hoc direct calls.
- Keep approval/audit flows explicit in decision paths.

## Anti-Patterns

- Do not bypass the voting service with direct backend calls.
- Do not use mocks outside test code.
- Do not allow unbounded deliberation waits.
