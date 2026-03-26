# OpenEvolve Governance Adapter — Agent Guide

> **Reviewed**: 2026-03-22 | **Constitutional Hash**: `608508a9bd224290`
> **Package**: `enhanced_agent_bus.openevolve_adapter`

Bridges AI evolution systems (OpenEvolve and compatibles) to the ACGS-2
constitutional governance framework.  Enforces MACI separation-of-powers,
risk-tier rollout constraints, and cascading evaluation with early exits.

---

## Structure

```
openevolve_adapter/
├── candidate.py      # EvolutionCandidate contract — the central data type
├── fitness.py        # ConstitutionalFitness — 60/40 weighted scoring
├── evolver.py        # GovernedEvolver — MACI-enforced evolution loop
├── rollout.py        # RolloutController — risk-tier gate and audit trail
├── cascade.py        # CascadeEvaluator — three-stage progressive pipeline
├── integration.py    # EvolutionMessageHandler + wire_into_processor
├── cli.py            # CLI entry point (evaluate / gate / info commands)
├── __init__.py       # Public re-exports
└── tests/
    └── test_openevolve_adapter.py   # 66 tests covering all modules
```

---

## Modules

### `candidate.py` — Data Contract

Every evolution candidate entering the pipeline must carry:

| Field | Type | Constraint |
|-------|------|-----------|
| `candidate_id` | `str` | non-empty |
| `constitutional_hash` | `str` | must equal `608508a9bd224290` |
| `verification_payload` | `VerificationPayload` | produced by external MACI Validator |
| `risk_tier` | `RiskTier` | `low / medium / high / critical` |
| `proposed_rollout_stage` | `RolloutStage` | `canary / shadow / partial / full` |
| `mutation_trace` | `list[MutationRecord]` | ancestry of mutations |

`__post_init__` enforces three hard invariants:

1. Constitutional hash matches `608508a9bd224290`.
2. `verification_payload.constitutional_hash` matches the outer candidate's hash.
3. `proposed_rollout_stage` is permitted for the given `risk_tier`.

```python
# Fails at construction — not silently at evaluation time
EvolutionCandidate(..., risk_tier=RiskTier.CRITICAL, proposed_rollout_stage=RolloutStage.FULL)
# → ValueError: RiskTier.CRITICAL does not allow RolloutStage.FULL
```

### `fitness.py` — Constitutional Fitness

```
fitness = (0.6 × performance_score + 0.4 × compliance_score) × risk_multiplier
```

Risk multipliers: `LOW=1.0`, `MEDIUM=0.9`, `HIGH=0.75`, `CRITICAL=0.5`.

Compliance is derived from `VerificationPayload`:
`compliance = 0.333×syntax_valid + 0.333×policy_compliant + 0.334×safety_score`

### `evolver.py` — GovernedEvolver (MACI)

- Accepts a `ConstitutionalVerifier` via **constructor injection** — never self-creates it.
- Re-verifies on every `evolve()` call (fresh payload, not cached).
- Rejects if: verifier raises, payload fails compliance, fitness below threshold.
- `evolve_batch()` returns results sorted: approved first, then by descending fitness.

```python
# ✓ correct — verifier injected
evolver = GovernedEvolver(verifier=my_external_validator)

# ✗ wrong — never do this inside GovernedEvolver
self._verifier = MyVerifier()  # MACI violation
```

### `rollout.py` — RolloutController

Enforces tier constraints **and** records every decision in an immutable audit trail.

| Risk Tier | Allowed Stages | Min Canary | Human Approval |
|-----------|---------------|------------|----------------|
| LOW | all | 1 h | no |
| MEDIUM | all (shadow required) | 1 h | no |
| HIGH | canary, shadow | 24 h | **yes** |
| CRITICAL | canary, shadow, partial | 72 h | **yes** |

The controller **decides** — it never executes.  Execution belongs to the Executor role (MACI).

### `cascade.py` — CascadeEvaluator

Three-stage progressive pipeline.  Candidates that fail early are discarded without running expensive stages (~10× compute savings).

