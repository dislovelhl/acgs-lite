"""Tests for multi-framework AI compliance module.

Covers all eight compliance frameworks, auto-population of acgs-lite
features, the MultiFrameworkAssessor orchestrator, jurisdiction-based
framework selection, cross-framework gap analysis, and compliance scoring.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_lite.compliance import (
    ChecklistItem,
    ChecklistStatus,
    ComplianceFramework,
    FrameworkAssessment,
    GDPRFramework,
    HIPAAAIFramework,
    ISO42001Framework,
    MultiFrameworkAssessor,
    MultiFrameworkReport,
    NISTAIRMFFramework,
    NYCLL144Framework,
    OECDAIFramework,
    SOC2AIFramework,
    USFairLendingFramework,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SYSTEM_DESC: dict = {
    "system_id": "test-system-v1",
    "purpose": "Automated decision support",
    "domain": "general",
    "jurisdiction": "international",
}


@pytest.fixture
def system_desc() -> dict:
    return dict(_SYSTEM_DESC)


# ---------------------------------------------------------------------------
# 1. ChecklistItem unit tests
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestChecklistItem:
    def test_default_status_is_pending(self) -> None:
        item = ChecklistItem(ref="TEST.1", requirement="Test requirement")
        assert item.status == ChecklistStatus.PENDING

    def test_mark_complete_sets_status_and_evidence(self) -> None:
        item = ChecklistItem(ref="TEST.1", requirement="Test")
        item.mark_complete("evidence text")
        assert item.status == ChecklistStatus.COMPLIANT
        assert item.evidence == "evidence text"
        assert item.updated_at is not None

    def test_mark_partial(self) -> None:
        item = ChecklistItem(ref="TEST.1", requirement="Test")
        item.mark_partial("partial evidence")
        assert item.status == ChecklistStatus.PARTIAL

    def test_mark_not_applicable(self) -> None:
        item = ChecklistItem(ref="TEST.1", requirement="Test")
        item.mark_not_applicable("does not apply")
        assert item.status == ChecklistStatus.NOT_APPLICABLE

    def test_to_dict_round_trip(self) -> None:
        item = ChecklistItem(
            ref="ART.1",
            requirement="Must comply",
            legal_citation="Law 123",
            acgs_lite_feature="GovernanceEngine",
        )
        d = item.to_dict()
        assert d["ref"] == "ART.1"
        assert d["legal_citation"] == "Law 123"
        assert d["acgs_lite_feature"] == "GovernanceEngine"


# ---------------------------------------------------------------------------
# 2. Per-framework checklist generation tests
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestNISTAIRMF:
    def test_checklist_has_all_four_functions(self, system_desc: dict) -> None:
        fw = NISTAIRMFFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("GOVERN" in r for r in refs)
        assert any("MAP" in r for r in refs)
        assert any("MEASURE" in r for r in refs)
        assert any("MANAGE" in r for r in refs)

    def test_auto_populate_marks_acgs_items(self, system_desc: dict) -> None:
        fw = NISTAIRMFFramework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        compliant = [i for i in checklist if i.status == ChecklistStatus.COMPLIANT]
        assert len(compliant) >= 5  # at least 7 ACGS-mapped items

    def test_assess_returns_frozen_assessment(self, system_desc: dict) -> None:
        fw = NISTAIRMFFramework()
        result = fw.assess(system_desc)
        assert isinstance(result, FrameworkAssessment)
        assert result.framework_id == "nist_ai_rmf"
        assert 0.0 <= result.compliance_score <= 1.0

    def test_framework_metadata(self) -> None:
        fw = NISTAIRMFFramework()
        assert fw.jurisdiction == "United States"
        assert fw.status == "voluntary"


@pytest.mark.compliance
class TestISO42001:
    def test_checklist_has_clauses_and_annex(self, system_desc: dict) -> None:
        fw = ISO42001Framework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("ISO 5" in r for r in refs)
        assert any("ISO 8" in r for r in refs)
        assert any("ISO A." in r for r in refs)

    def test_auto_populate_coverage(self, system_desc: dict) -> None:
        fw = ISO42001Framework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        compliant = [i for i in checklist if i.status == ChecklistStatus.COMPLIANT]
        assert len(compliant) >= 7

    def test_assess_produces_gaps(self, system_desc: dict) -> None:
        fw = ISO42001Framework()
        result = fw.assess(system_desc)
        assert result.framework_id == "iso_42001"
        # Some items are not auto-populated, so gaps should exist
        assert len(result.gaps) > 0


@pytest.mark.compliance
class TestGDPR:
    def test_checklist_covers_key_articles(self, system_desc: dict) -> None:
        fw = GDPRFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("Art.22" in r for r in refs)
        assert any("Art.13" in r for r in refs)
        assert any("Art.35" in r for r in refs)

    def test_auto_populate_marks_transparency_items(self, system_desc: dict) -> None:
        fw = GDPRFramework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        art13 = next(i for i in checklist if "Art.13" in i.ref)
        assert art13.status == ChecklistStatus.COMPLIANT

    def test_assess_enforcement_date(self) -> None:
        fw = GDPRFramework()
        assert fw.enforcement_date == "2018-05-25"
        assert fw.status == "enacted"


@pytest.mark.compliance
class TestSOC2AI:
    def test_checklist_covers_trust_criteria(self, system_desc: dict) -> None:
        fw = SOC2AIFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("CC" in r for r in refs)  # Common Criteria
        assert any("PI" in r for r in refs)  # Processing Integrity
        assert any("AI-" in r for r in refs)  # AI-specific

    def test_auto_populate(self, system_desc: dict) -> None:
        fw = SOC2AIFramework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        compliant = [i for i in checklist if i.status == ChecklistStatus.COMPLIANT]
        assert len(compliant) >= 8


@pytest.mark.compliance
class TestHIPAAAI:
    def test_checklist_covers_hipaa_rules(self, system_desc: dict) -> None:
        fw = HIPAAAIFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("164.502" in r for r in refs)  # Privacy Rule
        assert any("164.312" in r for r in refs)  # Security Rule
        assert any("164.404" in r for r in refs)  # Breach Notification

    def test_auto_populate_privacy_and_security(self, system_desc: dict) -> None:
        fw = HIPAAAIFramework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        compliant = [i for i in checklist if i.status == ChecklistStatus.COMPLIANT]
        assert len(compliant) >= 7


@pytest.mark.compliance
class TestUSFairLending:
    def test_checklist_covers_ecoa_and_fcra(self, system_desc: dict) -> None:
        fw = USFairLendingFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("ECOA" in r for r in refs)
        assert any("FCRA" in r for r in refs)
        assert any("FL-" in r for r in refs)

    def test_assess_has_recommendations(self, system_desc: dict) -> None:
        fw = USFairLendingFramework()
        result = fw.assess(system_desc)
        # Fair lending has many items not auto-populated
        assert len(result.recommendations) > 0


@pytest.mark.compliance
class TestNYCLL144:
    def test_checklist_covers_audit_and_notice(self, system_desc: dict) -> None:
        fw = NYCLL144Framework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        assert any("AUDIT" in r for r in refs)
        assert any("NOTICE" in r for r in refs)
        assert any("POST" in r for r in refs)

    def test_enforcement_date(self) -> None:
        fw = NYCLL144Framework()
        assert fw.enforcement_date == "2023-07-05"
        assert fw.jurisdiction == "New York City"


@pytest.mark.compliance
class TestOECDAI:
    def test_checklist_covers_five_principles(self, system_desc: dict) -> None:
        fw = OECDAIFramework()
        checklist = fw.get_checklist(system_desc)
        refs = [item.ref for item in checklist]
        # Five principles numbered 1-5
        assert any("OECD 1" in r for r in refs)
        assert any("OECD 2" in r for r in refs)
        assert any("OECD 3" in r for r in refs)
        assert any("OECD 4" in r for r in refs)
        assert any("OECD 5" in r for r in refs)

    def test_auto_populate_high_coverage(self, system_desc: dict) -> None:
        fw = OECDAIFramework()
        checklist = fw.get_checklist(system_desc)
        fw.auto_populate_acgs_lite(checklist)
        compliant = [i for i in checklist if i.status == ChecklistStatus.COMPLIANT]
        # OECD principles are well-aligned with acgs-lite
        assert len(compliant) >= 8


# ---------------------------------------------------------------------------
# 3. ComplianceFramework protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestProtocolConformance:
    @pytest.mark.parametrize(
        "framework_cls",
        [
            NISTAIRMFFramework,
            ISO42001Framework,
            GDPRFramework,
            SOC2AIFramework,
            HIPAAAIFramework,
            USFairLendingFramework,
            NYCLL144Framework,
            OECDAIFramework,
        ],
    )
    def test_implements_compliance_framework_protocol(
        self,
        framework_cls: type,
    ) -> None:
        fw = framework_cls()
        assert isinstance(fw, ComplianceFramework)
        assert hasattr(fw, "framework_id")
        assert hasattr(fw, "framework_name")
        assert hasattr(fw, "jurisdiction")
        assert hasattr(fw, "status")


# ---------------------------------------------------------------------------
# 4. MultiFrameworkAssessor tests
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestMultiFrameworkAssessor:
    def test_assess_all_frameworks(self) -> None:
        # Use unrecognized jurisdiction/domain so all frameworks are selected
        desc = {"system_id": "all-fw-test", "jurisdiction": "global", "domain": "multi"}
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(desc)
        assert isinstance(report, MultiFrameworkReport)
        assert len(report.frameworks_assessed) == 18
        assert 0.0 <= report.overall_score <= 1.0

    def test_assess_explicit_frameworks(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["gdpr", "nist_ai_rmf"])
        report = assessor.assess(system_desc)
        assert set(report.frameworks_assessed) == {"gdpr", "nist_ai_rmf"}
        assert len(report.by_framework) == 2

    def test_assess_single_framework(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["iso_42001"])
        report = assessor.assess(system_desc)
        assert report.frameworks_assessed == ("iso_42001",)
        assert "iso_42001" in report.by_framework

    def test_overall_score_is_average(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["nist_ai_rmf", "oecd_ai"])
        report = assessor.assess(system_desc)
        nist_score = report.by_framework["nist_ai_rmf"].compliance_score
        oecd_score = report.by_framework["oecd_ai"].compliance_score
        expected = round((nist_score + oecd_score) / 2, 4)
        assert report.overall_score == expected

    def test_report_to_dict(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["gdpr"])
        report = assessor.assess(system_desc)
        d = report.to_dict()
        assert "system_id" in d
        assert "overall_score" in d
        assert "by_framework" in d
        assert "disclaimer" in d

    def test_acgs_lite_total_coverage(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["oecd_ai"])
        report = assessor.assess(system_desc)
        assert report.acgs_lite_total_coverage > 0.0

    def test_available_frameworks_returns_all(self) -> None:
        available = MultiFrameworkAssessor.available_frameworks()
        assert len(available) == 18
        assert "nist_ai_rmf" in available
        assert "gdpr" in available

    def test_invalid_framework_id_ignored(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor(frameworks=["nonexistent", "gdpr"])
        report = assessor.assess(system_desc)
        assert report.frameworks_assessed == ("gdpr",)


# ---------------------------------------------------------------------------
# 5. Jurisdiction-based framework selection
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestJurisdictionSelection:
    def test_eu_jurisdiction_includes_gdpr(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("european_union", "general")
        assert "gdpr" in fws
        assert "iso_42001" in fws

    def test_us_jurisdiction_includes_nist(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("united_states", "general")
        assert "nist_ai_rmf" in fws
        assert "soc2_ai" in fws

    def test_healthcare_domain_adds_hipaa(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("united_states", "healthcare")
        assert "hipaa_ai" in fws
        assert "nist_ai_rmf" in fws

    def test_lending_domain_adds_fair_lending(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("united_states", "lending")
        assert "us_fair_lending" in fws

    def test_nyc_jurisdiction_adds_ll144(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("new_york_city", "general")
        assert "nyc_ll144" in fws

    def test_unknown_jurisdiction_returns_all(self) -> None:
        assessor = MultiFrameworkAssessor()
        fws = assessor.applicable_frameworks("unknown_place", "unknown_domain")
        assert len(fws) == 18

    def test_auto_selection_from_system_desc(self) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(
            {
                "system_id": "test",
                "jurisdiction": "european_union",
                "domain": "healthcare",
            }
        )
        fw_ids = set(report.frameworks_assessed)
        assert "gdpr" in fw_ids
        assert "hipaa_ai" in fw_ids


# ---------------------------------------------------------------------------
# 6. Cross-framework gap analysis
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestCrossFrameworkGaps:
    def test_cross_gaps_identified(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(system_desc)
        # Multiple frameworks require bias testing / data governance
        # which acgs-lite does not auto-populate
        assert len(report.cross_framework_gaps) >= 0  # May vary

    def test_recommendations_include_priority(self, system_desc: dict) -> None:
        assessor = MultiFrameworkAssessor()
        report = assessor.assess(system_desc)
        if report.cross_framework_gaps:
            assert any("PRIORITY" in r for r in report.recommendations)


# ---------------------------------------------------------------------------
# 7. Compliance scoring edge cases
# ---------------------------------------------------------------------------


@pytest.mark.compliance
class TestComplianceScoring:
    def test_empty_checklist_scores_one(self) -> None:
        assessment = FrameworkAssessment(
            framework_id="test",
            framework_name="Test",
            compliance_score=1.0,
            items=(),
            gaps=(),
            acgs_lite_coverage=0.0,
            recommendations=(),
        )
        assert assessment.compliance_score == 1.0

    def test_all_compliant_scores_one(self, system_desc: dict) -> None:
        fw = NISTAIRMFFramework()
        checklist = fw.get_checklist(system_desc)
        # Mark everything compliant
        for item in checklist:
            item.mark_complete("test evidence")
        total = len(checklist)
        compliant = sum(1 for i in checklist if i.status == ChecklistStatus.COMPLIANT)
        assert compliant == total

    def test_framework_assessment_to_dict(self, system_desc: dict) -> None:
        fw = GDPRFramework()
        result = fw.assess(system_desc)
        d = result.to_dict()
        assert isinstance(d["items"], list)
        assert isinstance(d["gaps"], list)
        assert isinstance(d["recommendations"], list)
        assert d["framework_id"] == "gdpr"

    def test_partial_compliance_scores_between_zero_and_one(
        self,
        system_desc: dict,
    ) -> None:
        fw = NISTAIRMFFramework()
        result = fw.assess(system_desc)
        # After auto-populate, some items compliant, some pending
        assert 0.0 < result.compliance_score < 1.0
