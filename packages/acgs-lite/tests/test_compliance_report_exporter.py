"""Regression tests for ComplianceReportExporter.

Covers all three output formats (text / markdown / json), file output helpers,
and the single-framework static helpers.

Also covers the EU AI Act ``unacceptable`` tier fix and the evidence→assessor
integration (``_evidence`` key in system_description).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acgs_lite.compliance import (
    MultiFrameworkAssessor,
    ComplianceReportExporter,
    EUAIActFramework,
    GDPRFramework,
    NISTAIRMFFramework,
)
from acgs_lite.compliance.report_exporter import ComplianceReportExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_report():
    """Minimal single-framework report for fast, repeatable tests."""
    assessor = MultiFrameworkAssessor(frameworks=["gdpr", "nist_ai_rmf"])
    return assessor.assess({"system_id": "report-test", "domain": "healthcare"})


@pytest.fixture(scope="module")
def single_framework_assessment():
    fw = GDPRFramework()
    return fw.assess({"system_id": "gdpr-only"})


@pytest.fixture(scope="module")
def exporter(sample_report):
    return ComplianceReportExporter(sample_report, title="Test Report")


# ---------------------------------------------------------------------------
# to_text()
# ---------------------------------------------------------------------------


class TestToText:
    def test_returns_non_empty_string(self, exporter):
        out = exporter.to_text()
        assert isinstance(out, str)
        assert len(out) > 100

    def test_contains_system_id(self, exporter):
        assert "report-test" in exporter.to_text()

    def test_contains_framework_names(self, exporter):
        out = exporter.to_text()
        assert "GDPR" in out or "General Data Protection" in out

    def test_contains_score_percentage(self, exporter):
        out = exporter.to_text()
        assert "%" in out

    def test_contains_title(self, exporter):
        assert "Test Report" in exporter.to_text()

    def test_contains_acgs_coverage(self, exporter):
        out = exporter.to_text()
        # Should mention coverage or auto-coverage
        assert "coverage" in out.lower() or "auto" in out.lower()

    def test_contains_disclaimer(self, exporter):
        out = exporter.to_text()
        assert "legal advice" in out.lower() or "disclaimer" in out.lower() or \
               "indicative" in out.lower()

    def test_no_trailing_exception(self, exporter):
        """Should not raise."""
        exporter.to_text()


# ---------------------------------------------------------------------------
# to_markdown()
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_returns_non_empty_string(self, exporter):
        out = exporter.to_markdown()
        assert isinstance(out, str)
        assert len(out) > 100

    def test_contains_markdown_headers(self, exporter):
        out = exporter.to_markdown()
        assert "#" in out

    def test_contains_system_id(self, exporter):
        assert "report-test" in exporter.to_markdown()

    def test_contains_table_syntax(self, exporter):
        out = exporter.to_markdown()
        assert "|" in out  # GFM tables

    def test_contains_status_badge_or_emoji(self, exporter):
        out = exporter.to_markdown()
        # Report exporter uses 🔵/🟢/🟡/🔴 for score bands and ⚠️ for gaps
        assert any(c in out for c in ("🔵", "🟢", "🟡", "🔴", "⚠️", "%", "gaps", "Gaps"))

    def test_different_from_text(self, exporter):
        assert exporter.to_markdown() != exporter.to_text()

    def test_contains_framework_ids(self, exporter):
        out = exporter.to_markdown()
        assert "gdpr" in out.lower() or "GDPR" in out


# ---------------------------------------------------------------------------
# to_json()
# ---------------------------------------------------------------------------


class TestToJson:
    def test_returns_valid_json(self, exporter):
        out = exporter.to_json()
        data = json.loads(out)  # must not raise
        assert isinstance(data, dict)

    def test_required_top_level_keys(self, exporter):
        data = json.loads(exporter.to_json())
        for key in ("system_id", "overall_score", "frameworks_assessed",
                    "by_framework", "report_title", "generated_at"):
            assert key in data, f"Missing key: {key}"

    def test_system_id_correct(self, exporter):
        data = json.loads(exporter.to_json())
        assert data["system_id"] == "report-test"

    def test_overall_score_in_range(self, exporter):
        data = json.loads(exporter.to_json())
        assert 0.0 <= data["overall_score"] <= 1.0

    def test_report_title_correct(self, exporter):
        data = json.loads(exporter.to_json())
        assert data["report_title"] == "Test Report"

    def test_by_framework_has_both_frameworks(self, exporter):
        data = json.loads(exporter.to_json())
        assert "gdpr" in data["by_framework"]
        assert "nist_ai_rmf" in data["by_framework"]

    def test_framework_entry_has_required_keys(self, exporter):
        data = json.loads(exporter.to_json())
        fw = data["by_framework"]["gdpr"]
        for key in ("framework_id", "framework_name", "compliance_score", "items", "gaps"):
            assert key in fw, f"Missing key in framework entry: {key}"

    def test_indent_parameter(self, exporter):
        compact = exporter.to_json(indent=0)
        pretty = exporter.to_json(indent=4)
        assert len(pretty) > len(compact)


# ---------------------------------------------------------------------------
# File output helpers
# ---------------------------------------------------------------------------


class TestFileOutput:
    def test_to_text_file(self, tmp_path, exporter):
        out = exporter.to_text_file(tmp_path / "report.txt")
        assert out.exists()
        assert out.read_text(encoding="utf-8") == exporter.to_text()

    def test_to_markdown_file(self, tmp_path, exporter):
        out = exporter.to_markdown_file(tmp_path / "report.md")
        assert out.exists()
        assert "#" in out.read_text(encoding="utf-8")

    def test_to_json_file(self, tmp_path, exporter):
        out = exporter.to_json_file(tmp_path / "report.json")
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "overall_score" in data

    def test_to_text_file_creates_parent_dirs(self, tmp_path, exporter):
        deep = tmp_path / "a" / "b" / "c" / "report.txt"
        exporter.to_text_file(deep)
        assert deep.exists()

    def test_to_json_file_returns_path(self, tmp_path, exporter):
        p = exporter.to_json_file(tmp_path / "r.json")
        assert isinstance(p, Path)

    def test_to_text_file_accepts_string_path(self, tmp_path, exporter):
        exporter.to_text_file(str(tmp_path / "str.txt"))
        assert (tmp_path / "str.txt").exists()


# ---------------------------------------------------------------------------
# Static single-framework helpers
# ---------------------------------------------------------------------------


class TestStaticHelpers:
    def test_framework_summary_text_returns_string(self, single_framework_assessment):
        out = ComplianceReportExporter.framework_summary_text(single_framework_assessment)
        assert isinstance(out, str)
        assert len(out) > 10

    def test_framework_summary_text_contains_score(self, single_framework_assessment):
        out = ComplianceReportExporter.framework_summary_text(single_framework_assessment)
        assert "%" in out

    def test_framework_summary_markdown_contains_header(self, single_framework_assessment):
        out = ComplianceReportExporter.framework_summary_markdown(single_framework_assessment)
        assert "#" in out or "|" in out

    def test_framework_summary_markdown_different_from_text(self, single_framework_assessment):
        text = ComplianceReportExporter.framework_summary_text(single_framework_assessment)
        md = ComplianceReportExporter.framework_summary_markdown(single_framework_assessment)
        assert text != md

    def test_static_helpers_work_with_nist(self):
        fw = NISTAIRMFFramework()
        a = fw.assess({"system_id": "nist-test"})
        text = ComplianceReportExporter.framework_summary_text(a)
        assert "NIST" in text or "nist" in text.lower()


# ---------------------------------------------------------------------------
# Default title
# ---------------------------------------------------------------------------


class TestDefaultTitle:
    def test_default_title_contains_acgs(self, sample_report):
        e = ComplianceReportExporter(sample_report)
        assert "ACGS" in e.to_text()

    def test_custom_title_used(self, sample_report):
        e = ComplianceReportExporter(sample_report, title="Audit Report Q1 2026")
        assert "Audit Report Q1 2026" in e.to_text()


# ---------------------------------------------------------------------------
# EU AI Act: unacceptable tier
# ---------------------------------------------------------------------------


class TestEUAIActUnacceptableTier:
    """Verify the unacceptable tier fix: only Art.5 items, no Art.9–15."""

    def _checklist_refs(self, system_description: dict) -> set[str]:
        fw = EUAIActFramework()
        return {i.ref for i in fw.get_checklist(system_description)}

    def test_unacceptable_only_art5(self):
        refs = self._checklist_refs({"risk_tier": "unacceptable"})
        non_art5 = {r for r in refs if not r.startswith("EU-AIA Art.5")}
        assert non_art5 == set(), (
            f"Non-Art.5 refs leaked into unacceptable checklist: {non_art5}"
        )

    def test_unacceptable_includes_all_art5_items(self):
        refs = self._checklist_refs({"risk_tier": "unacceptable"})
        assert "EU-AIA Art.5(1)" in refs
        assert "EU-AIA Art.5(2)" in refs

    def test_unacceptable_excludes_art9(self):
        refs = self._checklist_refs({"risk_tier": "unacceptable"})
        assert "EU-AIA Art.9(1)" not in refs

    def test_unacceptable_excludes_art14(self):
        refs = self._checklist_refs({"risk_tier": "unacceptable"})
        assert "EU-AIA Art.14(1)" not in refs

    def test_unacceptable_excludes_art50(self):
        """Art.50 (transparency for chatbots) doesn't apply to prohibited systems."""
        refs = self._checklist_refs({"risk_tier": "unacceptable"})
        assert "EU-AIA Art.50(1)" not in refs

    def test_unacceptable_smaller_than_high(self):
        unacceptable_refs = self._checklist_refs({"risk_tier": "unacceptable"})
        high_refs = self._checklist_refs({"risk_tier": "high"})
        assert len(unacceptable_refs) < len(high_refs)

    def test_unacceptable_smaller_than_limited(self):
        """Unacceptable should be even smaller than limited (Art.5 only vs Art.5+Art.50)."""
        unacceptable_refs = self._checklist_refs({"risk_tier": "unacceptable"})
        limited_refs = self._checklist_refs({"risk_tier": "limited"})
        assert len(unacceptable_refs) < len(limited_refs)

    def test_tier_ordering_item_counts(self):
        """Item count order: unacceptable < limited < high."""
        fw = EUAIActFramework()
        n_unacceptable = len(fw.get_checklist({"risk_tier": "unacceptable"}))
        n_limited = len(fw.get_checklist({"risk_tier": "limited"}))
        n_high = len(fw.get_checklist({"risk_tier": "high"}))
        assert n_unacceptable < n_limited < n_high, (
            f"Expected unacceptable({n_unacceptable}) < limited({n_limited}) < high({n_high})"
        )

    def test_assess_unacceptable_returns_valid_assessment(self):
        fw = EUAIActFramework()
        a = fw.assess({"system_id": "prohibited-sys", "risk_tier": "unacceptable"})
        assert a.framework_id == "eu_ai_act"
        assert 0.0 <= a.compliance_score <= 1.0
        # All items should be Art.5
        for item in a.items:
            assert item["ref"].startswith("EU-AIA Art.5"), (
                f"Non-Art.5 item in unacceptable assessment: {item['ref']}"
            )


