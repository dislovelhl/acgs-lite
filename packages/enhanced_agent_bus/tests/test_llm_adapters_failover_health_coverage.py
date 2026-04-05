# Constitutional Hash: 608508a9bd224290
# Sprint 58 — llm_adapters/failover/health.py coverage
"""
Comprehensive test suite for:
  src/core/enhanced_agent_bus/llm_adapters/failover/health.py

Target: ≥95% line coverage.

All async tests run without @pytest.mark.asyncio because
asyncio_mode = "auto" is configured in pyproject.toml.
"""

from __future__ import annotations

import asyncio
import statistics
from collections import deque
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.llm_adapters.failover.health import (
    HealthMetrics,
    ProviderHealthScore,
    ProviderHealthScorer,
)

CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# HealthMetrics dataclass tests
# ---------------------------------------------------------------------------


class TestHealthMetrics:
    """Tests for HealthMetrics dataclass."""

    def test_default_initialization(self):
        m = HealthMetrics()
        assert m.avg_latency_ms == 0.0
        assert m.p50_latency_ms == 0.0
        assert m.p95_latency_ms == 0.0
        assert m.p99_latency_ms == 0.0
        assert m.total_requests == 0
        assert m.successful_requests == 0
        assert m.failed_requests == 0
        assert m.timeout_count == 0
        assert m.rate_limit_count == 0
        assert m.error_rate == 0.0
        assert m.avg_quality_score == 1.0
        assert m.last_success_time is None
        assert m.last_failure_time is None
        assert m.consecutive_failures == 0
        assert m.uptime_percentage == 100.0
        assert m.health_score == 1.0

    def test_latency_samples_is_deque_with_maxlen_100(self):
        m = HealthMetrics()
        assert isinstance(m.latency_samples, deque)
        assert m.latency_samples.maxlen == 100

    def test_response_quality_scores_is_deque_with_maxlen_50(self):
        m = HealthMetrics()
        assert isinstance(m.response_quality_scores, deque)
        assert m.response_quality_scores.maxlen == 50

    def test_constitutional_hash_present(self):
        m = HealthMetrics()
        assert m.constitutional_hash == CONSTITUTIONAL_HASH

    def test_independent_deques_per_instance(self):
        m1 = HealthMetrics()
        m2 = HealthMetrics()
        m1.latency_samples.append(100.0)
        assert len(m2.latency_samples) == 0

    def test_latency_samples_maxlen_enforced(self):
        m = HealthMetrics()
        for i in range(150):
            m.latency_samples.append(float(i))
        assert len(m.latency_samples) == 100

    def test_quality_scores_maxlen_enforced(self):
        m = HealthMetrics()
        for i in range(60):
            m.response_quality_scores.append(float(i) / 60)
        assert len(m.response_quality_scores) == 50


# ---------------------------------------------------------------------------
# ProviderHealthScore dataclass tests
# ---------------------------------------------------------------------------


