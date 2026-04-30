# Governed Self-Evolution

ACGS-Lite self-evolution is a closed-loop policy improvement workflow. It analyzes runtime decision feedback, proposes constitutional changes, simulates their blast radius, and submits approved candidates into the existing amendment protocol. It does **not** let an agent rewrite or enforce its own validation logic.

## Why this exists

Production governance systems drift: new risk patterns appear, rules fire too often or too late, and low-confidence allow decisions accumulate. Self-evolution converts those signals into auditable improvement proposals while preserving deterministic enforcement and MACI separation of powers.

## Safety model

The self-evolution loop follows five gates:

1. **Observe** decision records, violations, confidence, triggered rules, and audit IDs.
2. **Propose** scored `EvolutionCandidate` objects. Candidates are plain data, not mutations.
3. **Simulate** candidates against an action corpus with `SelfEvolutionEngine.gate_candidates()`.
4. **Amend** only passing candidates through `AmendmentProtocol` voting and ratification.
5. **Roll out** through the normal lifecycle/bundle controls, where operators can stage, monitor, and roll back.

```mermaid
graph TD
    A[GovernanceDecisionRecord stream] --> B[SelfEvolutionEngine.evaluate]
    B --> C[Scored EvolutionCandidate list]
    C --> D[Simulation gate / blast radius / regression checks]
    D -- no-go --> E[Rejected with reasons]
    D -- go or review --> F[AmendmentProtocol draft]
    F --> G[MACI voting]
    G --> H[Executor ratify/enforce]
    H --> I[Lifecycle rollout / audit / rollback]
```

## Current candidate types

`SelfEvolutionEngine` currently detects:

- **Uncovered denials**: denied decisions with violation evidence but no active rule hit. Output: `add_rule` candidate.
- **Hot rules**: frequently triggered deny rules. Output: `modify_rule` candidate that increases priority and may escalate non-blocking severity to `high`.
- **Low-confidence allows**: repeated allowed decisions below the configured confidence threshold. Output: `add_rule` candidate requiring human review.

## Pre-amendment simulation gate

`gate_candidates(report, constitution, action_corpus)` rejects candidates before the amendment workflow if:

- the action corpus is empty,
- deny-to-allow regressions are introduced and `allow_regressions=False`,
- blast radius exceeds `SelfEvolutionConfig.max_blast_radius`, or
- weighted transition risk exceeds `SelfEvolutionConfig.max_weighted_risk`.

This aligns with AI governance/MLOps release discipline: observe continuously, evaluate offline, gate risky changes, preserve approval trails, and roll out with rollback support.

## Minimal usage

```python
from acgs_lite.constitution import Constitution, SelfEvolutionConfig, SelfEvolutionEngine
from acgs_lite.constitution.amendments import AmendmentProtocol

constitution = Constitution.default()
engine = SelfEvolutionEngine(SelfEvolutionConfig(min_support=3))

report = engine.evaluate(decision_records, constitution)
gate_report = engine.gate_candidates(
    report,
    constitution,
    action_corpus=[record.action for record in decision_records if record.action],
)

approved_report = type(report)(
    input_records=report.input_records,
    candidates=gate_report.approved_candidates,
    skipped=report.skipped,
)

protocol = AmendmentProtocol(quorum=2, approval_threshold=0.66)
amendments = engine.draft_amendments(
    approved_report,
    protocol,
    proposer_id="policy-proposer",
    open_voting=True,
)
```

## Recommended operating controls

- Keep `min_support` above 1 in production to avoid one-off noise.
- Use a representative regression corpus: recent allowed actions, denied actions, canary incidents, and known compliance fixtures.
- Treat `review` recommendations as human-review-required, not auto-merge.
- Keep `allow_regressions=False` for safety-critical deployments.
- Store `EvolutionGateReport.to_dict()` alongside amendment metadata for auditability.
- Pair accepted amendments with lifecycle rollout stages and rollback plans.
