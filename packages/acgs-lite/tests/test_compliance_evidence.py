"""Tests for the compliance evidence module.

Covers:
- EvidenceItem / EvidenceBundle data model
- ACGSLiteImportCollector (importability checks)
- FileSystemCollector (artefact scanning)
- EnvironmentVarCollector (env-var checks)
- ComplianceEvidenceEngine (collector orchestration)
- collect_evidence() convenience function
- EvidenceCollector protocol conformance

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from acgs_lite.compliance.evidence import (
    ACGSLiteImportCollector,
    ComplianceEvidenceEngine,
    EnvironmentVarCollector,
    EvidenceBundle,
    EvidenceCollector,
    EvidenceItem,
    FileSystemCollector,
    collect_evidence,
)


# ---------------------------------------------------------------------------
# EvidenceItem
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_fields(self):
        item = EvidenceItem(
            framework_id="gdpr",
            article_refs=("GDPR Art.5(2)", "GDPR Art.30(1)"),
            source="import:acgs_lite.audit.AuditLog",
            description="Audit log present",
            confidence=0.9,
        )
        assert item.framework_id == "gdpr"
        assert "GDPR Art.5(2)" in item.article_refs
        assert item.confidence == 0.9

    def test_confidence_range_in_real_items(self):
        """All real items in the mapping must have confidence in [0, 1]."""
        from acgs_lite.compliance.evidence import _COMPONENT_EVIDENCE, _ENV_EVIDENCE, _FILE_EVIDENCE
        for *_, conf in _COMPONENT_EVIDENCE:
            assert 0.0 <= conf <= 1.0
        for *_, conf in _FILE_EVIDENCE:
            assert 0.0 <= conf <= 1.0
        for *_, conf in _ENV_EVIDENCE:
            assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# EvidenceBundle
# ---------------------------------------------------------------------------


class TestEvidenceBundle:
    def _make_bundle(self) -> EvidenceBundle:
        return EvidenceBundle(
            system_id="test-sys",
            collected_at="2026-03-29T00:00:00+00:00",
            items=(
                EvidenceItem("gdpr", ("GDPR Art.5(2)",), "src1", "desc1", 0.9),
                EvidenceItem("eu_ai_act", ("EU-AIA Art.12(1)",), "src2", "desc2", 0.85),
                EvidenceItem("gdpr", ("GDPR Art.30(1)",), "src3", "desc3", 0.8),
                EvidenceItem("*", ("evidence of activity",), "src4", "desc4", 0.5),
            ),
        )

    def test_for_framework_filters_by_id(self):
        bundle = self._make_bundle()
        gdpr_items = bundle.for_framework("gdpr")
        # 2 gdpr items + 1 "*" (wildcard) item
        assert len(gdpr_items) == 3
        gdpr_only = [i for i in gdpr_items if i.framework_id == "gdpr"]
        assert len(gdpr_only) == 2

    def test_for_framework_includes_wildcard(self):
        bundle = self._make_bundle()
        items = bundle.for_framework("anything")
        # Should include the "*" item
        assert any(i.framework_id == "*" for i in items)

    def test_for_ref_returns_matching(self):
        bundle = self._make_bundle()
        items = bundle.for_ref("GDPR Art.5(2)")
        assert len(items) == 1
        assert items[0].source == "src1"

    def test_for_ref_returns_empty_for_unknown(self):
        bundle = self._make_bundle()
        assert bundle.for_ref("GDPR Art.99(99)") == []

    def test_summary_counts_by_framework(self):
        bundle = self._make_bundle()
        s = bundle.summary()
        assert s["gdpr"] == 2
        assert s["eu_ai_act"] == 1
        assert s["*"] == 1

    def test_to_dict_is_json_safe(self):
        import json
        bundle = self._make_bundle()
        d = bundle.to_dict()
        serialised = json.dumps(d)  # must not raise
        assert '"system_id"' in serialised
        assert '"items"' in serialised

    def test_to_dict_fields(self):
        bundle = self._make_bundle()
        d = bundle.to_dict()
        assert d["system_id"] == "test-sys"
        assert d["item_count"] == 4
        assert len(d["items"]) == 4
        first = d["items"][0]
        assert "framework_id" in first
        assert "article_refs" in first
        assert "source" in first
        assert "confidence" in first


# ---------------------------------------------------------------------------
# ACGSLiteImportCollector
# ---------------------------------------------------------------------------


class TestACGSLiteImportCollector:
    def test_returns_list(self):
        collector = ACGSLiteImportCollector()
        items = collector.collect({"system_id": "test"})
        assert isinstance(items, list)

    def test_items_are_evidence_item_instances(self):
        collector = ACGSLiteImportCollector()
        items = collector.collect({})
        for item in items:
            assert isinstance(item, EvidenceItem)

    def test_detects_acgs_lite_audit_log(self):
        """AuditLog is part of acgs_lite — should be detected."""
        collector = ACGSLiteImportCollector()
        items = collector.collect({})
        sources = {i.source for i in items}
        # At least one acgs_lite component should be importable in the test env
        assert any("import:acgs_lite" in s for s in sources), (
            "No acgs_lite components detected — is acgs-lite installed?"
        )

    def test_item_has_valid_article_refs(self):
        collector = ACGSLiteImportCollector()
        items = collector.collect({})
        for item in items:
            assert len(item.article_refs) >= 1
            assert all(isinstance(r, str) and len(r) > 0 for r in item.article_refs)

    def test_nonexistent_import_not_included(self):
        """A clearly non-existent import should never appear."""
        collector = ACGSLiteImportCollector()
        items = collector.collect({})
        sources = {i.source for i in items}
        assert "import:nonexistent.module.That.doesnt.exist" not in sources

    def test_is_importable_true_for_pathlib(self):
        assert ACGSLiteImportCollector._is_importable("pathlib.Path")

    def test_is_importable_false_for_garbage(self):
        assert not ACGSLiteImportCollector._is_importable("zzz_not_real_mod_xyz.Foo")


# ---------------------------------------------------------------------------
# FileSystemCollector
# ---------------------------------------------------------------------------


class TestFileSystemCollector:
    def test_no_artefacts_in_temp_dir(self, tmp_path: Path):
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        assert items == []

    def test_detects_rules_yaml(self, tmp_path: Path):
        (tmp_path / "rules.yaml").write_text("rules: []\n")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        sources = {i.source for i in items}
        assert any("rules.yaml" in s for s in sources)

    def test_rules_yaml_maps_to_nist_and_eu_ai_act(self, tmp_path: Path):
        (tmp_path / "rules.yaml").write_text("rules: []\n")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        fw_ids = {i.framework_id for i in items}
        assert "nist_ai_rmf" in fw_ids
        assert "eu_ai_act" in fw_ids

    def test_privacy_policy_md_maps_to_gdpr_and_ccpa(self, tmp_path: Path):
        (tmp_path / "privacy-policy.md").write_text("# Privacy Policy\n")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        fw_ids = {i.framework_id for i in items}
        assert "gdpr" in fw_ids
        assert "ccpa_cpra" in fw_ids

    def test_fria_maps_to_eu_ai_act_art26(self, tmp_path: Path):
        (tmp_path / "fria.docx").write_text("FRIA document")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        eu_items = [i for i in items if i.framework_id == "eu_ai_act"]
        all_refs = {r for i in eu_items for r in i.article_refs}
        assert "EU-AIA Art.26(9)" in all_refs

    def test_audit_jsonl_maps_to_eu_ai_act_art12(self, tmp_path: Path):
        (tmp_path / "system.audit.jsonl").write_text('{"event": "test"}\n')
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        eu_items = [i for i in items if i.framework_id == "eu_ai_act"]
        all_refs = {r for i in eu_items for r in i.article_refs}
        assert "EU-AIA Art.12(1)" in all_refs

    def test_impact_assessment_maps_to_gdpr_and_india_dpdp(self, tmp_path: Path):
        (tmp_path / "impact-assessment.pdf").write_text("impact assessment")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        fw_ids = {i.framework_id for i in items}
        assert "gdpr" in fw_ids
        assert "india_dpdp" in fw_ids

    def test_returns_empty_list_for_unrecognised_files(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("nothing here")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        assert items == []

    def test_confidence_above_zero_for_all_items(self, tmp_path: Path):
        (tmp_path / "rules.yaml").write_text("")
        (tmp_path / "risk-register.xlsx").write_text("")
        collector = FileSystemCollector(search_root=tmp_path)
        items = collector.collect({})
        for item in items:
            assert item.confidence > 0.0


# ---------------------------------------------------------------------------
# EnvironmentVarCollector
# ---------------------------------------------------------------------------


class TestEnvironmentVarCollector:
    def test_no_env_vars_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        for var in [
            "ACGS_AUDIT_ENABLED", "ACGS_HUMAN_OVERSIGHT", "GDPR_DATA_CONTROLLER",
            "GDPR_DPO_CONTACT", "CCPA_ENABLED", "CCPA_OPT_OUT_URL",
            "DPDP_DATA_FIDUCIARY", "LGPD_CONTROLLER", "CHINA_AI_PROVIDER",
            "ACGS_RISK_TIER", "DORA_ENTITY_TYPE", "ACGS_CONSTITUTIONAL_HASH",
        ]:
            monkeypatch.delenv(var, raising=False)
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        assert items == []

    def test_acgs_audit_enabled_true_adds_eu_ai_act(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ACGS_AUDIT_ENABLED", "true")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        fw_ids = {i.framework_id for i in items}
        assert "eu_ai_act" in fw_ids

    def test_acgs_audit_enabled_false_does_not_trigger(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ACGS_AUDIT_ENABLED", "false")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        # value_hint="true" → must match exactly
        audit_items = [i for i in items if "ACGS_AUDIT_ENABLED" in i.source]
        assert audit_items == []

    def test_gdpr_data_controller_adds_gdpr_items(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GDPR_DATA_CONTROLLER", "My Corp Ltd")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        gdpr_items = [i for i in items if i.framework_id == "gdpr"]
        assert len(gdpr_items) >= 1

    def test_ccpa_opt_out_url_adds_ccpa_item(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CCPA_OPT_OUT_URL", "https://example.com/opt-out")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        ccpa_items = [i for i in items if i.framework_id == "ccpa_cpra"]
        assert len(ccpa_items) >= 1

    def test_china_ai_provider_adds_china_items(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CHINA_AI_PROVIDER", "MyCompany")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        china_items = [i for i in items if i.framework_id == "china_ai"]
        assert len(china_items) >= 1

    def test_item_source_tag_contains_env_prefix(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GDPR_DPO_CONTACT", "dpo@example.com")
        collector = EnvironmentVarCollector()
        items = collector.collect({})
        assert any(i.source.startswith("env:") for i in items)


# ---------------------------------------------------------------------------
# ComplianceEvidenceEngine
# ---------------------------------------------------------------------------


class TestComplianceEvidenceEngine:
    def test_default_engine_returns_bundle(self):
        engine = ComplianceEvidenceEngine()
        bundle = engine.collect({"system_id": "my-ai"})
        assert isinstance(bundle, EvidenceBundle)
        assert bundle.system_id == "my-ai"

    def test_bundle_collected_at_is_iso_string(self):
        engine = ComplianceEvidenceEngine()
        bundle = engine.collect({})
        # Should parse as ISO date
        from datetime import datetime
        datetime.fromisoformat(bundle.collected_at)  # raises if invalid

    def test_custom_collector_is_called(self):
        called: list[bool] = []

        class CustomCollector:
            def collect(self, system_description: dict) -> list[EvidenceItem]:
                called.append(True)
                return [
                    EvidenceItem("gdpr", ("GDPR Art.5(2)",), "custom", "custom", 0.9)
                ]

        engine = ComplianceEvidenceEngine(collectors=[CustomCollector()])
        bundle = engine.collect({})
        assert called
        assert len(bundle.items) == 1

    def test_empty_collectors_list_returns_empty_bundle(self):
        engine = ComplianceEvidenceEngine(collectors=[])
        bundle = engine.collect({"system_id": "empty"})
        assert bundle.items == ()
        assert bundle.system_id == "empty"

    def test_multiple_collectors_items_aggregated(self):
        class C1:
            def collect(self, _: dict) -> list[EvidenceItem]:
                return [EvidenceItem("gdpr", ("A",), "c1", "d1", 0.8)]

        class C2:
            def collect(self, _: dict) -> list[EvidenceItem]:
                return [EvidenceItem("eu_ai_act", ("B",), "c2", "d2", 0.7)]

        engine = ComplianceEvidenceEngine(collectors=[C1(), C2()])
        bundle = engine.collect({})
        assert len(bundle.items) == 2

    def test_engine_propagates_system_description(self):
        received: list[dict] = []

        class SpyCollector:
            def collect(self, system_description: dict) -> list[EvidenceItem]:
                received.append(dict(system_description))
                return []

        engine = ComplianceEvidenceEngine(collectors=[SpyCollector()])
        engine.collect({"system_id": "spy-test", "domain": "healthcare"})
        assert received[0]["system_id"] == "spy-test"
        assert received[0]["domain"] == "healthcare"


# ---------------------------------------------------------------------------
# collect_evidence() convenience function
# ---------------------------------------------------------------------------


class TestCollectEvidenceFunction:
    def test_returns_bundle(self):
        bundle = collect_evidence({"system_id": "test"})
        assert isinstance(bundle, EvidenceBundle)

    def test_none_desc_uses_empty_dict(self):
        bundle = collect_evidence(None)
        assert isinstance(bundle, EvidenceBundle)

    def test_search_root_passed_to_fs_collector(self, tmp_path: Path):
        (tmp_path / "rules.yaml").write_text("rules: []")
        bundle = collect_evidence({"system_id": "t"}, search_root=tmp_path)
        sources = {i.source for i in bundle.items}
        assert any("rules.yaml" in s for s in sources)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestEvidenceCollectorProtocol:
    def test_builtin_collectors_satisfy_protocol(self):
        collectors = [
            ACGSLiteImportCollector(),
            FileSystemCollector(),
            EnvironmentVarCollector(),
        ]
        for c in collectors:
            assert isinstance(c, EvidenceCollector), (
                f"{type(c).__name__} does not satisfy EvidenceCollector protocol"
            )

    def test_custom_class_satisfies_protocol(self):
        class MyCollector:
            def collect(self, system_description: dict) -> list[EvidenceItem]:
                return []

        assert isinstance(MyCollector(), EvidenceCollector)

    def test_collect_evidence_exported_from_compliance_init(self):
        from acgs_lite.compliance import collect_evidence as exported_fn
        assert callable(exported_fn)

    def test_evidence_bundle_exported_from_compliance_init(self):
        from acgs_lite.compliance import EvidenceBundle as ExportedBundle
        assert ExportedBundle is EvidenceBundle