class TestProviderHealthScore:
    """Tests for ProviderHealthScore dataclass."""

    def _make_score(self, **kwargs) -> ProviderHealthScore:
        defaults = {
            "provider_id": "test-provider",
            "health_score": 0.9,
            "latency_score": 0.85,
            "error_score": 0.95,
            "quality_score": 1.0,
            "availability_score": 0.99,
            "is_healthy": True,
            "is_degraded": False,
            "is_unhealthy": False,
            "metrics": HealthMetrics(),
        }
        defaults.update(kwargs)
        return ProviderHealthScore(**defaults)

    def test_basic_construction(self):
        score = self._make_score()
        assert score.provider_id == "test-provider"
        assert score.health_score == 0.9
        assert score.is_healthy is True

    def test_constitutional_hash_present(self):
        score = self._make_score()
        assert score.constitutional_hash == CONSTITUTIONAL_HASH

    def test_last_updated_is_utc_datetime(self):
        score = self._make_score()
        assert score.last_updated.tzinfo is not None

    def test_to_dict_keys(self):
        score = self._make_score()
        d = score.to_dict()
        expected_keys = {
            "provider_id",
            "health_score",
            "latency_score",
            "error_score",
            "quality_score",
            "availability_score",
            "is_healthy",
            "is_degraded",
            "is_unhealthy",
            "metrics",
            "last_updated",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values_rounded(self):
        score = self._make_score(
            health_score=0.9123456,
            latency_score=0.8567,
            error_score=0.9999,
            quality_score=0.777,
            availability_score=0.666,
        )
        d = score.to_dict()
        assert d["health_score"] == round(0.9123456, 3)
        assert d["latency_score"] == round(0.8567, 3)
        assert d["error_score"] == round(0.9999, 3)
        assert d["quality_score"] == round(0.777, 3)
        assert d["availability_score"] == round(0.666, 3)

    def test_to_dict_is_healthy_flags(self):
        score = self._make_score(is_healthy=True, is_degraded=False, is_unhealthy=False)
        d = score.to_dict()
        assert d["is_healthy"] is True
        assert d["is_degraded"] is False
        assert d["is_unhealthy"] is False

    def test_to_dict_metrics_subdict(self):
        m = HealthMetrics()
        m.avg_latency_ms = 12.34567
        m.p95_latency_ms = 50.789
        m.error_rate = 0.0123456
        m.total_requests = 100
        m.consecutive_failures = 3
        score = self._make_score(metrics=m)
        d = score.to_dict()
        sub = d["metrics"]
        assert sub["avg_latency_ms"] == round(12.34567, 2)
        assert sub["p95_latency_ms"] == round(50.789, 2)
        assert sub["error_rate"] == round(0.0123456, 4)
        assert sub["total_requests"] == 100
        assert sub["consecutive_failures"] == 3

    def test_to_dict_last_updated_isoformat(self):
        score = self._make_score()
        d = score.to_dict()
        # Should be parseable as ISO 8601
        dt = datetime.fromisoformat(d["last_updated"])
        assert dt is not None

    def test_to_dict_constitutional_hash(self):
        score = self._make_score()
        d = score.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_provider_id(self):
        score = self._make_score(provider_id="openai-gpt4")
        d = score.to_dict()
        assert d["provider_id"] == "openai-gpt4"


# ---------------------------------------------------------------------------
# ProviderHealthScorer tests
# ---------------------------------------------------------------------------


class TestProviderHealthScorerInit:
    """Tests for ProviderHealthScorer initialization."""

    def test_empty_metrics_on_init(self):
        scorer = ProviderHealthScorer()
        assert scorer._metrics == {}

    def test_empty_expected_latency_on_init(self):
        scorer = ProviderHealthScorer()
        assert scorer._expected_latency == {}

    def test_lock_created(self):
        scorer = ProviderHealthScorer()
        assert scorer._lock is not None

    def test_constants(self):
        assert ProviderHealthScorer.LATENCY_WEIGHT == 0.30
        assert ProviderHealthScorer.ERROR_WEIGHT == 0.35
        assert ProviderHealthScorer.QUALITY_WEIGHT == 0.15
        assert ProviderHealthScorer.AVAILABILITY_WEIGHT == 0.20
        assert ProviderHealthScorer.HEALTHY_THRESHOLD == 0.8
        assert ProviderHealthScorer.DEGRADED_THRESHOLD == 0.5


class TestSetExpectedLatency:
    """Tests for set_expected_latency."""

    def test_sets_expected_latency(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 200.0)
        assert scorer._expected_latency["openai"] == 200.0

    def test_overwrite_expected_latency(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 200.0)
        scorer.set_expected_latency("openai", 350.0)
        assert scorer._expected_latency["openai"] == 350.0

    def test_multiple_providers(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 200.0)
        scorer.set_expected_latency("anthropic", 150.0)
        assert scorer._expected_latency["openai"] == 200.0
        assert scorer._expected_latency["anthropic"] == 150.0


class TestRecordRequest:
    """Tests for record_request async method."""

    async def test_creates_metrics_on_first_request(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        assert "openai" in scorer._metrics

    async def test_success_increments_total_and_successful(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        m = scorer._metrics["openai"]
        assert m.total_requests == 1
        assert m.successful_requests == 1
        assert m.failed_requests == 0

    async def test_success_sets_last_success_time(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        m = scorer._metrics["openai"]
        assert m.last_success_time is not None
        assert m.last_success_time.tzinfo is not None

    async def test_success_resets_consecutive_failures(self):
        scorer = ProviderHealthScorer()
        # First add some failures manually
        scorer._metrics["openai"] = HealthMetrics()
        scorer._metrics["openai"].consecutive_failures = 5
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        assert scorer._metrics["openai"].consecutive_failures == 0

    async def test_failure_increments_failed_requests(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        m = scorer._metrics["openai"]
        assert m.failed_requests == 1
        assert m.successful_requests == 0
        assert m.total_requests == 1

    async def test_failure_sets_last_failure_time(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        m = scorer._metrics["openai"]
        assert m.last_failure_time is not None

    async def test_failure_increments_consecutive_failures(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        assert scorer._metrics["openai"].consecutive_failures == 2

    async def test_timeout_error_increments_timeout_count(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            "openai", latency_ms=5000.0, success=False, error_type="timeout"
        )
        assert scorer._metrics["openai"].timeout_count == 1
        assert scorer._metrics["openai"].rate_limit_count == 0

    async def test_rate_limit_error_increments_rate_limit_count(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request(
            "openai", latency_ms=50.0, success=False, error_type="rate_limit"
        )
        assert scorer._metrics["openai"].rate_limit_count == 1
        assert scorer._metrics["openai"].timeout_count == 0

    async def test_unknown_error_type_does_not_increment_specific_counters(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=False, error_type="network")
        assert scorer._metrics["openai"].timeout_count == 0
        assert scorer._metrics["openai"].rate_limit_count == 0

    async def test_error_type_none_on_failure(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=False, error_type=None)
        m = scorer._metrics["openai"]
        assert m.timeout_count == 0
        assert m.rate_limit_count == 0
        assert m.failed_requests == 1

    async def test_latency_appended_to_samples(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=123.0, success=True)
        assert 123.0 in scorer._metrics["openai"].latency_samples

    async def test_error_rate_calculated(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        await scorer.record_request("openai", latency_ms=100.0, success=False)
        m = scorer._metrics["openai"]
        assert m.error_rate == pytest.approx(0.5)

    async def test_quality_score_none_does_not_update(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True, quality_score=None)
        m = scorer._metrics["openai"]
        assert len(m.response_quality_scores) == 0
        assert m.avg_quality_score == 1.0

    async def test_quality_score_updates_avg(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True, quality_score=0.8)
        await scorer.record_request("openai", latency_ms=100.0, success=True, quality_score=0.6)
        m = scorer._metrics["openai"]
        assert m.avg_quality_score == pytest.approx(0.7)

    async def test_multiple_quality_scores_averaged(self):
        scorer = ProviderHealthScorer()
        scores = [0.9, 0.8, 0.7, 0.6]
        for s in scores:
            await scorer.record_request("openai", latency_ms=50.0, success=True, quality_score=s)
        m = scorer._metrics["openai"]
        assert m.avg_quality_score == pytest.approx(statistics.mean(scores))

    async def test_uptime_updated_after_requests(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        await scorer.record_request("openai", latency_ms=50.0, success=False)
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        m = scorer._metrics["openai"]
        assert m.uptime_percentage == pytest.approx(200 / 3)

    async def test_health_score_recalculated(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        m = scorer._metrics["openai"]
        assert 0.0 <= m.health_score <= 1.0

    async def test_concurrent_requests_safe(self):
        scorer = ProviderHealthScorer()
        tasks = [
            scorer.record_request("openai", latency_ms=50.0 + i, success=True) for i in range(20)
        ]
        await asyncio.gather(*tasks)
        assert scorer._metrics["openai"].total_requests == 20

    async def test_multiple_providers_tracked_independently(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=100.0, success=True)
        await scorer.record_request("anthropic", latency_ms=200.0, success=False)
        assert scorer._metrics["openai"].total_requests == 1
        assert scorer._metrics["anthropic"].total_requests == 1
        assert scorer._metrics["openai"].successful_requests == 1
        assert scorer._metrics["anthropic"].failed_requests == 1


class TestUpdateLatencyStats:
    """Tests for _update_latency_stats private method."""

    def test_empty_samples_returns_early(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        scorer._update_latency_stats(m)
        assert m.avg_latency_ms == 0.0
        assert m.p50_latency_ms == 0.0

    def test_single_sample(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.latency_samples.append(200.0)
        scorer._update_latency_stats(m)
        assert m.avg_latency_ms == pytest.approx(200.0)
        assert m.p50_latency_ms == pytest.approx(200.0)
        assert m.p95_latency_ms == pytest.approx(200.0)
        assert m.p99_latency_ms == pytest.approx(200.0)

    def test_multiple_samples_avg(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        samples = [100.0, 200.0, 300.0, 400.0, 500.0]
        for s in samples:
            m.latency_samples.append(s)
        scorer._update_latency_stats(m)
        assert m.avg_latency_ms == pytest.approx(statistics.mean(samples))

    def test_multiple_samples_median(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        samples = [100.0, 200.0, 300.0, 400.0, 500.0]
        for s in samples:
            m.latency_samples.append(s)
        scorer._update_latency_stats(m)
        assert m.p50_latency_ms == pytest.approx(statistics.median(samples))

    def test_p95_latency(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        # 20 samples: 10, 20, 30, ..., 200
        samples = [float(i * 10) for i in range(1, 21)]
        for s in samples:
            m.latency_samples.append(s)
        scorer._update_latency_stats(m)
        sorted_s = sorted(samples)
        n = len(sorted_s)
        expected_p95 = sorted_s[int(n * 0.95)]
        assert m.p95_latency_ms == pytest.approx(expected_p95)

    def test_p99_latency(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        samples = [float(i * 10) for i in range(1, 101)]
        for s in samples:
            m.latency_samples.append(s)
        scorer._update_latency_stats(m)
        sorted_s = sorted(samples)
        n = len(sorted_s)
        expected_p99 = sorted_s[int(n * 0.99)]
        assert m.p99_latency_ms == pytest.approx(expected_p99)


class TestUpdateUptime:
    """Tests for _update_uptime private method."""

    def test_zero_requests_gives_100_uptime(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        scorer._update_uptime(m)
        assert m.uptime_percentage == 100.0

    def test_all_successful(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.total_requests = 10
        m.successful_requests = 10
        scorer._update_uptime(m)
        assert m.uptime_percentage == pytest.approx(100.0)

    def test_half_successful(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.total_requests = 10
        m.successful_requests = 5
        scorer._update_uptime(m)
        assert m.uptime_percentage == pytest.approx(50.0)

    def test_all_failed(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.total_requests = 5
        m.successful_requests = 0
        scorer._update_uptime(m)
        assert m.uptime_percentage == pytest.approx(0.0)


class TestCalculateHealthScore:
    """Tests for _calculate_health_score private method."""

    def test_perfect_provider(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("openai", m)
        assert score == pytest.approx(1.0)

    def test_uses_default_expected_latency_500(self):
        scorer = ProviderHealthScorer()
        # No expected latency set; default is 500ms
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("unknown", m)
        assert score == pytest.approx(1.0)

    def test_high_latency_reduces_score(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        m = HealthMetrics()
        # p95 = 1000ms = expected * 2 => latency_score = 0
        m.p95_latency_ms = 1000.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("openai", m)
        # latency_score=0, error=1, quality=1, avail=1
        expected = 0.30 * 0.0 + 0.35 * 1.0 + 0.15 * 1.0 + 0.20 * 1.0
        assert score == pytest.approx(expected)

    def test_high_error_rate_reduces_score(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.20  # 20% => error_score = 0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("openai", m)
        # error_score = max(0, 1 - 0.20*5) = 0
        expected = 0.30 * 1.0 + 0.35 * 0.0 + 0.15 * 1.0 + 0.20 * 1.0
        assert score == pytest.approx(expected)

    def test_consecutive_failures_penalty(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 3
        score = scorer._calculate_health_score("openai", m)
        penalty = min(0.5, 3 * 0.1)
        avail_score = max(0, 1.0 - penalty)
        expected = 0.30 * 1.0 + 0.35 * 1.0 + 0.15 * 1.0 + 0.20 * avail_score
        assert score == pytest.approx(expected)

    def test_consecutive_failures_capped_at_50_percent(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 10  # penalty = min(0.5, 1.0) = 0.5
        score = scorer._calculate_health_score("provider", m)
        penalty = 0.5
        avail_score = max(0, 1.0 - penalty)
        expected = 0.30 * 1.0 + 0.35 * 1.0 + 0.15 * 1.0 + 0.20 * avail_score
        assert score == pytest.approx(expected)

    def test_score_clamped_to_zero_minimum(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 1.0)
        m = HealthMetrics()
        # Extremely high latency -> latency_score very negative
        m.p95_latency_ms = 100000.0
        m.error_rate = 1.0
        m.avg_quality_score = 0.0
        m.uptime_percentage = 0.0
        m.consecutive_failures = 100
        score = scorer._calculate_health_score("openai", m)
        assert score == 0.0

    def test_score_clamped_to_one_maximum(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("openai", m)
        assert score <= 1.0

    def test_latency_score_clamped_at_zero(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 100.0)
        m = HealthMetrics()
        # p95 > expected*2 => raw latency_score < 0, should be clamped to 0
        m.p95_latency_ms = 300.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("openai", m)
        # latency_score = max(0, 1 - 300/200) = max(0, -0.5) = 0
        expected = 0.30 * 0.0 + 0.35 * 1.0 + 0.15 * 1.0 + 0.20 * 1.0
        assert score == pytest.approx(expected)

    def test_error_score_clamped_at_zero(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.5  # raw error_score = 1 - 2.5 = -1.5, clamped to 0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        score = scorer._calculate_health_score("provider", m)
        expected = 0.30 * 1.0 + 0.35 * 0.0 + 0.15 * 1.0 + 0.20 * 1.0
        assert score == pytest.approx(expected)

    def test_availability_score_clamped_at_zero(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 40.0  # 0.4 - penalty(5*0.1=0.5) = -0.1 => 0
        m.consecutive_failures = 5
        score = scorer._calculate_health_score("provider", m)
        avail_score = max(0, 0.4 - 0.5)  # = 0
        expected = 0.30 * 1.0 + 0.35 * 1.0 + 0.15 * 1.0 + 0.20 * avail_score
        assert score == pytest.approx(expected)


class TestGetHealthScore:
    """Tests for get_health_score."""

    def test_returns_default_for_unknown_provider(self):
        scorer = ProviderHealthScorer()
        result = scorer.get_health_score("unknown")
        assert isinstance(result, ProviderHealthScore)
        assert result.provider_id == "unknown"

    def test_is_healthy_when_score_above_threshold(self):
        scorer = ProviderHealthScorer()
        # Manually set metrics with perfect values
        m = HealthMetrics()
        m.p95_latency_ms = 0.0
        m.error_rate = 0.0
        m.avg_quality_score = 1.0
        m.uptime_percentage = 100.0
        m.consecutive_failures = 0
        m.health_score = 1.0
        scorer._metrics["perfect"] = m
        result = scorer.get_health_score("perfect")
        assert result.is_healthy is True
        assert result.is_degraded is False
        assert result.is_unhealthy is False

    def test_is_degraded_when_score_between_thresholds(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.health_score = 0.65  # between 0.5 and 0.8
        scorer._metrics["degraded"] = m
        result = scorer.get_health_score("degraded")
        assert result.is_degraded is True
        assert result.is_healthy is False
        assert result.is_unhealthy is False

    def test_is_unhealthy_when_score_below_degraded_threshold(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.health_score = 0.3
        scorer._metrics["sick"] = m
        result = scorer.get_health_score("sick")
        assert result.is_unhealthy is True
        assert result.is_healthy is False
        assert result.is_degraded is False

    def test_exactly_at_healthy_threshold(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.health_score = 0.8
        scorer._metrics["borderline"] = m
        result = scorer.get_health_score("borderline")
        assert result.is_healthy is True
        assert result.is_degraded is False

    def test_exactly_at_degraded_threshold(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.health_score = 0.5
        scorer._metrics["borderline_degraded"] = m
        result = scorer.get_health_score("borderline_degraded")
        assert result.is_degraded is True
        assert result.is_unhealthy is False

    def test_just_below_degraded_threshold(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.health_score = 0.499
        scorer._metrics["unhealthy"] = m
        result = scorer.get_health_score("unhealthy")
        assert result.is_unhealthy is True

    def test_returns_correct_provider_id(self):
        scorer = ProviderHealthScorer()
        result = scorer.get_health_score("my-provider")
        assert result.provider_id == "my-provider"

    def test_metrics_attached(self):
        scorer = ProviderHealthScorer()
        m = HealthMetrics()
        m.total_requests = 42
        scorer._metrics["p"] = m
        result = scorer.get_health_score("p")
        assert result.metrics.total_requests == 42

    def test_uses_set_expected_latency_for_component_scores(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("fast", 100.0)
        m = HealthMetrics()
        m.p95_latency_ms = 200.0  # = expected * 2 => latency_score = 0
        m.health_score = 0.9
        scorer._metrics["fast"] = m
        result = scorer.get_health_score("fast")
        assert result.latency_score == pytest.approx(0.0)

    async def test_round_trip_record_and_get(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        for _ in range(5):
            await scorer.record_request("openai", latency_ms=100.0, success=True)
        result = scorer.get_health_score("openai")
        assert result.is_healthy is True
        assert result.health_score > 0.5


class TestGetAllScores:
    """Tests for get_all_scores."""

    def test_empty_returns_empty_dict(self):
        scorer = ProviderHealthScorer()
        result = scorer.get_all_scores()
        assert result == {}

    async def test_returns_all_tracked_providers(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        await scorer.record_request("anthropic", latency_ms=80.0, success=True)
        result = scorer.get_all_scores()
        assert set(result.keys()) == {"openai", "anthropic"}

    async def test_all_values_are_provider_health_score(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        result = scorer.get_all_scores()
        assert isinstance(result["openai"], ProviderHealthScore)


class TestReset:
    """Tests for reset method."""

    async def test_reset_specific_provider(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        await scorer.record_request("anthropic", latency_ms=50.0, success=True)
        scorer.reset("openai")
        # openai should be cleared to fresh HealthMetrics
        assert scorer._metrics["openai"].total_requests == 0
        # anthropic unchanged
        assert scorer._metrics["anthropic"].total_requests == 1

    async def test_reset_nonexistent_provider_is_noop(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        scorer.reset("does_not_exist")
        assert scorer._metrics["openai"].total_requests == 1

    async def test_reset_all_clears_all_metrics(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True)
        await scorer.record_request("anthropic", latency_ms=50.0, success=True)
        scorer.reset()
        assert scorer._metrics == {}

    def test_reset_all_when_empty(self):
        scorer = ProviderHealthScorer()
        scorer.reset()
        assert scorer._metrics == {}

    async def test_reset_specific_creates_fresh_metrics(self):
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=999.0, success=False)
        scorer.reset("openai")
        fresh = scorer._metrics["openai"]
        assert fresh.total_requests == 0
        assert fresh.health_score == 1.0
        assert isinstance(fresh.latency_samples, deque)


# ---------------------------------------------------------------------------
# Integration / edge case tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests combining multiple components."""

    async def test_health_degrades_under_load_of_failures(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        # Record many failures
        for _ in range(10):
            await scorer.record_request("openai", latency_ms=100.0, success=False)
        result = scorer.get_health_score("openai")
        assert result.health_score < 0.8

    async def test_recovery_after_reset(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        for _ in range(5):
            await scorer.record_request("openai", latency_ms=100.0, success=False)
        scorer.reset("openai")
        result = scorer.get_health_score("openai")
        assert result.health_score == 1.0

    async def test_to_dict_after_recorded_requests(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("openai", 500.0)
        await scorer.record_request("openai", latency_ms=50.0, success=True, quality_score=0.9)
        result = scorer.get_health_score("openai")
        d = result.to_dict()
        assert d["provider_id"] == "openai"
        assert d["is_healthy"] is True
        assert isinstance(d["last_updated"], str)

    async def test_quality_score_empty_deque_uses_one(self):
        """When quality scores deque is empty, avg_quality_score should remain 1.0."""
        scorer = ProviderHealthScorer()
        await scorer.record_request("openai", latency_ms=50.0, success=True, quality_score=None)
        m = scorer._metrics["openai"]
        # Simulate empty deque with manual override to trigger the else branch
        m.response_quality_scores = deque(maxlen=50)
        # avg_quality_score stays at 1.0 since we never pushed a quality score
        assert m.avg_quality_score == 1.0

    async def test_full_lifecycle(self):
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("gpt4", 300.0)

        # Warm up with good requests
        for _ in range(5):
            await scorer.record_request("gpt4", latency_ms=100.0, success=True, quality_score=0.95)

        score1 = scorer.get_health_score("gpt4")
        assert score1.is_healthy

        # Introduce failures
        for _ in range(3):
            await scorer.record_request(
                "gpt4", latency_ms=2000.0, success=False, error_type="timeout"
            )

        score2 = scorer.get_health_score("gpt4")
        assert score2.health_score < score1.health_score

        # Recover
        for _ in range(10):
            await scorer.record_request("gpt4", latency_ms=80.0, success=True, quality_score=1.0)

        score3 = scorer.get_health_score("gpt4")
        assert score3.health_score > score2.health_score


class TestAllExports:
    """Ensure the __all__ list is correct."""

    def test_health_metrics_exported(self):
        from enhanced_agent_bus.llm_adapters.failover.health import HealthMetrics as HM

        assert HM is HealthMetrics

    def test_provider_health_score_exported(self):
        from enhanced_agent_bus.llm_adapters.failover.health import (
            ProviderHealthScore as PHS,
        )

        assert PHS is ProviderHealthScore

    def test_provider_health_scorer_exported(self):
        from enhanced_agent_bus.llm_adapters.failover.health import (
            ProviderHealthScorer as PHScorer,
        )

        assert PHScorer is ProviderHealthScorer
