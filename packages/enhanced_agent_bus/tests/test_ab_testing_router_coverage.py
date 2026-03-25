# Constitutional Hash: 608508a9bd224290
"""
Comprehensive coverage tests for ab_testing_infra/router.py.

Targets ≥90% coverage of ABTestRouter: routing, prediction, promotion,
properties, error paths, and all branching logic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Union
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.ab_testing_infra.models import (
    AB_TEST_CONFIDENCE_LEVEL,
    AB_TEST_MIN_IMPROVEMENT,
    AB_TEST_MIN_SAMPLES,
    AB_TEST_SPLIT,
    CANDIDATE_ALIAS,
    CHAMPION_ALIAS,
    MODEL_REGISTRY_NAME,
    CohortMetrics,
    CohortType,
    ComparisonResult,
    FeatureData,
    MetricsComparison,
    PredictionResult,
    PromotionResult,
    PromotionStatus,
    RoutingResult,
)
from enhanced_agent_bus.ab_testing_infra.router import ABTestRouter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(return_val=1):
    """Return a MagicMock with a .predict method."""
    m = MagicMock()
    m.predict = MagicMock(return_value=return_val)
    return m


def _make_router(**kw) -> ABTestRouter:
    """Create ABTestRouter with _ensure_initialized suppressed."""
    with patch.object(ABTestRouter, "_ensure_initialized"):
        return ABTestRouter(**kw)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestABTestRouterInit:
    """Tests for __init__ and __init__ branches."""

    def test_default_values(self):
        router = _make_router()
        assert router.candidate_split == AB_TEST_SPLIT
        assert router.champion_alias == CHAMPION_ALIAS
        assert router.candidate_alias == CANDIDATE_ALIAS
        assert router.min_samples == AB_TEST_MIN_SAMPLES
        assert router.confidence_level == AB_TEST_CONFIDENCE_LEVEL
        assert router.min_improvement == AB_TEST_MIN_IMPROVEMENT
        assert router.ab_test_active is True

    def test_split_ratio_param_takes_priority_over_candidate_split(self):
        router = _make_router(split_ratio=0.3, candidate_split=0.2)
        assert router.candidate_split == pytest.approx(0.3)

    def test_candidate_split_used_when_no_split_ratio(self):
        router = _make_router(candidate_split=0.25)
        assert router.candidate_split == pytest.approx(0.25)

    def test_fallback_to_ab_test_split_constant(self):
        router = _make_router()
        assert router.candidate_split == pytest.approx(AB_TEST_SPLIT)

    def test_invalid_split_too_high(self):
        with pytest.raises(ValueError, match="candidate_split must be between 0 and 1"):
            _make_router(candidate_split=1.1)

    def test_invalid_split_negative(self):
        with pytest.raises(ValueError, match="candidate_split must be between 0 and 1"):
            _make_router(split_ratio=-0.01)

    def test_boundary_zero_is_valid(self):
        router = _make_router(candidate_split=0.0)
        assert router.candidate_split == 0.0

    def test_boundary_one_is_valid(self):
        router = _make_router(candidate_split=1.0)
        assert router.candidate_split == 1.0

    def test_ab_test_active_is_true_by_default(self):
        router = _make_router()
        assert router.ab_test_active is True


# ---------------------------------------------------------------------------
# _ensure_initialized
# ---------------------------------------------------------------------------


class TestEnsureInitialized:
    """Tests for _ensure_initialized loading logic."""

    def test_skips_load_when_model_manager_is_ready(self):
        with patch.object(ABTestRouter, "_ensure_initialized"):
            router = ABTestRouter(candidate_split=0.1)

        router.model_manager.models_loaded = True
        router.model_manager.champion_model = MagicMock()
        router.model_manager.candidate_model = MagicMock()

        # Calling directly should NOT load (is_ready returns True)
        with patch.object(router.model_manager, "load_models") as mock_load:
            router._ensure_initialized()
            mock_load.assert_not_called()

    def test_attempts_load_when_not_ready_success(self):
        with patch.object(ABTestRouter, "_ensure_initialized"):
            router = ABTestRouter(candidate_split=0.1)

        with (
            patch.object(router.model_manager, "is_ready", return_value=False),
            patch.object(router.model_manager, "load_models", return_value=True) as mock_load,
        ):
            router._ensure_initialized()
            mock_load.assert_called_once()

    def test_logs_warning_when_load_fails(self):
        with patch.object(ABTestRouter, "_ensure_initialized"):
            router = ABTestRouter(candidate_split=0.1)

        with (
            patch.object(router.model_manager, "is_ready", return_value=False),
            patch.object(router.model_manager, "load_models", return_value=False),
            patch("enhanced_agent_bus.ab_testing_infra.router.logger") as mock_log,
        ):
            router._ensure_initialized()
            mock_log.warning.assert_called_once()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestABTestRouterProperties:
    """Tests for all public properties and their setters."""

    @pytest.fixture
    def router(self):
        return _make_router(candidate_split=0.2)

    def test_champion_metrics_property(self, router):
        m = router._champion_metrics
        assert isinstance(m, CohortMetrics)
        assert m.cohort == CohortType.CHAMPION

    def test_candidate_metrics_property(self, router):
        m = router._candidate_metrics
        assert isinstance(m, CohortMetrics)
        assert m.cohort == CohortType.CANDIDATE

    def test_champion_model_getter_setter(self, router):
        model = _make_model()
        router.champion_model = model
        assert router.champion_model is model

    def test_candidate_model_getter_setter(self, router):
        model = _make_model()
        router.candidate_model = model
        assert router.candidate_model is model

    def test_champion_version_getter_setter(self, router):
        router.champion_version = 42
        assert router.champion_version == 42

    def test_candidate_version_getter_setter(self, router):
        router.candidate_version = "v3"
        assert router.candidate_version == "v3"

    def test_split_ratio_getter(self, router):
        assert router.split_ratio == pytest.approx(0.2)

    def test_split_ratio_setter(self, router):
        router.split_ratio = 0.5
        assert router.split_ratio == pytest.approx(0.5)

    def test_candidate_split_getter(self, router):
        assert router.candidate_split == pytest.approx(0.2)

    def test_candidate_split_setter(self, router):
        router.candidate_split = 0.4
        assert router.candidate_split == pytest.approx(0.4)

    def test_min_samples_getter(self, router):
        assert router.min_samples == AB_TEST_MIN_SAMPLES

    def test_min_samples_setter(self, router):
        router.min_samples = 500
        assert router.min_samples == 500


# ---------------------------------------------------------------------------
# set_* convenience methods
# ---------------------------------------------------------------------------


class TestSetModelMethods:
    """Tests for set_champion_model / set_candidate_model delegation."""

    @pytest.fixture
    def router(self):
        return _make_router()

    def test_set_champion_model(self, router):
        model = _make_model()
        router.set_champion_model(model, version=7)
        assert router.champion_model is model
        assert router.champion_version == 7

    def test_set_candidate_model(self, router):
        model = _make_model()
        router.set_candidate_model(model, version=3)
        assert router.candidate_model is model
        assert router.candidate_version == 3

    def test_set_champion_model_default_version(self, router):
        model = _make_model()
        router.set_champion_model(model)
        assert router.champion_model is model

    def test_set_ab_test_active(self, router):
        router.set_ab_test_active(False)
        assert router.ab_test_active is False
        router.set_ab_test_active(True)
        assert router.ab_test_active is True


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouting:
    """Tests for the route() method and hash computation."""

    @pytest.fixture
    def router(self):
        return _make_router(candidate_split=0.5)

    def test_route_returns_routing_result(self, router):
        result = router.route("req-1")
        assert isinstance(result, RoutingResult)
        assert result.request_id == "req-1"

    def test_route_cohort_is_valid(self, router):
        for i in range(20):
            result = router.route(f"request-{i}")
            assert result.cohort in (CohortType.CHAMPION, CohortType.CANDIDATE)

    def test_route_is_deterministic(self, router):
        r1 = router.route("stable-id")
        r2 = router.route("stable-id")
        assert r1.cohort == r2.cohort
        assert r1.model_version == r2.model_version

    def test_route_inactive_always_champion(self, router):
        router.set_ab_test_active(False)
        for i in range(20):
            result = router.route(f"request-{i}")
            assert result.cohort == CohortType.CHAMPION

    def test_route_inactive_no_model_version(self, router):
        router.set_ab_test_active(False)
        result = router.route("no-version")
        assert result.model_version is None

    def test_route_stores_cohort_in_request_cohorts(self, router):
        router.route("tracked-req")
        assert "tracked-req" in router._request_cohorts

    def test_route_candidate_version_included(self, router):
        # Force candidate cohort by setting split=1.0 so all go to candidate
        router.candidate_split = 1.0
        router.candidate_version = 99
        result = router.route("candidate-req")
        if result.cohort == CohortType.CANDIDATE:
            assert result.model_version == 99

    def test_route_champion_version_included(self, router):
        # Force champion by setting split=0.0
        router.candidate_split = 0.0
        router.champion_version = 5
        result = router.route("champion-req")
        assert result.cohort == CohortType.CHAMPION
        assert result.model_version == 5

    def test_route_version_none_when_not_set(self, router):
        router.candidate_split = 0.0
        result = router.route("no-ver")
        assert result.model_version is None

    def test_compute_hash_value_range(self, router):
        for i in range(50):
            v = router._compute_hash_value(f"id-{i}")
            assert 0.0 <= v < 1.0

    def test_compute_hash_value_deterministic(self, router):
        v1 = router._compute_hash_value("same")
        v2 = router._compute_hash_value("same")
        assert v1 == v2

    def test_compute_hash_matches_sha256(self, router):
        rid = "test-hash-match"
        expected_int = int(hashlib.sha256(rid.encode()).hexdigest(), 16)
        expected = (expected_int % 10000) / 10000.0
        assert router._compute_hash_value(rid) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


class TestPrediction:
    """Tests for the predict() method."""

    @pytest.fixture
    def router(self):
        r = _make_router(candidate_split=0.5)
        r.set_champion_model(_make_model(return_val=1), version=1)
        r.set_candidate_model(_make_model(return_val=0), version=2)
        return r

    def test_predict_with_cohort_type(self, router):
        result = router.predict(CohortType.CHAMPION, [1.0, 2.0])
        assert isinstance(result, PredictionResult)
        assert result.cohort == CohortType.CHAMPION
        assert result.prediction == 1
        assert result.success is True

    def test_predict_with_routing_result(self, router):
        routing = RoutingResult(cohort=CohortType.CHAMPION, request_id="req-x")
        result = router.predict(routing, [1.0])
        assert result.request_id == "req-x"

    def test_predict_with_routing_result_uses_routing_request_id(self, router):
        routing = RoutingResult(cohort=CohortType.CANDIDATE, request_id="auto-id")
        result = router.predict(routing, [1.0], request_id="")
        assert result.request_id == "auto-id"

    def test_predict_with_routing_result_explicit_request_id_overrides(self, router):
        routing = RoutingResult(cohort=CohortType.CHAMPION, request_id="routing-id")
        result = router.predict(routing, [1.0], request_id="explicit-id")
        assert result.request_id == "explicit-id"

    def test_predict_candidate_cohort(self, router):
        result = router.predict(CohortType.CANDIDATE, [1.0, 2.0])
        assert result.cohort == CohortType.CANDIDATE
        assert result.prediction == 0

    def test_predict_records_latency(self, router):
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.latency_ms >= 0.0

    def test_predict_no_model_returns_failure(self):
        r = _make_router(candidate_split=0.5)
        result = r.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False
        assert result.prediction is None
        assert result.error is not None

    def test_predict_callable_model(self, router):
        """Model without .predict attribute — treated as callable."""
        func_model = MagicMock(spec=[])  # no .predict attribute
        func_model.return_value = 42
        router.champion_model = func_model
        result = router.predict(CohortType.CHAMPION, {"x": 1.0})
        assert result.prediction == 42
        assert result.success is True

    def test_predict_model_raises_runtime_error(self, router):
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=RuntimeError("boom"))
        router.champion_model = bad_model
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False
        assert "boom" in result.error

    def test_predict_model_raises_value_error(self, router):
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=ValueError("bad val"))
        router.champion_model = bad_model
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False

    def test_predict_model_raises_type_error(self, router):
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=TypeError("type"))
        router.champion_model = bad_model
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False

    def test_predict_model_raises_key_error(self, router):
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=KeyError("key"))
        router.champion_model = bad_model
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False

    def test_predict_model_raises_attribute_error(self, router):
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=AttributeError("attr"))
        router.champion_model = bad_model
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.success is False

    def test_predict_version_in_result(self, router):
        result = router.predict(CohortType.CHAMPION, [1.0])
        assert result.model_version == 1

    def test_predict_version_none_when_unset(self):
        r = _make_router(candidate_split=0.0)
        r.set_champion_model(_make_model(), version=None)
        result = r.predict(CohortType.CHAMPION, [1.0])
        assert result.model_version is None

    def test_route_and_predict(self, router):
        result = router.route_and_predict("combo-req", [1.0, 2.0])
        assert isinstance(result, PredictionResult)
        assert result.request_id == "combo-req"


# ---------------------------------------------------------------------------
# record_outcome
# ---------------------------------------------------------------------------


class TestRecordOutcome:
    """Tests for record_outcome()."""

    @pytest.fixture
    def router(self):
        return _make_router(candidate_split=0.5)

    def test_record_outcome_unknown_request_returns_false(self, router):
        ok = router.record_outcome("ghost-req", predicted=1, actual=1)
        assert ok is False

    def test_record_outcome_known_request_returns_true(self, router):
        router.route("known-req")
        ok = router.record_outcome("known-req", predicted=1, actual=1)
        assert ok is True

    def test_record_outcome_none_latency_defaults_to_zero(self, router):
        router.route("lat-req")
        ok = router.record_outcome("lat-req", predicted=1, actual=1, latency_ms=None)
        assert ok is True

    def test_record_outcome_explicit_latency(self, router):
        router.route("lat2-req")
        ok = router.record_outcome("lat2-req", predicted=0, actual=1, latency_ms=12.5)
        assert ok is True


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


class TestMetricsHelpers:
    """Tests for get_metrics_summary, get_champion/candidate_metrics, etc."""

    @pytest.fixture
    def router(self):
        return _make_router(candidate_split=0.2)

    def test_get_champion_metrics_returns_cohort_metrics(self, router):
        m = router.get_champion_metrics()
        assert isinstance(m, CohortMetrics)
        assert m.cohort == CohortType.CHAMPION

    def test_get_candidate_metrics_returns_cohort_metrics(self, router):
        m = router.get_candidate_metrics()
        assert isinstance(m, CohortMetrics)
        assert m.cohort == CohortType.CANDIDATE

    def test_get_metrics_summary_keys(self, router):
        s = router.get_metrics_summary()
        for key in (
            "ab_test_active",
            "candidate_split",
            "champion_version",
            "candidate_version",
            "champion_alias",
            "candidate_alias",
            "has_champion_model",
            "has_candidate_model",
            "champion",
            "candidate",
        ):
            assert key in s, f"Missing key: {key}"

    def test_get_metrics_summary_has_model_flags(self, router):
        s = router.get_metrics_summary()
        assert s["has_champion_model"] is False
        assert s["has_candidate_model"] is False

    def test_get_metrics_summary_has_model_flags_when_set(self, router):
        router.set_champion_model(_make_model())
        router.set_candidate_model(_make_model())
        s = router.get_metrics_summary()
        assert s["has_champion_model"] is True
        assert s["has_candidate_model"] is True

    def test_get_traffic_distribution(self, router):
        dist = router.get_traffic_distribution(n_requests=200)
        assert "champion_count" in dist
        assert "candidate_count" in dist
        assert dist["champion_count"] + dist["candidate_count"] == 200

    def test_compare_metrics_returns_metrics_comparison(self, router):
        comparison = router.compare_metrics()
        assert isinstance(comparison, MetricsComparison)


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


class TestPromotion:
    """Tests for promote_candidate()."""

    def _promotable_router(self):
        """Router where candidate is clearly better than champion."""
        router = _make_router(candidate_split=0.1, min_samples=50)

        router.champion_model = _make_model(1)
        router.champion_version = 1
        router.candidate_model = _make_model(0)
        router.candidate_version = 2

        # Champion: 80 % accuracy
        for i in range(200):
            router._champion_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 160 else 0,
                actual=1,
            )
        # Candidate: 95 % accuracy (clearly better)
        for i in range(200):
            router._candidate_metrics.record_request(
                latency_ms=45.0,
                prediction=1 if i < 190 else 0,
                actual=1,
            )
        return router

    def test_promote_insufficient_data(self):
        router = _make_router(min_samples=100_000)
        result = router.promote_candidate()
        assert result.status == PromotionStatus.NOT_READY
        assert result.success is False

    def test_promote_blocked_candidate_worse(self):
        router = _make_router(min_samples=50)
        # Champion: 95 %
        for i in range(200):
            router._champion_metrics.record_request(50.0, 1 if i < 190 else 0, 1)
        # Candidate: 70 %
        for i in range(200):
            router._candidate_metrics.record_request(45.0, 1 if i < 140 else 0, 1)
        result = router.promote_candidate()
        assert result.status == PromotionStatus.BLOCKED

    def test_promote_force_bypasses_checks(self):
        router = _make_router(min_samples=100_000)
        router.candidate_model = _make_model()
        router.candidate_version = 5
        result = router.promote_candidate(force=True)
        assert result.status == PromotionStatus.PROMOTED

    def test_promote_force_no_candidate_model_fails(self):
        router = _make_router(min_samples=100_000)
        # candidate_model is None (default)
        result = router.promote_candidate(force=True)
        assert result.status == PromotionStatus.ERROR

    def test_promote_success_swaps_models(self):
        router = self._promotable_router()
        old_candidate = router.candidate_model
        result = router.promote_candidate()
        assert result.status == PromotionStatus.PROMOTED
        assert result.success is True
        assert router.champion_model is old_candidate
        assert router.candidate_model is None

    def test_promote_success_versions(self):
        router = self._promotable_router()
        result = router.promote_candidate()
        assert result.previous_champion_version == 1
        assert result.new_champion_version == 2

    def test_promote_success_resets_metrics(self):
        router = self._promotable_router()
        router.promote_candidate()
        assert router._champion_metrics.request_count == 0
        assert router._candidate_metrics.request_count == 0

    def test_promote_success_timestamp(self):
        router = self._promotable_router()
        result = router.promote_candidate()
        assert result.promoted_at is not None
        assert isinstance(result.promoted_at, datetime)

    def test_promote_version_manager_mock_none_raises(self):
        """If _version_manager_mock attribute exists and is None, raise."""
        router = self._promotable_router()
        router._version_manager_mock = None
        result = router.promote_candidate()
        assert result.status == PromotionStatus.ERROR

    def test_promote_version_none_in_result(self):
        router = _make_router(min_samples=50)
        router.candidate_model = _make_model()
        router.candidate_version = None
        router.champion_version = None
        # Fill enough data so candidate appears better
        for i in range(200):
            router._champion_metrics.record_request(50.0, 1 if i < 160 else 0, 1)
        for i in range(200):
            router._candidate_metrics.record_request(45.0, 1 if i < 190 else 0, 1)
        result = router.promote_candidate()
        assert result.status == PromotionStatus.PROMOTED
        assert result.previous_champion_version is None
        assert result.new_champion_version is None

    def test_promote_comparison_included_in_result(self):
        router = self._promotable_router()
        result = router.promote_candidate()
        assert result.comparison is not None
        assert isinstance(result.comparison, MetricsComparison)

    def test_promote_blocked_comparison_included(self):
        router = _make_router(min_samples=50)
        for i in range(200):
            router._champion_metrics.record_request(50.0, 1 if i < 190 else 0, 1)
        for i in range(200):
            router._candidate_metrics.record_request(45.0, 1 if i < 140 else 0, 1)
        result = router.promote_candidate()
        assert result.comparison is not None
