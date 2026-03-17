# Deliberation Layer

> Scope: `src/core/enhanced_agent_bus/deliberation_layer/` — 33 files. HITL governance, impact scoring, consensus voting.

## STRUCTURE

```
deliberation_layer/
├── hitl_manager.py          # Human-in-the-loop approval orchestration
├── impact_scorer.py         # Governance action impact analysis
├── intent_classifier.py     # Action intent classification
├── voting_service.py        # Consensus voting coordination
├── vote_collector.py        # Vote aggregation
├── vote_consumer.py         # Async vote processing
├── vote_models.py           # Pydantic models for voting
├── multi_approver.py        # Multi-party approval chains
├── opa_guard.py             # OPA policy guard integration
├── opa_guard_models.py      # Guard Pydantic models
├── opa_guard_mixin.py       # Reusable guard mixin
├── adaptive_router.py       # Dynamic routing by governance context
├── llm_assistant.py         # LLM-assisted deliberation
├── loco_operator_client.py  # LocoOperator external client (NEVER a validator — MACI)
├── audit_signature.py       # Cryptographic audit signing
├── dashboard.py             # Deliberation monitoring
├── deliberation_queue.py    # Async deliberation queue
├── deliberation_mocks.py    # Test mocks for deliberation
├── redis_election_store.py  # Distributed election state (Redis)
├── redis_integration.py     # Redis pub/sub for real-time voting
├── tensorrt_optimizer.py    # TensorRT inference optimization
├── timeout_checker.py       # Deliberation timeout enforcement
├── integration.py           # Cross-module integration wiring
├── interfaces.py            # Abstract interfaces / protocols
├── tests/                   # Deliberation-specific tests
└── workflows/               # Deliberation workflow definitions
```

## WHERE TO LOOK

| Task                     | Location                              |
| ------------------------ | ------------------------------------- |
| Add HITL approval step   | `hitl_manager.py`                     |
| Change impact thresholds | `impact_scorer.py`                    |
| Modify voting logic      | `voting_service.py`, `vote_models.py` |
| Add OPA guard rule       | `opa_guard.py`, `opa_guard_mixin.py`  |
| LLM deliberation prompts | `llm_assistant.py`                    |
| Multi-party approvals    | `multi_approver.py`                   |

## CONVENTIONS

- `loco_operator_client.py` is **NEVER** a validator (MACI role separation).
- All voting operations go through `voting_service.py` — do not bypass with direct Redis calls.
- Impact scores are deterministic for the same input — no random sampling.
- Deliberation timeouts enforced via `timeout_checker.py` — never allow unbounded waits.

## ANTI-PATTERNS

- Do not call OPA directly — use `opa_guard_mixin.py` for consistent policy evaluation.
- Do not skip audit signing in approval paths (`audit_signature.py`).
- Do not use `deliberation_mocks.py` outside of test code.
