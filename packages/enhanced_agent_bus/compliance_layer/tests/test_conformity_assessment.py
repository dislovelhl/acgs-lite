from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

"""Tests for Conformity Assessment automation."""

import json
from datetime import UTC, datetime, timedelta, timezone

from enhanced_agent_bus.compliance_layer.conformity_assessment import (
    AssessmentStatus,
    ComplianceEvidence,
    ConformityAssessment,
    ConformityRequirement,
    ContinuousComplianceMonitor,
    EvidenceType,
)


class TestComplianceEvidence:
    def test_compute_hash_returns_sha256(self) -> None:
        evidence = ComplianceEvidence(content={"action": "test"})
        hash_result = evidence.compute_hash()
        assert len(hash_result) == 64
        assert evidence.content_hash == hash_result

    def test_compute_hash_deterministic(self) -> None:
        evidence1 = ComplianceEvidence(content={"key": "value"})
        evidence2 = ComplianceEvidence(content={"key": "value"})
        assert evidence1.compute_hash() == evidence2.compute_hash()

    def test_evidence_default_values(self) -> None:
        evidence = ComplianceEvidence()
        assert evidence.evidence_type == EvidenceType.AUDIT_LOG
        assert evidence.is_valid is True
        assert evidence.source == ""


class TestConformityRequirement:
    def test_requirement_default_status(self) -> None:
        req = ConformityRequirement(article="Article 9", description="Risk Management")
        assert req.status == AssessmentStatus.PENDING
        assert req.mandatory is True

    def test_requirement_with_evidence_types(self) -> None:
        req = ConformityRequirement(
            article="Article 15",
            description="Accuracy",
            evidence_types=[EvidenceType.TEST_RESULT, EvidenceType.Z3_PROOF],
        )
        assert len(req.evidence_types) == 2


