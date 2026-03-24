"""Tests for ISO 42001 AIMS Controller."""

from datetime import UTC, datetime, timedelta, timezone

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


class TestAIMSRiskEntry:
    def test_risk_entry_creation(self) -> None:
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="AI Bias Risk",
            description="Risk of biased outputs",
            likelihood=4,
            impact=5,
            risk_score=0,
            treatment="Implement fairness testing",
            owner="AI Team",
        )
        assert risk.risk_id == "R001"
        assert risk.status == "open"

    def test_risk_score_calculation(self) -> None:
        risk = AIMSRiskEntry(
            risk_id="R002",
            title="Test",
            description="Test",
            likelihood=3,
            impact=4,
            risk_score=0,
            treatment="Test",
            owner="Test",
        )
        assert risk.likelihood * risk.impact == 12


class TestAIMSRiskRegister:
    def test_add_risk(self) -> None:
        register = AIMSRiskRegister()
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Test Risk",
            description="Description",
            likelihood=4,
            impact=4,
            risk_score=0,
            treatment="Treatment",
            owner="Owner",
        )
        result = register.add_risk(risk)
        assert result == "R001"
        assert register.get_risk("R001").risk_score == 16

    def test_get_high_risks(self) -> None:
        register = AIMSRiskRegister()
        high_risk = AIMSRiskEntry(
            risk_id="R001",
            title="High Risk",
            description="Desc",
            likelihood=5,
            impact=5,
            risk_score=0,
            treatment="T",
            owner="O",
        )
        low_risk = AIMSRiskEntry(
            risk_id="R002",
            title="Low Risk",
            description="Desc",
            likelihood=2,
            impact=2,
            risk_score=0,
            treatment="T",
            owner="O",
        )
        register.add_risk(high_risk)
        register.add_risk(low_risk)
        high_risks = register.get_high_risks(threshold=15)
        assert len(high_risks) == 1
        assert high_risks[0].risk_id == "R001"

    def test_get_open_risks(self) -> None:
        register = AIMSRiskRegister()
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Open Risk",
            description="Desc",
            likelihood=3,
            impact=3,
            risk_score=0,
            treatment="T",
            owner="O",
        )
        register.add_risk(risk)
        assert len(register.get_open_risks()) == 1
        register.close_risk("R001")
        assert len(register.get_open_risks()) == 0

    def test_close_risk(self) -> None:
        register = AIMSRiskRegister()
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Risk",
            description="Desc",
            likelihood=3,
            impact=3,
            risk_score=0,
            treatment="T",
            owner="O",
        )
        register.add_risk(risk)
        result = register.close_risk("R001")
        assert result is True
        assert register.get_risk("R001").status == "closed"

    def test_close_nonexistent_risk(self) -> None:
        register = AIMSRiskRegister()
        result = register.close_risk("NONEXISTENT")
        assert result is False


class TestAIMSNonconformityTracker:
    def test_raise_nonconformity(self) -> None:
        tracker = AIMSNonconformityTracker()
        nc = AIMSNonconformity(
            nc_id="NC001",
            title="Missing Documentation",
            description="Control docs incomplete",
            clause=AIMSClause.SUPPORT,
            severity="minor",
        )
        result = tracker.raise_nonconformity(nc)
        assert result == "NC001"
        assert tracker.get_nonconformity("NC001") is not None

    def test_get_open_nonconformities(self) -> None:
        tracker = AIMSNonconformityTracker()
        nc = AIMSNonconformity(
            nc_id="NC001",
            title="Open NC",
            description="Desc",
            clause=AIMSClause.OPERATION,
            severity="major",
        )
        tracker.raise_nonconformity(nc)
        open_ncs = tracker.get_open_nonconformities()
        assert len(open_ncs) == 1

    def test_close_nonconformity(self) -> None:
        tracker = AIMSNonconformityTracker()
        nc = AIMSNonconformity(
            nc_id="NC001",
            title="NC to close",
            description="Desc",
            clause=AIMSClause.PERFORMANCE,
            severity="minor",
        )
        tracker.raise_nonconformity(nc)
        result = tracker.close_nonconformity(
            "NC001",
            corrective_action="Updated documentation",
            root_cause="Training gap",
        )
        assert result is True
        closed_nc = tracker.get_nonconformity("NC001")
        assert closed_nc.status == "closed"
        assert closed_nc.corrective_action == "Updated documentation"
        assert closed_nc.closed_at is not None


class TestAIMSAuditScheduler:
    def test_schedule_audit(self) -> None:
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        result = scheduler.schedule_audit(
            audit_id="A001",
            clause=AIMSClause.CONTEXT,
            scheduled_date=future_date,
            auditor="John Doe",
        )
        assert result == "A001"

    def test_get_upcoming_audits(self) -> None:
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        past_date = datetime.now(UTC) - timedelta(days=30)
        scheduler.schedule_audit("A001", AIMSClause.CONTEXT, future_date, "Auditor1")
        scheduler.schedule_audit("A002", AIMSClause.LEADERSHIP, past_date, "Auditor2")
        upcoming = scheduler.get_upcoming_audits()
        assert len(upcoming) == 1
        assert upcoming[0]["audit_id"] == "A001"

    def test_complete_audit(self) -> None:
        scheduler = AIMSAuditScheduler()
        future_date = datetime.now(UTC) + timedelta(days=30)
        scheduler.schedule_audit("A001", AIMSClause.PLANNING, future_date, "Auditor")
        result = scheduler.complete_audit(
            audit_id="A001",
            findings=["Finding 1", "Finding 2"],
            nonconformities=["NC001"],
        )
        assert result is True
        assert len(scheduler._completed_audits) == 1


