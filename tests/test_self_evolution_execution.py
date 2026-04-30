import json
import subprocess
import sys
from pathlib import Path

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.constitution.amendments import AmendmentProtocol, AmendmentStatus, AmendmentType
from acgs_lite.constitution.self_evolution import (
    EvolutionCandidate,
    SelfEvolutionConfig,
    SelfEvolutionEngine,
    SelfEvolutionReport,
)
from acgs_lite.engine.decision_record import GovernanceDecisionRecord


def _candidate(candidate_id: str, amendment_type: AmendmentType, changes: dict) -> EvolutionCandidate:
    return EvolutionCandidate(
        candidate_id=candidate_id,
        amendment_type=amendment_type,
        title=f"candidate {candidate_id}",
        description="test candidate",
        changes=changes,
        fitness=1.0,
        risk="medium",
        support=3,
    )


def test_gate_matrix_safe_overblocking_and_regression_candidates() -> None:
    baseline = Constitution.from_rules(
        [
            Rule(
                id="PII-001",
                text="Block customer pii export",
                severity=Severity.HIGH,
                keywords=["customer", "pii"],
            )
        ],
        name="baseline",
    )
    safe = _candidate(
        "safe",
        AmendmentType.add_rule,
        {
            "rule": {
                "id": "SAFE-001",
                "text": "Block wire transfer without approval",
                "severity": "high",
                "keywords": ["wire", "approval"],
            }
        },
    )
    overblocking = _candidate(
        "overblocking",
        AmendmentType.add_rule,
        {
            "rule": {
                "id": "OVER-001",
                "text": "Block normal activity",
                "severity": "high",
                "keywords": ["normal"],
            }
        },
    )
    regression = _candidate("regression", AmendmentType.remove_rule, {"rule_id": "PII-001"})
    report = SelfEvolutionReport(input_records=3, candidates=(safe, overblocking, regression))
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(min_fitness=0.0, max_blast_radius=0.34, max_weighted_risk=0.34)
    )

    gate_report = engine.gate_candidates(
        report,
        baseline,
        [
            "export customer pii",
            "wire transfer without approval",
            "normal greeting",
            "normal status check",
            "normal documentation update",
        ],
    )

    passed_ids = {result.candidate.candidate_id for result in gate_report.passed}
    failed = {result.candidate.candidate_id: result for result in gate_report.failed}
    assert passed_ids == {"safe"}
    assert "overblocking" in failed
    assert any("blast radius" in reason for reason in failed["overblocking"].reasons)
    assert "regression" in failed
    assert any("regression" in reason for reason in failed["regression"].reasons)


def test_self_evolution_amendment_flow_blocks_proposer_self_vote() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(min_support=1, min_fitness=0.0, max_blast_radius=1.0, max_weighted_risk=1.0)
    )
    records = [
        GovernanceDecisionRecord(
            decision="deny",
            action="export customer pii",
            violations=[{"message": "personal data exposure"}],
            audit_entry_id="audit-1",
        )
    ]
    report = engine.evaluate(records, constitution)
    gate_report = engine.gate_candidates(report, constitution, engine.action_corpus_from_records(records))
    approved_report = gate_report.to_evolution_report(input_records=report.input_records)
    protocol = AmendmentProtocol(quorum=1, approval_threshold=1.0)

    amendment = engine.draft_amendments(
        approved_report,
        protocol,
        proposer_id="self-evolution-proposer",
        open_voting=True,
        gate_report=gate_report,
    )[0]

    assert amendment.status is AmendmentStatus.voting
    with pytest.raises(ValueError, match="MACI violation"):
        protocol.vote(
            amendment.amendment_id,
            voter_id="self-evolution-proposer",
            approve=True,
        )


