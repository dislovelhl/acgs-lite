"""ClinicalGuard: Demo scenario acceptance tests.

These three scenarios ARE the hackathon demo. If they pass, the submission works.

Scenario 1 (REJECTED):
  Warfarin + Aspirin — major drug interaction, CRITICAL risk tier.

Scenario 2 (CONDITIONAL):
  Warfarin + Clopidogrel — interaction detected, lower risk, conditions required.

Scenario 3 (CONDITIONAL):
  Adalimumab without prior MTX — step therapy violation.

LLM is mocked in these tests to ensure deterministic results.
Constitutional rule matching is tested without any API calls.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from clinicalguard.skills.validate_clinical import (
    CONDITIONAL,
    REJECTED,
    RISK_CRITICAL,
    RISK_HIGH,
    LLMClinicalAssessment,
    validate_clinical_action,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def constitution():
    from pathlib import Path
    yaml_path = Path(__file__).parent.parent / "constitution" / "healthcare_v1.yaml"
    return Constitution.from_yaml(str(yaml_path))


@pytest.fixture
def engine(constitution):
    from acgs_lite.engine import GovernanceEngine
    return GovernanceEngine(constitution, strict=False)


@pytest.fixture
def audit_log():
    return AuditLog()


# Mock LLM responses for each scenario

def _mock_warfarin_aspirin() -> LLMClinicalAssessment:
    """Scenario 1: Major interaction, CRITICAL → REJECTED."""
    return LLMClinicalAssessment(
        evidence_tier="FDA_APPROVED",
        drug_interactions=[
            {
                "drugs": ["Warfarin", "Aspirin"],
                "severity": "MAJOR",
                "description": (
                    "Warfarin + Aspirin: Aspirin displaces Warfarin from protein "
                    "binding sites, increasing free Warfarin levels and bleeding risk "
                    "2-3x. FDA labeling: avoid concomitant use unless benefit > risk."
                ),
            }
        ],
        step_therapy_concern=False,
        dosing_concern=False,
        risk_tier=RISK_CRITICAL,
        reasoning=(
            "Warfarin + Aspirin is a major drug interaction with significant bleeding risk. "
            "Aspirin inhibits platelet aggregation AND increases free Warfarin levels. "
            "This combination requires rejection unless explicitly justified with close INR monitoring."
        ),
        recommended_decision=REJECTED,
        conditions=[],
        llm_available=True,
    )


def _mock_warfarin_clopidogrel() -> LLMClinicalAssessment:
    """Scenario 2: Interaction + condition required → CONDITIONAL."""
    return LLMClinicalAssessment(
        evidence_tier="GUIDELINE",
        drug_interactions=[
            {
                "drugs": ["Warfarin", "Clopidogrel"],
                "severity": "MODERATE",
                "description": (
                    "Warfarin + Clopidogrel: dual anticoagulation increases bleeding risk. "
                    "Acceptable in post-ACS/stent patients with close monitoring. "
                    "Requires documented indication and INR monitoring plan."
                ),
            }
        ],
        step_therapy_concern=False,
        dosing_concern=False,
        risk_tier=RISK_HIGH,
        reasoning=(
            "Warfarin + Clopidogrel dual anticoagulation is guideline-concordant post-ACS "
            "but requires INR monitoring and documented clinical indication."
        ),
        recommended_decision=CONDITIONAL,
        conditions=[
            "Document clinical indication (post-ACS, mechanical valve, etc.)",
            "INR monitoring plan required per HC-005 and HC-008",
            "Bleeding risk assessment documented",
        ],
        llm_available=True,
    )


def _mock_adalimumab_no_step_therapy() -> LLMClinicalAssessment:
    """Scenario 3: Missing step therapy → CONDITIONAL."""
    return LLMClinicalAssessment(
        evidence_tier="GUIDELINE",
        drug_interactions=[],
        step_therapy_concern=True,
        step_therapy_detail=(
            "ACR 2022 guidelines require conventional DMARD failure (methotrexate ≥12 weeks) "
            "before initiating biologic therapy for moderate-to-severe RA. "
            "No prior DMARD trial documented in this proposal."
        ),
        dosing_concern=False,
        risk_tier=RISK_HIGH,
        reasoning=(
            "Adalimumab is FDA-approved for RA but requires documented methotrexate failure "
            "per ACR guidelines and most insurance step-therapy requirements. "
            "Prior treatment history is not documented."
        ),
        recommended_decision=CONDITIONAL,
        conditions=[
            "Document step therapy: MTX ≥12 weeks at therapeutic dose (per HC-004)",
            "Confirm diagnosis of moderate-to-severe RA with disease activity score",
        ],
        llm_available=True,
    )


# ── Scenario 1: Warfarin + Aspirin → REJECTED, CRITICAL ──────────────────────

class TestScenario1WarfarinAspirin:
    """Demo scenario 1: catch a major drug interaction before it reaches a patient."""

    ACTION = (
        "Patient SYNTH-042 currently on Warfarin 5mg/day for atrial fibrillation. "
        "Propose adding Aspirin 325mg daily for cardiovascular prophylaxis."
    )

    @pytest.mark.asyncio
    async def test_decision_is_rejected(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_aspirin(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert result["decision"] == REJECTED, f"Expected REJECTED, got {result['decision']}"

    @pytest.mark.asyncio
    async def test_risk_tier_is_critical(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_aspirin(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert result["risk_tier"] == RISK_CRITICAL

    @pytest.mark.asyncio
    async def test_drug_interaction_present(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_aspirin(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert len(result["drug_interactions"]) >= 1
        major = [i for i in result["drug_interactions"] if i["severity"] == "MAJOR"]
        assert major, "Expected at least one MAJOR interaction"

    @pytest.mark.asyncio
    async def test_audit_id_and_hash_present(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_aspirin(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert result["audit_id"].startswith("HC-")
        assert result["constitutional_hash"]
        assert result["appeal_path"]  # rejected decisions must have appeal path

    @pytest.mark.asyncio
    async def test_audit_log_entry_written(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_aspirin(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        # Verify the entry is in the audit log
        entries = [e for e in audit_log.entries if e.id == result["audit_id"]]
        assert len(entries) == 1
        assert entries[0].valid is False  # REJECTED → valid=False


# ── Scenario 2: Warfarin + Clopidogrel → CONDITIONAL, HIGH ───────────────────

class TestScenario2WarfarinClopidogrel:
    """Demo scenario 2: moderate interaction with conditions."""

    ACTION = (
        "Patient SYNTH-042 on Warfarin 5mg/day. Post-ACS (STEMI 2 weeks ago). "
        "Propose Clopidogrel 75mg/day as antiplatelet therapy."
    )

    @pytest.mark.asyncio
    async def test_decision_is_conditional(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_clopidogrel(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert result["decision"] == CONDITIONAL

    @pytest.mark.asyncio
    async def test_conditions_non_empty(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_clopidogrel(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert len(result["conditions"]) >= 1, "CONDITIONAL must have at least one condition"

    @pytest.mark.asyncio
    async def test_audit_chain_valid_after_two_entries(self, engine, audit_log):
        """Audit chain remains valid after multiple entries."""
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_warfarin_clopidogrel(),
        ):
            await validate_clinical_action(self.ACTION, engine=engine, audit_log=audit_log)
            await validate_clinical_action(self.ACTION, engine=engine, audit_log=audit_log)

        assert audit_log.verify_chain() is True


# ── Scenario 3: Adalimumab without step therapy → CONDITIONAL ────────────────

class TestScenario3StepTherapy:
    """Demo scenario 3: biologic proposed without documented first-line therapy."""

    ACTION = (
        "Patient SYNTH-099 with moderate-to-severe rheumatoid arthritis (DAS28=5.2). "
        "Prescribe Adalimumab 40mg subcutaneous every 2 weeks. "
        "No prior treatment documented."
    )

    @pytest.mark.asyncio
    async def test_decision_is_conditional(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_adalimumab_no_step_therapy(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        assert result["decision"] == CONDITIONAL

    @pytest.mark.asyncio
    async def test_step_therapy_in_conditions(self, engine, audit_log):
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_adalimumab_no_step_therapy(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        condition_text = " ".join(result["conditions"]).lower()
        assert any(
            kw in condition_text for kw in ["step therapy", "mtx", "hc-004", "methotrexate"]
        ), f"Expected step therapy in conditions, got: {result['conditions']}"

    @pytest.mark.asyncio
    async def test_hc004_constitutional_rule_fires(self, engine, audit_log):
        """HC-004 should fire on 'No prior treatment documented' text."""
        # This tests the GovernanceEngine directly — no LLM mock needed
        with patch(
            "clinicalguard.skills.validate_clinical.get_llm_assessment",
            return_value=_mock_adalimumab_no_step_therapy(),
        ):
            result = await validate_clinical_action(
                self.ACTION, engine=engine, audit_log=audit_log
            )
        # HC-004 keywords: "no prior treatment" → should fire
        rule_ids = [v["rule_id"] for v in result.get("violations", [])]
        assert "HC-004" in rule_ids, (
            f"Expected HC-004 in violations for step therapy text. Got: {rule_ids}"
        )

    @pytest.mark.asyncio
    async def test_full_demo_audit_chain(self, engine, audit_log):
        """Run all 3 scenarios end-to-end and verify audit chain integrity."""
        mocks = [
            _mock_warfarin_aspirin(),
            _mock_warfarin_clopidogrel(),
            _mock_adalimumab_no_step_therapy(),
        ]
        actions = [
            TestScenario1WarfarinAspirin.ACTION,
            TestScenario2WarfarinClopidogrel.ACTION,
            self.ACTION,
        ]
        audit_ids = []
        for action, mock_llm in zip(actions, mocks, strict=True):
            with patch(
                "clinicalguard.skills.validate_clinical.get_llm_assessment",
                return_value=mock_llm,
            ):
                result = await validate_clinical_action(
                    action, engine=engine, audit_log=audit_log
                )
                audit_ids.append(result["audit_id"])

        # Chain must be valid after 3 entries
        assert audit_log.verify_chain() is True
        assert len(audit_log) == 3

        # Each audit_id must be unique
        assert len(set(audit_ids)) == 3, "Duplicate audit IDs detected"

        # All entries queryable
        from clinicalguard.skills.audit_query import query_audit_trail
        for aid in audit_ids:
            response = query_audit_trail(audit_log, audit_id=aid)
            assert response["found"] is True
            assert response["chain_valid"] is True
