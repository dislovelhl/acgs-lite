# Bittensor Grant Application
## Constitutional AI Governance Subnet — ACGS Integration

**Applicant:** ACGS Project  
**Date:** March 2026  
**Grant Type:** Subnet Development  
**Requested Amount:** $150,000 USD equivalent in TAO  
**GitHub:** https://github.com/dislovelhl/acgs  
**Contact:** Honglin Lyu — hello@acgs.ai

---

## 1. Project Overview

### One-Line Summary

A Bittensor subnet where miners provide human deliberation for the ~3% of AI governance decisions that automated systems cannot resolve alone — turning the hard edge of constitutional AI into a decentralized, incentive-aligned market for human wisdom.

### Problem

Constitutional AI governance systems can automate most compliance decisions, but not all. The ACGS engine resolves ~97% of governance decisions autonomously in under one millisecond. The remaining ~3% — value conflicts, ambiguous contexts, irreconcilable stakeholder positions — are escalated by design because no algorithm can substitute for genuine normative judgment.

Today, that escalation goes to a centralized human review queue. This creates:

- **Single point of failure:** one team's values encode the constitution
- **Legitimacy deficit:** synthetically authored constitutions lack democratic credibility
- **Scaling ceiling:** human review doesn't scale with governance volume
- **No incentive alignment:** reviewers are employees, not stakeholders

### Solution

A Bittensor subnet that operationalizes the escalation path. The subnet owner runs ACGS constitutional governance infrastructure; miners resolve the hard 3%; validators ensure quality and legitimacy; TAO emissions reward high-quality human reasoning.

The result: a decentralized, incentive-aligned constitutional court for AI systems.

---

## 2. Team

| Role | Background |
|------|-----------|
| **Subnet Lead / ACGS Engine** | Honglin Lyu — built the ACGS governance engine — constitutional validation, Z3 formal verification, 9-framework compliance (EU AI Act, NIST AI RMF, ISO 42001, GDPR, HIPAA, SOC2, OECD AI Principles, NYC LL144, US Fair Lending), HITL deliberation layer. Contact: hello@acgs.ai |
| **Bittensor Integration** | Andrew (Taehoon) Kim — Bittensor ecosystem developer. LinkedIn: https://www.linkedin.com/in/kimtaeh3/ |

**Existing codebase:** Production-grade Python/Rust system with:
- 560ns P50 latency on the Rust hot path
- 847-scenario benchmark suite (100% compliance rate)
- Full test suite, structured logging, Pydantic models, async-first design
- PyPI package (`pip install acgs`)

---

## 3. Technical Architecture

### Core Components Already Built

The following modules form the subnet's operational core and are **fully implemented**:

| Component | File | Status |
|-----------|------|--------|
| Governance engine | `acgs_lite/engine/core.py` | ✅ Production |
| 7-vector impact scorer | `deliberation_layer/impact_scorer.py` | ✅ Production |
| Adaptive router (3-tier) | `deliberation_layer/adaptive_router.py` | ✅ Production |
| Deliberation queue | `deliberation_layer/deliberation_queue.py` | ✅ Production |
| HITL manager | `deliberation_layer/hitl_manager.py` | ✅ Production |
| Z3 formal verifier | `verification_layer/z3_policy_verifier.py` | ✅ Production |
| MACI enforcer (7-role) | `maci/enforcer.py` | ✅ Production |
| Polis deliberation engine | `governance/polis_engine.py` | ✅ Production |
| Audit log (hash-chained) | `acgs_lite/audit.py` | ✅ Production |
| 9 compliance frameworks | `acgs_lite/compliance/` | ✅ Production |
| Report generator | `acgs_lite/report.py` | ✅ Production |
| ConstitutionBuilder API | `acgs_lite/constitution/templates.py` | ✅ Production |

### What the Grant Funds (New Build)

| Component | Description | Phase |
|-----------|-------------|-------|
| **Bittensor integration layer** | Miner protocol, task broadcast, response collection, TAO reward distribution | Phase 1 |
| **Constitutional hash anchoring** | Write hash + block height to Bittensor chain via extrinsic | Phase 1 |
| **Validator scoring pipeline** | Quality + constitutional compliance scoring for miner outputs | Phase 1 |
| **Deliberative authenticity detection** | Distinguish genuine human reasoning from AI-generated responses | Phase 2 |
| **Audit log on Arweave** | Append-only governance decisions; merkle root anchored on Bittensor chain | Phase 2 |
| **Miner qualification tiers** | Complexity-based task routing; Human Reviewer pool for escalations | Phase 2 |
| **Precedent feedback loop** | Miner judgments → Bayesian weight updates → improved automated decisions | Phase 3 |
| **ZKP compliance proofs** | Noir-based ZK-SNARKs: prove "passed governance" without revealing content | Phase 3 |

