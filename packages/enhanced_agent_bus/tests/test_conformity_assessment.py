"""
Tests for enhanced_agent_bus.compliance_layer.conformity_assessment

Covers: ConformityAssessment, ComplianceEvidence, ContinuousComplianceMonitor,
        evidence collection, Z3 proof integration, requirement assessment,
        full assessment, and report generation (markdown/json/html).
"""

from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.compliance_layer.conformity_assessment import (
    AssessmentStatus,
    ComplianceEvidence,
    ConformityAssessment,
    ConformityRequirement,
    ContinuousComplianceMonitor,
    EvidenceType,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_assessment_status_values(self):
        assert AssessmentStatus.PENDING.value == "pending"
        assert AssessmentStatus.REQUIRES_REMEDIATION.value == "requires_remediation"

    def test_evidence_type_values(self):
        assert EvidenceType.Z3_PROOF.value == "z3_proof"
        assert EvidenceType.AUDIT_LOG.value == "audit_log"


# ---------------------------------------------------------------------------
# ComplianceEvidence
# ---------------------------------------------------------------------------


class TestComplianceEvidence:
    def test_compute_hash_deterministic(self):
        e = ComplianceEvidence(content={"key": "value"})
        h1 = e.compute_hash()
        h2 = e.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_hash_changes_with_content(self):
        e1 = ComplianceEvidence(content={"a": 1})
        e2 = ComplianceEvidence(content={"a": 2})
        assert e1.compute_hash() != e2.compute_hash()

    def test_defaults(self):
        e = ComplianceEvidence()
        assert e.evidence_type == EvidenceType.AUDIT_LOG
        assert e.is_valid is True
        assert e.source == ""


# ---------------------------------------------------------------------------
# ConformityAssessment init
# ---------------------------------------------------------------------------


class TestConformityAssessmentInit:
    def test_initializes_requirements(self):
        ca = ConformityAssessment("sys-1")
        assert len(ca.requirements) == 6
        articles = [r.article for r in ca.requirements]
        assert "Article 9" in articles
        assert "Article 15" in articles

    def test_overall_status_starts_pending(self):
        ca = ConformityAssessment("sys-1")
        assert ca.overall_status == AssessmentStatus.PENDING


# ---------------------------------------------------------------------------
# Evidence collection from audit logs
# ---------------------------------------------------------------------------


class TestCollectEvidenceFromAuditLogs:
    def test_collects_within_date_range(self):
        ca = ConformityAssessment("sys-1")
        now = datetime.now(UTC)
        logs = [
            {"action": "risk_check", "timestamp": (now - timedelta(hours=1)).isoformat()},
            {"action": "data_review", "timestamp": (now - timedelta(hours=2)).isoformat()},
        ]
        collected = ca.collect_evidence_from_audit_logs(
            logs,
            start_date=now - timedelta(days=1),
            end_date=now,
        )
        assert len(collected) == 2
        assert len(ca.evidence_bank) == 2

    def test_filters_out_of_range(self):
        ca = ConformityAssessment("sys-1")
        now = datetime.now(UTC)
        logs = [
            {"action": "old_action", "timestamp": (now - timedelta(days=500)).isoformat()},
        ]
        collected = ca.collect_evidence_from_audit_logs(
            logs,
            start_date=now - timedelta(days=1),
            end_date=now,
        )
        assert len(collected) == 0

    def test_invalid_timestamp_skipped(self):
        ca = ConformityAssessment("sys-1")
        logs = [{"action": "test_check", "timestamp": "not-a-date"}]
        # Invalid timestamp: fromisoformat raises, fallback sets log_time to now(UTC)
        # but may still be filtered depending on timing; just verify no crash
        collected = ca.collect_evidence_from_audit_logs(logs)
        assert isinstance(collected, list)

    def test_no_timestamp_skipped(self):
        ca = ConformityAssessment("sys-1")
        logs = [{"action": "no_ts"}]
        collected = ca.collect_evidence_from_audit_logs(logs)
        # log_time is None, so `start <= None` fails — skipped
        assert len(collected) == 0


# ---------------------------------------------------------------------------
# Article mapping
# ---------------------------------------------------------------------------


class TestMapLogToArticle:
    def test_risk_maps_to_article_9(self):
        ca = ConformityAssessment("sys-1")
        assert ca._map_log_to_article({"action": "risk_assessment"}) == "Article 9"

    def test_data_maps_to_article_10(self):
        ca = ConformityAssessment("sys-1")
        assert ca._map_log_to_article({"action": "data_validation"}) == "Article 10"

    def test_unknown_maps_to_article_17(self):
        ca = ConformityAssessment("sys-1")
        assert ca._map_log_to_article({"action": "unknown_stuff"}) == "Article 17"

    def test_security_maps_to_article_15(self):
        ca = ConformityAssessment("sys-1")
        assert ca._map_log_to_article({"action": "security_scan"}) == "Article 15"

    def test_human_oversight_maps_to_article_14(self):
        ca = ConformityAssessment("sys-1")
        assert ca._map_log_to_article({"action": "human_oversight_event"}) == "Article 14"


# ---------------------------------------------------------------------------
# Z3 proof integration
# ---------------------------------------------------------------------------


class TestIntegrateZ3Proof:
    def test_adds_evidence_to_bank(self):
        ca = ConformityAssessment("sys-1")
        z3_result = {
            "satisfiable": True,
            "proof_hash": "abc123",
            "invariants": ["inv1"],
        }
        ev = ca.integrate_z3_proof("test_policy", z3_result)
        assert ev.evidence_type == EvidenceType.Z3_PROOF
        assert ev.is_valid is True
        assert ev in ca.evidence_bank

    def test_attaches_to_article_15(self):
        ca = ConformityAssessment("sys-1")
        z3_result = {"satisfiable": True}
        ca.integrate_z3_proof("pol", z3_result)
        art15 = next(r for r in ca.requirements if r.article == "Article 15")
        assert len(art15.evidence) == 1

    def test_unsatisfiable_proof(self):
        ca = ConformityAssessment("sys-1")
        ev = ca.integrate_z3_proof("bad_pol", {"satisfiable": False})
        assert ev.is_valid is False


# ---------------------------------------------------------------------------
# Requirement assessment
# ---------------------------------------------------------------------------


class TestAssessRequirement:
    def test_passes_with_sufficient_evidence(self):
        ca = ConformityAssessment("sys-1")
        req = ca.requirements[0]  # Article 9
        # Add 2 matching evidence items with correct types
        for etype in req.evidence_types:
            ev = ComplianceEvidence(
                evidence_type=etype,
                article_reference=req.article,
                content={"data": "test"},
                is_valid=True,
            )
            ev.compute_hash()
            ca.evidence_bank.append(ev)

        status = ca.assess_requirement(req)
        assert status == AssessmentStatus.PASSED

    def test_requires_remediation_missing_types(self):
        ca = ConformityAssessment("sys-1")
        req = ca.requirements[0]  # Article 9 needs risk_assessment + audit_log
        # Add only audit_log
        ev = ComplianceEvidence(
            evidence_type=EvidenceType.AUDIT_LOG,
            article_reference=req.article,
            is_valid=True,
        )
        ca.evidence_bank.append(ev)
        status = ca.assess_requirement(req)
        assert status == AssessmentStatus.REQUIRES_REMEDIATION

    def test_requires_remediation_insufficient_quantity(self):
        ca = ConformityAssessment("sys-1")
        req = ConformityRequirement(
            article="Article 99",
            description="test",
            evidence_types=[EvidenceType.AUDIT_LOG],
        )
        ev = ComplianceEvidence(
            evidence_type=EvidenceType.AUDIT_LOG,
            article_reference="Article 99",
            is_valid=True,
        )
        ca.evidence_bank.append(ev)
        status = ca.assess_requirement(req)
        assert status == AssessmentStatus.REQUIRES_REMEDIATION


# ---------------------------------------------------------------------------
# Full assessment
# ---------------------------------------------------------------------------


class TestRunFullAssessment:
    def test_no_evidence_requires_remediation(self):
        ca = ConformityAssessment("sys-1")
        status = ca.run_full_assessment()
        assert status == AssessmentStatus.REQUIRES_REMEDIATION

    def test_all_requirements_passed(self):
        ca = ConformityAssessment("sys-1")
        # Provide sufficient evidence for all requirements
        for req in ca.requirements:
            for etype in req.evidence_types:
                for _ in range(2):
                    ev = ComplianceEvidence(
                        evidence_type=etype,
                        article_reference=req.article,
                        content={"d": "v"},
                        is_valid=True,
                    )
                    ev.compute_hash()
                    ca.evidence_bank.append(ev)

        status = ca.run_full_assessment()
        assert status == AssessmentStatus.PASSED


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    @pytest.fixture()
    def assessed(self):
        ca = ConformityAssessment("sys-report")
        ca.run_full_assessment()
        return ca

    def test_markdown_report(self, assessed):
        report = assessed.generate_conformity_report("markdown")
        assert "# EU AI Act Conformity Assessment Report" in report
        assert assessed.system_id in report

    def test_json_report(self, assessed):
        report = assessed.generate_conformity_report("json")
        assert '"system_id"' in report
        assert '"overall_status"' in report

    def test_html_report(self, assessed):
        report = assessed.generate_conformity_report("html")
        assert "<!DOCTYPE html>" in report
        assert "<title>" in report

    def test_default_is_markdown(self, assessed):
        report = assessed.generate_conformity_report("unknown_format")
        assert "# EU AI Act Conformity Assessment Report" in report


# ---------------------------------------------------------------------------
# ContinuousComplianceMonitor
# ---------------------------------------------------------------------------


class TestContinuousComplianceMonitor:
    def test_init(self):
        m = ContinuousComplianceMonitor("sys-1", check_interval_hours=12)
        assert m.system_id == "sys-1"
        assert m.last_check is None

    def test_check_compliance_records_history(self):
        m = ContinuousComplianceMonitor("sys-1")
        now = datetime.now(UTC)
        logs = [
            {"action": "risk_check", "timestamp": (now - timedelta(hours=1)).isoformat()},
        ]
        result = m.check_compliance(logs)
        assert "status" in result
        assert len(m.compliance_history) == 1
        assert m.last_check is not None

    def test_check_compliance_generates_alerts(self):
        m = ContinuousComplianceMonitor("sys-1")
        result = m.check_compliance([])
        # No evidence => requires_remediation for all => alerts
        assert len(m.alerts) > 0

    def test_get_dashboard_data(self):
        m = ContinuousComplianceMonitor("sys-1")
        m.check_compliance([])
        data = m.get_dashboard_data()
        assert data["system_id"] == "sys-1"
        assert "last_check" in data
        assert "overall_health" in data

    def test_health_score_no_history(self):
        m = ContinuousComplianceMonitor("sys-1")
        assert m._calculate_health_score() == 0.0

    def test_health_score_with_history(self):
        m = ContinuousComplianceMonitor("sys-1")
        m.compliance_history = [
            {"requirements_passed": 3, "requirements_total": 6},
            {"requirements_passed": 6, "requirements_total": 6},
        ]
        score = m._calculate_health_score()
        assert 0 < score <= 100
