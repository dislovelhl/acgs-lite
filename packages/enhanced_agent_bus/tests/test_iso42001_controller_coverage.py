# Constitutional Hash: 608508a9bd224290
"""Comprehensive tests for compliance_layer/iso42001_controller.py.

Targets ≥95% coverage of all classes, methods, and code paths.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.compliance_layer.iso42001_controller import (
    AIManagementSystemController,
    AIMSAuditScheduler,
    AIMSBlockchainAnchoring,
    AIMSClause,
    AIMSNonconformity,
    AIMSNonconformityTracker,
    AIMSRequirement,
    AIMSRiskEntry,
    AIMSRiskRegister,
    ComplianceStatus,
    create_aims_controller,
)

# ---------------------------------------------------------------------------
# AIMSClause enum
# ---------------------------------------------------------------------------


class TestAIMSClause:
    def test_all_values(self):
        assert AIMSClause.CONTEXT.value == "4"
        assert AIMSClause.LEADERSHIP.value == "5"
        assert AIMSClause.PLANNING.value == "6"
        assert AIMSClause.SUPPORT.value == "7"
        assert AIMSClause.OPERATION.value == "8"
        assert AIMSClause.PERFORMANCE.value == "9"
        assert AIMSClause.IMPROVEMENT.value == "10"

    def test_enum_members(self):
        members = list(AIMSClause)
        assert len(members) == 7


# ---------------------------------------------------------------------------
# ComplianceStatus enum
# ---------------------------------------------------------------------------


class TestComplianceStatus:
    def test_all_values(self):
        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.PARTIAL.value == "partial"
        assert ComplianceStatus.GAP.value == "gap"
        assert ComplianceStatus.NOT_ASSESSED.value == "not_assessed"

    def test_enum_members(self):
        assert len(list(ComplianceStatus)) == 4


# ---------------------------------------------------------------------------
# AIMSRequirement dataclass
# ---------------------------------------------------------------------------


class TestAIMSRequirement:
    def test_default_status(self):
        req = AIMSRequirement(
            clause=AIMSClause.CONTEXT,
            requirement_id="4.1",
            description="Understanding the organization",
        )
        assert req.status == ComplianceStatus.NOT_ASSESSED
        assert req.evidence == []
        assert req.gap_description is None
        assert req.action_required is None
        assert req.owner is None
        assert req.due_date is None

    def test_custom_fields(self):
        due = datetime(2026, 12, 31, tzinfo=UTC)
        req = AIMSRequirement(
            clause=AIMSClause.LEADERSHIP,
            requirement_id="5.1",
            description="Leadership commitment",
            status=ComplianceStatus.PARTIAL,
            evidence=["doc1", "doc2"],
            gap_description="Leadership involvement lacking",
            action_required="Schedule leadership training",
            owner="CTO",
            due_date=due,
        )
        assert req.status == ComplianceStatus.PARTIAL
        assert req.evidence == ["doc1", "doc2"]
        assert req.gap_description == "Leadership involvement lacking"
        assert req.action_required == "Schedule leadership training"
        assert req.owner == "CTO"
        assert req.due_date == due

    def test_evidence_list_independence(self):
        req1 = AIMSRequirement(clause=AIMSClause.CONTEXT, requirement_id="4.1", description="desc")
        req2 = AIMSRequirement(clause=AIMSClause.CONTEXT, requirement_id="4.2", description="desc2")
        req1.evidence.append("item")
        assert req2.evidence == []


# ---------------------------------------------------------------------------
# AIMSRiskEntry dataclass
# ---------------------------------------------------------------------------


class TestAIMSRiskEntry:
    def test_default_status(self):
        risk = AIMSRiskEntry(
            risk_id="R-001",
            title="Bias risk",
            description="AI model may exhibit bias",
            likelihood=3,
            impact=4,
            risk_score=0,  # will be updated by register
            treatment="Mitigate with bias testing",
            owner="AI Ethics Team",
        )
        assert risk.status == "open"
        assert isinstance(risk.created_at, datetime)

    def test_created_at_timezone_aware(self):
        risk = AIMSRiskEntry(
            risk_id="R-002",
            title="Title",
            description="Desc",
            likelihood=2,
            impact=3,
            risk_score=6,
            treatment="Accept",
            owner="Owner",
        )
        assert risk.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# AIMSNonconformity dataclass
# ---------------------------------------------------------------------------


class TestAIMSNonconformity:
    def test_defaults(self):
        nc = AIMSNonconformity(
            nc_id="NC-001",
            title="Missing documentation",
            description="No documented evidence for clause 7.5",
            clause=AIMSClause.SUPPORT,
            severity="minor",
        )
        assert nc.status == "open"
        assert nc.root_cause is None
        assert nc.corrective_action is None
        assert nc.closed_at is None
        assert isinstance(nc.created_at, datetime)


# ---------------------------------------------------------------------------
# AIMSRiskRegister
# ---------------------------------------------------------------------------


class TestAIMSRiskRegister:
    def _make_risk(self, risk_id: str, likelihood: int = 3, impact: int = 3) -> AIMSRiskEntry:
        return AIMSRiskEntry(
            risk_id=risk_id,
            title=f"Risk {risk_id}",
            description="Description",
            likelihood=likelihood,
            impact=impact,
            risk_score=likelihood * impact,
            treatment="Mitigate",
            owner="Owner",
        )

    def test_add_risk_computes_score(self):
        register = AIMSRiskRegister()
        risk = self._make_risk("R-001", likelihood=4, impact=5)
        returned_id = register.add_risk(risk)
        assert returned_id == "R-001"
        # score is recomputed by add_risk
        stored = register.get_risk("R-001")
        assert stored.risk_score == 20  # 4 * 5

    def test_get_risk_existing(self):
        register = AIMSRiskRegister()
        risk = self._make_risk("R-002", likelihood=2, impact=3)
        register.add_risk(risk)
        result = register.get_risk("R-002")
        assert result is not None
        assert result.risk_id == "R-002"

    def test_get_risk_missing(self):
        register = AIMSRiskRegister()
        result = register.get_risk("NONEXISTENT")
        assert result is None

    def test_get_high_risks_default_threshold(self):
        register = AIMSRiskRegister()
        low = self._make_risk("R-LOW", likelihood=2, impact=3)  # 6
        mid = self._make_risk("R-MID", likelihood=3, impact=4)  # 12
        high = self._make_risk("R-HIGH", likelihood=4, impact=4)  # 16
        register.add_risk(low)
        register.add_risk(mid)
        register.add_risk(high)
        highs = register.get_high_risks()
        ids = [r.risk_id for r in highs]
        assert "R-HIGH" in ids
        assert "R-LOW" not in ids
        assert "R-MID" not in ids

    def test_get_high_risks_custom_threshold(self):
        register = AIMSRiskRegister()
        risk = self._make_risk("R-001", likelihood=3, impact=4)  # 12
        register.add_risk(risk)
        assert len(register.get_high_risks(threshold=10)) == 1
        assert len(register.get_high_risks(threshold=15)) == 0

    def test_get_high_risks_exactly_at_threshold(self):
        register = AIMSRiskRegister()
        risk = self._make_risk("R-001", likelihood=3, impact=5)  # 15
        register.add_risk(risk)
        assert len(register.get_high_risks(threshold=15)) == 1

    def test_get_open_risks(self):
        register = AIMSRiskRegister()
        r1 = self._make_risk("R-001")
        r2 = self._make_risk("R-002")
        register.add_risk(r1)
        register.add_risk(r2)
        register.close_risk("R-002")
        open_risks = register.get_open_risks()
        assert len(open_risks) == 1
        assert open_risks[0].risk_id == "R-001"

    def test_close_risk_existing(self):
        register = AIMSRiskRegister()
        risk = self._make_risk("R-001")
        register.add_risk(risk)
        result = register.close_risk("R-001")
        assert result is True
        stored = register.get_risk("R-001")
        assert stored.status == "closed"

    def test_close_risk_nonexistent(self):
        register = AIMSRiskRegister()
        result = register.close_risk("NONEXISTENT")
        assert result is False

    def test_constitutional_hash_set(self):
        register = AIMSRiskRegister()
        assert register._constitutional_hash == CONSTITUTIONAL_HASH

    def test_empty_register(self):
        register = AIMSRiskRegister()
        assert register.get_open_risks() == []
        assert register.get_high_risks() == []


# ---------------------------------------------------------------------------
# AIMSNonconformityTracker
# ---------------------------------------------------------------------------


class TestAIMSNonconformityTracker:
    def _make_nc(self, nc_id: str, status: str = "open") -> AIMSNonconformity:
        nc = AIMSNonconformity(
            nc_id=nc_id,
            title=f"NC {nc_id}",
            description="Description",
            clause=AIMSClause.SUPPORT,
            severity="minor",
        )
        nc.status = status
        return nc

    def test_raise_nonconformity_returns_id(self):
        tracker = AIMSNonconformityTracker()
        nc = self._make_nc("NC-001")
        result = tracker.raise_nonconformity(nc)
        assert result == "NC-001"

    def test_get_nonconformity_existing(self):
        tracker = AIMSNonconformityTracker()
        nc = self._make_nc("NC-001")
        tracker.raise_nonconformity(nc)
        result = tracker.get_nonconformity("NC-001")
        assert result is not None
        assert result.nc_id == "NC-001"

    def test_get_nonconformity_missing(self):
        tracker = AIMSNonconformityTracker()
        result = tracker.get_nonconformity("NONEXISTENT")
        assert result is None

    def test_get_open_nonconformities(self):
        tracker = AIMSNonconformityTracker()
        nc1 = self._make_nc("NC-001", status="open")
        nc2 = self._make_nc("NC-002", status="closed")
        nc3 = self._make_nc("NC-003", status="open")
        tracker.raise_nonconformity(nc1)
        tracker.raise_nonconformity(nc2)
        tracker.raise_nonconformity(nc3)
        open_ncs = tracker.get_open_nonconformities()
        ids = [nc.nc_id for nc in open_ncs]
        assert "NC-001" in ids
        assert "NC-003" in ids
        assert "NC-002" not in ids

    def test_close_nonconformity_existing(self):
        tracker = AIMSNonconformityTracker()
        nc = self._make_nc("NC-001")
        tracker.raise_nonconformity(nc)
        result = tracker.close_nonconformity("NC-001", "Fixed the gap", "Lack of process")
        assert result is True
        stored = tracker.get_nonconformity("NC-001")
        assert stored.status == "closed"
        assert stored.corrective_action == "Fixed the gap"
        assert stored.root_cause == "Lack of process"
        assert stored.closed_at is not None
        assert stored.closed_at.tzinfo is not None

    def test_close_nonconformity_nonexistent(self):
        tracker = AIMSNonconformityTracker()
        result = tracker.close_nonconformity("NONEXISTENT", "action", "cause")
        assert result is False

    def test_raise_emits_warning_log(self, caplog):
        import logging

        tracker = AIMSNonconformityTracker()
        nc = self._make_nc("NC-LOG")
        with caplog.at_level(logging.WARNING):
            tracker.raise_nonconformity(nc)
        assert "NC-LOG" in caplog.text

    def test_empty_tracker(self):
        tracker = AIMSNonconformityTracker()
        assert tracker.get_open_nonconformities() == []


# ---------------------------------------------------------------------------
# AIMSAuditScheduler
# ---------------------------------------------------------------------------


class TestAIMSAuditScheduler:
    def test_schedule_audit_returns_id(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        result = scheduler.schedule_audit(
            audit_id="AUD-001",
            clause=AIMSClause.PERFORMANCE,
            scheduled_date=future_date,
            auditor="Internal Auditor",
        )
        assert result == "AUD-001"

    def test_schedule_audit_stores_record(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        scheduler.schedule_audit(
            audit_id="AUD-001",
            clause=AIMSClause.OPERATION,
            scheduled_date=future_date,
            auditor="Auditor A",
        )
        upcoming = scheduler.get_upcoming_audits()
        assert len(upcoming) == 1
        assert upcoming[0]["audit_id"] == "AUD-001"
        assert upcoming[0]["status"] == "scheduled"
        assert upcoming[0]["auditor"] == "Auditor A"

    def test_complete_audit_existing(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        scheduler.schedule_audit(
            audit_id="AUD-001",
            clause=AIMSClause.PERFORMANCE,
            scheduled_date=future_date,
            auditor="Auditor A",
        )
        result = scheduler.complete_audit(
            audit_id="AUD-001",
            findings=["Finding 1", "Finding 2"],
            nonconformities=["NC-001"],
        )
        assert result is True

    def test_complete_audit_moves_to_completed(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        scheduler.schedule_audit(
            audit_id="AUD-001",
            clause=AIMSClause.PERFORMANCE,
            scheduled_date=future_date,
            auditor="Auditor",
        )
        scheduler.complete_audit("AUD-001", ["finding"], ["nc"])
        # Should no longer be in scheduled
        assert len(scheduler._scheduled_audits) == 0
        assert len(scheduler._completed_audits) == 1

    def test_complete_audit_sets_status(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=1)
        scheduler.schedule_audit("AUD-001", AIMSClause.CONTEXT, future_date, "Aud")
        scheduler.complete_audit("AUD-001", [], [])
        completed = scheduler._completed_audits[0]
        assert completed["status"] == "completed"
        assert "completed_at" in completed
        assert "findings" in completed
        assert "nonconformities" in completed

    def test_complete_audit_nonexistent(self):
        scheduler = AIMSAuditScheduler()
        result = scheduler.complete_audit("NONEXISTENT", [], [])
        assert result is False

    def test_get_upcoming_audits_filters_past(self):
        scheduler = AIMSAuditScheduler()
        past_date = datetime.now(UTC) - timedelta(days=1)
        future_date = datetime.now(UTC) + timedelta(days=30)
        scheduler.schedule_audit("AUD-PAST", AIMSClause.CONTEXT, past_date, "Aud")
        scheduler.schedule_audit("AUD-FUTURE", AIMSClause.CONTEXT, future_date, "Aud")
        upcoming = scheduler.get_upcoming_audits()
        ids = [a["audit_id"] for a in upcoming]
        assert "AUD-FUTURE" in ids
        assert "AUD-PAST" not in ids

    def test_multiple_scheduled_audits(self):
        scheduler = AIMSAuditScheduler()
        base = datetime.now(UTC) + timedelta(days=10)
        for i in range(3):
            scheduler.schedule_audit(
                f"AUD-{i:03d}",
                AIMSClause.OPERATION,
                base + timedelta(days=i),
                "Aud",
            )
        upcoming = scheduler.get_upcoming_audits()
        assert len(upcoming) == 3

    def test_complete_audit_with_empty_lists(self):
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=5)
        scheduler.schedule_audit("AUD-001", AIMSClause.IMPROVEMENT, future_date, "Aud")
        result = scheduler.complete_audit("AUD-001", [], [])
        assert result is True
        completed = scheduler._completed_audits[0]
        assert completed["findings"] == []
        assert completed["nonconformities"] == []

    def test_complete_audit_second_of_two_scheduled(self):
        """Covers the for-loop branch where first audit doesn't match (175->174)."""
        scheduler = AIMSAuditScheduler()
        future = datetime.now(UTC) + timedelta(days=10)
        scheduler.schedule_audit("AUD-001", AIMSClause.CONTEXT, future, "Aud1")
        scheduler.schedule_audit("AUD-002", AIMSClause.PLANNING, future, "Aud2")
        # Complete the second one — the loop iterates over AUD-001 first (no match), then AUD-002
        result = scheduler.complete_audit("AUD-002", ["finding"], [])
        assert result is True
        assert len(scheduler._completed_audits) == 1
        assert scheduler._completed_audits[0]["audit_id"] == "AUD-002"
        # AUD-001 should still be scheduled
        assert len(scheduler._scheduled_audits) == 1
        assert scheduler._scheduled_audits[0]["audit_id"] == "AUD-001"