### Scoring Architecture

**Layer 1 — Subnet Opportunity Scoring** (validator incentive signal):

| # | Vector | Weight |
|---|--------|--------|
| V1 | Emission yield | 25% |
| V2 | Hardware accessibility | 15% |
| V3 | Competition saturation | 15% |
| V4 | **Constitutional compliance (hard gate)** | 20% |
| V5 | Validator consensus | 10% |
| V6 | Trend momentum | 10% |
| V7 | Stake depth | 5% |

V4 is a non-negotiable gate: if constitutional compliance falls below 0.60, the overall score caps at 40 regardless of other vectors.

**Layer 2 — Per-Decision Governance Scoring** (routing decisions to miners):

| # | Dimension | Weight |
|---|-----------|--------|
| 1 | Safety | 20% |
| 2 | Security | 20% |
| 3 | Privacy | 15% |
| 4 | Fairness | 15% |
| 5 | Reliability | 10% |
| 6 | Transparency | 10% |
| 7 | Efficiency | 10% |

Routing tiers:
- **LOW** (< 0.3): Automated, sub-millisecond, ~97% of decisions
- **MEDIUM** (0.3–0.8): Auto-remediation + 15-min human override window, ~2%
- **HIGH** (≥ 0.8): Blocks until human miner approval, ~1%

### MACI Role Mapping onto Bittensor

The ACGS MACI (Minimal Anti-Collusion Infrastructure) separation-of-powers maps directly to Bittensor's three-party architecture:

| MACI Role | Bittensor Party | Responsibility |
|-----------|----------------|----------------|
| Proposer | Miner | Submits AI output for governance evaluation |
| Quality Validator | Validator | Scores output quality against rubric |
| Constitutional Validator | Validator (independent pipeline) | Checks governance rule compliance |
| Governor | SN Owner | Defines constitution, rubric, weights |
| Executor | SN Owner (gated) | Triggers emission after dual validation |
| Auditor | Validator | Spot-checks historical decisions for drift |
| Human Reviewer | Miner (escalation pool) | Resolves the 3% ambiguous cases |

**Golden rule enforced:** no agent validates its own output. Quality Validator and Constitutional Validator are independent pipelines with no shared state.

---

## 4. Why Bittensor?

### Decentralized Legitimacy

The core criticism of Constitutional AI is the "synthetic constitution problem" — a small developer team writes the rules. A Bittensor subnet distributes interpretive authority worldwide. Miner judgments accumulate as AI governance case law, creating democratic legitimacy that no centralized system can match.

### Incentive Alignment

TAO emissions naturally reward high-quality reasoning. The subnet creates an economic market for human wisdom — miners who provide thoughtful, well-reasoned governance judgments earn more. No equivalent mechanism exists in centralized HITL systems.

### Decentralized Compute

The ACGS verification pipeline (Z3 formal proofs, 7-vector scoring, compliance checking) requires compute. Sourcing this from other Bittensor subnets keeps the entire governance stack decentralized.

### On-Chain Audit Trail

Regulatory environments (EU AI Act, NIST AI RMF, SOC2) increasingly require tamper-proof governance records. Bittensor's chain provides immutable, third-party-controlled audit evidence that no centralized system can credibly offer.

### Novel Subnet Category

This subnet introduces **human reasoning as a service** — a fundamentally different task type from GPU compute. Miners need reasoning ability, not hardware. This broadens the Bittensor participant base to include governance professionals, ethicists, legal scholars, and domain experts.

---

## 5. Revenue Model

| Revenue Stream | Target Customer | Pricing | Time to Revenue |
|----------------|----------------|---------|-----------------|
| AI-Compliant Compute (IaaS) | Corporations, governments | Pay-per-decision or subscription | Near-term |
| Governance Certification | Regulated industries (healthcare, finance, public sector) | Annual fees or per-audit | Medium-term |
| Governance Intelligence | AI labs, researchers | Data licensing or subscription | Long-term |

The governance intelligence stream compounds: every miner resolution adds to an anonymized dataset of real AI governance decisions made by humans. This dataset has no equivalent anywhere — it becomes more valuable as the subnet scales.

---

## 6. Roadmap and Budget

### Phase 1 — Subnet Foundation (Months 1–3) | $50,000

