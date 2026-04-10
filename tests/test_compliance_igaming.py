"""Tests for the iGaming compliance framework module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_lite.compliance.base import ChecklistStatus, ComplianceFramework, FrameworkAssessment
from acgs_lite.compliance.igaming import IGamingFramework, infer_risk_tier
from acgs_lite.compliance.multi_framework import MultiFrameworkAssessor
from acgs_lite.compliance.obligation_mappings import get_obligations_for_refs
from acgs_lite.compliance.runtime_obligations import ObligationType

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestIGamingFrameworkProtocol:
    def test_satisfies_compliance_framework_protocol(self) -> None:
        framework = IGamingFramework()
        assert isinstance(framework, ComplianceFramework)

    def test_class_attributes(self) -> None:
        fw = IGamingFramework()
        assert fw.framework_id == "igaming"
        assert fw.framework_name == "iGaming Compliance (UKGC LCCP + Responsible Gambling)"
        assert fw.jurisdiction == "united_kingdom"
        assert fw.status == "proposed"
        assert fw.enforcement_date is None


# ---------------------------------------------------------------------------
# get_checklist
# ---------------------------------------------------------------------------


class TestGetChecklist:
    def test_sports_betting_returns_minimum_items(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "sports_betting"})
        assert len(items) >= 15

    def test_casino_returns_correct_refs(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "casino"})
        refs = {item.ref for item in items}
        # Core RG refs must be present
        assert "IGAMING-RG-1.1" in refs
        assert "IGAMING-RG-1.2" in refs
        assert "IGAMING-RG-1.3" in refs
        # KYC refs
        assert "IGAMING-KYC-2.1" in refs
        assert "IGAMING-KYC-2.2" in refs
        # AI refs
        assert "IGAMING-AI-4.1" in refs
        assert "IGAMING-AI-4.3" in refs

    def test_all_items_have_legal_citation(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        for item in items:
            assert item.legal_citation, f"{item.ref} missing legal_citation"

    def test_at_least_three_blocking_items(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "gambling"})
        blocking = [i for i in items if i.blocking]
        assert len(blocking) >= 3

    def test_blocking_items_include_self_exclusion_and_age_verification(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "gambling"})
        blocking_refs = {i.ref for i in items if i.blocking}
        assert "IGAMING-RG-1.1" in blocking_refs  # self-exclusion
        assert "IGAMING-KYC-2.1" in blocking_refs  # age verification
        assert "IGAMING-AI-4.3" in blocking_refs  # no targeting vulnerable players

    def test_checklist_items_start_as_pending(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "casino"})
        pending = [i for i in items if i.status == ChecklistStatus.PENDING]
        # Before auto_populate, all items without acgs_lite_feature are PENDING
        assert len(pending) > 0


# ---------------------------------------------------------------------------
# auto_populate_acgs_lite
# ---------------------------------------------------------------------------


class TestAutoPopulate:
    def test_marks_at_least_five_items_compliant(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({"domain": "gambling"})
        fw.auto_populate_acgs_lite(items)
        compliant = [i for i in items if i.status == ChecklistStatus.COMPLIANT]
        assert len(compliant) >= 5

    def test_auto_populated_items_have_evidence(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        fw.auto_populate_acgs_lite(items)
        for item in items:
            if item.status == ChecklistStatus.COMPLIANT:
                assert item.evidence, f"{item.ref} is COMPLIANT but has no evidence"

    def test_auto_populate_idempotent(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        fw.auto_populate_acgs_lite(items)
        count_first = sum(1 for i in items if i.status == ChecklistStatus.COMPLIANT)
        fw.auto_populate_acgs_lite(items)
        count_second = sum(1 for i in items if i.status == ChecklistStatus.COMPLIANT)
        assert count_first == count_second

    def test_rg_11_marked_compliant_by_governance_engine(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        fw.auto_populate_acgs_lite(items)
        rg11 = next(i for i in items if i.ref == "IGAMING-RG-1.1")
        assert rg11.status == ChecklistStatus.COMPLIANT
        assert "GovernanceEngine" in (rg11.evidence or "")

    def test_ai_43_marked_compliant_by_governance_engine(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        fw.auto_populate_acgs_lite(items)
        ai43 = next(i for i in items if i.ref == "IGAMING-AI-4.3")
        assert ai43.status == ChecklistStatus.COMPLIANT

    def test_kyc_22_marked_compliant_by_audit_log(self) -> None:
        fw = IGamingFramework()
        items = fw.get_checklist({})
        fw.auto_populate_acgs_lite(items)
        kyc22 = next(i for i in items if i.ref == "IGAMING-KYC-2.2")
        assert kyc22.status == ChecklistStatus.COMPLIANT
        assert "AuditLog" in (kyc22.evidence or "")


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------


class TestAssess:
    def test_returns_framework_assessment(self) -> None:
        fw = IGamingFramework()
        result = fw.assess(
            {
                "system_id": "bet365",
                "domain": "gambling",
                "jurisdiction": "united_kingdom",
            }
        )
        assert isinstance(result, FrameworkAssessment)

    def test_framework_id_is_igaming(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "bet365", "domain": "gambling"})
        assert result.framework_id == "igaming"

    def test_compliance_score_between_zero_and_one(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test"})
        assert 0.0 <= result.compliance_score <= 1.0

    def test_acgs_lite_coverage_greater_than_zero(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test"})
        assert result.acgs_lite_coverage > 0.0

    def test_items_tuple_populated(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test", "domain": "casino"})
        assert len(result.items) >= 15

    def test_items_are_dicts_with_expected_keys(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test"})
        for item in result.items:
            assert "ref" in item
            assert "status" in item
            assert "blocking" in item
            assert "requirement" in item

    def test_assessed_at_is_iso_timestamp(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test"})
        # Basic smoke test: string, non-empty, contains 'T'
        assert isinstance(result.assessed_at, str)
        assert "T" in result.assessed_at

    def test_gaps_only_contain_blocking_items(self) -> None:
        fw = IGamingFramework()
        result = fw.assess({"system_id": "test"})
        # All gaps should correspond to blocking items that are not compliant
        for gap in result.gaps:
            # Gap format: "IGAMING-XY-z.z: requirement text..."
            ref = gap.split(":")[0]
            matching = [i for i in result.items if i.get("ref") == ref]
            if matching:
                assert matching[0].get("blocking") is True


# ---------------------------------------------------------------------------
# infer_risk_tier
# ---------------------------------------------------------------------------


class TestInferRiskTier:
    @pytest.mark.parametrize(
        "domain,expected",
        [
            ("sports_betting", "HIGH"),
            ("gambling", "HIGH"),
            ("casino", "HIGH"),
            ("betting", "HIGH"),
            ("igaming", "MEDIUM"),
            ("other", "LOW"),
            ("saas", "LOW"),
            ("healthcare", "LOW"),
            ("", "LOW"),
        ],
    )
    def test_risk_tier_by_domain(self, domain: str, expected: str) -> None:
        result = infer_risk_tier({"domain": domain})
        assert result == expected

    def test_sports_betting_is_high(self) -> None:
        assert infer_risk_tier({"domain": "sports_betting"}) == "HIGH"

    def test_other_is_low(self) -> None:
        assert infer_risk_tier({"domain": "other"}) == "LOW"

    def test_empty_description_is_low(self) -> None:
        assert infer_risk_tier({}) == "LOW"


# ---------------------------------------------------------------------------
# MultiFrameworkAssessor integration
# ---------------------------------------------------------------------------


class TestMultiFrameworkIntegration:
    def test_gambling_domain_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "domain": "gambling",
                "jurisdiction": "united_kingdom",
            }
        )
        assert "igaming" in report.frameworks_assessed

    def test_united_kingdom_jurisdiction_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "jurisdiction": "united_kingdom",
            }
        )
        assert "igaming" in report.frameworks_assessed

    def test_sports_betting_domain_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "domain": "sports_betting",
            }
        )
        assert "igaming" in report.frameworks_assessed

    def test_casino_domain_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "domain": "casino",
            }
        )
        assert "igaming" in report.frameworks_assessed

    def test_igaming_framework_in_by_framework(self) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["igaming"])
        report = assessor.assess({"system_id": "test"})
        assert "igaming" in report.by_framework
        assert report.by_framework["igaming"].framework_id == "igaming"

    def test_available_frameworks_includes_igaming(self) -> None:
        available = MultiFrameworkAssessor.available_frameworks()
        assert "igaming" in available

    def test_malta_jurisdiction_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "jurisdiction": "malta",
            }
        )
        assert "igaming" in report.frameworks_assessed

    def test_gibraltar_jurisdiction_includes_igaming(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "jurisdiction": "gibraltar",
            }
        )
        assert "igaming" in report.frameworks_assessed


# ---------------------------------------------------------------------------
# Obligation mappings
# ---------------------------------------------------------------------------


class TestObligationMappings:
    def test_igaming_rg_11_maps_to_cool_off(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-RG-1.1"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.COOL_OFF

    def test_igaming_rg_12_maps_to_cool_off(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-RG-1.2"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.COOL_OFF

    def test_igaming_rg_13_maps_to_spend_limit(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-RG-1.3"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.SPEND_LIMIT

    def test_igaming_kyc_21_maps_to_consent_check(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-KYC-2.1"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.CONSENT_CHECK

    def test_igaming_ai_41_maps_to_hitl_required(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-AI-4.1"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.HITL_REQUIRED

    def test_igaming_ai_43_maps_to_hitl_required(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-AI-4.3"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.HITL_REQUIRED

    def test_obligations_have_correct_framework_id(self) -> None:
        refs = [
            "IGAMING-RG-1.1",
            "IGAMING-RG-1.2",
            "IGAMING-RG-1.3",
            "IGAMING-KYC-2.1",
            "IGAMING-AI-4.1",
            "IGAMING-AI-4.3",
        ]
        obligations = get_obligations_for_refs(refs)
        for ob in obligations:
            assert ob.framework_id == "igaming"

    def test_unknown_ref_returns_empty_list(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-UNKNOWN-99.9"])
        assert obligations == []

    def test_mixed_refs_returns_only_known(self) -> None:
        obligations = get_obligations_for_refs(["IGAMING-RG-1.1", "IGAMING-BOGUS-0.0"])
        assert len(obligations) == 1
        assert obligations[0].obligation_type == ObligationType.COOL_OFF