class TestAIManagementSystemController:
    def test_initialization(self) -> None:
        controller = AIManagementSystemController("Test Org")
        assert controller._organization == "Test Org"
        assert len(controller._requirements) > 0

    def test_requirements_initialized(self) -> None:
        controller = AIManagementSystemController()
        assert "4.1" in controller._requirements
        assert "10.2" in controller._requirements

    def test_assess_requirement(self) -> None:
        controller = AIManagementSystemController()
        result = controller.assess_requirement(
            requirement_id="4.1",
            status=ComplianceStatus.COMPLIANT,
            evidence=["Policy document", "Audit log"],
        )
        assert result is True
        req = controller._requirements["4.1"]
        assert req.status == ComplianceStatus.COMPLIANT

    def test_assess_nonexistent_requirement(self) -> None:
        controller = AIManagementSystemController()
        result = controller.assess_requirement(
            requirement_id="99.99",
            status=ComplianceStatus.COMPLIANT,
            evidence=[],
        )
        assert result is False

    def test_get_compliance_summary(self) -> None:
        controller = AIManagementSystemController()
        controller.assess_requirement("4.1", ComplianceStatus.COMPLIANT, ["Evidence"])
        controller.assess_requirement("4.2", ComplianceStatus.GAP, [], gap_description="Missing")
        summary = controller.get_compliance_summary()
        assert summary["organization"] == "ACGS-2"
        assert summary["compliant"] == 1
        assert summary["gap"] == 1
        assert "compliance_percentage" in summary

    def test_get_gaps(self) -> None:
        controller = AIManagementSystemController()
        controller.assess_requirement("4.1", ComplianceStatus.COMPLIANT, [])
        controller.assess_requirement("4.2", ComplianceStatus.GAP, [], gap_description="Gap")
        gaps = controller.get_gaps()
        assert len(gaps) == 1
        assert gaps[0].requirement_id == "4.2"

    def test_property_access(self) -> None:
        controller = AIManagementSystemController()
        assert isinstance(controller.risk_register, AIMSRiskRegister)
        assert isinstance(controller.nonconformity_tracker, AIMSNonconformityTracker)
        assert isinstance(controller.audit_scheduler, AIMSAuditScheduler)


class TestAIMSBlockchainAnchoring:
    def test_anchor_risk(self) -> None:
        controller = AIManagementSystemController()
        anchoring = AIMSBlockchainAnchoring(controller)
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Test Risk",
            description="Desc",
            likelihood=3,
            impact=3,
            risk_score=9,
            treatment="Treatment",
            owner="Owner",
        )
        result = anchoring.anchor_risk(risk)
        assert "anchor_hash" in result
        assert result["type"] == "aims_risk"
        assert len(result["anchor_hash"]) == 64

    def test_anchor_nonconformity(self) -> None:
        controller = AIManagementSystemController()
        anchoring = AIMSBlockchainAnchoring(controller)
        nc = AIMSNonconformity(
            nc_id="NC001",
            title="Test NC",
            description="Desc",
            clause=AIMSClause.OPERATION,
            severity="minor",
        )
        result = anchoring.anchor_nonconformity(nc)
        assert "anchor_hash" in result
        assert result["type"] == "aims_nonconformity"

    def test_anchor_audit_result(self) -> None:
        controller = AIManagementSystemController()
        anchoring = AIMSBlockchainAnchoring(controller)
        audit = {
            "audit_id": "A001",
            "clause": AIMSClause.CONTEXT,
            "status": "completed",
            "findings": ["F1", "F2"],
            "nonconformities": [],
        }
        result = anchoring.anchor_audit_result(audit)
        assert "anchor_hash" in result
        assert result["type"] == "aims_audit"

    def test_get_anchored_records(self) -> None:
        controller = AIManagementSystemController()
        anchoring = AIMSBlockchainAnchoring(controller)
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Test",
            description="Desc",
            likelihood=3,
            impact=3,
            risk_score=9,
            treatment="T",
            owner="O",
        )
        anchoring.anchor_risk(risk)
        records = anchoring.get_anchored_records()
        assert len(records) == 1

    def test_verify_anchor(self) -> None:
        controller = AIManagementSystemController()
        anchoring = AIMSBlockchainAnchoring(controller)
        risk = AIMSRiskEntry(
            risk_id="R001",
            title="Test",
            description="Desc",
            likelihood=3,
            impact=3,
            risk_score=9,
            treatment="T",
            owner="O",
        )
        result = anchoring.anchor_risk(risk)
        anchor_hash = result["anchor_hash"]
        assert anchoring.verify_anchor(anchor_hash) is True
        assert anchoring.verify_anchor("invalid_hash") is False


class TestFactoryFunction:
    def test_create_aims_controller(self) -> None:
        controller = create_aims_controller("My Org")
        assert controller._organization == "My Org"

    def test_create_aims_controller_with_callback(self) -> None:
        events = []

        def callback(event_type: str, data: dict) -> None:
            events.append((event_type, data))

        controller = create_aims_controller("Test", audit_callback=callback)
        controller.assess_requirement("4.1", ComplianceStatus.COMPLIANT, [])
        assert len(events) == 1
        assert events[0][0] == "aims_requirement_assessed"
