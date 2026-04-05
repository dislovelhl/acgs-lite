# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for constitutional amendment_model.py.

Targets ≥ 90% coverage of:
  src/core/enhanced_agent_bus/constitutional/amendment_model.py
"""

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_PROPOSAL_KWARGS = dict(
    proposed_changes={"rule": "new text"},
    justification="This justification is long enough to pass validation.",
    proposer_agent_id="agent-test-001",
    target_version="1.0.0",
)


def make_proposal(**overrides) -> AmendmentProposal:
    kwargs = {**MINIMAL_PROPOSAL_KWARGS, **overrides}
    return AmendmentProposal(**kwargs)


def make_approved_proposal(**overrides) -> AmendmentProposal:
    p = make_proposal(**overrides)
    p.submit_for_review()
    p.approve(approver_id="approver-001", approver_role="judicial")
    return p


def make_active_proposal(**overrides) -> AmendmentProposal:
    p = make_approved_proposal(**overrides)
    p.activate()
    return p


# ---------------------------------------------------------------------------
# AmendmentStatus enum
# ---------------------------------------------------------------------------


class TestAmendmentStatusEnum:
    """Ensure all enum values are reachable and have the expected string values."""

    def test_all_status_values(self):
        assert AmendmentStatus.PROPOSED.value == "proposed"
        assert AmendmentStatus.UNDER_REVIEW.value == "under_review"
        assert AmendmentStatus.APPROVED.value == "approved"
        assert AmendmentStatus.REJECTED.value == "rejected"
        assert AmendmentStatus.ACTIVE.value == "active"
        assert AmendmentStatus.ROLLED_BACK.value == "rolled_back"
        assert AmendmentStatus.WITHDRAWN.value == "withdrawn"

    def test_status_is_str(self):
        # AmendmentStatus inherits from str
        assert isinstance(AmendmentStatus.PROPOSED, str)
        assert AmendmentStatus.PROPOSED == "proposed"


# ---------------------------------------------------------------------------
# Model creation & field defaults
# ---------------------------------------------------------------------------


class TestAmendmentProposalCreation:
    """Tests for model construction, field defaults, and required fields."""

    def test_minimal_valid_proposal(self):
        p = make_proposal()
        assert p.proposal_id  # uuid4 auto-generated
        assert p.status == AmendmentStatus.PROPOSED
        assert p.impact_score is None
        assert p.impact_factors == {}
        assert p.impact_recommendation is None
        assert p.requires_deliberation is False
        assert p.governance_metrics_before == {}
        assert p.governance_metrics_after == {}
        assert p.approval_chain == []
        assert p.rejection_reason is None
        assert p.rollback_reason is None
        assert p.reviewed_at is None
        assert p.activated_at is None
        assert p.rolled_back_at is None
        assert p.new_version is None

    def test_constitutional_hash_in_default_metadata(self):
        p = make_proposal()
        assert p.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_hash_injected_when_missing_from_custom_metadata(self):
        p = make_proposal(metadata={"audit_id": "x"})
        assert p.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert p.metadata["audit_id"] == "x"

    def test_constitutional_hash_preserved_when_already_present(self):
        p = make_proposal(metadata={"constitutional_hash": CONSTITUTIONAL_HASH, "extra": 1})
        assert p.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_explicit_proposal_id_preserved(self):
        p = make_proposal(proposal_id="my-custom-id")
        assert p.proposal_id == "my-custom-id"

    def test_empty_string_proposal_id_gets_new_uuid(self):
        # The __init__ guard: `if not self.proposal_id: self.proposal_id = str(uuid4())`
        p = make_proposal(proposal_id="")
        # Pydantic accepts empty string; __init__ then replaces it
        assert p.proposal_id  # truthy => was replaced

    def test_proposal_with_new_version(self):
        p = make_proposal(new_version="2.0.0")
        assert p.new_version == "2.0.0"

    def test_proposal_with_impact_details(self):
        p = make_proposal(
            impact_score=0.75,
            impact_factors={"semantic": 0.6, "permission": 0.9},
            impact_recommendation="Requires HITL review.",
            requires_deliberation=True,
        )
        assert p.impact_score == 0.75
        assert p.impact_factors["semantic"] == 0.6
        assert p.impact_recommendation == "Requires HITL review."
        assert p.requires_deliberation is True

    def test_proposal_with_governance_metrics(self):
        p = make_proposal(
            governance_metrics_before={"health": 0.9},
            governance_metrics_after={"health": 0.8},
        )
        assert p.governance_metrics_before == {"health": 0.9}
        assert p.governance_metrics_after == {"health": 0.8}

    def test_proposal_with_timestamps(self):
        now = datetime.now(UTC)
        p = make_proposal(
            reviewed_at=now,
            activated_at=now,
            rolled_back_at=now,
        )
        assert p.reviewed_at == now
        assert p.activated_at == now
        assert p.rolled_back_at == now

    def test_proposal_with_approval_chain(self):
        chain = [{"approver_id": "a1", "decision": "approved"}]
        p = make_proposal(approval_chain=chain)
        assert p.approval_chain == chain

    def test_created_at_is_utc_aware(self):
        p = make_proposal()
        assert p.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Field validators
# ---------------------------------------------------------------------------


class TestFieldValidators:
    """Tests for all @field_validator methods."""

    # --- justification ---

    def test_justification_too_short_raises(self):
        with pytest.raises((ValueError, PydanticValidationError)):
            make_proposal(justification="short")

    def test_justification_whitespace_only_raises(self):
        with pytest.raises((ValueError, PydanticValidationError)):
            make_proposal(justification="   tiny   ")

    def test_justification_exactly_10_chars_after_strip(self):
        p = make_proposal(justification="  1234567890  ")
        assert p.justification == "1234567890"

    def test_justification_is_stripped(self):
        p = make_proposal(justification="  valid justification text  ")
        assert p.justification == "valid justification text"

    # --- proposed_changes ---

    def test_empty_proposed_changes_raises(self):
        with pytest.raises((ValueError, PydanticValidationError)):
            make_proposal(proposed_changes={})

    def test_non_empty_proposed_changes_accepted(self):
        p = make_proposal(proposed_changes={"key": "val"})
        assert p.proposed_changes == {"key": "val"}

    # --- target_version semantic versioning ---

    def test_invalid_target_version_pattern_raises(self):
        with pytest.raises(PydanticValidationError):
            make_proposal(target_version="1.0")  # only 2 parts

    def test_invalid_target_version_alpha_raises(self):
        with pytest.raises(PydanticValidationError):
            make_proposal(target_version="a.b.c")

    def test_valid_target_version_accepted(self):
        p = make_proposal(target_version="3.14.159")
        assert p.target_version == "3.14.159"

    def test_valid_new_version_accepted(self):
        p = make_proposal(new_version="0.0.1")
        assert p.new_version == "0.0.1"

    def test_new_version_none_accepted(self):
        # validate_semantic_version returns None for None input
        p = make_proposal(new_version=None)
        assert p.new_version is None

    def test_invalid_new_version_pattern_raises(self):
        with pytest.raises(PydanticValidationError):
            make_proposal(new_version="1.0")

    def test_version_with_non_integer_parts_raises(self):
        # Pattern allows only digits per segment; "1.x.0" fails the regex pattern
        with pytest.raises(PydanticValidationError):
            make_proposal(target_version="1.x.0")

    # --- impact_score bounds ---

    def test_impact_score_above_1_raises(self):
        with pytest.raises(PydanticValidationError):
            make_proposal(impact_score=1.1)

    def test_impact_score_below_0_raises(self):
        with pytest.raises(PydanticValidationError):
            make_proposal(impact_score=-0.1)

    def test_impact_score_boundary_0_accepted(self):
        p = make_proposal(impact_score=0.0)
        assert p.impact_score == 0.0

    def test_impact_score_boundary_1_accepted(self):
        p = make_proposal(impact_score=1.0)
        assert p.impact_score == 1.0


# ---------------------------------------------------------------------------
# Status-check properties
# ---------------------------------------------------------------------------


class TestStatusProperties:
    """Tests for all status-check @property methods."""

    def test_is_proposed(self):
        p = make_proposal()
        assert p.is_proposed is True
        assert p.is_under_review is False
        assert p.is_approved is False
        assert p.is_rejected is False
        assert p.is_active is False
        assert p.is_rolled_back is False
        assert p.is_withdrawn is False
        assert p.is_pending is True
        assert p.is_final is False

    def test_is_under_review(self):
        p = make_proposal()
        p.submit_for_review()
        assert p.is_under_review is True
        assert p.is_proposed is False
        assert p.is_pending is True
        assert p.is_final is False

    def test_is_approved(self):
        p = make_approved_proposal()
        assert p.is_approved is True
        assert p.is_pending is False
        assert p.is_final is False

    def test_is_rejected(self):
        p = make_proposal()
        p.submit_for_review()
        p.reject(reviewer_id="r1", reason="Not acceptable.")
        assert p.is_rejected is True
        assert p.is_final is True
        assert p.is_pending is False

    def test_is_active(self):
        p = make_active_proposal()
        assert p.is_active is True
        assert p.is_final is False

    def test_is_rolled_back(self):
        p = make_active_proposal()
        p.rollback(reason="Governance degraded significantly.")
        assert p.is_rolled_back is True
        assert p.is_final is True

    def test_is_withdrawn_from_proposed(self):
        p = make_proposal()
        p.withdraw()
        assert p.is_withdrawn is True
        assert p.is_final is True

    def test_is_withdrawn_from_under_review(self):
        p = make_proposal()
        p.submit_for_review()
        p.withdraw()
        assert p.is_withdrawn is True
        assert p.is_final is True


# ---------------------------------------------------------------------------
# Impact-level properties
# ---------------------------------------------------------------------------


class TestImpactProperties:
    """Tests for high_impact / medium_impact / low_impact properties."""

    def test_no_score_all_false(self):
        p = make_proposal()
        assert p.high_impact is False
        assert p.medium_impact is False
        assert p.low_impact is False

    def test_exact_high_boundary_0_8(self):
        p = make_proposal(impact_score=0.8)
        assert p.high_impact is True
        assert p.medium_impact is False
        assert p.low_impact is False

    def test_above_high_boundary(self):
        p = make_proposal(impact_score=0.99)
        assert p.high_impact is True

    def test_below_high_boundary_is_medium(self):
        p = make_proposal(impact_score=0.79)
        assert p.high_impact is False
        assert p.medium_impact is True
        assert p.low_impact is False

    def test_exact_medium_lower_boundary_0_5(self):
        p = make_proposal(impact_score=0.5)
        assert p.medium_impact is True
        assert p.low_impact is False

    def test_just_below_0_5_is_low(self):
        p = make_proposal(impact_score=0.49)
        assert p.low_impact is True
        assert p.medium_impact is False

    def test_zero_score_is_low(self):
        p = make_proposal(impact_score=0.0)
        assert p.low_impact is True


# ---------------------------------------------------------------------------
# State transition methods — happy paths
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """Tests for all state-transition methods (happy paths)."""

    def test_full_lifecycle_proposed_to_active(self):
        p = make_proposal()
        assert p.status == AmendmentStatus.PROPOSED

        p.submit_for_review()
        assert p.status == AmendmentStatus.UNDER_REVIEW

        p.approve(approver_id="ap-001", approver_role="judicial")
        assert p.status == AmendmentStatus.APPROVED
        assert p.reviewed_at is not None
        assert len(p.approval_chain) == 1
        assert p.approval_chain[0]["approver_id"] == "ap-001"
        assert p.approval_chain[0]["approver_role"] == "judicial"
        assert p.approval_chain[0]["decision"] == "approved"

        p.activate(governance_metrics_before={"health": 0.95})
        assert p.status == AmendmentStatus.ACTIVE
        assert p.activated_at is not None
        assert p.governance_metrics_before == {"health": 0.95}

    def test_activate_without_governance_metrics(self):
        p = make_approved_proposal()
        p.activate()  # no metrics_before
        assert p.status == AmendmentStatus.ACTIVE
        assert p.governance_metrics_before == {}

    def test_rollback_with_metrics_after(self):
        p = make_active_proposal()
        metrics_after = {"health": 0.5, "latency": 9.0}
        p.rollback(reason="Degraded performance.", governance_metrics_after=metrics_after)
        assert p.status == AmendmentStatus.ROLLED_BACK
        assert p.rolled_back_at is not None
        assert p.rollback_reason == "Degraded performance."
        assert p.governance_metrics_after == metrics_after

    def test_rollback_without_metrics_after(self):
        p = make_active_proposal()
        p.rollback(reason="System instability detected.")
        assert p.status == AmendmentStatus.ROLLED_BACK
        assert p.governance_metrics_after == {}

    def test_reject_records_chain_entry(self):
        p = make_proposal()
        p.submit_for_review()
        p.reject(reviewer_id="r-001", reason="Violates principle.", reviewer_role="judicial")
        assert p.status == AmendmentStatus.REJECTED
        assert p.rejection_reason == "Violates principle."
        assert p.reviewed_at is not None
        chain = p.approval_chain[0]
        assert chain["reviewer_id"] == "r-001"
        assert chain["reviewer_role"] == "judicial"
        assert chain["decision"] == "rejected"
        assert chain["reason"] == "Violates principle."
        assert "timestamp" in chain

    def test_reject_default_role(self):
        p = make_proposal()
        p.submit_for_review()
        p.reject(reviewer_id="r-002", reason="Policy conflict.")
        assert p.approval_chain[0]["reviewer_role"] == "unknown"

    def test_approve_default_role(self):
        p = make_proposal()
        p.submit_for_review()
        p.approve(approver_id="a-002")
        assert p.approval_chain[0]["approver_role"] == "unknown"

    def test_withdraw_from_proposed(self):
        p = make_proposal()
        p.withdraw()
        assert p.status == AmendmentStatus.WITHDRAWN

    def test_withdraw_from_under_review(self):
        p = make_proposal()
        p.submit_for_review()
        p.withdraw()
        assert p.status == AmendmentStatus.WITHDRAWN


# ---------------------------------------------------------------------------
# State transition methods — error paths
# ---------------------------------------------------------------------------


class TestStateTransitionErrors:
    """Tests for state-transition guard errors."""

    def test_submit_for_review_from_under_review_raises(self):
        p = make_proposal()
        p.submit_for_review()
        with pytest.raises((ValueError, ACGSValidationError), match="PROPOSED status"):
            p.submit_for_review()

    def test_submit_for_review_from_approved_raises(self):
        p = make_approved_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="PROPOSED status"):
            p.submit_for_review()

    def test_approve_from_proposed_raises(self):
        p = make_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="UNDER_REVIEW status"):
            p.approve(approver_id="a-001")

    def test_approve_from_approved_raises(self):
        p = make_approved_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="UNDER_REVIEW status"):
            p.approve(approver_id="a-001")

    def test_reject_from_proposed_raises(self):
        p = make_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="UNDER_REVIEW status"):
            p.reject(reviewer_id="r-001", reason="no")

    def test_reject_from_approved_raises(self):
        p = make_approved_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="UNDER_REVIEW status"):
            p.reject(reviewer_id="r-001", reason="no")

    def test_activate_from_proposed_raises(self):
        p = make_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="APPROVED status"):
            p.activate()

    def test_activate_from_under_review_raises(self):
        p = make_proposal()
        p.submit_for_review()
        with pytest.raises((ValueError, ACGSValidationError), match="APPROVED status"):
            p.activate()

    def test_activate_from_active_raises(self):
        p = make_active_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="APPROVED status"):
            p.activate()

    def test_rollback_from_proposed_raises(self):
        p = make_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="ACTIVE status"):
            p.rollback(reason="n/a")

    def test_rollback_from_approved_raises(self):
        p = make_approved_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="ACTIVE status"):
            p.rollback(reason="n/a")

    def test_rollback_from_rolled_back_raises(self):
        p = make_active_proposal()
        p.rollback(reason="first rollback")
        with pytest.raises((ValueError, ACGSValidationError), match="ACTIVE status"):
            p.rollback(reason="second rollback")

    def test_withdraw_from_approved_raises(self):
        p = make_approved_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="pending proposals"):
            p.withdraw()

    def test_withdraw_from_rejected_raises(self):
        p = make_proposal()
        p.submit_for_review()
        p.reject(reviewer_id="r", reason="bad")
        with pytest.raises((ValueError, ACGSValidationError), match="pending proposals"):
            p.withdraw()

    def test_withdraw_from_active_raises(self):
        p = make_active_proposal()
        with pytest.raises((ValueError, ACGSValidationError), match="pending proposals"):
            p.withdraw()


# ---------------------------------------------------------------------------
# calculate_metrics_delta
# ---------------------------------------------------------------------------


class TestCalculateMetricsDelta:
    """Tests for the calculate_metrics_delta method."""

    def test_delta_with_full_overlap(self):
        p = make_proposal(
            governance_metrics_before={"v_rate": 0.01, "latency": 2.0, "health": 0.95},
            governance_metrics_after={"v_rate": 0.03, "latency": 3.5, "health": 0.80},
        )
        delta = p.calculate_metrics_delta()
        assert delta["v_rate"] == pytest.approx(0.02)
        assert delta["latency"] == pytest.approx(1.5)
        assert delta["health"] == pytest.approx(-0.15)

    def test_delta_empty_when_no_before(self):
        p = make_proposal(governance_metrics_after={"health": 0.9})
        assert p.calculate_metrics_delta() == {}

    def test_delta_empty_when_no_after(self):
        p = make_proposal(governance_metrics_before={"health": 0.9})
        assert p.calculate_metrics_delta() == {}

    def test_delta_empty_when_neither(self):
        p = make_proposal()
        assert p.calculate_metrics_delta() == {}

    def test_delta_partial_overlap_skips_missing_after_key(self):
        # "extra" is in before but NOT in after  → not included in delta
        p = make_proposal(
            governance_metrics_before={"health": 0.9, "extra": 1.0},
            governance_metrics_after={"health": 0.8},
        )
        delta = p.calculate_metrics_delta()
        assert "health" in delta
        assert "extra" not in delta

    def test_delta_zero_when_equal(self):
        p = make_proposal(
            governance_metrics_before={"health": 0.9},
            governance_metrics_after={"health": 0.9},
        )
        delta = p.calculate_metrics_delta()
        assert delta["health"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for to_dict / model_dump and the datetime field_serializer."""

    def test_to_dict_keys_present(self):
        p = make_proposal()
        d = p.to_dict()
        expected_keys = {
            "proposal_id",
            "proposed_changes",
            "justification",
            "proposer_agent_id",
            "target_version",
            "new_version",
            "status",
            "impact_score",
            "impact_factors",
            "impact_recommendation",
            "requires_deliberation",
            "governance_metrics_before",
            "governance_metrics_after",
            "approval_chain",
            "rejection_reason",
            "rollback_reason",
            "metadata",
            "created_at",
            "reviewed_at",
            "activated_at",
            "rolled_back_at",
        }
        assert expected_keys.issubset(d.keys())

    def test_to_dict_status_is_string(self):
        p = make_proposal()
        d = p.to_dict()
        assert d["status"] == "proposed"

    def test_datetime_serializer_returns_iso_string(self):
        p = make_active_proposal()
        d = p.to_dict()
        # created_at and activated_at should be ISO strings
        assert isinstance(d["created_at"], str)
        assert isinstance(d["activated_at"], str)
        # Parse back to confirm validity
        datetime.fromisoformat(d["created_at"])
        datetime.fromisoformat(d["activated_at"])

    def test_datetime_serializer_returns_none_for_unset(self):
        p = make_proposal()
        d = p.to_dict()
        assert d["reviewed_at"] is None
        assert d["activated_at"] is None
        assert d["rolled_back_at"] is None

    def test_serialize_datetime_directly(self):
        """Call the field_serializer method directly to hit both branches."""
        p = make_proposal()
        now = datetime.now(UTC)
        # non-None branch
        result = p.serialize_datetime(now)
        assert result == now.isoformat()
        # None branch
        assert p.serialize_datetime(None) is None

    def test_repr_contains_expected_fields(self):
        p = make_proposal(target_version="2.3.4")
        r = repr(p)
        assert "AmendmentProposal" in r
        assert p.proposal_id in r
        assert "2.3.4" in r
        assert "proposed" in r

    def test_repr_with_impact_score(self):
        p = make_proposal(impact_score=0.42)
        r = repr(p)
        assert "0.42" in r

    def test_repr_with_no_impact_score(self):
        p = make_proposal()
        r = repr(p)
        assert "None" in r


