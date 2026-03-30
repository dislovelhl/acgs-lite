# TODOS

Deferred work from /autoplan review (2026-03-30). Items gated on testnet validation results.

## P1 — Blocked on testnet results

### Miner acquisition strategy
**What:** Define how to bootstrap first 50 miners on testnet. TAO yield comparison, onboarding docs, community outreach.
**Why:** Both CEO reviewers flagged: no miners = no subnet. Bittensor miners are GPU operators, not governance deliberators.
**Gate:** Before mainnet. Testnet gives signal on organic vs. recruited participation.
**Effort:** M (human) / S (CC)

### ~~bt.Synapse adapter layer~~ DONE (2026-03-30)
**What:** ~~Replace frozen dataclass synapse mocks with real `bittensor.Synapse` wrappers.~~
**Delivered:** `synapse_adapter.py` (GovernanceDeliberation + conversions), `axon_server.py` (MinerAxonServer), `dendrite_client.py` (ValidatorDendriteClient). 24 tests. testnet_deploy.py rewired to use adapter. Falls back to Pydantic BaseModel when bittensor not installed.

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

## P2 — From /autoplan cookbook review (2026-03-30)

### Generic semantic-guardrail adapter (was: openai-guardrails adapter)
**What:** Create `acgs_lite.integrations.semantic_guardrails` — a generic adapter interface that wraps any provider's LLM-based guardrails (OpenAI, Anthropic, custom) with ACGS constitutional governance on top.
**Why:** Codex CEO review flagged that a named `openai-guardrails` adapter contradicts the vendor-neutral premise. Design as provider-agnostic interface with pluggable backends.
**Gate:** After Priority 1 (per-rule eval harness) ships and validates the engine's rule accuracy.
**Effort:** M (human) / S (CC)
**Depends on:** Per-rule eval harness (Priority 1)

### Red-team CI pipeline (expanded scope)
**What:** Adversarial testing targeting the ACGS governance engine via Promptfoo + custom abuse-case corpus. Must cover paraphrase bypass, multi-turn agent abuse, tool-call escalation, memory poisoning, and policy ambiguity — not just single-turn keyword bypass.
**Why:** Codex CEO + Eng both flagged: Promptfoo alone covers only one abuse surface. Real-world abuse is multi-dimensional.
**Gate:** After eval harness identifies weakest rules (target red-teaming at those rules first).
**Effort:** L (human) / M (CC)
**Depends on:** Per-rule eval harness (Priority 1)

### ZDR observability mode (needs compliance design)
**What:** Zero Data Retention tracing mode for enhanced_agent_bus. Codex CEO flagged: egress constraint alone ≠ compliance. Needs encryption, access control, deletion semantics, tenant isolation, and deployment story.
**Why:** Financial services / healthcare deployments need observability without data leaving the trust boundary.
**Gate:** First enterprise customer expressing this need, or compliance certification initiative.
**Effort:** XL (human) / L (CC) — research + design before implementation
**Depends on:** Compliance certification strategy (P3)

### Reference app / demo
**What:** A polished reference application showing ACGS wrapping an AI agent (e.g., OpenAI agent) with constitutional governance. Shows the full stack: GovernedAgent → constitutional rules → audit trail → compliance report.
**Why:** Codex CEO argued "a polished reference app beats a governance diagram for devtool adoption." For distribution and adoption, showing beats telling.
**Gate:** Strategic decision on go-to-market approach.
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

### ~~Throughput model~~ DONE (2026-03-30)
**What:** ~~Size on-chain write rate at target customer volumes.~~
**Delivered:** `docs/strategy/10-throughput-model.md`. Chain is not the bottleneck at any volume (100K/day uses <1% of block capacity). Real bottleneck is miner supply. Batch size 100 confirmed correct for testnet.

## ClinicalGuard Hackathon — Deferred Items

### Post-hackathon if wins
**RxNorm/DrugBank integration**: Real drug interaction database via API. Requires agreements. Significant trust improvement for real deployment.
**Multi-tenant audit isolation**: Per-customer audit log scoping. Required for any real healthcare deployment.
**Constitutional amendment UI**: Web UI for clinical experts to propose and vote on new rules. Uses existing amendment engine.
**Streaming A2A responses**: Real-time validation progress for slow LLM calls.

### Out of scope (explicit decision 2026-03-30)
- Bittensor subnet integration (different product line)
- EU AI Act compliance module for ClinicalGuard (overkill for hackathon)
