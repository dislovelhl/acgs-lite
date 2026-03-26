"""
Tests for AmendmentRecommender -- targets >= 90% coverage.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.adaptive_governance.amendment_recommender import (
    AmendmentRecommendation,
    AmendmentRecommender,
    RecommendationPriority,
    RecommendationTrigger,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recommender(**kwargs) -> AmendmentRecommender:
    defaults = {
        "risk_threshold": 0.8,
        "cooldown_minutes": 60,
        "max_pending_recommendations": 10,
    }
    defaults.update(kwargs)
    return AmendmentRecommender(**defaults)


# ---------------------------------------------------------------------------
# evaluate_risk_signal
# ---------------------------------------------------------------------------


class TestEvaluateRiskSignal:
    def test_below_threshold_returns_none(self) -> None:
        recommender = _make_recommender(risk_threshold=0.8)
        result = recommender.evaluate_risk_signal(risk_score=0.5, trajectory_prefix=[0, 1])
        assert result is None
        assert len(recommender.get_pending()) == 0

    def test_at_threshold_returns_none(self) -> None:
        """Risk must *exceed* threshold, not merely equal it."""
        recommender = _make_recommender(risk_threshold=0.8)
        result = recommender.evaluate_risk_signal(risk_score=0.79, trajectory_prefix=[0, 1])
        assert result is None

    def test_above_threshold_returns_recommendation(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[3])
        assert result is not None
        assert isinstance(result, AmendmentRecommendation)
        assert result.trigger == RecommendationTrigger.DTMC_RISK_THRESHOLD
        assert result.risk_score == 0.85
        assert len(recommender.get_pending()) == 1

    def test_cooldown_prevents_duplicate(self) -> None:
        recommender = _make_recommender(cooldown_minutes=60)
        first = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[3])
        assert first is not None
        # Same area should be in cooldown
        second = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[3])
        assert second is None
        assert len(recommender.get_pending()) == 1

    def test_max_pending_cap(self) -> None:
        recommender = _make_recommender(max_pending_recommendations=2, cooldown_minutes=0)
        # Use different trajectory prefixes to avoid cooldown
        r1 = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[0])
        r2 = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[1])
        r3 = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[2])
        assert r1 is not None
        assert r2 is not None
        assert r3 is None
        assert len(recommender.get_pending()) == 2

    def test_empty_trajectory_uses_general_area(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[])
        assert result is not None
        assert result.target_area == "governance.general"

    def test_context_overrides_target_area(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(
            risk_score=0.85,
            trajectory_prefix=[3],
            context={"target_area": "custom.area"},
        )
        assert result is not None
        assert result.target_area == "custom.area"

    def test_unknown_state_falls_back_to_general(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[99])
        assert result is not None
        assert result.target_area == "governance.general"


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------


class TestPriorityScoring:
    def test_critical_at_095(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.96, trajectory_prefix=[4])
        assert result is not None
        assert result.priority == RecommendationPriority.CRITICAL

    def test_high_at_080(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[3])
        assert result is not None
        assert result.priority == RecommendationPriority.HIGH

    def test_medium_at_050(self) -> None:
        recommender = _make_recommender(risk_threshold=0.4)
        result = recommender.evaluate_risk_signal(risk_score=0.55, trajectory_prefix=[2])
        assert result is not None
        assert result.priority == RecommendationPriority.MEDIUM

    def test_low_below_050(self) -> None:
        recommender = _make_recommender(risk_threshold=0.1)
        result = recommender.evaluate_risk_signal(risk_score=0.2, trajectory_prefix=[1])
        assert result is not None
        assert result.priority == RecommendationPriority.LOW


# ---------------------------------------------------------------------------
# evaluate_threshold_drift
# ---------------------------------------------------------------------------


class TestEvaluateThresholdDrift:
    def test_significant_drift_generates_recommendation(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_threshold_drift(
            metric_name="impact_score",
            current_value=0.9,
            baseline_value=0.7,
            drift_magnitude=0.25,
        )
        assert result is not None
        assert result.trigger == RecommendationTrigger.THRESHOLD_DRIFT
        assert result.priority == RecommendationPriority.MEDIUM
        assert result.target_area == "thresholds.impact_score"
        assert "thresholds.impact_score" in result.proposed_changes

    def test_small_drift_returns_none(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_threshold_drift(
            metric_name="impact_score",
            current_value=0.71,
            baseline_value=0.70,
            drift_magnitude=0.05,
        )
        assert result is None

    def test_negative_drift_with_magnitude(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_threshold_drift(
            metric_name="risk_tolerance",
            current_value=0.5,
            baseline_value=0.7,
            drift_magnitude=-0.3,
        )
        assert result is not None
        assert result.risk_score == 0.3  # abs(drift_magnitude)

    def test_drift_cooldown(self) -> None:
        recommender = _make_recommender(cooldown_minutes=60)
        first = recommender.evaluate_threshold_drift(
            metric_name="impact_score",
            current_value=0.9,
            baseline_value=0.7,
            drift_magnitude=0.25,
        )
        assert first is not None
        second = recommender.evaluate_threshold_drift(
            metric_name="impact_score",
            current_value=0.95,
            baseline_value=0.7,
            drift_magnitude=0.35,
        )
        assert second is None

    def test_drift_max_pending_cap(self) -> None:
        recommender = _make_recommender(max_pending_recommendations=1, cooldown_minutes=0)
        first = recommender.evaluate_threshold_drift(
            metric_name="m1",
            current_value=0.9,
            baseline_value=0.5,
            drift_magnitude=0.8,
        )
        second = recommender.evaluate_threshold_drift(
            metric_name="m2",
            current_value=0.9,
            baseline_value=0.5,
            drift_magnitude=0.8,
        )
        assert first is not None
        assert second is None


# ---------------------------------------------------------------------------
# Acknowledge and dismiss
# ---------------------------------------------------------------------------


class TestAcknowledgeAndDismiss:
    def test_acknowledge_moves_to_history(self) -> None:
        recommender = _make_recommender()
        rec = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[3])
        assert rec is not None
        assert len(recommender.get_pending()) == 1

        acked = recommender.acknowledge(rec.recommendation_id)
        assert acked is not None
        assert acked.recommendation_id == rec.recommendation_id
        assert len(recommender.get_pending()) == 0
        assert len(recommender._history) == 1

    def test_acknowledge_unknown_returns_none(self) -> None:
        recommender = _make_recommender()
        result = recommender.acknowledge("nonexistent-id")
        assert result is None

    def test_dismiss_removes_from_pending(self) -> None:
        recommender = _make_recommender()
        rec = recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[3])
        assert rec is not None
        dismissed = recommender.dismiss(rec.recommendation_id, reason="not relevant")
        assert dismissed is True
        assert len(recommender.get_pending()) == 0
        assert len(recommender._history) == 1

    def test_dismiss_unknown_returns_false(self) -> None:
        recommender = _make_recommender()
        result = recommender.dismiss("nonexistent-id")
        assert result is False


# ---------------------------------------------------------------------------
# get_pending returns copy
# ---------------------------------------------------------------------------


class TestGetPending:
    def test_returns_copy_not_reference(self) -> None:
        recommender = _make_recommender()
        recommender.evaluate_risk_signal(risk_score=0.9, trajectory_prefix=[3])
        pending = recommender.get_pending()
        assert len(pending) == 1
        pending.clear()
        assert len(recommender.get_pending()) == 1  # original unaffected


# ---------------------------------------------------------------------------
# Evidence and ID format
# ---------------------------------------------------------------------------


class TestRecommendationStructure:
    def test_evidence_fields(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(
            risk_score=0.85,
            trajectory_prefix=[2, 3],
            context={"source": "test"},
        )
        assert result is not None
        assert result.evidence["risk_score"] == 0.85
        assert result.evidence["threshold"] == 0.8
        assert result.evidence["trajectory_prefix"] == [2, 3]
        assert result.evidence["context"] == {"source": "test"}

    def test_recommendation_id_format(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[3])
        assert result is not None
        assert result.recommendation_id.startswith("REC-")
        parts = result.recommendation_id.split("-", 2)
        assert len(parts) >= 2
        # Second part should be a timestamp (digits only)
        assert parts[1].isdigit()

    def test_created_at_is_utc(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[3])
        assert result is not None
        assert result.created_at.tzinfo is not None

    def test_proposed_changes_structure(self) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[3])
        assert result is not None
        area = result.target_area
        assert area in result.proposed_changes
        change = result.proposed_changes[area]
        assert change["action"] == "review_and_tighten"
        assert change["requires_human_review"] is True
        assert change["current_risk"] == 0.85


# ---------------------------------------------------------------------------
# State area mapping
# ---------------------------------------------------------------------------


class TestStateAreaMapping:
    @pytest.mark.parametrize(
        ("state", "expected_area"),
        [
            (0, "governance.negligible"),
            (1, "governance.low_risk"),
            (2, "governance.medium_risk"),
            (3, "governance.high_risk"),
            (4, "governance.critical"),
        ],
    )
    def test_state_maps_to_area(self, state: int, expected_area: str) -> None:
        recommender = _make_recommender()
        result = recommender.evaluate_risk_signal(risk_score=0.85, trajectory_prefix=[state])
        assert result is not None
        assert result.target_area == expected_area
