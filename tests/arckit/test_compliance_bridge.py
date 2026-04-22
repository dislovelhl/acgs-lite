from __future__ import annotations

from acgs_lite.arckit.compliance_bridge import (
    EU_AI_ACT_CONTROLS,
    ISO_42001_CONTROLS,
    NIST_AI_RMF_CONTROLS,
    map_rule_to_controls,
)


def test_bridge_001_eu_controls_are_non_empty() -> None:
    assert EU_AI_ACT_CONTROLS
    assert all(isinstance(key, str) for key in EU_AI_ACT_CONTROLS)


def test_bridge_002_nist_controls_are_non_empty() -> None:
    assert NIST_AI_RMF_CONTROLS


def test_bridge_003_iso_controls_are_non_empty() -> None:
    assert ISO_42001_CONTROLS


def test_bridge_004_data_protection_maps_to_eu_ai_act_art_10() -> None:
    assert "EU AI Act Art.10" in map_rule_to_controls("data-protection")


def test_bridge_005_risk_maps_to_nist_manage_1() -> None:
    assert "NIST AI RMF MANAGE-1" in map_rule_to_controls("risk")


def test_bridge_006_principles_return_iso_controls() -> None:
    assert any(control.startswith("ISO 42001") for control in map_rule_to_controls("principles"))


def test_bridge_007_unknown_category_returns_empty_list() -> None:
    assert map_rule_to_controls("unknown") == []


def test_bridge_008_all_control_references_are_strings() -> None:
    all_controls = [
        *map_rule_to_controls("principles"),
        *map_rule_to_controls("risk"),
        *map_rule_to_controls("data-protection"),
        *map_rule_to_controls("compliance"),
    ]
    assert all(isinstance(control, str) and control for control in all_controls)