```
Stage 1: Syntax    (<1 ms)   — structural validity, no I/O
         threshold: structural (any failure = fatal)

Stage 2: Quick     (~1 ms)   — lightweight 50/50 blend, no external calls
         threshold: configurable (default 0.3)

Stage 3: Full      (~100 ms) — re-verify + ConstitutionalFitness
         threshold: configurable (default 0.5)
```

`CascadeResult.exit_stage` tells you where a candidate stopped.

### `integration.py` — MessageProcessor Wire-Up

`EvolutionMessageHandler` is a drop-in handler for `MessageType.GOVERNANCE_REQUEST`.

- Messages without `metadata["evolution_candidate"] = True` are **skipped** (pass-through).
- On match: deserialises candidate → cascade → rollout gate → `ValidationResult`.
- Returns structured `metadata` understood by the existing bus infrastructure.

```python
from enhanced_agent_bus.openevolve_adapter import EvolutionMessageHandler, wire_into_processor

handler = EvolutionMessageHandler(verifier=my_verifier)
wire_into_processor(processor, handler)
```

**Message payload contract** (`AgentMessage.metadata`):

```json
{
  "evolution_candidate": true,
  "candidate_id": "cand-abc123",
  "constitutional_hash": "608508a9bd224290",
  "risk_tier": "low",
  "proposed_rollout_stage": "canary",
  "performance_score": 0.85,
  "verification_payload": {
    "validator_id": "validator-001",
    "verified_at": "2026-03-22T10:00:00+00:00",
    "constitutional_hash": "608508a9bd224290",
    "syntax_valid": true,
    "policy_compliant": true,
    "safety_score": 0.92,
    "notes": ""
  },
  "mutation_trace": [
    { "operator": "crossover", "parent_id": "p-0", "description": "blend parents" }
  ],
  "fitness_inputs": { "metric": 0.85 }
}
```

### `cli.py` — Command-Line Interface

```bash
# Cascade evaluate a candidate JSON file
python -m enhanced_agent_bus.openevolve_adapter.cli evaluate candidate.json \
  --performance-score 0.85 --gate --json

# Rollout gate only
python -m enhanced_agent_bus.openevolve_adapter.cli gate candidate.json

# Print version / hash
python -m enhanced_agent_bus.openevolve_adapter.cli info
```

Exit codes: `0` = passed/allowed, `1` = error, `2` = rejected/denied.

---

## MACI Roles

| Role | Responsibility in this adapter |
|------|-------------------------------|
| **Proposer** | `GovernedEvolver` — scores candidates, proposes rollout |
| **Validator** | Injected `ConstitutionalVerifier` — independent, never self-created |
| **Executor** | **Not in this adapter** — execution is downstream, outside this boundary |

**Golden Rule**: `GovernedEvolver` never constructs its own verifier.

---

## Where to Look

| Task | Module |
|------|--------|
| Change rollout stage constraints | `rollout.py` → `_TIER_CONSTRAINTS` |
| Adjust fitness weights | `fitness.py` → `PERFORMANCE_WEIGHT`, `COMPLIANCE_WEIGHT` |
| Tune cascade thresholds | `cascade.py` → `CascadeEvaluator.__init__` defaults |
| Add a new message handler | `integration.py` → `EvolutionMessageHandler.__call__` |
| Add a CLI command | `cli.py` → `_make_parser`, `main` |

---

## Testing

```bash
python -m pytest packages/enhanced_agent_bus/openevolve_adapter/tests/ \
  --import-mode=importlib -q
```

66 tests covering all modules. No external services required — all verifiers
are protocol stubs.

---

## Anti-Patterns (Forbidden)

| Pattern | Why | Fix |
|---------|-----|-----|
| `GovernedEvolver(verifier=self._build_verifier())` | MACI self-validation | Inject from outside |
| Skipping `EvolutionCandidate.__post_init__` | Bypasses hash + tier guards | Never use `object.__setattr__` to avoid it |
| Using `_StubVerifier` in production | Echoes candidate's own payload back | Always inject a real validator service |
| `RolloutController.gate()` result ignored | Unenforced gate = no governance | Check `decision.allowed` before executing |

Constitutional Hash: `608508a9bd224290`