def test_drafted_amendment_contains_reconstructable_gate_metadata() -> None:
    constitution = Constitution.from_rules([], name="empty")
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(min_support=1, min_fitness=0.0, max_blast_radius=1.0, max_weighted_risk=1.0)
    )
    records = [
        GovernanceDecisionRecord(
            decision="deny",
            action="export customer pii",
            violations=[{"message": "personal data exposure"}],
            audit_entry_id="audit-1",
        )
    ]
    report = engine.evaluate(records, constitution)
    gate_report = engine.gate_candidates(report, constitution, ["export customer pii"])
    approved_report = gate_report.to_evolution_report(input_records=report.input_records)
    protocol = AmendmentProtocol(quorum=1, approval_threshold=1.0)

    amendment = engine.draft_amendments(approved_report, protocol, gate_report=gate_report)[0]

    assert amendment.metadata["candidate_id"] == approved_report.candidates[0].candidate_id
    assert amendment.metadata["gate_result"]["candidate"]["candidate_id"] == amendment.metadata["candidate_id"]
    assert len(amendment.metadata["gate_report_hash"]) == 64
    assert amendment.metadata["evidence"][0]["audit_entry_id"] == "audit-1"


def test_draft_amendments_rejects_failed_candidates_when_gate_report_supplied() -> None:
    baseline = Constitution.from_rules(
        [
            Rule(
                id="PII-001",
                text="Block customer pii export",
                severity=Severity.HIGH,
                keywords=["customer", "pii"],
            )
        ],
        name="baseline",
    )
    safe = _candidate(
        "safe",
        AmendmentType.add_rule,
        {
            "rule": {
                "id": "SAFE-001",
                "text": "Block wire transfer without approval",
                "severity": "high",
                "keywords": ["wire", "approval"],
            }
        },
    )
    regression = _candidate("regression", AmendmentType.remove_rule, {"rule_id": "PII-001"})
    unfiltered_report = SelfEvolutionReport(input_records=2, candidates=(safe, regression))
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(min_fitness=0.0, max_blast_radius=1.0, max_weighted_risk=1.0)
    )
    gate_report = engine.gate_candidates(
        unfiltered_report,
        baseline,
        ["export customer pii", "wire transfer without approval"],
    )

    protocol = AmendmentProtocol(quorum=1, approval_threshold=1.0)
    with pytest.raises(ValueError, match="not approved by the supplied gate_report"):
        engine.draft_amendments(
            unfiltered_report,
            protocol,
            gate_report=gate_report,
        )
    assert len(protocol) == 0


def test_draft_amendments_rejects_stale_gate_report_candidate_payload() -> None:
    baseline = Constitution.from_rules([], name="baseline")
    gated_candidate = _candidate(
        "same-id",
        AmendmentType.add_rule,
        {
            "rule": {
                "id": "SAFE-001",
                "text": "Block wire transfer without approval",
                "severity": "high",
                "keywords": ["wire", "approval"],
            }
        },
    )
    mutated_candidate = _candidate(
        "same-id",
        AmendmentType.add_rule,
        {
            "rule": {
                "id": "MUTATED-001",
                "text": "Block every normal action",
                "severity": "high",
                "keywords": ["normal"],
            }
        },
    )
    engine = SelfEvolutionEngine(
        SelfEvolutionConfig(min_fitness=0.0, max_blast_radius=1.0, max_weighted_risk=1.0)
    )
    gate_report = engine.gate_candidates(
        SelfEvolutionReport(input_records=1, candidates=(gated_candidate,)),
        baseline,
        ["wire transfer without approval"],
    )
    protocol = AmendmentProtocol(quorum=1, approval_threshold=1.0)

    with pytest.raises(ValueError, match="not approved by the supplied gate_report"):
        engine.draft_amendments(
            SelfEvolutionReport(input_records=1, candidates=(mutated_candidate,)),
            protocol,
            gate_report=gate_report,
        )
    assert len(protocol) == 0


def test_build_evolution_corpus_script_outputs_traceable_rows(tmp_path: Path) -> None:
    input_path = tmp_path / "decisions.jsonl"
    output_path = tmp_path / "corpus.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "audit_entry_id": "a1",
                        "decision": "deny",
                        "action": " export   customer pii ",
                        "violations": [{"message": "personal data exposure"}],
                    }
                ),
                json.dumps(
                    {
                        "audit_entry_id": "a2",
                        "decision": "allow",
                        "confidence": 0.4,
                        "action": "normal greeting",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_evolution_corpus.py",
            str(input_path),
            "--output",
            str(output_path),
            "--validate-schema",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert {row["text"] for row in rows} == {
        "export customer pii",
        "personal data exposure",
        "normal greeting",
    }
    assert all(row["source_audit_entry_ids"] for row in rows)
    assert any("low_confidence" in row["labels"] for row in rows)