# ---------------------------------------------------------------------------
# Edge cases & miscellaneous
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Miscellaneous edge-case and integration tests."""

    def test_approval_chain_accumulates_multiple_entries(self):
        # Simulate two separate review cycles by directly setting state
        p = make_proposal()
        p.submit_for_review()
        p.approve(approver_id="a1", approver_role="judicial")
        # Manually reset to simulate a second review cycle
        p.status = AmendmentStatus.UNDER_REVIEW
        p.approve(approver_id="a2", approver_role="executive")
        assert len(p.approval_chain) == 2

    def test_activate_with_none_metrics_before_does_not_override(self):
        p = make_approved_proposal(governance_metrics_before={"health": 0.9})
        p.activate(governance_metrics_before=None)
        # The existing governance_metrics_before field should still hold its
        # initial value since None is falsy
        assert p.governance_metrics_before == {"health": 0.9}

    def test_rollback_with_none_metrics_after_does_not_override(self):
        p = make_active_proposal(governance_metrics_after={"health": 0.7})
        p.rollback(reason="Test rollback.", governance_metrics_after=None)
        assert p.governance_metrics_after == {"health": 0.7}

    def test_impact_score_exactly_0_8_is_high(self):
        p = make_proposal(impact_score=0.8)
        assert p.high_impact is True
        assert p.medium_impact is False

    def test_impact_score_just_below_0_8_is_medium(self):
        p = make_proposal(impact_score=0.7999)
        assert p.high_impact is False
        assert p.medium_impact is True

    def test_full_lifecycle_with_rollback(self):
        p = make_proposal(
            proposed_changes={"rule_a": "updated"},
            justification="Full lifecycle test from proposal to rollback.",
            proposer_agent_id="agent-lifecycle",
            target_version="1.2.3",
            new_version="1.3.0",
        )
        p.submit_for_review()
        p.approve(approver_id="judicial-001", approver_role="judicial")
        p.activate(governance_metrics_before={"health": 0.95, "latency": 2.1})
        p.rollback(
            reason="Latency degraded beyond SLO.",
            governance_metrics_after={"health": 0.60, "latency": 8.5},
        )
        assert p.is_rolled_back
        assert p.is_final
        delta = p.calculate_metrics_delta()
        assert delta["health"] == pytest.approx(-0.35)
        assert delta["latency"] == pytest.approx(6.4)

    def test_full_lifecycle_with_rejection(self):
        p = make_proposal()
        p.submit_for_review()
        p.reject(
            reviewer_id="judicial-002",
            reason="Amendment conflicts with Article 3.",
            reviewer_role="judicial",
        )
        assert p.is_rejected
        assert p.is_final
        assert p.rejection_reason == "Amendment conflicts with Article 3."

    def test_model_created_at_is_auto_set(self):
        before = datetime.now(UTC)
        p = make_proposal()
        after = datetime.now(UTC)
        assert before <= p.created_at <= after


# ---------------------------------------------------------------------------
# Direct validator method coverage (dead-code paths blocked by Pydantic pattern)
# ---------------------------------------------------------------------------


class TestValidatorDirectCalls:
    """Call field_validator classmethods directly to reach lines blocked by the pattern."""

    def test_validate_semantic_version_none_returns_none(self):
        # Line 178: return None
        result = AmendmentProposal.validate_semantic_version(None)
        assert result is None

    def test_validate_semantic_version_valid_returns_value(self):
        result = AmendmentProposal.validate_semantic_version("1.2.3")
        assert result == "1.2.3"

    def test_validate_semantic_version_wrong_part_count_raises(self):
        # Line 182: len(parts) != 3 branch
        with pytest.raises((ValueError, ACGSValidationError), match="semantic versioning"):
            AmendmentProposal.validate_semantic_version("1.0")

    def test_validate_semantic_version_non_integer_parts_raises(self):
        # Lines 188-189: ValueError from map(int, ...) — 'a.b.c' passes split but
        # not int conversion
        with pytest.raises(
            (ValueError, ACGSValidationError), match="Invalid semantic version format"
        ):
            AmendmentProposal.validate_semantic_version("a.b.c")

    def test_validate_semantic_version_negative_version_raises(self):
        # Lines 186-187: negative parts branch
        with pytest.raises(
            (ValueError, ACGSValidationError), match="Invalid semantic version format"
        ):
            AmendmentProposal.validate_semantic_version("-1.0.0")

    def test_validate_justification_too_short_raises(self):
        # Line 162: raise ValueError
        with pytest.raises((ValueError, ACGSValidationError), match="at least 10 characters"):
            AmendmentProposal.validate_justification("tiny")

    def test_validate_justification_valid_strips_whitespace(self):
        result = AmendmentProposal.validate_justification("  valid justification  ")
        assert result == "valid justification"

    def test_validate_proposed_changes_empty_raises(self):
        # Line 170: raise ValueError
        with pytest.raises((ValueError, ACGSValidationError), match="cannot be empty"):
            AmendmentProposal.validate_proposed_changes({})

    def test_validate_proposed_changes_non_empty_returns_value(self):
        result = AmendmentProposal.validate_proposed_changes({"x": 1})
        assert result == {"x": 1}