# ---------------------------------------------------------------------------
# Evidence → MultiFrameworkAssessor integration
# ---------------------------------------------------------------------------


class TestEvidenceIntegration:
    """Verify that _evidence key in system_description upgrades PENDING items."""

    def test_evidence_upgrades_pending_to_compliant(self):
        """An EvidenceItem for a PENDING article ref should mark it COMPLIANT."""
        from acgs_lite.compliance.evidence import EvidenceBundle, EvidenceItem

        # Run without evidence first to get baseline
        assessor = MultiFrameworkAssessor(frameworks=["gdpr"])
        baseline = assessor.assess({"system_id": "ev-test"})
        baseline_score = baseline.by_framework["gdpr"].compliance_score

        # Find a PENDING item's ref
        gdpr_items = baseline.by_framework["gdpr"].items
        pending = [i for i in gdpr_items if i["status"] == "pending"]
        if not pending:
            pytest.skip("All GDPR items already COMPLIANT — nothing to upgrade")
        target_ref = pending[0]["ref"]

        # Build a bundle with evidence for that ref
        bundle = EvidenceBundle(
            system_id="ev-test",
            collected_at="2026-03-29T00:00:00+00:00",
            items=(
                EvidenceItem(
                    framework_id="gdpr",
                    article_refs=(target_ref,),
                    source="test:manual",
                    description=f"Manual evidence satisfying {target_ref}",
                    confidence=0.9,
                ),
            ),
        )

        enriched = assessor.assess({"system_id": "ev-test", "_evidence": bundle})
        enriched_score = enriched.by_framework["gdpr"].compliance_score

        assert enriched_score >= baseline_score, (
            f"Evidence did not improve score: baseline={baseline_score} enriched={enriched_score}"
        )

        # The target item should now be COMPLIANT
        enriched_items = enriched.by_framework["gdpr"].items
        target = next(i for i in enriched_items if i["ref"] == target_ref)
        assert target["status"] == "compliant"

    def test_evidence_does_not_affect_already_compliant_items(self):
        """Already-COMPLIANT items should remain COMPLIANT and evidence field unchanged."""
        from acgs_lite.compliance.evidence import EvidenceBundle, EvidenceItem

        assessor = MultiFrameworkAssessor(frameworks=["nist_ai_rmf"])
        baseline = assessor.assess({"system_id": "ev-test2"})
        compliant_items = [
            i for i in baseline.by_framework["nist_ai_rmf"].items
            if i["status"] == "compliant"
        ]
        if not compliant_items:
            pytest.skip("No COMPLIANT NIST items in baseline")

        ref = compliant_items[0]["ref"]
        bundle = EvidenceBundle(
            system_id="ev-test2",
            collected_at="2026-03-29T00:00:00+00:00",
            items=(
                EvidenceItem("nist_ai_rmf", (ref,), "test", "already compliant", 0.8),
            ),
        )
        enriched = assessor.assess({"system_id": "ev-test2", "_evidence": bundle})
        # Score should be unchanged (already compliant)
        assert enriched.by_framework["nist_ai_rmf"].compliance_score == \
               baseline.by_framework["nist_ai_rmf"].compliance_score

    def test_no_evidence_key_unchanged_behaviour(self):
        """Omitting _evidence must not change existing assess() behaviour."""
        assessor = MultiFrameworkAssessor(frameworks=["oecd_ai"])
        desc = {"system_id": "no-ev"}
        r1 = assessor.assess(desc)
        r2 = assessor.assess(desc)
        assert r1.by_framework["oecd_ai"].compliance_score == \
               r2.by_framework["oecd_ai"].compliance_score

    def test_none_evidence_unchanged(self):
        """Explicitly passing _evidence=None must behave identically to omitting it."""
        assessor = MultiFrameworkAssessor(frameworks=["oecd_ai"])
        r_no_ev = assessor.assess({"system_id": "x"})
        r_none_ev = assessor.assess({"system_id": "x", "_evidence": None})
        assert r_no_ev.by_framework["oecd_ai"].compliance_score == \
               r_none_ev.by_framework["oecd_ai"].compliance_score

    def test_wildcard_evidence_applies_to_all_frameworks(self):
        """Evidence with framework_id='*' should apply to every framework."""
        from acgs_lite.compliance.evidence import EvidenceBundle, EvidenceItem

        assessor = MultiFrameworkAssessor(frameworks=["gdpr", "nist_ai_rmf"])
        baseline = assessor.assess({"system_id": "wc-test"})

        # Find a PENDING item in any framework
        pending_ref = None
        pending_fw = None
        for fw_id in ("gdpr", "nist_ai_rmf"):
            for item in baseline.by_framework[fw_id].items:
                if item["status"] == "pending":
                    pending_ref = item["ref"]
                    pending_fw = fw_id
                    break
            if pending_ref:
                break

        if not pending_ref:
            pytest.skip("No PENDING items in baseline")

        bundle = EvidenceBundle(
            system_id="wc-test",
            collected_at="2026-03-29T00:00:00+00:00",
            items=(
                EvidenceItem("*", (pending_ref,), "test:wildcard", "wildcard evidence", 0.7),
            ),
        )
        enriched = assessor.assess({"system_id": "wc-test", "_evidence": bundle})
        target = next(
            i for i in enriched.by_framework[pending_fw].items
            if i["ref"] == pending_ref
        )
        assert target["status"] == "compliant"

    def test_collect_evidence_integrates_with_assessor(self, tmp_path):
        """Full pipeline: collect evidence → pass to assessor → score improves."""
        from acgs_lite.compliance.evidence import collect_evidence

        # Plant a rules.yaml that proves governance config
        (tmp_path / "rules.yaml").write_text("rules: []")

        bundle = collect_evidence({"system_id": "pipeline-test"}, search_root=tmp_path)
        assert len(bundle.items) > 0, "No evidence collected"

        assessor = MultiFrameworkAssessor(frameworks=["nist_ai_rmf"])
        without_ev = assessor.assess({"system_id": "pipeline-test"})
        with_ev = assessor.assess({"system_id": "pipeline-test", "_evidence": bundle})

        # Score should be same or better with evidence
        assert with_ev.by_framework["nist_ai_rmf"].compliance_score >= \
               without_ev.by_framework["nist_ai_rmf"].compliance_score