# ---------------------------------------------------------------------------
# AIManagementSystemController
# ---------------------------------------------------------------------------


class TestAIManagementSystemController:
    def test_default_initialization(self):
        ctrl = AIManagementSystemController()
        assert ctrl._organization == "ACGS-2"
        assert ctrl._constitutional_hash == CONSTITUTIONAL_HASH
        assert ctrl._audit_callback is None

    def test_custom_organization(self):
        ctrl = AIManagementSystemController(organization_name="MyOrg")
        assert ctrl._organization == "MyOrg"

    def test_requirements_initialized(self):
        ctrl = AIManagementSystemController()
        # 29 base requirements defined in _initialize_requirements
        assert len(ctrl._requirements) == 29

    def test_all_base_requirement_ids(self):
        ctrl = AIManagementSystemController()
        expected_ids = [
            "4.1",
            "4.2",
            "4.3",
            "4.4",
            "5.1",
            "5.2",
            "5.3",
            "6.1",
            "6.2",
            "6.3",
            "6.4",
            "7.1",
            "7.2",
            "7.3",
            "7.4",
            "7.5",
            "8.1",
            "8.2",
            "8.3",
            "8.4",
            "8.5",
            "8.6",
            "8.7",
            "8.8",
            "9.1",
            "9.2",
            "9.3",
            "10.1",
            "10.2",
        ]
        for req_id in expected_ids:
            assert req_id in ctrl._requirements, f"Missing requirement: {req_id}"

    def test_all_requirements_default_not_assessed(self):
        ctrl = AIManagementSystemController()
        for req in ctrl._requirements.values():
            assert req.status == ComplianceStatus.NOT_ASSESSED

    def test_audit_callback_invoked(self):
        callback = MagicMock()
        ctrl = AIManagementSystemController(audit_callback=callback)
        ctrl.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.COMPLIANT,
            evidence=["doc1"],
        )
        callback.assert_called_once()
        event_type, data = callback.call_args[0]
        assert event_type == "aims_requirement_assessed"
        assert data["requirement_id"] == "4.1"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_audit_callback_not_invoked_when_none(self):
        ctrl = AIManagementSystemController(audit_callback=None)
        # Should not raise
        result = ctrl.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.COMPLIANT,
            evidence=[],
        )
        assert result is True

    def test_assess_requirement_existing(self):
        ctrl = AIManagementSystemController()
        result = ctrl.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.COMPLIANT,
            evidence=["policy.pdf"],
        )
        assert result is True
        req = ctrl._requirements["4.1"]
        assert req.status == ComplianceStatus.COMPLIANT
        assert req.evidence == ["policy.pdf"]

    def test_assess_requirement_with_gap(self):
        ctrl = AIManagementSystemController()
        result = ctrl.assess_requirement(
            requirement_id="5.1",
            status=ComplianceStatus.GAP,
            evidence=[],
            gap_description="No leadership involvement",
            action_required="Leadership training required",
        )
        assert result is True
        req = ctrl._requirements["5.1"]
        assert req.gap_description == "No leadership involvement"
        assert req.action_required == "Leadership training required"

    def test_assess_requirement_nonexistent(self):
        ctrl = AIManagementSystemController()
        result = ctrl.assess_requirement(
            requirement_id="99.99",
            status=ComplianceStatus.COMPLIANT,
            evidence=[],
        )
        assert result is False

    def test_assess_requirement_gap_flag_in_audit(self):
        callback = MagicMock()
        ctrl = AIManagementSystemController(audit_callback=callback)
        ctrl.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.GAP,
            evidence=[],
            gap_description="Missing evidence",
        )
        _, data = callback.call_args[0]
        assert data["has_gap"] is True

    def test_assess_requirement_no_gap_flag_in_audit(self):
        callback = MagicMock()
        ctrl = AIManagementSystemController(audit_callback=callback)
        ctrl.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.COMPLIANT,
            evidence=["doc"],
        )
        _, data = callback.call_args[0]
        assert data["has_gap"] is False

    def test_get_compliance_summary_all_not_assessed(self):
        ctrl = AIManagementSystemController()
        summary = ctrl.get_compliance_summary()
        assert summary["organization"] == "ACGS-2"
        assert summary["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert summary["total_requirements"] == 29
        assert summary["compliant"] == 0
        assert summary["partial"] == 0
        assert summary["gap"] == 0
        assert summary["not_assessed"] == 29
        assert summary["compliance_percentage"] == 0

    def test_get_compliance_summary_mixed(self):
        ctrl = AIManagementSystemController()
        ctrl.assess_requirement("4.1", ComplianceStatus.COMPLIANT, ["e1"])
        ctrl.assess_requirement("4.2", ComplianceStatus.COMPLIANT, ["e2"])
        ctrl.assess_requirement("4.3", ComplianceStatus.PARTIAL, [])
        ctrl.assess_requirement("4.4", ComplianceStatus.GAP, [], "gap desc")
        summary = ctrl.get_compliance_summary()
        assert summary["compliant"] == 2
        assert summary["partial"] == 1
        assert summary["gap"] == 1
        assert summary["not_assessed"] == 25

    def test_get_compliance_percentage_calculation(self):
        ctrl = AIManagementSystemController()
        # Mark all 29 as compliant
        for req_id in ctrl._requirements:
            ctrl.assess_requirement(req_id, ComplianceStatus.COMPLIANT, [])
        summary = ctrl.get_compliance_summary()
        assert summary["compliance_percentage"] == 100.0

    def test_get_compliance_summary_includes_risk_and_nc_counts(self):
        ctrl = AIManagementSystemController()
        # Add a high risk
        risk = AIMSRiskEntry(
            risk_id="R-001",
            title="High risk",
            description="desc",
            likelihood=5,
            impact=5,
            risk_score=25,
            treatment="Mitigate",
            owner="Owner",
        )
        ctrl.risk_register.add_risk(risk)
        # Add an open NC
        nc = AIMSNonconformity(
            nc_id="NC-001",
            title="NC",
            description="desc",
            clause=AIMSClause.CONTEXT,
            severity="minor",
        )
        ctrl.nonconformity_tracker.raise_nonconformity(nc)
        summary = ctrl.get_compliance_summary()
        assert summary["high_risks"] >= 1
        assert summary["open_nonconformities"] >= 1

    def test_get_compliance_summary_upcoming_audits(self):
        ctrl = AIManagementSystemController()
        future = datetime.now(UTC) + timedelta(days=10)
        ctrl.audit_scheduler.schedule_audit("AUD-001", AIMSClause.CONTEXT, future, "Aud")
        summary = ctrl.get_compliance_summary()
        assert summary["upcoming_audits"] >= 1

    def test_get_gaps_returns_only_gap_requirements(self):
        ctrl = AIManagementSystemController()
        ctrl.assess_requirement("4.1", ComplianceStatus.GAP, [], "gap1")
        ctrl.assess_requirement("4.2", ComplianceStatus.COMPLIANT, ["doc"])
        ctrl.assess_requirement("4.3", ComplianceStatus.GAP, [], "gap2")
        gaps = ctrl.get_gaps()
        assert len(gaps) == 2
        gap_ids = [g.requirement_id for g in gaps]
        assert "4.1" in gap_ids
        assert "4.3" in gap_ids
        assert "4.2" not in gap_ids

    def test_get_gaps_empty_when_all_compliant(self):
        ctrl = AIManagementSystemController()
        for req_id in ctrl._requirements:
            ctrl.assess_requirement(req_id, ComplianceStatus.COMPLIANT, [])
        assert ctrl.get_gaps() == []

    def test_risk_register_property(self):
        ctrl = AIManagementSystemController()
        assert isinstance(ctrl.risk_register, AIMSRiskRegister)

    def test_nonconformity_tracker_property(self):
        ctrl = AIManagementSystemController()
        assert isinstance(ctrl.nonconformity_tracker, AIMSNonconformityTracker)

    def test_audit_scheduler_property(self):
        ctrl = AIManagementSystemController()
        assert isinstance(ctrl.audit_scheduler, AIMSAuditScheduler)

    def test_emit_audit_with_callback(self):
        events = []

        def callback(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        ctrl = AIManagementSystemController(audit_callback=callback)
        ctrl._emit_audit("test_event", {"key": "value"})
        assert len(events) == 1
        assert events[0][0] == "test_event"
        assert events[0][1]["key"] == "value"
        assert events[0][1]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_emit_audit_without_callback(self):
        ctrl = AIManagementSystemController(audit_callback=None)
        # Should not raise
        ctrl._emit_audit("test_event", {"key": "value"})


# ---------------------------------------------------------------------------
# create_aims_controller factory
# ---------------------------------------------------------------------------


class TestCreateAimsController:
    def test_default_factory(self):
        ctrl = create_aims_controller()
        assert isinstance(ctrl, AIManagementSystemController)
        assert ctrl._organization == "ACGS-2"

    def test_custom_organization(self):
        ctrl = create_aims_controller(organization_name="TestOrg")
        assert ctrl._organization == "TestOrg"

    def test_with_callback(self):
        cb = MagicMock()
        ctrl = create_aims_controller(audit_callback=cb)
        assert ctrl._audit_callback is cb

    def test_factory_produces_initialized_requirements(self):
        ctrl = create_aims_controller()
        assert len(ctrl._requirements) == 29


# ---------------------------------------------------------------------------
# AIMSBlockchainAnchoring
# ---------------------------------------------------------------------------


class TestAIMSBlockchainAnchoring:
    def _make_controller(self) -> AIManagementSystemController:
        return AIManagementSystemController()

    def _make_risk(self, risk_id: str = "R-001") -> AIMSRiskEntry:
        risk = AIMSRiskEntry(
            risk_id=risk_id,
            title="Test Risk",
            description="Description",
            likelihood=3,
            impact=4,
            risk_score=12,
            treatment="Mitigate",
            owner="Owner",
        )
        return risk

    def _make_nc(self, nc_id: str = "NC-001") -> AIMSNonconformity:
        return AIMSNonconformity(
            nc_id=nc_id,
            title="Test NC",
            description="Description",
            clause=AIMSClause.SUPPORT,
            severity="major",
        )

    def test_initialization(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        assert anchoring._controller is ctrl
        assert anchoring._constitutional_hash == CONSTITUTIONAL_HASH
        assert anchoring._anchored_records == []

    def test_anchor_risk_returns_record(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk()
        record = anchoring.anchor_risk(risk)
        assert record["type"] == "aims_risk"
        assert record["risk_id"] == "R-001"
        assert record["title"] == "Test Risk"
        assert record["risk_score"] == 12
        assert record["status"] == "open"
        assert "anchor_hash" in record
        assert record["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_anchor_risk_computes_valid_sha256(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk()
        record = anchoring.anchor_risk(risk)
        # anchor_hash should be a valid 64-char hex string
        anchor_hash = record["anchor_hash"]
        assert len(anchor_hash) == 64
        assert all(c in "0123456789abcdef" for c in anchor_hash)

    def test_anchor_risk_appends_to_records(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk()
        anchoring.anchor_risk(risk)
        assert len(anchoring._anchored_records) == 1

    def test_anchor_nonconformity_returns_record(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        nc = self._make_nc()
        record = anchoring.anchor_nonconformity(nc)
        assert record["type"] == "aims_nonconformity"
        assert record["nc_id"] == "NC-001"
        assert record["title"] == "Test NC"
        assert record["clause"] == AIMSClause.SUPPORT.value
        assert record["severity"] == "major"
        assert record["status"] == "open"
        assert "anchor_hash" in record
        assert "timestamp" in record

    def test_anchor_nonconformity_computes_sha256(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        nc = self._make_nc()
        record = anchoring.anchor_nonconformity(nc)
        assert len(record["anchor_hash"]) == 64

    def test_anchor_nonconformity_appends_to_records(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        nc = self._make_nc()
        anchoring.anchor_nonconformity(nc)
        assert len(anchoring._anchored_records) == 1

    def test_anchor_audit_result_with_clause_enum(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        audit = {
            "audit_id": "AUD-001",
            "clause": AIMSClause.PERFORMANCE,
            "status": "completed",
            "findings": ["Finding 1"],
            "nonconformities": ["NC-001"],
        }
        record = anchoring.anchor_audit_result(audit)
        assert record["type"] == "aims_audit"
        assert record["audit_id"] == "AUD-001"
        assert record["clause"] == AIMSClause.PERFORMANCE.value
        assert record["status"] == "completed"
        assert record["findings_count"] == 1
        assert record["nc_count"] == 1
        assert "anchor_hash" in record
        assert "timestamp" in record

    def test_anchor_audit_result_with_string_clause(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        audit = {
            "audit_id": "AUD-002",
            "clause": "9",  # string, not enum
            "status": "completed",
            "findings": [],
            "nonconformities": [],
        }
        record = anchoring.anchor_audit_result(audit)
        assert record["clause"] == "9"

    def test_anchor_audit_result_empty_lists(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        audit = {
            "audit_id": "AUD-003",
            "clause": AIMSClause.CONTEXT,
            "status": "completed",
        }
        record = anchoring.anchor_audit_result(audit)
        assert record["findings_count"] == 0
        assert record["nc_count"] == 0

    def test_anchor_audit_result_missing_keys(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        audit: dict = {}
        record = anchoring.anchor_audit_result(audit)
        assert record["audit_id"] is None
        assert record["status"] is None
        assert record["findings_count"] == 0
        assert record["nc_count"] == 0

    def test_get_anchored_records_returns_copy(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk()
        anchoring.anchor_risk(risk)
        records = anchoring.get_anchored_records()
        assert len(records) == 1
        # Modifying the returned list should not affect internal state
        records.clear()
        assert len(anchoring._anchored_records) == 1

    def test_get_anchored_records_empty(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        assert anchoring.get_anchored_records() == []

    def test_verify_anchor_existing(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk()
        record = anchoring.anchor_risk(risk)
        anchor_hash = record["anchor_hash"]
        assert anchoring.verify_anchor(anchor_hash) is True

    def test_verify_anchor_nonexistent(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        assert anchoring.verify_anchor("nonexistent_hash") is False

    def test_multiple_anchored_records(self):
        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk("R-001")
        nc = self._make_nc("NC-001")
        audit = {
            "audit_id": "AUD-001",
            "clause": AIMSClause.CONTEXT,
            "status": "completed",
            "findings": [],
            "nonconformities": [],
        }
        anchoring.anchor_risk(risk)
        anchoring.anchor_nonconformity(nc)
        anchoring.anchor_audit_result(audit)
        records = anchoring.get_anchored_records()
        assert len(records) == 3
        types = {r["type"] for r in records}
        assert "aims_risk" in types
        assert "aims_nonconformity" in types
        assert "aims_audit" in types

    def test_anchor_risk_logs_info(self, caplog):
        import logging

        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        risk = self._make_risk("R-LOG")
        with caplog.at_level(logging.INFO):
            anchoring.anchor_risk(risk)
        assert "R-LOG" in caplog.text

    def test_anchor_nonconformity_logs_info(self, caplog):
        import logging

        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        nc = self._make_nc("NC-LOG")
        with caplog.at_level(logging.INFO):
            anchoring.anchor_nonconformity(nc)
        assert "NC-LOG" in caplog.text

    def test_anchor_audit_logs_info(self, caplog):
        import logging

        ctrl = self._make_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)
        audit = {
            "audit_id": "AUD-LOG",
            "clause": AIMSClause.CONTEXT,
            "status": "completed",
            "findings": [],
            "nonconformities": [],
        }
        with caplog.at_level(logging.INFO):
            anchoring.anchor_audit_result(audit)
        assert "AUD-LOG" in caplog.text


# ---------------------------------------------------------------------------
# Integration: full workflow
# ---------------------------------------------------------------------------


class TestAIMSIntegration:
    def test_full_compliance_workflow(self):
        events: list = []

        def cb(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        ctrl = create_aims_controller("TestOrg", audit_callback=cb)

        # Assess several requirements
        ctrl.assess_requirement("4.1", ComplianceStatus.COMPLIANT, ["evidence.pdf"])
        ctrl.assess_requirement("4.2", ComplianceStatus.PARTIAL, [], gap_description="partial gap")
        ctrl.assess_requirement("4.3", ComplianceStatus.GAP, [], gap_description="full gap")

        # Add a risk
        risk = AIMSRiskEntry(
            risk_id="R-001",
            title="Data bias",
            description="Model may exhibit bias",
            likelihood=4,
            impact=5,
            risk_score=0,
            treatment="Monitor",
            owner="Ethics",
        )
        ctrl.risk_register.add_risk(risk)

        # Add NC
        nc = AIMSNonconformity(
            nc_id="NC-001",
            title="Missing policy",
            description="AI policy not documented",
            clause=AIMSClause.LEADERSHIP,
            severity="major",
        )
        ctrl.nonconformity_tracker.raise_nonconformity(nc)
        ctrl.nonconformity_tracker.close_nonconformity("NC-001", "Policy created", "Oversight")

        # Schedule and complete audit
        future = datetime.now(UTC) + timedelta(days=7)
        ctrl.audit_scheduler.schedule_audit("AUD-001", AIMSClause.PERFORMANCE, future, "Aud")
        ctrl.audit_scheduler.complete_audit("AUD-001", ["finding"], [])

        # Check summary
        summary = ctrl.get_compliance_summary()
        assert summary["organization"] == "TestOrg"
        assert summary["compliant"] == 1
        assert summary["partial"] == 1
        assert summary["gap"] == 1
        assert summary["open_nonconformities"] == 0

        # All callback events emitted
        assert len(events) == 3

    def test_blockchain_anchoring_workflow(self):
        ctrl = create_aims_controller()
        anchoring = AIMSBlockchainAnchoring(ctrl)

        risk = AIMSRiskEntry(
            risk_id="R-BC-001",
            title="Anchored risk",
            description="desc",
            likelihood=3,
            impact=3,
            risk_score=9,
            treatment="Accept",
            owner="Owner",
        )
        risk_record = anchoring.anchor_risk(risk)

        nc = AIMSNonconformity(
            nc_id="NC-BC-001",
            title="Anchored NC",
            description="desc",
            clause=AIMSClause.OPERATION,
            severity="critical",
        )
        nc_record = anchoring.anchor_nonconformity(nc)

        # Verify both hashes exist
        assert anchoring.verify_anchor(risk_record["anchor_hash"]) is True
        assert anchoring.verify_anchor(nc_record["anchor_hash"]) is True
        assert anchoring.verify_anchor("fake") is False

        all_records = anchoring.get_anchored_records()
        assert len(all_records) == 2

    def test_compliance_percentage_with_partial_requirements(self):
        ctrl = create_aims_controller()
        total = len(ctrl._requirements)

        # Assess half as compliant
        req_ids = list(ctrl._requirements.keys())
        half = total // 2
        for req_id in req_ids[:half]:
            ctrl.assess_requirement(req_id, ComplianceStatus.COMPLIANT, [])

        summary = ctrl.get_compliance_summary()
        expected_pct = round((half / total) * 100, 1)
        assert summary["compliance_percentage"] == expected_pct
