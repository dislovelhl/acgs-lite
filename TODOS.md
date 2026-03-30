# TODOS

Deferred work from /autoplan review (2026-03-30). Items gated on testnet validation results.

## P1 — Blocked on testnet results

### Miner acquisition strategy
**What:** Define how to bootstrap first 50 miners on testnet. TAO yield comparison, onboarding docs, community outreach.
**Why:** Both CEO reviewers flagged: no miners = no subnet. Bittensor miners are GPU operators, not governance deliberators.
**Gate:** Before mainnet. Testnet gives signal on organic vs. recruited participation.
**Effort:** M (human) / S (CC)

### bt.Synapse adapter layer
**What:** Replace frozen dataclass synapse mocks with real `bittensor.Synapse` wrappers. Integrate with `bt.axon`, `bt.dendrite`, `bt.metagraph`.
**Why:** Current code validates logic but doesn't talk real Bittensor protocol. testnet_deploy.py bridges this but needs hardening.
**Gate:** Before testnet launch. Requires `pip install bittensor>=7.0.0`.
**Effort:** M (human) / S (CC)

## P2 — Blocked on research

### Authenticity detection (unsolved)
**What:** Replace regex-based `AuthenticityDetector` with something not trivially gameable by LLMs.
**Why:** 4/4 reviewers flagged as security theater. Current heuristics (word count, hedging, bullet-list detection) are defeated by one prompt iteration.
**Candidates:** Interactive probing (follow-up questions), behavioral fingerprinting, or accept AI-assisted deliberation and design incentives around quality rather than humanness.
**Gate:** Research breakthrough. Do not ship on mainnet without solving this.
**Effort:** XL (human) / L (CC) — this is a research problem, not an engineering one.

### Precedent poisoning safeguards
**What:** External gold set, appeals process, held-out evaluation to distinguish "agreed on" from "correct" in the precedent feedback loop.
**Why:** Both eng reviewers flagged: learning from unverified miners before anti-gaming exists risks locking in consensus-shaped mistakes.
**Gate:** After authenticity detection is solved.
**Effort:** L (human) / M (CC)

## P2 — Blocked on testnet validation

### On-chain anchoring (Phase 2)
**What:** ChainAnchor for batch Merkle proof submission to Bittensor chain. ZKP compliance certificates. NMC multi-miner deliberation.
**Why:** Enterprise selling point, but enterprise buyers need to trust the network first.
**Gate:** Testnet demonstrates quality signal and miner participation.
**Effort:** XL (human) / L (CC)

### Manifold trust preservation on pool change
**What:** Implement manifold resize that preserves existing trust when miners join/leave, instead of rebuilding from scratch.
**Why:** Current `_rebuild_manifold()` discards all accumulated trust on any pool change. At scale, trust signal never accumulates.
**Gate:** After testnet pool stabilizes (> 10 miners for > 1 week).
**Effort:** M (human) / S (CC)

### Constitution rollout protocol
**What:** Staged rollout with dual-hash acceptance window (grace window implemented), epoch-aware version pinning, and split-brain detection.
**Why:** Hard-reject on hash mismatch causes mass rejection during rollover. Grace window is a band-aid.
**Gate:** After testnet runs multiple constitution rotations.
**Effort:** M (human) / S (CC)

## P3 — Nice to have

### Centralized SaaS alternative track
**What:** REST API governance service with optional Bittensor backend. Decouple governance engine from distribution.
**Why:** Both CEO reviewers recommended this as the faster path to revenue. Enterprise buyers want SLAs, not subnets.
**Gate:** Strategic decision after testnet results.
**Effort:** XL (human) / L (CC)

### TurboQuant vLLM integration
**What:** Triton kernel path via `pip install turboquant` for real 8x attention speedup. Blocked on vllm-project/vllm#38280.
**Why:** Pure Python baseline achieves 0.93 cosine fidelity at 4-bit. Triton achieves >0.99.
**Gate:** vLLM PR merged.
**Effort:** M (human) / S (CC)

### Compliance framework maintenance
**What:** Ongoing updates to 9 pre-built compliance frameworks (EU AI Act, NIST, HIPAA, etc.) as regulations evolve.
**Why:** Codex CEO voice flagged: frameworks become stale without a maintenance cadence.
**Gate:** After first enterprise customer.
**Effort:** Ongoing, S per framework per quarter.

### Throughput model
**What:** Size on-chain write rate at target customer volumes (1K, 10K, 100K decisions/day). Confirm Bittensor chain can handle it.
**Why:** CEO review flagged: on-chain/off-chain split not sized against real workload.
**Gate:** Before Phase 2.
**Effort:** S (human) / S (CC)
