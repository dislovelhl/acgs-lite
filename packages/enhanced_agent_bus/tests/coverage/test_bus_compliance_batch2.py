"""
Tests for under-covered compliance and batch_processor_infra modules.

Covers:
- compliance_layer/compliance_reporter.py
- compliance_layer/soc2_auditor.py
- compliance_layer/nist_risk_assessor.py
- compliance_layer/euaiact_compliance.py
- compliance_layer/decision_explainer.py
- multi_tenancy/orm_models.py
- batch_processor_infra/governance.py
- batch_processor_infra/metrics.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# compliance_reporter.py
# ---------------------------------------------------------------------------


class TestComplianceMetrics:
    def test_defaults(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        m = ComplianceMetrics()
        assert m.total_controls == 0
        assert m.compliance_rate == 0.0
        assert m.overall_score == 0.0
        assert m.critical_violations == 0

    def test_constitutional_hash_present(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        m = ComplianceMetrics()
        assert m.constitutional_hash != ""


class TestComplianceReporterStaticMethods:
    """Unit tests for the static helper methods on ComplianceReporter."""

    def _make_assessment(self, **kwargs):
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
        )

        defaults = {
            "assessment_id": "test-001",
            "framework": ComplianceFramework.NIST_AI_RMF,
            "system_name": "test",
        }
        defaults.update(kwargs)
        return ComplianceAssessment(**defaults)

    def _make_metrics(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        return ComplianceMetrics()

    def test_accumulate_control_totals(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        metrics = self._make_metrics()
        assessment = self._make_assessment()
        assessment.controls_assessed = 10
        assessment.controls_compliant = 7
        assessment.controls_partial = 2
        assessment.controls_non_compliant = 1

        ComplianceReporter._accumulate_control_totals(metrics, assessment)
        assert metrics.total_controls == 10
        assert metrics.compliant_controls == 7
        assert metrics.partial_controls == 2
        assert metrics.non_compliant_controls == 1

    def test_set_framework_score_nist(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        metrics = self._make_metrics()
        assessment = self._make_assessment(framework=ComplianceFramework.NIST_AI_RMF)
        assessment.compliance_score = 85.0

        ComplianceReporter._set_framework_score(metrics, assessment)
        assert metrics.nist_score == 85.0
        assert metrics.soc2_score == 0.0

    def test_set_framework_score_soc2(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        metrics = self._make_metrics()
        assessment = self._make_assessment(framework=ComplianceFramework.SOC2_TYPE_II)
        assessment.compliance_score = 92.0

        ComplianceReporter._set_framework_score(metrics, assessment)
        assert metrics.soc2_score == 92.0

    def test_set_framework_score_euaiact(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        metrics = self._make_metrics()
        assessment = self._make_assessment(framework=ComplianceFramework.EU_AI_ACT)
        assessment.compliance_score = 77.5

        ComplianceReporter._set_framework_score(metrics, assessment)
        assert metrics.euaiact_score == 77.5

    def test_set_framework_score_unknown_framework(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.models import ComplianceFramework

        metrics = self._make_metrics()
        assessment = self._make_assessment(framework=ComplianceFramework.ISO_27001)
        assessment.compliance_score = 60.0

        ComplianceReporter._set_framework_score(metrics, assessment)
        assert metrics.nist_score == 0.0
        assert metrics.soc2_score == 0.0
        assert metrics.euaiact_score == 0.0

    def test_accumulate_violation_totals(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceFramework,
            ComplianceViolation,
            RiskSeverity,
        )

        metrics = self._make_metrics()
        assessment = self._make_assessment()
        assessment.violations = [
            ComplianceViolation(
                violation_id="v1",
                framework=ComplianceFramework.NIST_AI_RMF,
                control_id="c1",
                severity=RiskSeverity.CRITICAL,
                description="crit",
            ),
            ComplianceViolation(
                violation_id="v2",
                framework=ComplianceFramework.NIST_AI_RMF,
                control_id="c2",
                severity=RiskSeverity.HIGH,
                description="high",
            ),
            ComplianceViolation(
                violation_id="v3",
                framework=ComplianceFramework.NIST_AI_RMF,
                control_id="c3",
                severity=RiskSeverity.MEDIUM,
                description="med",
            ),
            ComplianceViolation(
                violation_id="v4",
                framework=ComplianceFramework.NIST_AI_RMF,
                control_id="c4",
                severity=RiskSeverity.LOW,
                description="low",
            ),
        ]

        ComplianceReporter._accumulate_violation_totals(metrics, assessment)
        assert metrics.critical_violations == 1
        assert metrics.high_violations == 1
        assert metrics.medium_violations == 1
        assert metrics.low_violations == 1

    def test_finalize_compliance_rate_zero_controls(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        metrics = self._make_metrics()
        ComplianceReporter._finalize_compliance_rate(metrics)
        assert metrics.compliance_rate == 0.0

    def test_finalize_compliance_rate_with_controls(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        metrics = self._make_metrics()
        metrics.total_controls = 10
        metrics.compliant_controls = 6
        metrics.partial_controls = 2

        ComplianceReporter._finalize_compliance_rate(metrics)
        expected = (6 + 2 * 0.5) / 10 * 100
        assert metrics.compliance_rate == expected

    def test_finalize_overall_score_no_valid(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        metrics = self._make_metrics()
        ComplianceReporter._finalize_overall_score(metrics)
        assert metrics.overall_score == 0.0

    def test_finalize_overall_score_with_scores(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        metrics = self._make_metrics()
        metrics.nist_score = 80.0
        metrics.soc2_score = 90.0
        metrics.euaiact_score = 0.0  # not counted

        ComplianceReporter._finalize_overall_score(metrics)
        assert metrics.overall_score == round((80.0 + 90.0) / 2, 2)


class TestComplianceReporterInstanceMethods:
    def _make_reporter(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        return ComplianceReporter()

    def test_generate_executive_summary_strong(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(overall_score=95.0)
        summary = reporter._generate_executive_summary(m)
        assert "Strong" in summary
        assert "95.0%" in summary

    def test_generate_executive_summary_acceptable(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(overall_score=75.0)
        summary = reporter._generate_executive_summary(m)
        assert "Acceptable" in summary

    def test_generate_executive_summary_needs_improvement(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(overall_score=50.0)
        summary = reporter._generate_executive_summary(m)
        assert "Needs Improvement" in summary

    def test_extract_key_findings(self):
        from enhanced_agent_bus.compliance_layer.models import (
            ComplianceAssessment,
            ComplianceFramework,
        )

        reporter = self._make_reporter()
        a = ComplianceAssessment(
            assessment_id="a1",
            framework=ComplianceFramework.NIST_AI_RMF,
            system_name="test",
        )
        a.findings = ["f1", "f2", "f3", "f4"]
        findings = reporter._extract_key_findings([a])
        assert len(findings) == 3  # top 3 only
        assert "[nist_ai_rmf]" in findings[0]

    def test_generate_recommendations_with_critical(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(critical_violations=2, high_violations=1, overall_score=80.0)
        recs = reporter._generate_recommendations(m, [])
        assert any("critical" in r.lower() for r in recs)
        assert any("high-severity" in r.lower() for r in recs)
        assert any("90%" in r for r in recs)

    def test_generate_recommendations_no_critical_high_score(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(overall_score=95.0)
        recs = reporter._generate_recommendations(m, [])
        assert not any("critical" in r.lower() for r in recs)

    def test_generate_next_steps_with_non_compliant(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics(non_compliant_controls=3, partial_controls=2)
        steps = reporter._generate_next_steps(m)
        assert any("3" in s for s in steps)
        assert any("2" in s for s in steps)
        assert any("90 days" in s for s in steps)

    def test_generate_next_steps_all_compliant(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceMetrics,
        )

        reporter = self._make_reporter()
        m = ComplianceMetrics()
        steps = reporter._generate_next_steps(m)
        assert any("90 days" in s for s in steps)
        assert not any("Remediate" in s for s in steps)

    def test_get_report_none(self):
        reporter = self._make_reporter()
        assert reporter.get_report("nonexistent") is None

    def test_list_reports_empty(self):
        reporter = self._make_reporter()
        assert reporter.list_reports() == []


class TestComplianceReporterAsync:
    @pytest.mark.asyncio
    async def test_generate_unified_report(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        nist = NISTRiskAssessor()
        soc2 = SOC2Auditor()
        euai = EUAIActCompliance()

        reporter = ComplianceReporter(nist, soc2, euai)
        report = await reporter.generate_unified_report()

        assert report.report_id.startswith("ucr-")
        assert report.metrics.overall_score > 0
        assert report.executive_summary != ""
        assert len(report.recommendations) > 0
        assert len(report.next_steps) > 0

        # stored
        assert reporter.get_report(report.report_id) is report
        assert len(reporter.list_reports()) == 1

    @pytest.mark.asyncio
    async def test_generate_dashboard(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        reporter = ComplianceReporter(NISTRiskAssessor(), SOC2Auditor(), EUAIActCompliance())
        dashboard = await reporter.generate_dashboard()

        assert len(dashboard.framework_status) == 3
        assert len(dashboard.recent_assessments) == 3
        assert len(dashboard.recommendations) > 0

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            ComplianceReporter,
        )

        reporter = ComplianceReporter()
        result1 = await reporter.initialize()
        result2 = await reporter.initialize()
        assert result1 is True
        assert result2 is True


class TestComplianceReporterSingleton:
    def test_get_and_reset(self):
        from enhanced_agent_bus.compliance_layer.compliance_reporter import (
            get_compliance_reporter,
            reset_compliance_reporter,
        )

        reset_compliance_reporter()
        r1 = get_compliance_reporter()
        r2 = get_compliance_reporter()
        assert r1 is r2
        reset_compliance_reporter()
        r3 = get_compliance_reporter()
        assert r3 is not r1


# ---------------------------------------------------------------------------
# soc2_auditor.py
# ---------------------------------------------------------------------------


class TestSOC2ControlValidator:
    def _make_pi_control(self, **overrides):
        from enhanced_agent_bus.compliance_layer.models import ProcessingIntegrityControl

        defaults = {
            "control_id": "PI-T1",
            "control_name": "Test",
            "description": "desc",
            "criteria": "CC7.1",
            "completeness_check": True,
            "accuracy_check": True,
            "timeliness_check": True,
            "authorization_check": True,
        }
        defaults.update(overrides)
        return ProcessingIntegrityControl(**defaults)

    def _make_c_control(self, **overrides):
        from enhanced_agent_bus.compliance_layer.models import ConfidentialityControl

        defaults = {
            "control_id": "C-T1",
            "control_name": "Test",
            "description": "desc",
            "criteria": "C1.1",
            "encryption_at_rest": True,
            "encryption_in_transit": True,
            "access_controls": ["RBAC"],
            "retention_policy": "90 days",
        }
        defaults.update(overrides)
        return ConfidentialityControl(**defaults)

    def _make_a_control(self, **overrides):
        from enhanced_agent_bus.compliance_layer.models import AvailabilityControl

        defaults = {
            "control_id": "A-T1",
            "control_name": "Test",
            "description": "desc",
            "criteria": "A1.1",
            "uptime_target": 99.9,
            "current_uptime": 99.95,
            "disaster_recovery_plan": True,
            "monitoring_enabled": True,
            "incident_response_plan": True,
            "capacity_planning": True,
            "backup_procedures": ["daily"],
        }
        defaults.update(overrides)
        return AvailabilityControl(**defaults)

    def test_pi_all_pass(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_pi_control()
        assert v.validate_processing_integrity(ctrl) is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_pi_partial(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_pi_control(completeness_check=False, accuracy_check=False)
        assert v.validate_processing_integrity(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_pi_non_compliant(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_pi_control(
            completeness_check=False,
            accuracy_check=False,
            timeliness_check=False,
        )
        assert v.validate_processing_integrity(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_confidentiality_all_pass(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_c_control()
        assert v.validate_confidentiality(ctrl) is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_confidentiality_partial(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_c_control(encryption_at_rest=False, retention_policy="")
        assert v.validate_confidentiality(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_confidentiality_non_compliant(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_c_control(
            encryption_at_rest=False,
            encryption_in_transit=False,
            access_controls=[],
        )
        assert v.validate_confidentiality(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_availability_compliant(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_a_control()
        assert v.validate_availability(ctrl) is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_availability_partial(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_a_control(
            disaster_recovery_plan=False,
            capacity_planning=False,
            backup_procedures=[],
        )
        assert v.validate_availability(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_availability_non_compliant(self):
        from enhanced_agent_bus.compliance_layer.models import ComplianceStatus
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2ControlValidator

        v = SOC2ControlValidator()
        ctrl = self._make_a_control(
            current_uptime=90.0,
            disaster_recovery_plan=False,
            monitoring_enabled=False,
            incident_response_plan=False,
            capacity_planning=False,
            backup_procedures=[],
        )
        assert v.validate_availability(ctrl) is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT


class TestSOC2EvidenceCollector:
    def test_collect_and_retrieve(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2EvidenceCollector

        collector = SOC2EvidenceCollector()
        ev = collector.collect_evidence(
            control_id="PI1.1",
            evidence_type="test",
            description="test evidence",
            source="unit-test",
        )
        assert ev.evidence_id.startswith("ev-")
        assert ev.control_id == "PI1.1"

        retrieved = collector.get_evidence_for_control("PI1.1")
        assert len(retrieved) == 1
        assert retrieved[0].evidence_id == ev.evidence_id

    def test_get_evidence_for_nonexistent_control(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2EvidenceCollector

        collector = SOC2EvidenceCollector()
        assert collector.get_evidence_for_control("NONE") == []

    def test_validate_evidence_success(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2EvidenceCollector

        collector = SOC2EvidenceCollector()
        ev = collector.collect_evidence(
            control_id="C1.1",
            evidence_type="test",
            description="desc",
            source="test",
        )
        assert collector.validate_evidence(ev.evidence_id, "reviewer-1") is True

    def test_validate_evidence_not_found(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2EvidenceCollector

        collector = SOC2EvidenceCollector()
        assert collector.validate_evidence("nonexistent", "rev") is False

    def test_get_all_evidence(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2EvidenceCollector

        collector = SOC2EvidenceCollector()
        collector.collect_evidence("c1", "t", "d", "s")
        collector.collect_evidence("c2", "t", "d", "s")
        assert len(collector.get_all_evidence()) == 2


class TestSOC2Auditor:
    @pytest.mark.asyncio
    async def test_audit(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert assessment.compliance_score > 0
        assert assessment.controls_assessed > 0
        assert assessment.framework.value == "soc2_type_ii"

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        assert await auditor.initialize() is True
        assert await auditor.initialize() is True

    def test_get_controls(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        auditor._initialize_default_controls()
        assert len(auditor.get_pi_controls()) == 3
        assert len(auditor.get_c_controls()) == 3
        assert len(auditor.get_a_controls()) == 3

    @pytest.mark.asyncio
    async def test_validate_uptime_sla(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        await auditor.initialize()
        report = auditor.validate_uptime_sla()
        assert report["sla_compliant"] is True
        assert report["average_uptime"] >= 99.9

    @pytest.mark.asyncio
    async def test_validate_uptime_sla_empty(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        # Don't initialize -> no controls
        report = auditor.validate_uptime_sla()
        assert report["controls_validated"] == 0
        assert report["sla_compliant"] is False

    @pytest.mark.asyncio
    async def test_generate_evidence_package(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        await auditor.initialize()
        package = auditor.generate_evidence_package(period_days=30)
        assert len(package.evidence_items) > 0
        assert package.completeness_score > 0
        assert len(package.incident_log) == 1

    @pytest.mark.asyncio
    async def test_data_classification(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import SOC2Auditor

        auditor = SOC2Auditor()
        await auditor.initialize()
        matrix = auditor.get_data_classification_matrix()
        assert len(matrix) == 4

        entry = auditor.classify_data("User PII")
        assert entry is not None
        assert entry.classification.value == "pii"

        assert auditor.classify_data("nonexistent") is None

    def test_singleton(self):
        from enhanced_agent_bus.compliance_layer.soc2_auditor import (
            get_soc2_auditor,
            reset_soc2_auditor,
        )

        reset_soc2_auditor()
        a1 = get_soc2_auditor()
        a2 = get_soc2_auditor()
        assert a1 is a2
        reset_soc2_auditor()


# ---------------------------------------------------------------------------
# nist_risk_assessor.py
# ---------------------------------------------------------------------------


class TestNISTMAPFunction:
    def test_establish_and_get_context(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTMAPFunction,
        )

        m = NISTMAPFunction()
        ctx = m.establish_context("sys1", "AI governance")
        assert ctx.context_id.startswith("ctx-")
        assert m.get_context(ctx.context_id) is ctx
        assert m.get_context("nonexistent") is None

    def test_list_contexts(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTMAPFunction,
        )

        m = NISTMAPFunction()
        m.establish_context("s1", "p1")
        m.establish_context("s2", "p2")
        assert len(m.list_contexts()) == 2


class TestNISTGovernFunction:
    def test_register_policy(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTGovernFunction,
        )

        g = NISTGovernFunction()
        policy = g.register_policy("pol-1", "Test Policy", "content here")
        assert policy["policy_id"] == "pol-1"
        assert policy["policy_name"] == "Test Policy"

    def test_assign_and_get_accountability(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTGovernFunction,
        )

        g = NISTGovernFunction()
        g.assign_accountability("risk_owner", "alice")
        assert g.get_accountability("risk_owner") == "alice"
        assert g.get_accountability("unknown") is None


class TestNISTRiskAssessor:
    @pytest.mark.asyncio
    async def test_assess_risk_default(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )

        assessor = NISTRiskAssessor()
        assessment = await assessor.assess_risk("test-system")
        assert assessment.framework.value == "nist_ai_rmf"
        assert assessment.controls_assessed == 3  # 3 default threats

    @pytest.mark.asyncio
    async def test_assess_risk_with_context(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )

        assessor = NISTRiskAssessor()
        ctx = assessor.map_function.establish_context("sys", "purpose")
        assessment = await assessor.assess_risk("sys", context=ctx)
        assert assessment.compliance_score >= 0

    def test_add_threat(self):
        from enhanced_agent_bus.compliance_layer.models import (
            RiskSeverity,
            ThreatCategory,
            ThreatModel,
        )
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )

        assessor = NISTRiskAssessor()
        threat = ThreatModel(
            threat_id="T-CUSTOM",
            category=ThreatCategory.DATA_POISONING,
            name="Custom Threat",
            description="desc",
            attack_vector="api",
            likelihood=RiskSeverity.LOW,
            impact=RiskSeverity.LOW,
        )
        assessor.add_threat(threat)
        threats = assessor.get_threats()
        assert any(t.threat_id == "T-CUSTOM" for t in threats)

    def test_add_mitigation(self):
        from enhanced_agent_bus.compliance_layer.models import RiskMitigation
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )

        assessor = NISTRiskAssessor()
        mit = RiskMitigation(
            mitigation_id="m1",
            threat_id="t1",
            name="M1",
            description="desc",
        )
        assessor.add_mitigation(mit)
        assert "m1" in assessor._mitigations

    def test_create_risk_register_entry(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            NISTRiskAssessor,
        )

        assessor = NISTRiskAssessor()
        assessor._initialize_default_threats()
        ctx = assessor.map_function.establish_context("sys", "purpose")
        entry = assessor.create_risk_register_entry(ctx)
        assert entry.entry_id.startswith("rre-")
        assert entry.entry_id in assessor.get_risk_register()

    def test_singleton(self):
        from enhanced_agent_bus.compliance_layer.nist_risk_assessor import (
            get_nist_risk_assessor,
            reset_nist_risk_assessor,
        )

        reset_nist_risk_assessor()
        a1 = get_nist_risk_assessor()
        a2 = get_nist_risk_assessor()
        assert a1 is a2
        reset_nist_risk_assessor()


# ---------------------------------------------------------------------------
# euaiact_compliance.py
# ---------------------------------------------------------------------------


class TestArticle13Transparency:
    def test_check_compliance(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            Article13Transparency,
        )

        art13 = Article13Transparency()
        result = art13.check_compliance()
        assert result["article"] == "Article 13"
        assert result["is_compliant"] is True
        assert result["compliance_rate"] == 1.0

    def test_get_requirements(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            Article13Transparency,
        )

        art13 = Article13Transparency()
        reqs = art13.get_requirements()
        assert len(reqs) == 3


class TestArticle14HumanOversight:
    def test_check_compliance(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            Article14HumanOversight,
        )

        art14 = Article14HumanOversight()
        result = art14.check_compliance()
        assert result["article"] == "Article 14"
        assert result["is_compliant"] is True
        assert len(result["oversight_levels"]) == 3

    def test_get_mechanisms(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            Article14HumanOversight,
        )

        art14 = Article14HumanOversight()
        mechs = art14.get_mechanisms()
        assert len(mechs) == 3


class TestHighRiskSystemValidator:
    def test_classify_limited_risk(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("test-sys")
        assert cls.risk_level == "limited"
        assert cls.is_high_risk is False

    def test_classify_high_risk_biometric(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("bio-sys", biometric_categorization=True)
        assert cls.risk_level == "high"
        assert cls.is_high_risk is True

    def test_classify_high_risk_critical_infra(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("infra-sys", critical_infrastructure=True)
        assert cls.is_high_risk is True

    def test_classify_high_risk_annex_iii(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("annex-sys", annex_iii_category="employment")
        assert cls.is_high_risk is True
        assert cls.risk_level == "high"

    def test_classify_significant_plus_safety(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("combo", significant_decisions=True, safety_component=True)
        assert cls.is_high_risk is True

    def test_classify_significant_only_not_high(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            HighRiskSystemValidator,
        )

        v = HighRiskSystemValidator()
        cls = v.classify_system("sig-only", significant_decisions=True)
        assert cls.is_high_risk is False


class TestEUAIActCompliance:
    @pytest.mark.asyncio
    async def test_assess(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )

        compliance = EUAIActCompliance()
        assessment = await compliance.assess()
        assert assessment.framework.value == "eu_ai_act"
        assert assessment.compliance_score > 0
        assert assessment.controls_assessed > 0

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )

        c = EUAIActCompliance()
        assert await c.initialize() is True
        assert await c.initialize() is True

    @pytest.mark.asyncio
    async def test_get_documentation(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )

        c = EUAIActCompliance()
        await c.initialize()
        docs = c.get_documentation()
        assert len(docs) == 1
        assert docs[0].system_name == "ACGS-2"

    @pytest.mark.asyncio
    async def test_get_classifications(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )

        c = EUAIActCompliance()
        await c.initialize()
        cls_list = c.get_classifications()
        assert len(cls_list) == 1

    @pytest.mark.asyncio
    async def test_generate_transparency_report(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            EUAIActCompliance,
        )

        c = EUAIActCompliance()
        await c.initialize()
        report = c.generate_transparency_report()
        assert "article_13_compliance" in report
        assert "article_14_compliance" in report
        assert len(report["transparency_requirements"]) == 3

    def test_singleton(self):
        from enhanced_agent_bus.compliance_layer.euaiact_compliance import (
            get_euaiact_compliance,
            reset_euaiact_compliance,
        )

        reset_euaiact_compliance()
        c1 = get_euaiact_compliance()
        c2 = get_euaiact_compliance()
        assert c1 is c2
        reset_euaiact_compliance()


# ---------------------------------------------------------------------------
# decision_explainer.py
# ---------------------------------------------------------------------------


class TestDecisionExplainer:
    @pytest.mark.asyncio
    async def test_explain_allow(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        result = await explainer.explain("allow", 0.3)
        assert result.verdict == "ALLOW"
        assert "ALLOW" in result.summary
        assert result.impact_score == 0.3
        assert len(result.factors) > 0
        assert len(result.governance_vector) == 7
        assert result.explanation_id.startswith("exp-")

    @pytest.mark.asyncio
    async def test_explain_deny(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        result = await explainer.explain("deny", 0.9)
        assert result.verdict == "DENY"
        assert "DENY" in result.summary

    @pytest.mark.asyncio
    async def test_explain_conditional(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        result = await explainer.explain("conditional", 0.5)
        assert result.verdict == "CONDITIONAL"

    @pytest.mark.asyncio
    async def test_explain_unknown_verdict(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        result = await explainer.explain("custom", 0.5)
        assert "custom" in result.summary.lower() or "CUSTOM" in result.summary

    @pytest.mark.asyncio
    async def test_explain_with_context(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            ExplanationContext,
        )

        explainer = DecisionExplainer()
        ctx = ExplanationContext(decision_id="dec-test-1", tenant_id="acme")
        result = await explainer.explain("allow", 0.4, context=ctx)
        assert result.decision_id == "dec-test-1"

    @pytest.mark.asyncio
    async def test_explain_custom_factor_scores(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        scores = {
            "semantic_score": 0.9,
            "permission_score": 0.1,
            "volume_score": 0.5,
            "context_score": 0.8,
            "drift_score": 0.05,
        }
        result = await explainer.explain("allow", 0.3, factor_scores=scores)
        assert len(result.factors) == 5
        # semantic_score has highest weight*value
        assert result.factors[0].factor_value == 0.9 or any(
            f.factor_value == 0.9 for f in result.factors
        )

    @pytest.mark.asyncio
    async def test_counterfactuals_disabled(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer(enable_counterfactuals=False)
        result = await explainer.explain("allow", 0.5)
        assert result.counterfactual_hints == []

    @pytest.mark.asyncio
    async def test_counterfactuals_generated(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer(max_counterfactuals=2)
        result = await explainer.explain("deny", 0.8)
        assert len(result.counterfactual_hints) <= 2

    def test_calculate_factors(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        scores = {"semantic_score": 0.7, "permission_score": 0.5}
        factors = explainer._calculate_factors(scores)
        assert len(factors) == 2
        sem = next(f for f in factors if f.factor_id == "f-semantic_score")
        assert sem.factor_value == 0.7
        assert sem.factor_weight == 0.6
        assert sem.contribution == 0.7 * 0.6

    def test_calculate_factors_unknown_factor(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        factors = explainer._calculate_factors({"custom_score": 0.5})
        assert len(factors) == 1
        assert factors[0].factor_weight == 0.1  # default weight

    def test_governance_vector(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f1",
                factor_name="F1",
                factor_value=0.8,
                factor_weight=0.5,
                contribution=0.4,
                explanation="e",
                governance_dimension="safety",
            ),
            FactorContribution(
                factor_id="f2",
                factor_name="F2",
                factor_value=0.3,
                factor_weight=0.5,
                contribution=0.15,
                explanation="e",
                governance_dimension="safety",
            ),
        ]
        vector = explainer._calculate_governance_vector(factors)
        assert vector["safety"] == 0.8  # max of 0.8, 0.3
        assert vector["fairness"] == 0.0

    def test_calculate_confidence_empty(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        assert explainer._calculate_confidence([], 0.5) == 0.5

    def test_calculate_confidence_extreme_impact(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f",
                factor_name="F",
                factor_value=0.5,
                factor_weight=1.0,
                contribution=0.5,
                explanation="e",
            ),
        ]
        conf = explainer._calculate_confidence(factors, 0.95)
        assert conf > 0.5

    def test_generate_counterfactuals_high_value(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f1",
                factor_name="F1",
                factor_value=0.8,
                factor_weight=0.6,
                contribution=0.48,
                explanation="e",
            ),
        ]
        cfs = explainer._generate_counterfactuals(factors, "allow", 0.3)
        assert len(cfs) == 1
        assert cfs[0]["modified_value"] == 0.3  # high -> lower

    def test_generate_counterfactuals_low_value(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f1",
                factor_name="F1",
                factor_value=0.2,
                factor_weight=0.5,
                contribution=0.1,
                explanation="e",
            ),
        ]
        cfs = explainer._generate_counterfactuals(factors, "deny", 0.8)
        assert cfs[0]["modified_value"] == 0.8

    def test_generate_counterfactuals_mid_value(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f1",
                factor_name="F1",
                factor_value=0.45,
                factor_weight=0.5,
                contribution=0.225,
                explanation="e",
            ),
        ]
        cfs = explainer._generate_counterfactuals(factors, "allow", 0.5)
        assert cfs[0]["modified_value"] == 0.9  # < 0.5 -> 0.9

    def test_detailed_reasoning_includes_factors(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
            FactorContribution,
        )

        explainer = DecisionExplainer()
        factors = [
            FactorContribution(
                factor_id="f1",
                factor_name="Content Analysis",
                factor_value=0.7,
                factor_weight=0.6,
                contribution=0.42,
                explanation="e",
            ),
        ]
        vector = {
            "safety": 0.7,
            "security": 0.0,
            "privacy": 0.0,
            "fairness": 0.0,
            "reliability": 0.0,
            "transparency": 0.0,
            "efficiency": 0.0,
        }
        text = explainer._generate_detailed_reasoning("allow", factors, vector, 0.3)
        assert "Content Analysis" in text
        assert "7-Dimensional Governance Vector" in text

    def test_get_and_list_explanations(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            DecisionExplainer,
        )

        explainer = DecisionExplainer()
        assert explainer.get_explanation("none") is None
        assert explainer.list_explanations() == []

    def test_singleton(self):
        from enhanced_agent_bus.compliance_layer.decision_explainer import (
            get_decision_explainer,
            reset_decision_explainer,
        )

        reset_decision_explainer()
        e1 = get_decision_explainer()
        e2 = get_decision_explainer()
        assert e1 is e2
        reset_decision_explainer()


# ---------------------------------------------------------------------------
# multi_tenancy/orm_models.py
# ---------------------------------------------------------------------------


class TestOrmModels:
    """Tests for ORM model definitions and helper methods.

    These tests verify the ORM classes can be instantiated and their helper
    methods work correctly without requiring a real database.
    """

    def test_tenant_status_enum(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        assert TenantStatusEnum.ACTIVE == "active"
        assert TenantStatusEnum.PENDING == "pending"
        assert TenantStatusEnum.SUSPENDED == "suspended"
        assert TenantStatusEnum.DEACTIVATED == "deactivated"
        assert TenantStatusEnum.MIGRATING == "migrating"

    def test_tenant_orm_repr(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantORM

        t = TenantORM(tenant_id="tid-1", slug="acme", status="active", name="Acme")
        r = repr(t)
        assert "tid-1" in r
        assert "acme" in r

    def test_tenant_is_active(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantORM

        t = TenantORM(status="active", name="t", slug="t1")
        assert t.is_active() is True
        t.status = "suspended"
        assert t.is_active() is False

    def test_tenant_validate_constitutional_compliance(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import (
            CONSTITUTIONAL_HASH,
            TenantORM,
        )

        t = TenantORM(constitutional_hash=CONSTITUTIONAL_HASH, name="t", slug="t2", status="active")
        assert t.validate_constitutional_compliance() is True
        t.constitutional_hash = "bad-hash"
        assert t.validate_constitutional_compliance() is False

    def test_enterprise_integration_repr(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import (
            EnterpriseIntegrationORM,
        )

        e = EnterpriseIntegrationORM(
            integration_id="int-1",
            integration_type="sso",
            provider="okta",
            name="Okta SSO",
            tenant_id="tid-1",
        )
        r = repr(e)
        assert "int-1" in r
        assert "sso" in r

    def test_tenant_role_mapping_repr(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantRoleMappingORM

        m = TenantRoleMappingORM(
            mapping_id="map-1",
            external_role="admin-group",
            internal_role="admin",
            tenant_id="tid-1",
        )
        r = repr(m)
        assert "admin-group" in r
        assert "admin" in r

    def test_migration_job_repr(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import MigrationJobORM

        j = MigrationJobORM(
            job_id="job-1",
            job_type="region",
            status="running",
            tenant_id="tid-1",
        )
        r = repr(j)
        assert "job-1" in r
        assert "region" in r

    def test_tenant_audit_log_repr(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantAuditLogORM

        log = TenantAuditLogORM(
            log_id="log-1",
            action="create",
            tenant_id="tid-1",
            actor_id="user-1",
        )
        r = repr(log)
        assert "log-1" in r
        assert "create" in r

    def test_json_type_variant(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import JSONType

        assert JSONType is not None

    def test_dedupe_indexes_runs(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import _dedupe_indexes

        _dedupe_indexes()  # should not raise

    def test_dedupe_class_registry_runs(self):
        from enhanced_agent_bus.multi_tenancy.orm_models import _dedupe_class_registry

        _dedupe_class_registry()  # should not raise


# ---------------------------------------------------------------------------
# batch_processor_infra/governance.py
# ---------------------------------------------------------------------------


class TestBatchGovernanceManager:
    def test_validate_batch_context_valid(self):
        from enhanced_agent_bus.batch_processor_infra.governance import (
            BatchGovernanceManager,
        )
        from enhanced_agent_bus.models import CONSTITUTIONAL_HASH

        mgr = BatchGovernanceManager()
        br = MagicMock()
        br.constitutional_hash = CONSTITUTIONAL_HASH
        result = mgr.validate_batch_context(br)
        assert result.is_valid is True

    def test_validate_batch_context_bad_hash(self):
        from enhanced_agent_bus.batch_processor_infra.governance import (
            BatchGovernanceManager,
        )

        mgr = BatchGovernanceManager()
        br = MagicMock()
        br.constitutional_hash = "bad-hash"
        result = mgr.validate_batch_context(br)
        assert result.is_valid is False

    def test_validate_item_valid_no_hash(self):
        from enhanced_agent_bus.batch_processor_infra.governance import (
            BatchGovernanceManager,
        )
        from enhanced_agent_bus.models import BatchRequestItem

        mgr = BatchGovernanceManager()
        item = BatchRequestItem(request_id="r1", content={"msg": "hello"})
        result = mgr.validate_item(item)
        assert result.is_valid is True

    def test_validate_item_valid_matching_hash(self):
        from enhanced_agent_bus.batch_processor_infra.governance import (
            BatchGovernanceManager,
        )
        from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, BatchRequestItem

        mgr = BatchGovernanceManager()
        item = BatchRequestItem(
            request_id="r2",
            content={"msg": "hello"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        result = mgr.validate_item(item)
        assert result.is_valid is True

    def test_validate_item_bad_hash(self):
        from enhanced_agent_bus.batch_processor_infra.governance import (
            BatchGovernanceManager,
        )
        from enhanced_agent_bus.models import BatchRequestItem

        mgr = BatchGovernanceManager()
        item = BatchRequestItem(
            request_id="r3",
            content={"msg": "hello"},
            constitutional_hash="wrong-hash",
        )
        result = mgr.validate_item(item)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# batch_processor_infra/metrics.py
# ---------------------------------------------------------------------------


class TestBatchMetricsState:
    def test_defaults(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetricsState

        s = BatchMetricsState()
        assert s.total_batches == 0
        assert s.total_items == 0
        assert s.total_constitutional_violations == 0


class TestBatchMetrics:
    def _make_stats(self, **kwargs):
        from enhanced_agent_bus.models import BatchResponseStats

        defaults = {
            "total_items": 10,
            "successful_items": 8,
            "failed_items": 2,
            "processing_time_ms": 100.0,
        }
        defaults.update(kwargs)
        return BatchResponseStats(**defaults)

    def test_record_batch_processed(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        stats = self._make_stats()
        m.record_batch_processed(stats, 150.0)
        cum = m.get_cumulative_metrics()
        assert cum["total_batches"] == 1
        assert cum["total_items"] == 10
        assert cum["total_succeeded"] == 8
        assert cum["total_failed"] == 2

    def test_record_item_latency(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        for i in range(5):
            m.record_item_latency(float(i))
        assert len(m._latencies) == 5

    def test_record_item_latency_cap(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        for i in range(10005):
            m.record_item_latency(float(i))
        assert len(m._latencies) == 10000

    def test_record_retry(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        m.record_retry()
        m.record_retry()
        assert m.get_cumulative_metrics()["total_retries"] == 2

    def test_record_slow_item(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        m.record_slow_item()
        assert m.get_cumulative_metrics()["total_slow_items"] == 1

    def test_calculate_batch_stats(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics
        from enhanced_agent_bus.models import BatchItemStatus

        m = BatchMetrics()
        results = [
            SimpleNamespace(status=BatchItemStatus.SUCCESS.value, processing_time_ms=10.0),
            SimpleNamespace(status=BatchItemStatus.SUCCESS.value, processing_time_ms=20.0),
            SimpleNamespace(status=BatchItemStatus.FAILED.value, processing_time_ms=5.0),
            SimpleNamespace(status=BatchItemStatus.SKIPPED.value, processing_time_ms=1.0),
        ]
        stats = m.calculate_batch_stats(4, results, 100.0)
        assert stats.total_items == 4
        assert stats.successful_items == 2
        assert stats.failed_items == 1
        assert stats.skipped == 1
        assert stats.p50_latency_ms > 0
        assert stats.average_item_time_ms > 0

    def test_calculate_batch_stats_empty(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        stats = m.calculate_batch_stats(0, [], 0.0)
        assert stats.total_items == 0
        assert stats.p50_latency_ms == 0.0

    def test_calculate_batch_stats_single_item(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics
        from enhanced_agent_bus.models import BatchItemStatus

        m = BatchMetrics()
        results = [
            SimpleNamespace(status=BatchItemStatus.SUCCESS.value, processing_time_ms=15.0),
        ]
        stats = m.calculate_batch_stats(1, results, 20.0)
        assert stats.p50_latency_ms == 15.0
        assert stats.p95_latency_ms == 15.0
        assert stats.p99_latency_ms == 15.0

    def test_calculate_batch_stats_no_processing_time(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics
        from enhanced_agent_bus.models import BatchItemStatus

        m = BatchMetrics()
        results = [
            SimpleNamespace(status=BatchItemStatus.SUCCESS.value),  # no processing_time_ms
        ]
        stats = m.calculate_batch_stats(1, results, 10.0)
        assert stats.p50_latency_ms == 0.0

    def test_get_cumulative_metrics_zero(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        cum = m.get_cumulative_metrics()
        assert cum["success_rate"] == 0.0
        assert cum["total_batches"] == 0

    def test_get_cumulative_metrics_success_rate(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        m._state.total_succeeded = 9
        m._state.total_failed = 1
        cum = m.get_cumulative_metrics()
        assert cum["success_rate"] == 90.0

    def test_reset(self):
        from enhanced_agent_bus.batch_processor_infra.metrics import BatchMetrics

        m = BatchMetrics()
        m.record_retry()
        m.record_item_latency(1.0)
        m.reset()
        cum = m.get_cumulative_metrics()
        assert cum["total_retries"] == 0
        assert len(m._latencies) == 0
