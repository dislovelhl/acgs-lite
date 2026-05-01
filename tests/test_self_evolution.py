from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution.amendments import AmendmentProtocol, AmendmentStatus, AmendmentType
from acgs_lite.constitution.self_evolution import (
    EvolutionCandidate,
    SelfEvolutionConfig,
    SelfEvolutionEngine,
    SelfEvolutionReport,
)
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

    amendments = engine.draft_amendments(
        report, protocol, proposer_id="policy-proposer", open_voting=True
    )

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


def test_self_evolution_gate_rejects_empty_action_corpus() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(SelfEvolutionConfig(min_support=1, min_fitness=0.0))
    report = engine.evaluate(
        [
            GovernanceDecisionRecord(
                decision="deny",
                action="export customer pii to public bucket",
                violations=[{"message": "public bucket personal data exposure"}],
            )
        ],
        constitution,
    )

    gate_report = engine.gate_candidates(report, constitution, [])

    assert gate_report.evaluated == 1
    assert gate_report.approved_candidates == ()
    assert gate_report.failed[0].reasons == ("empty action corpus",)


def test_self_evolution_gate_blocks_excessive_blast_radius_before_amendment() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(
            min_support=1,
            min_fitness=0.0,
            max_blast_radius=0.40,
            max_weighted_risk=1.0,
        )
    )
    report = engine.evaluate(
        [
            GovernanceDecisionRecord(
                decision="deny",
                action="export customer pii to public bucket",
                violations=[{"message": "public bucket personal data exposure"}],
            )
        ],
        constitution,
    )

    gate_report = engine.gate_candidates(
        report,
        constitution,
        ["export customer pii to public bucket", "normal greeting"],
    )

    assert gate_report.evaluated == 1
    assert len(gate_report.failed) == 1
    assert gate_report.failed[0].recommendation == "no-go"
    assert gate_report.failed[0].blast_radius == 0.5
    assert "blast radius" in gate_report.failed[0].reasons[0]


def test_self_evolution_gate_approves_bounded_candidate() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(
            min_support=1,
            min_fitness=0.0,
            max_blast_radius=0.75,
            max_weighted_risk=1.0,
        )
    )
    report = engine.evaluate(
        [
            GovernanceDecisionRecord(
                decision="deny",
                action="export customer pii to public bucket",
                violations=[{"message": "public bucket personal data exposure"}],
            )
        ],
        constitution,
    )

    gate_report = engine.gate_candidates(
        report,
        constitution,
        ["export customer pii to public bucket", "normal greeting"],
    )

    assert len(gate_report.passed) == 1
    assert gate_report.approved_candidates == (report.candidates[0],)
    assert gate_report.passed[0].recommendation == "review"


def test_action_corpus_from_records_deduplicates_actions_and_evidence() -> None:
    engine = SelfEvolutionEngine()
    records = [
        GovernanceDecisionRecord(
            decision="deny",
            action=" export   customer pii ",
            violations=[{"message": "public bucket personal data exposure"}],
        ),
        {
            "decision": "deny",
            "action": "export customer pii",
            "violations": ["public bucket personal data exposure", {"reason": "missing consent"}],
        },
    ]

    corpus = engine.action_corpus_from_records(records)

    assert corpus == (
        "export customer pii",
        "public bucket personal data exposure",
        "missing consent",
    )


def test_gate_candidates_fails_closed_for_invalid_candidate() -> None:
    constitution = Constitution.from_rules([], name="empty")
    candidate = EvolutionCandidate(
        candidate_id="bad",
        amendment_type=AmendmentType.add_rule,
        title="Invalid generated rule",
        description="Missing required rule text should fail before amendment drafting.",
        changes={"rule": {"id": "BAD-001"}},
        fitness=1.0,
        risk="high",
        support=1,
    )
    report = SelfEvolutionReport(input_records=1, candidates=(candidate,))

    gate_report = SelfEvolutionEngine(SelfEvolutionConfig(min_fitness=0.0)).gate_candidates(
        report, constitution, ["anything"]
    )

    assert gate_report.approved_candidates == ()
    assert gate_report.failed[0].recommendation == "no-go"
    assert "candidate simulation failed" in gate_report.failed[0].reasons[0]


def test_gate_report_to_evolution_report_keeps_only_approved_candidates() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(
            min_support=1, min_fitness=0.0, max_blast_radius=1.0, max_weighted_risk=1.0
        )
    )
    report = engine.evaluate(
        [
            GovernanceDecisionRecord(
                decision="deny",
                action="export customer pii",
                violations=[{"message": "personal data exposure"}],
            )
        ],
        constitution,
    )
    gate_report = engine.gate_candidates(report, constitution, ["export customer pii"])

    approved_report = gate_report.to_evolution_report(
        input_records=report.input_records, skipped=report.skipped
    )

    assert approved_report.input_records == 1
    assert approved_report.candidates == gate_report.approved_candidates
