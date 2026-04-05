"""
ACGS-2 Deliberation Layer - OPA Guard Models Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for OPA guard data models.
"""

import importlib.util
import os
import sys

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Load module directly to work with conftest module isolation
_parent_dir = os.path.dirname(os.path.dirname(__file__))
_models_path = os.path.join(_parent_dir, "deliberation_layer", "opa_guard_models.py")


def _load_module(name: str, path: str):
    """Load a module directly from path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_opa_models = _load_module("_opa_guard_models", _models_path)

# Import from loaded module
GUARD_CONSTITUTIONAL_HASH = _opa_models.GUARD_CONSTITUTIONAL_HASH
GuardDecision = _opa_models.GuardDecision
SignatureStatus = _opa_models.SignatureStatus
ReviewStatus = _opa_models.ReviewStatus
GuardResult = _opa_models.GuardResult
Signature = _opa_models.Signature
SignatureResult = _opa_models.SignatureResult
CriticReview = _opa_models.CriticReview
ReviewResult = _opa_models.ReviewResult


# ============================================================================
# Constitutional Hash Tests
# ============================================================================


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_guard_constitutional_hash_value(self):
        """Verify guard constitutional hash value."""
        assert GUARD_CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ============================================================================
# GuardDecision Enum Tests
# ============================================================================


class TestGuardDecision:
    """Test GuardDecision enum."""

    def test_all_decisions(self):
        """Test all guard decisions exist."""
        assert GuardDecision.ALLOW.value == "allow"
        assert GuardDecision.DENY.value == "deny"
        assert GuardDecision.REQUIRE_REVIEW.value == "require_review"
        assert GuardDecision.REQUIRE_SIGNATURES.value == "require_signatures"
        assert GuardDecision.PENDING.value == "pending"

    def test_decision_count(self):
        """Test number of decisions."""
        assert len(GuardDecision) == 5


# ============================================================================
# SignatureStatus Enum Tests
# ============================================================================


class TestSignatureStatus:
    """Test SignatureStatus enum."""

    def test_all_statuses(self):
        """Test all signature statuses exist."""
        assert SignatureStatus.PENDING.value == "pending"
        assert SignatureStatus.COLLECTED.value == "collected"
        assert SignatureStatus.EXPIRED.value == "expired"
        assert SignatureStatus.REJECTED.value == "rejected"


# ============================================================================
# ReviewStatus Enum Tests
# ============================================================================


class TestReviewStatus:
    """Test ReviewStatus enum."""

    def test_all_statuses(self):
        """Test all review statuses exist."""
        assert ReviewStatus.PENDING.value == "pending"
        assert ReviewStatus.IN_PROGRESS.value == "in_progress"
        assert ReviewStatus.APPROVED.value == "approved"
        assert ReviewStatus.REJECTED.value == "rejected"
        assert ReviewStatus.ESCALATED.value == "escalated"


# ============================================================================
# GuardResult Tests
# ============================================================================


class TestGuardResult:
    """Test GuardResult dataclass."""

    def test_default_creation(self):
        """Test default guard result creation."""
        result = GuardResult()
        assert result.decision == GuardDecision.PENDING
        assert result.is_allowed is False
        assert result.agent_id == ""
        assert result.action_type == ""
        assert result.constitutional_valid is False
        assert result.validation_errors == []
        assert result.validation_warnings == []
        assert result.risk_level == "unknown"
        assert result.risk_score == 0.0
        assert result.requires_signatures is False
        assert result.requires_review is False
        assert result.constitutional_hash == GUARD_CONSTITUTIONAL_HASH
        assert result.guard_id is not None
        assert result.timestamp is not None

    def test_custom_guard_result(self):
        """Test custom guard result."""
        result = GuardResult(
            decision=GuardDecision.ALLOW,
            is_allowed=True,
            agent_id="agent-1",
            action_type="deploy",
            constitutional_valid=True,
            risk_level="low",
            risk_score=0.15,
        )
        assert result.decision == GuardDecision.ALLOW
        assert result.is_allowed is True
        assert result.agent_id == "agent-1"
        assert result.action_type == "deploy"
        assert result.constitutional_valid is True
        assert result.risk_level == "low"
        assert result.risk_score == 0.15

    def test_guard_result_with_validation_errors(self):
        """Test guard result with validation errors."""
        result = GuardResult(
            decision=GuardDecision.DENY,
            validation_errors=["Missing permission", "Invalid agent"],
            validation_warnings=["Deprecated action"],
        )
        assert result.decision == GuardDecision.DENY
        assert len(result.validation_errors) == 2
        assert len(result.validation_warnings) == 1

    def test_guard_result_with_signatures_required(self):
        """Test guard result requiring signatures."""
        result = GuardResult(
            decision=GuardDecision.REQUIRE_SIGNATURES,
            requires_signatures=True,
            required_signers=["admin-1", "admin-2", "security-lead"],
        )
        assert result.requires_signatures is True
        assert len(result.required_signers) == 3

    def test_guard_result_to_dict(self):
        """Test guard result to_dict serialization."""
        result = GuardResult(
            decision=GuardDecision.ALLOW,
            agent_id="test-agent",
            action_type="read",
            constitutional_valid=True,
            risk_level="low",
            risk_score=0.1,
        )
        d = result.to_dict()

        assert d["decision"] == "allow"
        assert d["agent_id"] == "test-agent"
        assert d["action_type"] == "read"
        assert d["constitutional_valid"] is True
        assert d["risk_level"] == "low"
        assert d["risk_score"] == 0.1
        assert d["constitutional_hash"] == GUARD_CONSTITUTIONAL_HASH
        assert "guard_id" in d
        assert "timestamp" in d


# ============================================================================
# Signature Tests
# ============================================================================


class TestSignature:
    """Test Signature dataclass."""

    def test_signature_creation(self):
        """Test signature creation with auto-generated hash."""
        sig = Signature(signer_id="signer-1")
        assert sig.signer_id == "signer-1"
        assert sig.signature_hash != ""  # Auto-generated
        assert len(sig.signature_hash) == 32  # SHA256 truncated to 32 chars
        assert sig.confidence == 1.0
        assert sig.reasoning == ""

    def test_signature_with_custom_hash(self):
        """Test signature with provided hash."""
        sig = Signature(signer_id="signer-2", signature_hash="custom_hash_12345")
        assert sig.signature_hash == "custom_hash_12345"

    def test_signature_with_details(self):
        """Test signature with full details."""
        sig = Signature(
            signer_id="admin-lead",
            reasoning="Approved after security review",
            confidence=0.95,
            metadata={"review_type": "security"},
        )
        assert sig.reasoning == "Approved after security review"
        assert sig.confidence == 0.95
        assert sig.metadata["review_type"] == "security"


# ============================================================================
# SignatureResult Tests
# ============================================================================


class TestSignatureResult:
    """Test SignatureResult dataclass."""

    def test_default_signature_result(self):
        """Test default signature result."""
        result = SignatureResult()
        assert result.status == SignatureStatus.PENDING
        assert result.required_signers == []
        assert result.required_count == 0
        assert result.threshold == 1.0
        assert result.signatures == []
        assert result.collected_count == 0
        assert result.is_complete is False
        assert result.is_valid is False

    def test_signature_result_with_requirements(self):
        """Test signature result with requirements."""
        result = SignatureResult(
            decision_id="dec-123",
            required_signers=["admin-1", "admin-2"],
            required_count=2,
            threshold=1.0,
        )
        assert result.decision_id == "dec-123"
        assert len(result.required_signers) == 2
        assert result.required_count == 2
        assert result.missing_signers == ["admin-1", "admin-2"]

    def test_add_signature(self):
        """Test adding signatures."""
        result = SignatureResult(
            decision_id="dec-456", required_signers=["admin-1", "admin-2"], required_count=2
        )

        # Add first signature
        sig1 = Signature(signer_id="admin-1", reasoning="Approved")
        success = result.add_signature(sig1)
        assert success is True
        assert result.collected_count == 1
        assert "admin-1" not in result.missing_signers
        assert result.is_complete is False

        # Add second signature
        sig2 = Signature(signer_id="admin-2", reasoning="Also approved")
        success = result.add_signature(sig2)
        assert success is True
        assert result.collected_count == 2
        assert result.is_complete is True
        assert result.is_valid is True
        assert result.status == SignatureStatus.COLLECTED

    def test_add_signature_unauthorized_signer(self):
        """Test adding signature from unauthorized signer."""
        result = SignatureResult(required_signers=["admin-1"], required_count=1)

        sig = Signature(signer_id="unauthorized-user")
        success = result.add_signature(sig)
        assert success is False
        assert result.collected_count == 0

    def test_add_duplicate_signature_updates(self):
        """Test that duplicate signatures update existing."""
        result = SignatureResult(required_signers=["admin-1"], required_count=1)

        sig1 = Signature(signer_id="admin-1", reasoning="First approval")
        result.add_signature(sig1)

        sig2 = Signature(signer_id="admin-1", reasoning="Updated approval")
        result.add_signature(sig2)

        assert result.collected_count == 1
        assert result.signatures[0].reasoning == "Updated approval"

    def test_signature_rejection(self):
        """Test signature rejection."""
        result = SignatureResult(
            decision_id="dec-reject", required_signers=["admin-1", "admin-2"], required_count=2
        )

        success = result.reject("admin-1", reason="Security concerns")
        assert success is True
        assert "admin-1" in result.rejected_by
        assert result.status == SignatureStatus.REJECTED
        assert result.is_valid is False
        assert "rejection_admin-1" in result.metadata

    def test_reject_unauthorized_signer(self):
        """Test rejection from unauthorized signer."""
        result = SignatureResult(required_signers=["admin-1"], required_count=1)

        success = result.reject("unauthorized-user")
        assert success is False
        assert len(result.rejected_by) == 0

    def test_signature_result_to_dict(self):
        """Test signature result to_dict serialization."""
        result = SignatureResult(
            decision_id="dec-dict", required_signers=["admin-1"], required_count=1
        )
        sig = Signature(signer_id="admin-1")
        result.add_signature(sig)

        d = result.to_dict()
        assert d["decision_id"] == "dec-dict"
        assert d["status"] == "collected"
        assert len(d["signatures"]) == 1
        assert d["collected_count"] == 1
        assert d["is_complete"] is True
        assert d["constitutional_hash"] == GUARD_CONSTITUTIONAL_HASH

    def test_threshold_based_completion(self):
        """Test threshold-based completion."""
        result = SignatureResult(
            required_signers=["admin-1", "admin-2", "admin-3"],
            required_count=3,
            threshold=0.66,  # 66% threshold (2/3 = 0.666...)
        )

        # Add 2 of 3 signatures (66.67%)
        result.add_signature(Signature(signer_id="admin-1"))
        assert result.is_complete is False

        result.add_signature(Signature(signer_id="admin-2"))
        assert result.is_complete is True


# ============================================================================
# CriticReview Tests
# ============================================================================


class TestCriticReview:
    """Test CriticReview dataclass."""

    def test_default_critic_review(self):
        """Test default critic review."""
        review = CriticReview(critic_id="critic-1")
        assert review.critic_id == "critic-1"
        assert review.review_type == "general"
        assert review.verdict == ""
        assert review.confidence == 1.0
        assert review.concerns == []
        assert review.recommendations == []

    def test_critic_review_with_details(self):
        """Test critic review with full details."""
        review = CriticReview(
            critic_id="safety-critic",
            review_type="safety",
            verdict="approve",
            reasoning="Action meets safety requirements",
            confidence=0.9,
            concerns=["Minor risk noted"],
            recommendations=["Add monitoring"],
        )
        assert review.review_type == "safety"
        assert review.verdict == "approve"
        assert len(review.concerns) == 1
        assert len(review.recommendations) == 1


# ============================================================================
# ReviewResult Tests
# ============================================================================


class TestReviewResult:
    """Test ReviewResult dataclass."""

    def test_default_review_result(self):
        """Test default review result."""
        result = ReviewResult()
        assert result.status == ReviewStatus.PENDING
        assert result.required_critics == []
        assert result.reviews == []
        assert result.approval_count == 0
        assert result.rejection_count == 0
        assert result.escalation_count == 0
        assert result.consensus_reached is False
        assert result.consensus_verdict == ""

    def test_add_review(self):
        """Test adding reviews."""
        result = ReviewResult(
            decision_id="dec-review", required_critics=["critic-1", "critic-2", "critic-3"]
        )

        review = CriticReview(
            critic_id="critic-1",
            verdict="approve",
            confidence=0.9,
            concerns=["Minor issue"],
            recommendations=["Monitor closely"],
        )
        success = result.add_review(review)

        assert success is True
        assert result.approval_count == 1
        assert "Minor issue" in result.all_concerns
        assert "Monitor closely" in result.all_recommendations

    def test_consensus_approval(self):
        """Test consensus reached with approval."""
        result = ReviewResult(
            decision_id="dec-consensus", required_critics=["critic-1", "critic-2", "critic-3"]
        )

        # Add 2 approvals (majority of 3)
        result.add_review(CriticReview(critic_id="critic-1", verdict="approve", confidence=0.9))
        result.add_review(CriticReview(critic_id="critic-2", verdict="approve", confidence=0.8))

        assert result.consensus_reached is True
        assert result.consensus_verdict == "approve"
        assert result.status == ReviewStatus.APPROVED
        assert result.completed_at is not None

    def test_consensus_rejection(self):
        """Test consensus reached with rejection."""
        result = ReviewResult(
            decision_id="dec-reject", required_critics=["critic-1", "critic-2", "critic-3"]
        )

        # Add 2 rejections (majority of 3)
        result.add_review(CriticReview(critic_id="critic-1", verdict="reject"))
        result.add_review(CriticReview(critic_id="critic-2", verdict="reject"))

        assert result.consensus_reached is True
        assert result.consensus_verdict == "reject"
        assert result.status == ReviewStatus.REJECTED

    def test_consensus_escalation(self):
        """Test consensus reached with escalation."""
        result = ReviewResult(
            decision_id="dec-escalate", required_critics=["critic-1", "critic-2", "critic-3"]
        )

        # Add 2 escalations (majority of 3)
        result.add_review(CriticReview(critic_id="critic-1", verdict="escalate"))
        result.add_review(CriticReview(critic_id="critic-2", verdict="escalate"))

        assert result.consensus_reached is True
        assert result.consensus_verdict == "escalate"
        assert result.status == ReviewStatus.ESCALATED

    def test_no_consensus_with_insufficient_reviews(self):
        """Test no consensus with insufficient reviews."""
        result = ReviewResult(
            decision_id="dec-insufficient",
            required_critics=["c-1", "c-2", "c-3", "c-4", "c-5"],  # 5 required
        )

        # Add only 1 review (need at least 3 for consensus)
        result.add_review(CriticReview(critic_id="c-1", verdict="approve"))

        assert result.consensus_reached is False
        assert result.status == ReviewStatus.PENDING

    def test_consensus_confidence_calculation(self):
        """Test consensus confidence is calculated correctly."""
        result = ReviewResult(decision_id="dec-confidence", required_critics=["c-1", "c-2", "c-3"])

        result.add_review(CriticReview(critic_id="c-1", verdict="approve", confidence=0.8))
        result.add_review(CriticReview(critic_id="c-2", verdict="approve", confidence=0.9))

        assert result.consensus_reached is True
        # Confidence should be (0.8 + 0.9) / 2 = 0.85
        assert result.consensus_confidence == pytest.approx(0.85, rel=0.01)

    def test_review_result_to_dict(self):
        """Test review result to_dict serialization."""
        result = ReviewResult(
            decision_id="dec-dict", required_critics=["critic-1"], review_types=["safety", "ethics"]
        )
        result.add_review(
            CriticReview(critic_id="critic-1", verdict="approve", reasoning="All checks passed")
        )

        d = result.to_dict()
        assert d["decision_id"] == "dec-dict"
        assert d["status"] == "approved"
        assert d["required_critics"] == ["critic-1"]
        assert d["review_types"] == ["safety", "ethics"]
        assert len(d["reviews"]) == 1
        assert d["approval_count"] == 1
        assert d["consensus_reached"] is True
        assert d["consensus_verdict"] == "approve"
        assert d["constitutional_hash"] == GUARD_CONSTITUTIONAL_HASH

    def test_empty_review_no_crash(self):
        """Test _check_consensus with no reviews doesn't crash."""
        result = ReviewResult()
        result._check_consensus()  # Should not raise
        assert result.consensus_reached is False


# ============================================================================
# Module Export Tests
# ============================================================================


class TestModuleExports:
    """Test module exports."""

    def test_all_exports(self):
        """Test __all__ exports are correct."""
        expected = [
            "GUARD_CONSTITUTIONAL_HASH",
            "GuardDecision",
            "SignatureStatus",
            "ReviewStatus",
            "GuardResult",
            "Signature",
            "SignatureResult",
            "CriticReview",
            "ReviewResult",
        ]
        assert set(_opa_models.__all__) == set(expected)
