from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution.amendments import AmendmentProtocol, AmendmentStatus, AmendmentType
from acgs_lite.constitution.self_evolution import SelfEvolutionConfig, SelfEvolutionEngine
from acgs_lite.engine.decision_record import GovernanceDecisionRecord, TriggeredRule


def test_self_evolution_generates_uncovered_denial_rule_candidate() -> None:
    constitution = Constitution.from_rules([], name="empty")
    records = [
        GovernanceDecisionRecord(
            decision="deny",
            action="export customer pii to public bucket",
            violations=[{"message": "public bucket personal data exposure"}],
            audit_entry_id="a1",
        ),
        GovernanceDecisionRecord(
            decision="deny",
            action="export customer pii to public bucket",
            violations=[{"message": "public bucket personal data exposure"}],
            audit_entry_id="a2",
        ),
    ]

    report = SelfEvolutionEngine(SelfEvolutionConfig(min_support=2)).evaluate(records, constitution)

    assert report.input_records == 2
    assert len(report.candidates) == 1
    candidate = report.candidates[0]
    assert candidate.amendment_type is AmendmentType.add_rule
    assert candidate.support == 2
    assert candidate.changes["rule"]["category"] == "self-evolution"
    assert "pii" in candidate.changes["rule"]["keywords"]
    assert constitution.rules == []


def test_self_evolution_drafts_and_opens_formal_amendment() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(SelfEvolutionConfig(min_support=1, min_fitness=0.0))
    report = engine.evaluate(
        [
            {
                "decision": "allow",
                "confidence": 0.2,
                "action": "transfer funds without normal approval context",
                "audit_entry_id": "a3",
            }
        ],
        constitution,
    )
    protocol = AmendmentProtocol(quorum=1, approval_threshold=1.0)

    amendments = engine.draft_amendments(report, protocol, proposer_id="policy-proposer", open_voting=True)

    assert len(amendments) == 1
    amendment = amendments[0]
    assert amendment.status is AmendmentStatus.voting
    assert amendment.proposer_id == "policy-proposer"
    assert amendment.metadata["source"] == "self_evolution"
    assert amendment.metadata["candidate_id"] == report.candidates[0].candidate_id


def test_self_evolution_tunes_hot_rule_without_mutating_constitution() -> None:
    rule = Rule(
        id="RISK-001",
        text="Warn on unusual risk",
        severity=Severity.MEDIUM,
        keywords=["risk"],
        priority=3,
    )
    constitution = Constitution.from_rules([rule], name="base")
    records = [
        GovernanceDecisionRecord(
            decision="deny",
            triggered_rules=[TriggeredRule(id="RISK-001")],
            action="unusual risk operation",
        ),
        GovernanceDecisionRecord(
            decision="deny",
            triggered_rules=[TriggeredRule(id="RISK-001")],
            action="unusual risk operation",
        ),
    ]

    report = SelfEvolutionEngine(SelfEvolutionConfig(min_support=2, min_fitness=0.0)).evaluate(
        records, constitution
    )

    hot_rule_candidates = [c for c in report.candidates if c.changes.get("rule_id") == "RISK-001"]
    assert len(hot_rule_candidates) == 1
    candidate = hot_rule_candidates[0]
    assert candidate.changes["priority"] == 5
    assert candidate.changes["severity"] == "high"
    assert constitution.rules[0].priority == 3
    assert constitution.rules[0].severity is Severity.MEDIUM
