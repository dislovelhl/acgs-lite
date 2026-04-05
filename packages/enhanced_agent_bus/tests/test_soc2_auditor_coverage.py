"""
Tests for src/core/enhanced_agent_bus/compliance_layer/soc2_auditor.py

Coverage target: >= 85%
Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.compliance_layer.models import (
    AvailabilityControl,
    ComplianceStatus,
    ConfidentialityControl,
    DataClassification,
    ProcessingIntegrityControl,
)
from enhanced_agent_bus.compliance_layer.soc2_auditor import (
    SOC2Auditor,
    SOC2ControlValidator,
    SOC2EvidenceCollector,
    get_soc2_auditor,
    reset_soc2_auditor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pi_control(
    control_id: str = "PI-T1",
    completeness: bool = True,
    accuracy: bool = True,
    timeliness: bool = True,
    authorization: bool = True,
) -> ProcessingIntegrityControl:
    return ProcessingIntegrityControl(
        control_id=control_id,
        control_name="Test PI Control",
        description="A test PI control",
        criteria="CC7.1",
        completeness_check=completeness,
        accuracy_check=accuracy,
        timeliness_check=timeliness,
        authorization_check=authorization,
    )


def _make_confidentiality_control(
    control_id: str = "C-T1",
    encryption_at_rest: bool = True,
    encryption_in_transit: bool = True,
    access_controls: list | None = None,
    retention_policy: str = "90 days",
) -> ConfidentialityControl:
    return ConfidentialityControl(
        control_id=control_id,
        control_name="Test Confidentiality Control",
        description="A test confidentiality control",
        criteria="C1.1",
        encryption_at_rest=encryption_at_rest,
        encryption_in_transit=encryption_in_transit,
        access_controls=access_controls if access_controls is not None else ["RBAC"],
        retention_policy=retention_policy,
    )


def _make_availability_control(
    control_id: str = "A-T1",
    current_uptime: float = 99.95,
    uptime_target: float = 99.9,
    disaster_recovery_plan: bool = True,
    monitoring_enabled: bool = True,
    incident_response_plan: bool = True,
    capacity_planning: bool = True,
    backup_procedures: list | None = None,
) -> AvailabilityControl:
    return AvailabilityControl(
        control_id=control_id,
        control_name="Test Availability Control",
        description="A test availability control",
        criteria="A1.1",
        uptime_target=uptime_target,
        current_uptime=current_uptime,
        recovery_time_objective=60,
        recovery_point_objective=15,
        redundancy_mechanisms=["Load balancer"],
        backup_procedures=backup_procedures if backup_procedures is not None else ["Daily backup"],
        disaster_recovery_plan=disaster_recovery_plan,
        monitoring_enabled=monitoring_enabled,
        incident_response_plan=incident_response_plan,
        capacity_planning=capacity_planning,
    )


# ---------------------------------------------------------------------------
# SOC2ControlValidator - ProcessingIntegrity
# ---------------------------------------------------------------------------


class TestSOC2ControlValidatorProcessingIntegrity:
    def setup_method(self):
        self.validator = SOC2ControlValidator()

    def test_constitutional_hash_set(self):
        assert self.validator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_all_checks_true_returns_compliant(self):
        ctrl = _make_pi_control()
        result = self.validator.validate_processing_integrity(ctrl)
        assert result is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_three_checks_true_returns_partial(self):
        # passed = 3 → PARTIAL (>=2 but <4)
        ctrl = _make_pi_control(authorization=False)
        result = self.validator.validate_processing_integrity(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_two_checks_true_returns_partial(self):
        ctrl = _make_pi_control(timeliness=False, authorization=False)
        result = self.validator.validate_processing_integrity(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_one_check_true_returns_non_compliant(self):
        # passed = 1 → NON_COMPLIANT (<2)
        ctrl = _make_pi_control(accuracy=False, timeliness=False, authorization=False)
        result = self.validator.validate_processing_integrity(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_no_checks_true_returns_non_compliant(self):
        ctrl = _make_pi_control(
            completeness=False, accuracy=False, timeliness=False, authorization=False
        )
        result = self.validator.validate_processing_integrity(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# SOC2ControlValidator - Confidentiality
# ---------------------------------------------------------------------------


class TestSOC2ControlValidatorConfidentiality:
    def setup_method(self):
        self.validator = SOC2ControlValidator()

    def test_all_checks_true_returns_compliant(self):
        ctrl = _make_confidentiality_control()
        result = self.validator.validate_confidentiality(ctrl)
        assert result is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_three_checks_true_returns_partial(self):
        # Remove retention_policy → passed = 3 → PARTIAL
        ctrl = _make_confidentiality_control(retention_policy="")
        result = self.validator.validate_confidentiality(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_two_checks_true_returns_partial(self):
        ctrl = _make_confidentiality_control(
            encryption_at_rest=False,
            retention_policy="",
        )
        result = self.validator.validate_confidentiality(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_one_check_true_returns_non_compliant(self):
        ctrl = _make_confidentiality_control(
            encryption_at_rest=False,
            encryption_in_transit=False,
            access_controls=[],
            retention_policy="",
        )
        # passed=0 → NON_COMPLIANT
        result = self.validator.validate_confidentiality(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_empty_access_controls_reduces_score(self):
        ctrl = _make_confidentiality_control(access_controls=[])
        # encryption_at_rest=True, encryption_in_transit=True, access=False, retention=True → 3
        result = self.validator.validate_confidentiality(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL


# ---------------------------------------------------------------------------
# SOC2ControlValidator - Availability
# ---------------------------------------------------------------------------


class TestSOC2ControlValidatorAvailability:
    def setup_method(self):
        self.validator = SOC2ControlValidator()

    def test_all_checks_met_returns_compliant(self):
        ctrl = _make_availability_control()
        result = self.validator.validate_availability(ctrl)
        assert result is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_five_checks_met_returns_compliant(self):
        # passed=5 (uptime below target, rest all True) → COMPLIANT (>=5)
        ctrl = _make_availability_control(current_uptime=99.8, uptime_target=99.9)
        # uptime check fails → passed=5 which is >=5 → COMPLIANT
        result = self.validator.validate_availability(ctrl)
        assert result is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_three_checks_met_returns_partial(self):
        ctrl = _make_availability_control(
            current_uptime=90.0,  # fails
            disaster_recovery_plan=False,  # fails
            monitoring_enabled=False,  # fails
            # incident_response_plan=True, capacity_planning=True, backup_procedures=[1 item]
        )
        # passed = 3 → PARTIAL
        result = self.validator.validate_availability(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.PARTIAL

    def test_two_checks_met_returns_non_compliant(self):
        ctrl = _make_availability_control(
            current_uptime=90.0,
            disaster_recovery_plan=False,
            monitoring_enabled=False,
            incident_response_plan=False,
            backup_procedures=[],
        )
        # passed = capacity_planning(T) + incident... wait, incident=False too
        # uptime=F, dr=F, monitoring=F, incident=F, capacity=T, backup=F → passed=1 → NON_COMPLIANT
        result = self.validator.validate_availability(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_zero_checks_returns_non_compliant(self):
        ctrl = _make_availability_control(
            current_uptime=90.0,
            disaster_recovery_plan=False,
            monitoring_enabled=False,
            incident_response_plan=False,
            capacity_planning=False,
            backup_procedures=[],
        )
        result = self.validator.validate_availability(ctrl)
        assert result is False
        assert ctrl.implementation_status == ComplianceStatus.NON_COMPLIANT

    def test_uptime_exactly_at_target_passes(self):
        ctrl = _make_availability_control(current_uptime=99.9, uptime_target=99.9)
        result = self.validator.validate_availability(ctrl)
        assert result is True
        assert ctrl.implementation_status == ComplianceStatus.COMPLIANT


# ---------------------------------------------------------------------------
# SOC2EvidenceCollector
# ---------------------------------------------------------------------------


class TestSOC2EvidenceCollector:
    def setup_method(self):
        self.collector = SOC2EvidenceCollector()

    def test_constitutional_hash_set(self):
        assert self.collector.constitutional_hash == CONSTITUTIONAL_HASH

    def test_collect_evidence_returns_item(self):
        item = self.collector.collect_evidence(
            control_id="PI1.1",
            evidence_type="control_validation",
            description="Test evidence",
            source="test-suite",
        )
        assert item.control_id == "PI1.1"
        assert item.evidence_type == "control_validation"
        assert item.source == "test-suite"
        assert item.collected_by == "acgs2-soc2-auditor"
        assert item.hash_value == CONSTITUTIONAL_HASH
        assert item.constitutional_hash == CONSTITUTIONAL_HASH
        assert item.evidence_id.startswith("ev-")

    def test_collect_evidence_with_artifact_path(self):
        item = self.collector.collect_evidence(
            control_id="C1.1",
            evidence_type="log",
            description="Log evidence",
            source="audit-log",
            artifact_path="evidence/c/C1.1/",
        )
        assert item.artifact_path == "evidence/c/C1.1/"

    def test_collect_evidence_stores_in_internal_dict(self):
        item = self.collector.collect_evidence(
            control_id="A1.1",
            evidence_type="metric",
            description="Uptime metric",
            source="monitoring",
        )
        all_items = self.collector.get_all_evidence()
        assert item in all_items

    def test_get_evidence_for_control_filters_correctly(self):
        self.collector.collect_evidence("PI1.1", "type_a", "desc_a", "src_a")
        self.collector.collect_evidence("C1.1", "type_b", "desc_b", "src_b")
        self.collector.collect_evidence("PI1.1", "type_c", "desc_c", "src_c")

        pi_evidence = self.collector.get_evidence_for_control("PI1.1")
        assert len(pi_evidence) == 2
        assert all(e.control_id == "PI1.1" for e in pi_evidence)

    def test_get_evidence_for_control_returns_empty_when_none(self):
        result = self.collector.get_evidence_for_control("NONEXISTENT")
        assert result == []

    def test_validate_evidence_returns_false_for_missing_id(self):
        result = self.collector.validate_evidence("nonexistent-id", "reviewer@example.com")
        assert result is False

    def test_validate_evidence_sets_reviewer_and_validity(self):
        item = self.collector.collect_evidence("PI1.1", "type", "desc", "src")
        result = self.collector.validate_evidence(item.evidence_id, "auditor@example.com")
        assert result is True
        evidence = self.collector._evidence[item.evidence_id]
        assert evidence.reviewer == "auditor@example.com"
        assert evidence.is_valid is True
        assert evidence.review_date is not None

    def test_get_all_evidence_returns_all(self):
        for i in range(3):
            self.collector.collect_evidence(f"C{i}", "type", f"desc{i}", "src")
        assert len(self.collector.get_all_evidence()) == 3

    def test_multiple_collect_calls_produce_unique_ids(self):
        items = [self.collector.collect_evidence("PI1.1", "type", "desc", "src") for _ in range(10)]
        ids = {item.evidence_id for item in items}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# SOC2Auditor - initialization
# ---------------------------------------------------------------------------


class TestSOC2AuditorInit:
    def setup_method(self):
        self.auditor = SOC2Auditor()

    def test_constitutional_hash_set(self):
        assert self.auditor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_not_initialized_initially(self):
        assert self.auditor._initialized is False

    def test_has_control_validator(self):
        assert isinstance(self.auditor.control_validator, SOC2ControlValidator)

    def test_has_evidence_collector(self):
        assert isinstance(self.auditor.evidence_collector, SOC2EvidenceCollector)

    async def test_initialize_sets_flag(self):
        result = await self.auditor.initialize()
        assert result is True
        assert self.auditor._initialized is True

    async def test_initialize_idempotent(self):
        await self.auditor.initialize()
        # Second call should short-circuit
        result = await self.auditor.initialize()
        assert result is True

    async def test_initialize_populates_pi_controls(self):
        await self.auditor.initialize()
        assert len(self.auditor._pi_controls) == 3

    async def test_initialize_populates_c_controls(self):
        await self.auditor.initialize()
        assert len(self.auditor._c_controls) == 3

    async def test_initialize_populates_a_controls(self):
        await self.auditor.initialize()
        assert len(self.auditor._a_controls) == 3

    async def test_initialize_populates_data_classification(self):
        await self.auditor.initialize()
        assert len(self.auditor._data_classification) == 4


# ---------------------------------------------------------------------------
# SOC2Auditor - default control contents
# ---------------------------------------------------------------------------


class TestSOC2AuditorDefaultControls:
    def setup_method(self):
        self.auditor = SOC2Auditor()
        self.auditor._initialize_default_controls()
        self.auditor._initialize_data_classification()

    def test_pi_control_ids(self):
        assert set(self.auditor._pi_controls.keys()) == {"PI1.1", "PI1.2", "PI1.3"}

    def test_c_control_ids(self):
        assert set(self.auditor._c_controls.keys()) == {"C1.1", "C1.2", "C1.3"}

    def test_a_control_ids(self):
        assert set(self.auditor._a_controls.keys()) == {"A1.1", "A1.2", "A1.3"}

    def test_pi_controls_are_compliant(self):
        for ctrl in self.auditor._pi_controls.values():
            assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_c_controls_are_compliant(self):
        for ctrl in self.auditor._c_controls.values():
            assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_a_controls_are_compliant(self):
        for ctrl in self.auditor._a_controls.values():
            assert ctrl.implementation_status == ComplianceStatus.COMPLIANT

    def test_data_classification_entry_ids(self):
        assert set(self.auditor._data_classification.keys()) == {
            "dc-001",
            "dc-002",
            "dc-003",
            "dc-004",
        }

    def test_pii_classification_has_indicators(self):
        entry = self.auditor._data_classification["dc-002"]
        assert entry.classification == DataClassification.PII
        assert len(entry.pii_indicators) > 0

    def test_a1_1_uptime_above_target(self):
        ctrl = self.auditor._a_controls["A1.1"]
        assert ctrl.current_uptime >= ctrl.uptime_target


# ---------------------------------------------------------------------------
# SOC2Auditor - audit()
# ---------------------------------------------------------------------------


class TestSOC2AuditorAudit:
    async def test_audit_returns_assessment(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert assessment is not None

    async def test_audit_assessment_id_prefix(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert assessment.assessment_id.startswith("soc2-")

    async def test_audit_correct_system_name(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit(system_name="TestSystem")
        assert assessment.system_name == "TestSystem"

    async def test_audit_default_system_name(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert assessment.system_name == "ACGS-2"

    async def test_audit_controls_assessed_count(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        # 3 PI + 3 C + 3 A = 9
        assert assessment.controls_assessed == 9

    async def test_audit_all_compliant_by_default(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        # C1.2 has no retention_policy, so it lands as PARTIAL.
        # All others are fully compliant → 8 compliant, 1 partial, 0 non-compliant.
        assert assessment.controls_non_compliant == 0
        assert assessment.controls_compliant + assessment.controls_partial == 9

    async def test_audit_compliance_score_above_90(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        # With 8 compliant and 1 partial out of 9: (8 + 0.5) / 9 * 100 ≈ 94.44
        assert assessment.compliance_score > 90.0

    async def test_audit_constitutional_hash(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert assessment.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_audit_with_non_compliant_pi_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # Override PI1.1 to have failing checks → NON_COMPLIANT (covers line 442)
        auditor._pi_controls["PI1.1"].completeness_check = False
        auditor._pi_controls["PI1.1"].accuracy_check = False
        auditor._pi_controls["PI1.1"].timeliness_check = False
        auditor._pi_controls["PI1.1"].authorization_check = False
        assessment = await auditor.audit()
        assert assessment.controls_non_compliant >= 1

    async def test_audit_with_partial_pi_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # 3 of 4 checks → PARTIAL (covers line 440)
        auditor._pi_controls["PI1.1"].authorization_check = False
        assessment = await auditor.audit()
        assert assessment.controls_partial >= 1

    async def test_audit_findings_added_when_non_compliant(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # Make one control non-compliant
        auditor._pi_controls["PI1.1"].completeness_check = False
        auditor._pi_controls["PI1.1"].accuracy_check = False
        auditor._pi_controls["PI1.1"].timeliness_check = False
        auditor._pi_controls["PI1.1"].authorization_check = False
        assessment = await auditor.audit()
        assert len(assessment.findings) > 0
        assert "remediation" in assessment.findings[0]

    async def test_audit_no_findings_when_all_compliant(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        assert len(assessment.findings) == 0

    async def test_audit_with_non_compliant_c_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # 0 of 4 checks → NON_COMPLIANT (covers line 453)
        auditor._c_controls["C1.1"].encryption_at_rest = False
        auditor._c_controls["C1.1"].encryption_in_transit = False
        auditor._c_controls["C1.1"].access_controls = []
        auditor._c_controls["C1.1"].retention_policy = ""
        assessment = await auditor.audit()
        assert assessment.controls_non_compliant >= 1

    async def test_audit_with_partial_c_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        auditor._c_controls["C1.1"].encryption_at_rest = False
        auditor._c_controls["C1.1"].encryption_in_transit = False
        assessment = await auditor.audit()
        assert assessment.controls_partial >= 1

    async def test_audit_with_partial_a_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # 3 of 6 checks → PARTIAL (covers line 461-462)
        auditor._a_controls["A1.1"].current_uptime = 80.0  # fails uptime check
        auditor._a_controls["A1.1"].disaster_recovery_plan = False  # fails
        auditor._a_controls["A1.1"].monitoring_enabled = False  # fails
        assessment = await auditor.audit()
        assert assessment.controls_partial >= 1

    async def test_audit_with_non_compliant_a_control(self):
        auditor = SOC2Auditor()
        await auditor.initialize()
        # 1 of 6 checks → NON_COMPLIANT (covers lines 463-464)
        auditor._a_controls["A1.1"].current_uptime = 80.0  # fails
        auditor._a_controls["A1.1"].disaster_recovery_plan = False  # fails
        auditor._a_controls["A1.1"].monitoring_enabled = False  # fails
        auditor._a_controls["A1.1"].incident_response_plan = False  # fails
        auditor._a_controls["A1.1"].backup_procedures = []  # fails
        # Only capacity_planning=True remains → passed=1 → NON_COMPLIANT
        assessment = await auditor.audit()
        assert assessment.controls_non_compliant >= 1

    async def test_audit_evidence_collected(self):
        auditor = SOC2Auditor()
        # Pre-populate some evidence
        auditor.evidence_collector.collect_evidence("PI1.1", "type", "desc", "src")
        assessment = await auditor.audit()
        assert len(assessment.evidence_collected) >= 1

    async def test_audit_initializes_if_not_done(self):
        auditor = SOC2Auditor()
        assert auditor._initialized is False
        await auditor.audit()
        assert auditor._initialized is True


# ---------------------------------------------------------------------------
# SOC2Auditor - get controls
# ---------------------------------------------------------------------------


class TestSOC2AuditorGetControls:
    def setup_method(self):
        self.auditor = SOC2Auditor()
        self.auditor._initialize_default_controls()

    def test_get_pi_controls_returns_list(self):
        result = self.auditor.get_pi_controls()
        assert isinstance(result, list)
        assert len(result) == 3

    def test_get_c_controls_returns_list(self):
        result = self.auditor.get_c_controls()
        assert isinstance(result, list)
        assert len(result) == 3

    def test_get_a_controls_returns_list(self):
        result = self.auditor.get_a_controls()
        assert isinstance(result, list)
        assert len(result) == 3

    def test_get_pi_controls_are_correct_type(self):
        for ctrl in self.auditor.get_pi_controls():
            assert isinstance(ctrl, ProcessingIntegrityControl)

    def test_get_c_controls_are_correct_type(self):
        for ctrl in self.auditor.get_c_controls():
            assert isinstance(ctrl, ConfidentialityControl)

    def test_get_a_controls_are_correct_type(self):
        for ctrl in self.auditor.get_a_controls():
            assert isinstance(ctrl, AvailabilityControl)


# ---------------------------------------------------------------------------
# SOC2Auditor - validate_uptime_sla()
# ---------------------------------------------------------------------------


class TestSOC2AuditorValidateUptimeSLA:
    def setup_method(self):
        self.auditor = SOC2Auditor()
        self.auditor._initialize_default_controls()

    def test_uptime_sla_returns_dict(self):
        result = self.auditor.validate_uptime_sla()
        assert isinstance(result, dict)

    def test_uptime_sla_has_required_keys(self):
        result = self.auditor.validate_uptime_sla()
        required_keys = {
            "target_uptime",
            "controls_validated",
            "controls_meeting_sla",
            "average_uptime",
            "sla_compliant",
            "control_details",
            "constitutional_hash",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_uptime_sla_compliant_with_default_controls(self):
        result = self.auditor.validate_uptime_sla()
        assert result["sla_compliant"] is True

    def test_uptime_sla_average_uptime_computed(self):
        result = self.auditor.validate_uptime_sla()
        assert result["average_uptime"] > 0.0

    def test_uptime_sla_controls_validated_equals_a_control_count(self):
        result = self.auditor.validate_uptime_sla()
        assert result["controls_validated"] == len(self.auditor._a_controls)

    def test_uptime_sla_custom_target_below_average(self):
        result = self.auditor.validate_uptime_sla(target_uptime=99.0)
        assert result["target_uptime"] == 99.0
        assert result["sla_compliant"] is True

    def test_uptime_sla_custom_target_above_average_not_compliant(self):
        result = self.auditor.validate_uptime_sla(target_uptime=100.0)
        assert result["sla_compliant"] is False

    def test_uptime_sla_constitutional_hash_in_result(self):
        result = self.auditor.validate_uptime_sla()
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_uptime_sla_control_details_list(self):
        result = self.auditor.validate_uptime_sla()
        assert isinstance(result["control_details"], list)
        assert len(result["control_details"]) == 3

    def test_uptime_sla_control_detail_fields(self):
        result = self.auditor.validate_uptime_sla()
        detail = result["control_details"][0]
        assert "control_id" in detail
        assert "current_uptime" in detail
        assert "meets_sla" in detail
        assert "rto_minutes" in detail
        assert "rpo_minutes" in detail

    def test_uptime_sla_with_no_a_controls(self):
        auditor = SOC2Auditor()
        # No controls loaded
        result = auditor.validate_uptime_sla()
        assert result["controls_validated"] == 0
        assert result["average_uptime"] == 0.0
        assert result["sla_compliant"] is False


# ---------------------------------------------------------------------------
# SOC2Auditor - generate_evidence_package()
# ---------------------------------------------------------------------------


class TestSOC2AuditorGenerateEvidencePackage:
    def setup_method(self):
        self.auditor = SOC2Auditor()
        self.auditor._initialize_default_controls()
        self.auditor._initialize_data_classification()

    def test_generates_package(self):
        pkg = self.auditor.generate_evidence_package()
        assert pkg is not None

    def test_package_id_prefix(self):
        pkg = self.auditor.generate_evidence_package()
        assert pkg.package_id.startswith("evpkg-")

    def test_package_name_contains_period_days(self):
        pkg = self.auditor.generate_evidence_package(period_days=90)
        assert "90" in pkg.package_name

    def test_default_period_is_60_days(self):
        pkg = self.auditor.generate_evidence_package()
        assert "60" in pkg.package_name

    def test_evidence_items_collected_for_all_controls(self):
        pkg = self.auditor.generate_evidence_package()
        # 3 PI + 3 C + 3 A controls = 9 items
        assert len(pkg.evidence_items) == 9

    def test_pi_controls_evidence_populated(self):
        pkg = self.auditor.generate_evidence_package()
        assert len(pkg.pi_controls_evidence) == 3

    def test_c_controls_evidence_populated(self):
        pkg = self.auditor.generate_evidence_package()
        assert len(pkg.c_controls_evidence) == 3

    def test_a_controls_evidence_populated(self):
        pkg = self.auditor.generate_evidence_package()
        assert len(pkg.a_controls_evidence) == 3

    def test_uptime_metrics_populated(self):
        pkg = self.auditor.generate_evidence_package()
        assert len(pkg.uptime_metrics) == 3
        for _control_id, uptime in pkg.uptime_metrics.items():
            assert isinstance(uptime, float)

    def test_incident_log_has_package_generated_entry(self):
        pkg = self.auditor.generate_evidence_package()
        assert len(pkg.incident_log) == 1
        assert pkg.incident_log[0]["type"] == "package_generated"

    def test_incident_log_contains_constitutional_hash(self):
        pkg = self.auditor.generate_evidence_package()
        assert pkg.incident_log[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_completeness_score_above_zero(self):
        pkg = self.auditor.generate_evidence_package()
        assert pkg.completeness_score > 0.0

    def test_period_start_before_period_end(self):
        pkg = self.auditor.generate_evidence_package()
        assert pkg.period_start < pkg.period_end

    def test_custom_period_days(self):
        pkg30 = self.auditor.generate_evidence_package(period_days=30)
        pkg90 = self.auditor.generate_evidence_package(period_days=90)
        diff30 = (pkg30.period_end - pkg30.period_start).days
        diff90 = (pkg90.period_end - pkg90.period_start).days
        assert diff30 < diff90


# ---------------------------------------------------------------------------
# SOC2Auditor - data classification
# ---------------------------------------------------------------------------


class TestSOC2AuditorDataClassification:
    def setup_method(self):
        self.auditor = SOC2Auditor()
        self.auditor._initialize_data_classification()

    def test_get_data_classification_matrix_returns_list(self):
        result = self.auditor.get_data_classification_matrix()
        assert isinstance(result, list)
        assert len(result) == 4

    def test_classify_data_finds_exact_match(self):
        entry = self.auditor.classify_data("Agent Messages")
        assert entry is not None
        assert entry.data_type == "Agent Messages"

    def test_classify_data_case_insensitive(self):
        entry = self.auditor.classify_data("agent messages")
        assert entry is not None

    def test_classify_data_returns_none_for_unknown(self):
        entry = self.auditor.classify_data("Unknown Data Type XYZ")
        assert entry is None

    def test_classify_data_user_pii(self):
        entry = self.auditor.classify_data("User PII")
        assert entry is not None
        assert entry.classification == DataClassification.PII

    def test_classify_data_governance_decisions(self):
        entry = self.auditor.classify_data("Governance Decisions")
        assert entry is not None
        assert entry.classification == DataClassification.CONFIDENTIAL

    def test_classify_data_compliance_reports(self):
        entry = self.auditor.classify_data("Compliance Reports")
        assert entry is not None
        assert entry.classification == DataClassification.CONFIDENTIAL


# ---------------------------------------------------------------------------
# Singleton helpers: get_soc2_auditor / reset_soc2_auditor
# ---------------------------------------------------------------------------


class TestSingletonHelpers:
    def setup_method(self):
        reset_soc2_auditor()

    def teardown_method(self):
        reset_soc2_auditor()

    def test_get_soc2_auditor_returns_instance(self):
        auditor = get_soc2_auditor()
        assert isinstance(auditor, SOC2Auditor)

    def test_get_soc2_auditor_returns_same_instance(self):
        auditor1 = get_soc2_auditor()
        auditor2 = get_soc2_auditor()
        assert auditor1 is auditor2

    def test_reset_soc2_auditor_clears_singleton(self):
        auditor1 = get_soc2_auditor()
        reset_soc2_auditor()
        auditor2 = get_soc2_auditor()
        assert auditor1 is not auditor2

    def test_reset_soc2_auditor_after_reset_returns_new_instance(self):
        get_soc2_auditor()
        reset_soc2_auditor()
        auditor = get_soc2_auditor()
        assert isinstance(auditor, SOC2Auditor)


# ---------------------------------------------------------------------------
# Full integration: audit after generating evidence package
# ---------------------------------------------------------------------------


class TestSOC2FullIntegration:
    async def test_evidence_package_then_audit(self):
        auditor = SOC2Auditor()
        # initialize() loads default controls before generating the package
        await auditor.initialize()
        pkg = auditor.generate_evidence_package()
        assert len(pkg.evidence_items) > 0
        # Audit reuses the same evidence_collector - items should still be there
        assessment = await auditor.audit()
        assert len(assessment.evidence_collected) > 0

    async def test_audit_compliance_score_matches_compliant_fraction(self):
        auditor = SOC2Auditor()
        assessment = await auditor.audit()
        expected = (
            (assessment.controls_compliant + assessment.controls_partial * 0.5)
            / (assessment.controls_assessed)
            * 100
        )
        assert abs(assessment.compliance_score - round(expected, 2)) < 0.01

    async def test_uptime_sla_after_audit(self):
        auditor = SOC2Auditor()
        await auditor.audit()
        report = auditor.validate_uptime_sla()
        assert report["sla_compliant"] is True

    def test_evidence_package_evidence_collector_sync(self):
        auditor = SOC2Auditor()
        auditor._initialize_default_controls()
        pkg = auditor.generate_evidence_package()
        # The evidence collector should hold the same items as the package
        all_evidence = auditor.evidence_collector.get_all_evidence()
        assert len(all_evidence) == len(pkg.evidence_items)