class TestConformityAssessment:
    def test_initialization(self) -> None:
        assessment = ConformityAssessment("test-system")
        assert assessment.system_id == "test-system"
        assert len(assessment.requirements) == 6

    def test_initialization_with_date(self) -> None:
        date = datetime(2025, 1, 1, tzinfo=UTC)
        assessment = ConformityAssessment("test-system", assessment_date=date)
        assert assessment.assessment_date == date

    def test_constitutional_hash_present(self) -> None:
        assessment = ConformityAssessment("test-system")
        assert assessment.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_requirements_initialized(self) -> None:
        assessment = ConformityAssessment("test-system")
        articles = [r.article for r in assessment.requirements]
        assert "Article 9" in articles
        assert "Article 13" in articles
        assert "Article 15" in articles

    def test_collect_evidence_from_audit_logs(self) -> None:
        assessment = ConformityAssessment("test-system")
        logs = [
            {"action": "risk_assessment", "timestamp": datetime.now(UTC).isoformat()},
            {
                "action": "human_oversight_check",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {"action": "transparency_update", "timestamp": datetime.now(UTC).isoformat()},
        ]
        evidence = assessment.collect_evidence_from_audit_logs(logs)
        assert len(evidence) == 3
        assert all(e.content_hash for e in evidence)

    def test_collect_evidence_filters_by_date(self) -> None:
        assessment = ConformityAssessment("test-system")
        old_date = (datetime.now(UTC) - timedelta(days=500)).isoformat()
        logs = [
            {"action": "test", "timestamp": old_date},
        ]
        evidence = assessment.collect_evidence_from_audit_logs(logs)
        assert len(evidence) == 0

    def test_map_log_to_article_risk(self) -> None:
        assessment = ConformityAssessment("test-system")
        result = assessment._map_log_to_article({"action": "risk_evaluation"})
        assert result == "Article 9"

    def test_map_log_to_article_transparency(self) -> None:
        assessment = ConformityAssessment("test-system")
        result = assessment._map_log_to_article({"action": "transparency_report"})
        assert result == "Article 13"

    def test_map_log_to_article_human_oversight(self) -> None:
        assessment = ConformityAssessment("test-system")
        result = assessment._map_log_to_article({"action": "human_oversight_triggered"})
        assert result == "Article 14"

    def test_map_log_to_article_default(self) -> None:
        assessment = ConformityAssessment("test-system")
        result = assessment._map_log_to_article({"action": "unknown_action"})
        assert result == "Article 17"

    def test_integrate_z3_proof(self) -> None:
        assessment = ConformityAssessment("test-system")
        z3_result = {
            "satisfiable": True,
            "proof_hash": "abc123",
            "invariants": ["safety", "fairness"],
        }
        evidence = assessment.integrate_z3_proof("test_policy", z3_result)
        assert evidence.evidence_type == EvidenceType.Z3_PROOF
        assert evidence.is_valid is True
        assert evidence.article_reference == "Article 15"

    def test_integrate_z3_proof_invalid(self) -> None:
        assessment = ConformityAssessment("test-system")
        z3_result = {"satisfiable": False}
        evidence = assessment.integrate_z3_proof("failing_policy", z3_result)
        assert evidence.is_valid is False

    def test_assess_requirement_passed(self) -> None:
        assessment = ConformityAssessment("test-system")
        for _ in range(3):
            evidence = ComplianceEvidence(
                evidence_type=EvidenceType.RISK_ASSESSMENT,
                article_reference="Article 9",
                content={"test": "data"},
            )
            evidence.compute_hash()
            assessment.evidence_bank.append(evidence)

        evidence = ComplianceEvidence(
            evidence_type=EvidenceType.AUDIT_LOG,
            article_reference="Article 9",
            content={"test": "data"},
        )
        evidence.compute_hash()
        assessment.evidence_bank.append(evidence)

        req = assessment.requirements[0]
        status = assessment.assess_requirement(req)
        assert status == AssessmentStatus.PASSED

    def test_assess_requirement_missing_evidence(self) -> None:
        assessment = ConformityAssessment("test-system")
        req = assessment.requirements[0]
        status = assessment.assess_requirement(req)
        assert status == AssessmentStatus.REQUIRES_REMEDIATION
        assert len(req.remediation_actions) > 0

    def test_run_full_assessment_no_evidence(self) -> None:
        assessment = ConformityAssessment("test-system")
        status = assessment.run_full_assessment()
        assert status == AssessmentStatus.REQUIRES_REMEDIATION

    def test_generate_markdown_report(self) -> None:
        assessment = ConformityAssessment("test-system")
        assessment.run_full_assessment()
        report = assessment.generate_conformity_report("markdown")
        assert "EU AI Act Conformity Assessment Report" in report
        assert "Article 9" in report
        assert CONSTITUTIONAL_HASH in report

    def test_generate_json_report(self) -> None:
        assessment = ConformityAssessment("test-system")
        assessment.run_full_assessment()
        report = assessment.generate_conformity_report("json")
        data = json.loads(report)
        assert data["system_id"] == "test-system"
        assert "requirements" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_generate_html_report(self) -> None:
        assessment = ConformityAssessment("test-system")
        report = assessment.generate_conformity_report("html")
        assert "<!DOCTYPE html>" in report
        assert "EU AI Act Conformity Assessment Report" in report


class TestContinuousComplianceMonitor:
    def test_initialization(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        assert monitor.system_id == "test-system"
        assert len(monitor.compliance_history) == 0

    def test_check_compliance(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        logs = [{"action": "test", "timestamp": datetime.now(UTC).isoformat()}]
        result = monitor.check_compliance(logs)
        assert "status" in result
        assert "requirements_total" in result
        assert len(monitor.compliance_history) == 1

    def test_check_compliance_creates_alerts(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        result = monitor.check_compliance([])
        assert len(monitor.alerts) > 0

    def test_get_dashboard_data(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        monitor.check_compliance([])
        data = monitor.get_dashboard_data()
        assert data["system_id"] == "test-system"
        assert "overall_health" in data
        assert "last_check" in data

    def test_health_score_calculation(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        monitor.compliance_history = [
            {"requirements_passed": 5, "requirements_total": 6},
            {"requirements_passed": 6, "requirements_total": 6},
        ]
        score = monitor._calculate_health_score()
        assert 80 <= score <= 100

    def test_health_score_empty_history(self) -> None:
        monitor = ContinuousComplianceMonitor("test-system")
        score = monitor._calculate_health_score()
        assert score == 0.0
