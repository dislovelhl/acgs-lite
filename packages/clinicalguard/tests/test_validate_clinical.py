"""Unit tests for validate_clinical_action skill.

Tests edge cases, LLM fallback, empty input, confidence scoring.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine
from clinicalguard.skills.validate_clinical import (
    APPROVED,
    CONDITIONAL,
    REJECTED,
    RISK_CRITICAL,
    RISK_LOW,
    LLMClinicalAssessment,
    validate_clinical_action,
)


@pytest.fixture
def engine():
    from pathlib import Path

    yaml_path = Path(__file__).parent.parent / "constitution" / "healthcare_v1.yaml"
    constitution = Constitution.from_yaml(str(yaml_path))
    return GovernanceEngine(constitution, strict=False)


@pytest.fixture
def audit_log():
    return AuditLog()


def _clean_assessment(**kwargs) -> LLMClinicalAssessment:
    defaults = dict(
        evidence_tier="FDA_APPROVED",
        drug_interactions=[],
        step_therapy_concern=False,
        dosing_concern=False,
        risk_tier=RISK_LOW,
        reasoning="Guideline-concordant. No interactions.",
        recommended_decision=APPROVED,
        conditions=[],
        llm_available=True,
    )
    defaults.update(kwargs)
    return LLMClinicalAssessment(**defaults)


class TestEmptyInput:
    @pytest.mark.asyncio
    async def test_empty_string_rejected(self, engine, audit_log):
        result = await validate_clinical_action("", engine=engine, audit_log=audit_log)
        assert result["decision"] == REJECTED

    @pytest.mark.asyncio
    async def test_whitespace_only_rejected(self, engine, audit_log):
        result = await validate_clinical_action("   ", engine=engine, audit_log=audit_log)
        assert result["decision"] == REJECTED


class TestLLMFallback:
    """When LLM is unavailable, rule-only path should still produce a valid response."""

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_result(self, engine, audit_log):
        fallback = LLMClinicalAssessment(
            llm_available=False,
            error="ANTHROPIC_API_KEY not set",
            reasoning="LLM reasoning unavailable — constitutional rules only.",
            recommended_decision=CONDITIONAL,
            risk_tier="MEDIUM",
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=fallback,
        ):
            result = await validate_clinical_action(
                "Prescribe Metformin 500mg for Type 2 diabetes SYNTH-010.",
                engine=engine,
                audit_log=audit_log,
            )
        assert result["decision"] == CONDITIONAL  # fail-closed: never APPROVED without LLM
        assert result["llm_available"] is False
        assert result["audit_id"].startswith("HC-")

    @pytest.mark.asyncio
    async def test_llm_unavailable_lower_confidence(self, engine, audit_log):
        fallback = LLMClinicalAssessment(
            llm_available=False,
            error="timeout",
            recommended_decision=CONDITIONAL,
            risk_tier="MEDIUM",
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=fallback,
        ):
            result = await validate_clinical_action(
                "Prescribe Lisinopril 10mg for hypertension SYNTH-011.",
                engine=engine,
                audit_log=audit_log,
            )
        assert result["confidence"] < 0.80, "Confidence should be lower without LLM"


class TestConstitutionalRules:
    """Verify specific GovernanceEngine rules fire on the expected keywords."""

    @pytest.mark.asyncio
    async def test_hc003_phi_pattern_fires(self, engine, audit_log):
        """HC-003: SSN pattern should fire."""
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_clean_assessment(),
        ):
            result = await validate_clinical_action(
                "Patient SSN 123-45-6789 needs medication review.",
                engine=engine,
                audit_log=audit_log,
            )
        rule_ids = [v["rule_id"] for v in result.get("violations", [])]
        assert "HC-003" in rule_ids, f"HC-003 should fire on SSN pattern, got: {rule_ids}"

    @pytest.mark.asyncio
    async def test_hc007_dosing_fires(self, engine, audit_log):
        """HC-007: '10x dose' should fire."""
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_clean_assessment(
                dosing_concern=True,
                dosing_detail="10x standard dose",
                recommended_decision=REJECTED,
                risk_tier=RISK_CRITICAL,
            ),
        ):
            result = await validate_clinical_action(
                "Prescribe Methotrexate at 10x dose for faster response for SYNTH-020.",
                engine=engine,
                audit_log=audit_log,
            )
        rule_ids = [v["rule_id"] for v in result.get("violations", [])]
        assert "HC-007" in rule_ids, f"HC-007 should fire on '10x dose', got: {rule_ids}"

    @pytest.mark.asyncio
    async def test_hc005_fires_on_skip_interaction_check(self, engine, audit_log):
        """HC-005: 'skip interaction check' keyword should fire the rule.

        Note: Complex drug interactions (Warfarin+Aspirin) are detected by the LLM
        reasoning layer, not the GovernanceEngine. HC-005 catches explicit bypasses.
        """
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_clean_assessment(),
        ):
            result = await validate_clinical_action(
                "Patient SYNTH-042. Skip interaction check and prescribe Aspirin 325mg.",
                engine=engine,
                audit_log=audit_log,
            )
        rule_ids = [v["rule_id"] for v in result.get("violations", [])]
        assert "HC-005" in rule_ids, (
            f"HC-005 should fire on 'skip interaction check', got: {rule_ids}"
        )

    @pytest.mark.asyncio
    async def test_llm_detects_drug_interaction_semantically(self, engine, audit_log):
        """Drug interactions are detected by LLM, returned in drug_interactions field."""
        mock = _clean_assessment(
            drug_interactions=[
                {
                    "drugs": ["Warfarin", "Aspirin"],
                    "severity": "MAJOR",
                    "description": "bleeding risk",
                }
            ],
            recommended_decision=REJECTED,
            risk_tier=RISK_CRITICAL,
        )
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=mock,
        ):
            result = await validate_clinical_action(
                "Patient SYNTH-042 on Warfarin. Add Aspirin 325mg daily.",
                engine=engine,
                audit_log=audit_log,
            )
        assert result["decision"] == REJECTED
        assert len(result["drug_interactions"]) >= 1
        major = [i for i in result["drug_interactions"] if i["severity"] == "MAJOR"]
        assert major, "LLM should have detected MAJOR Warfarin+Aspirin interaction"


class TestAuditIntegrity:
    @pytest.mark.asyncio
    async def test_audit_id_format(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_clean_assessment(),
        ):
            result = await validate_clinical_action(
                "Prescribe Lisinopril 5mg SYNTH-001.", engine=engine, audit_log=audit_log
            )
        assert result["audit_id"].startswith("HC-")
        parts = result["audit_id"].split("-")
        assert len(parts) >= 3

    @pytest.mark.asyncio
    async def test_persistence_callback_called(self, engine, audit_log):
        called = []

        def mock_persist(log):
            called.append(len(log))

        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_clean_assessment(),
        ):
            await validate_clinical_action(
                "Prescribe Atorvastatin 20mg SYNTH-002.",
                engine=engine,
                audit_log=audit_log,
                on_persist=mock_persist,
            )
        assert called, "Persistence callback should have been called"
        assert called[0] >= 1