| Milestone | Deliverable |
|-----------|------------|
| M1 | Bittensor integration layer: task broadcast, miner protocol, response collection |
| M2 | Constitutional hash anchoring via Bittensor extrinsic |
| M3 | Validator scoring pipeline: quality + constitutional compliance |
| M4 | Testnet deployment with synthetic governance scenarios |
| M5 | Public documentation and miner onboarding guide |

**Success criteria:** 10+ miners registered on testnet; validator scoring pipeline live; constitutional hash anchored to chain.

### Phase 2 — Production Hardening (Months 4–6) | $50,000

| Milestone | Deliverable |
|-----------|------------|
| M6 | Deliberative authenticity detection (human vs. AI response classifier) |
| M7 | Audit log on Arweave with merkle root anchoring |
| M8 | Miner qualification tiers and Human Reviewer escalation pool |
| M9 | Mainnet launch with real governance decisions |
| M10 | First external client integration (design partner) |

**Success criteria:** Mainnet live; ≥50 active miners; first external governance decisions processed; audit log on Arweave.

### Phase 3 — Compounding Value (Months 7–9) | $50,000

| Milestone | Deliverable |
|-----------|------------|
| M11 | Precedent feedback loop: miner judgments → Bayesian weight updates |
| M12 | ZKP compliance proofs via Noir (prove "passed governance" without revealing content) |
| M13 | Governance intelligence data product (anonymized, aggregated case dataset) |
| M14 | Multi-framework compliance reporting (EU AI Act, NIST, HIPAA, SOC2) |
| M15 | Constitutional amendment workflow (on-chain governance of the governance rules) |

**Success criteria:** Feedback loop measurably improving automated decision accuracy; first ZKP proof generated; governance intelligence dataset available for research licensing.

### Budget Allocation

| Category | Amount | Notes |
|----------|--------|-------|
| Bittensor integration development | $60,000 | Protocol layer, validator pipeline, chain integration |
| Authenticity detection research | $20,000 | Human vs. AI response classifier |
| ZKP implementation (Noir) | $20,000 | Compliance proofs without content disclosure |
| Infrastructure (testnet + mainnet) | $15,000 | Compute, storage, monitoring |
| Documentation and community | $10,000 | Miner onboarding, developer docs |
| Contingency | $25,000 | *(requested as buffer or milestone-unlocked)* |
| **Total** | **$150,000** | |

---

## 7. Open Questions Acknowledged

The following design challenges are open and will be addressed with community input:

1. **Sybil resistance:** How do validators detect AI-generated miner responses at scale?
2. **Deliberation latency:** Finding the right cadence for MEDIUM/HIGH tier escalations.
3. **Constitutional evolution:** Governance of the governance rules — when does miner case law amend the constitution?
4. **Cross-subnet compute:** Mechanics of sourcing ACGS infrastructure compute from other subnets.
5. **MACI implementation detail:** Enforcing Quality Validator ≠ Constitutional Validator at the protocol level.

---

## 8. What Success Looks Like (12 Months)

| Metric | Target |
|--------|--------|
| Active miners | ≥100 |
| Governance decisions processed (mainnet) | ≥10,000 |
| External design partners integrated | ≥3 |
| Constitutional hash anchored to chain | ✅ |
| ZKP compliance proofs live | ✅ |
| Governance intelligence dataset | ≥1,000 labeled cases |
| External revenue (IaaS + certification) | First paying customers |

---

## 9. Why Now

The EU AI Act's August 2026 compliance deadline is the forcing function. Regulated-industry AI teams are actively looking for governance infrastructure today. The ACGS engine is production-ready. The subnet integration is a defined, bounded engineering problem. The window to become the default AI governance infrastructure layer on Bittensor is open — but not indefinitely.

---

## 10. Supporting Materials

| Document | Location |
|----------|----------|
| Subnet Concept (full) | `docs/strategy/06-subnet-concept.md` |
| Technical Accuracy Audit | `docs/strategy/06-subnet-concept-technical-notes.md` |
| Detailed Q&A (scoring, ZKP, MACI mapping) | `docs/strategy/07-subnet-concept-qa-responses.md` |
| Codebase | https://github.com/dislovelhl/acgs |
| PyPI package | `pip install acgs` |
| Benchmark results | `autoresearch/results.tsv` (847 scenarios, 100% compliance rate) |

---

*For questions or to discuss the application, contact: Honglin Lyu — hello@acgs.ai*

*Constitutional Hash (current rule set): `608508a9bd224290`*
