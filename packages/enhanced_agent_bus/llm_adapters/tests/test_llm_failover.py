"""
Tests for LLM Provider Failover System
Constitutional Hash: 608508a9bd224290

Comprehensive tests for:
- LLM-specific circuit breaker configurations
- Provider health scoring
- Proactive failover
- Provider warmup
- Request hedging
- Failover orchestrator
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.circuit_breaker import (
    CONSTITUTIONAL_HASH,
    CircuitState,
    FallbackStrategy,
    ServiceSeverity,
)
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityDimension,
    CapabilityLevel,
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    ProviderCapabilityProfile,
)
from enhanced_agent_bus.llm_adapters.llm_failover import (
    LLM_CIRCUIT_CONFIGS,
    FailoverEvent,
    HealthMetrics,
    HedgedRequest,
    LLMFailoverOrchestrator,
    LLMProviderType,
    ProactiveFailoverManager,
    ProviderHealthScore,
    ProviderHealthScorer,
    ProviderWarmupManager,
    RequestHedgingManager,
    WarmupResult,
    get_llm_circuit_config,
    get_llm_failover_orchestrator,
    reset_llm_failover_orchestrator,
)

# =============================================================================
# LLM Circuit Config Tests
# =============================================================================


class TestLLMCircuitConfigs:
    """Tests for LLM-specific circuit breaker configurations."""

    def test_config_exists_for_major_providers(self) -> None:
        """Test configurations exist for major providers."""
        expected_providers = ["openai", "anthropic", "google", "azure", "bedrock", "local"]
        for provider in expected_providers:
            key = f"llm:{provider}"
            assert key in LLM_CIRCUIT_CONFIGS, f"Missing config for {provider}"

    def test_openai_config(self) -> None:
        """Test OpenAI circuit breaker configuration."""
        config = LLM_CIRCUIT_CONFIGS["llm:openai"]

        assert config.name == "llm:openai"
        assert config.failure_threshold == 5
        assert config.timeout_seconds == 30.0
        assert config.fallback_strategy == FallbackStrategy.CACHED_VALUE
        assert config.severity == ServiceSeverity.HIGH
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_anthropic_config(self) -> None:
        """Test Anthropic circuit breaker configuration."""
        config = LLM_CIRCUIT_CONFIGS["llm:anthropic"]

        assert config.name == "llm:anthropic"
        assert config.failure_threshold == 5
        assert config.timeout_seconds == 45.0  # Longer for complex reasoning
        assert config.severity == ServiceSeverity.HIGH

    def test_google_config_higher_tolerance(self) -> None:
        """Test Google config has higher failure tolerance."""
        config = LLM_CIRCUIT_CONFIGS["llm:google"]

        # Google has variable latency, so higher tolerance
        assert config.failure_threshold == 7
        assert config.timeout_seconds == 60.0
        assert config.severity == ServiceSeverity.MEDIUM

    def test_local_config_fast_recovery(self) -> None:
        """Test local model config has fast recovery."""
        config = LLM_CIRCUIT_CONFIGS["llm:local"]

        assert config.failure_threshold == 3
        assert config.timeout_seconds == 10.0
        assert config.fallback_strategy == FallbackStrategy.BYPASS

    def test_get_llm_circuit_config_known(self) -> None:
        """Test getting config for known provider."""
        config = get_llm_circuit_config("openai")

        assert config.name == "llm:openai"
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_llm_circuit_config_unknown(self) -> None:
        """Test getting config for unknown provider returns default."""
        config = get_llm_circuit_config("unknown-provider")

        assert config.name == "llm:unknown-provider"
        assert config.failure_threshold == 5
        assert config.timeout_seconds == 30.0
        assert config.constitutional_hash == CONSTITUTIONAL_HASH


class TestLLMProviderType:
    """Tests for LLMProviderType enum."""

    def test_provider_type_values(self) -> None:
        """Test provider type enum values."""
        assert LLMProviderType.OPENAI.value == "openai"
        assert LLMProviderType.ANTHROPIC.value == "anthropic"
        assert LLMProviderType.GOOGLE.value == "google"
        assert LLMProviderType.AZURE.value == "azure"
        assert LLMProviderType.BEDROCK.value == "bedrock"
        assert LLMProviderType.LOCAL.value == "local"


# =============================================================================
# Health Metrics Tests
# =============================================================================


class TestHealthMetrics:
    """Tests for HealthMetrics dataclass."""

    def test_default_values(self) -> None:
        """Test health metrics default values."""
        metrics = HealthMetrics()

        assert metrics.avg_latency_ms == 0.0
        assert metrics.total_requests == 0
        assert metrics.error_rate == 0.0
        assert metrics.health_score == 1.0
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_latency_samples_deque(self) -> None:
        """Test latency samples deque with maxlen."""
        metrics = HealthMetrics()

        # Add more than maxlen samples
        for i in range(150):
            metrics.latency_samples.append(i)

        # Should be capped at maxlen (100)
        assert len(metrics.latency_samples) == 100


class TestProviderHealthScore:
    """Tests for ProviderHealthScore dataclass."""

    def test_health_score_creation(self) -> None:
        """Test creating a health score."""
        score = ProviderHealthScore(
            provider_id="test-provider",
            health_score=0.85,
            latency_score=0.9,
            error_score=0.95,
            quality_score=0.8,
            availability_score=0.9,
            is_healthy=True,
            is_degraded=False,
            is_unhealthy=False,
            metrics=HealthMetrics(),
        )

        assert score.provider_id == "test-provider"
        assert score.health_score == 0.85
        assert score.is_healthy is True
        assert score.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self) -> None:
        """Test health score serialization."""
        score = ProviderHealthScore(
            provider_id="test-provider",
            health_score=0.85,
            latency_score=0.9,
            error_score=0.95,
            quality_score=0.8,
            availability_score=0.9,
            is_healthy=True,
            is_degraded=False,
            is_unhealthy=False,
            metrics=HealthMetrics(),
        )

        d = score.to_dict()

        assert d["provider_id"] == "test-provider"
        assert d["health_score"] == 0.85
        assert d["is_healthy"] is True
        assert "metrics" in d
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Provider Health Scorer Tests
# =============================================================================


class TestProviderHealthScorer:
    """Tests for ProviderHealthScorer."""

    def test_scorer_creation(self) -> None:
        """Test creating a health scorer."""
        scorer = ProviderHealthScorer()

        assert scorer.LATENCY_WEIGHT == 0.30
        assert scorer.ERROR_WEIGHT == 0.35
        assert scorer.HEALTHY_THRESHOLD == 0.8

    def test_set_expected_latency(self) -> None:
        """Test setting expected latency."""
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("test-provider", 200.0)

        assert scorer._expected_latency["test-provider"] == 200.0

    async def test_record_successful_request(self) -> None:
        """Test recording a successful request."""
        scorer = ProviderHealthScorer()
        scorer.set_expected_latency("test-provider", 500.0)

        await scorer.record_request(
            provider_id="test-provider",
            latency_ms=100.0,
            success=True,
        )

        health = scorer.get_health_score("test-provider")

        assert health.metrics.total_requests == 1
        assert health.metrics.successful_requests == 1
        assert health.metrics.error_rate == 0.0
        assert health.health_score > 0.8  # Should be healthy

    async def test_record_failed_request(self) -> None:
        """Test recording a failed request."""
        scorer = ProviderHealthScorer()

        await scorer.record_request(
            provider_id="test-provider",
            latency_ms=500.0,
            success=False,
            error_type="timeout",
        )

        health = scorer.get_health_score("test-provider")

        assert health.metrics.failed_requests == 1
        assert health.metrics.timeout_count == 1
        assert health.metrics.error_rate == 1.0

    async def test_error_rate_calculation(self) -> None:
        """Test error rate is calculated correctly."""
        scorer = ProviderHealthScorer()

        # 3 successes, 1 failure = 25% error rate
        for _ in range(3):
            await scorer.record_request("test-provider", 100.0, success=True)
        await scorer.record_request("test-provider", 100.0, success=False)

        health = scorer.get_health_score("test-provider")

        assert health.metrics.total_requests == 4
        assert health.metrics.error_rate == 0.25

    async def test_latency_percentiles(self) -> None:
        """Test latency percentile calculations."""
        scorer = ProviderHealthScorer()

        # Record varied latencies
        latencies = [100, 150, 200, 250, 300, 350, 400, 450, 500, 1000]
        for lat in latencies:
            await scorer.record_request("test-provider", lat, success=True)

        health = scorer.get_health_score("test-provider")

        assert health.metrics.avg_latency_ms > 0
        assert health.metrics.p50_latency_ms > 0
        assert health.metrics.p95_latency_ms > 0

    async def test_quality_score_tracking(self) -> None:
        """Test quality score tracking."""
        scorer = ProviderHealthScorer()

        await scorer.record_request("test-provider", 100.0, success=True, quality_score=0.9)
        await scorer.record_request("test-provider", 100.0, success=True, quality_score=0.8)

        health = scorer.get_health_score("test-provider")

        assert health.metrics.avg_quality_score == pytest.approx(0.85)

    async def test_consecutive_failures_penalty(self) -> None:
        """Test consecutive failures reduce health score."""
        scorer = ProviderHealthScorer()

        # First establish some baseline
        for _ in range(5):
            await scorer.record_request("test-provider", 100.0, success=True)

        health_before = scorer.get_health_score("test-provider").health_score

        # Now record consecutive failures
        for _ in range(3):
            await scorer.record_request("test-provider", 500.0, success=False)

        health_after = scorer.get_health_score("test-provider").health_score

        assert health_after < health_before

    def test_get_all_scores(self) -> None:
        """Test getting all provider scores."""
        scorer = ProviderHealthScorer()

        # Initialize some providers
        scorer._metrics["provider-1"] = HealthMetrics()
        scorer._metrics["provider-2"] = HealthMetrics()

        scores = scorer.get_all_scores()

        assert "provider-1" in scores
        assert "provider-2" in scores

    def test_reset_single_provider(self) -> None:
        """Test resetting a single provider's metrics."""
        scorer = ProviderHealthScorer()
        scorer._metrics["provider-1"] = HealthMetrics(total_requests=100)
        scorer._metrics["provider-2"] = HealthMetrics(total_requests=50)

        scorer.reset("provider-1")

        assert scorer._metrics["provider-1"].total_requests == 0
        assert scorer._metrics["provider-2"].total_requests == 50

    def test_reset_all(self) -> None:
        """Test resetting all metrics."""
        scorer = ProviderHealthScorer()
        scorer._metrics["provider-1"] = HealthMetrics(total_requests=100)
        scorer._metrics["provider-2"] = HealthMetrics(total_requests=50)

        scorer.reset()

        assert len(scorer._metrics) == 0


# =============================================================================
# Proactive Failover Tests
# =============================================================================


class TestFailoverEvent:
    """Tests for FailoverEvent dataclass."""

    def test_failover_event_creation(self) -> None:
        """Test creating a failover event."""
        event = FailoverEvent(
            event_id="fo-123",
            from_provider="provider-a",
            to_provider="provider-b",
            reason="health_degraded",
            latency_ms=50.0,
        )

        assert event.event_id == "fo-123"
        assert event.from_provider == "provider-a"
        assert event.to_provider == "provider-b"
        assert event.reason == "health_degraded"
        assert event.success is True
        assert event.constitutional_hash == CONSTITUTIONAL_HASH


class TestProactiveFailoverManager:
    """Tests for ProactiveFailoverManager."""

    @pytest.fixture
    def failover_manager(self) -> ProactiveFailoverManager:
        """Create a failover manager for testing."""
        scorer = ProviderHealthScorer()
        registry = CapabilityRegistry()
        return ProactiveFailoverManager(scorer, registry)

    def test_manager_creation(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test creating a failover manager."""
        assert failover_manager.PROACTIVE_FAILOVER_THRESHOLD == 0.6
        assert failover_manager.RECOVERY_THRESHOLD == 0.85

    def test_set_primary_provider(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test setting primary provider for tenant."""
        failover_manager.set_primary_provider("tenant-1", "provider-a")

        assert failover_manager._primary_providers["tenant-1"] == "provider-a"

    def test_set_fallback_chain(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test setting fallback chain."""
        failover_manager.set_fallback_chain(
            "provider-a",
            ["provider-b", "provider-c"],
        )

        assert failover_manager._fallback_chains["provider-a"] == [
            "provider-b",
            "provider-c",
        ]

    async def test_check_failover_healthy_provider(
        self, failover_manager: ProactiveFailoverManager
    ) -> None:
        """Test no failover when provider is healthy."""
        failover_manager.set_primary_provider("tenant-1", "provider-a")

        # Record successful requests to make provider healthy
        for _ in range(5):
            await failover_manager.health_scorer.record_request("provider-a", 100.0, success=True)

        provider, failover_occurred = await failover_manager.check_and_failover(
            "tenant-1",
            requirements=[],
        )

        assert provider == "provider-a"
        assert failover_occurred is False

    async def test_check_failover_degraded_provider(
        self, failover_manager: ProactiveFailoverManager
    ) -> None:
        """Test failover when provider is degraded."""
        failover_manager.set_primary_provider("tenant-1", "provider-a")
        failover_manager.set_fallback_chain("provider-a", ["provider-b"])

        # Make provider-a degraded
        for _ in range(10):
            await failover_manager.health_scorer.record_request("provider-a", 100.0, success=False)

        # Make provider-b healthy
        for _ in range(5):
            await failover_manager.health_scorer.record_request("provider-b", 100.0, success=True)

        provider, failover_occurred = await failover_manager.check_and_failover(
            "tenant-1",
            requirements=[],
        )

        assert provider == "provider-b"
        assert failover_occurred is True

    def test_get_active_provider(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test getting active provider."""
        failover_manager.set_primary_provider("tenant-1", "provider-a")
        failover_manager._active_failovers["tenant-1"] = "provider-b"

        active = failover_manager.get_active_provider("tenant-1")

        assert active == "provider-b"

    def test_get_failover_history(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test getting failover history."""
        # Add some events
        failover_manager._failover_history.append(
            FailoverEvent(
                event_id="fo-1",
                from_provider="a",
                to_provider="b",
                reason="test",
            )
        )

        history = failover_manager.get_failover_history()

        assert len(history) == 1
        assert history[0].event_id == "fo-1"

    def test_get_failover_stats(self, failover_manager: ProactiveFailoverManager) -> None:
        """Test getting failover statistics."""
        # Add some events
        failover_manager._failover_history.append(
            FailoverEvent(
                event_id="fo-1",
                from_provider="a",
                to_provider="b",
                reason="proactive",
                latency_ms=50.0,
            )
        )
        failover_manager._failover_history.append(
            FailoverEvent(
                event_id="fo-2",
                from_provider="b",
                to_provider="c",
                reason="health_degraded",
                latency_ms=100.0,
            )
        )

        stats = failover_manager.get_failover_stats()

        assert stats["total_failovers"] == 2
        assert stats["successful_failovers"] == 2
        assert stats["failover_success_rate"] == 1.0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Warmup Manager Tests
# =============================================================================


class TestWarmupResult:
    """Tests for WarmupResult dataclass."""

    def test_warmup_result_creation(self) -> None:
        """Test creating a warmup result."""
        result = WarmupResult(
            provider_id="test-provider",
            success=True,
            latency_ms=100.0,
        )

        assert result.provider_id == "test-provider"
        assert result.success is True
        assert result.latency_ms == 100.0
        assert result.error is None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestProviderWarmupManager:
    """Tests for ProviderWarmupManager."""

    @pytest.fixture
    def warmup_manager(self) -> ProviderWarmupManager:
        """Create a warmup manager for testing."""
        return ProviderWarmupManager()

    def test_manager_creation(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test creating a warmup manager."""
        assert warmup_manager.DEFAULT_WARMUP_INTERVAL == timedelta(minutes=5)
        assert warmup_manager.WARMUP_TIMEOUT_MS == 10000

    def test_register_warmup_handler(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test registering a warmup handler."""
        handler = AsyncMock()
        warmup_manager.register_warmup_handler("test-provider", handler)

        assert "test-provider" in warmup_manager._warmup_handlers

    async def test_warmup_success(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test successful warmup."""
        handler = AsyncMock(return_value=None)
        warmup_manager.register_warmup_handler("test-provider", handler)

        result = await warmup_manager.warmup("test-provider")

        assert result.success is True
        assert result.latency_ms > 0
        assert result.error is None
        handler.assert_called_once()

    async def test_warmup_failure(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test warmup failure."""
        handler = AsyncMock(side_effect=RuntimeError("Connection failed"))
        warmup_manager.register_warmup_handler("test-provider", handler)

        result = await warmup_manager.warmup("test-provider")

        assert result.success is False
        assert "Connection failed" in result.error

    async def test_warmup_no_handler(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test warmup with no handler registered."""
        result = await warmup_manager.warmup("unknown-provider")

        assert result.success is False
        assert "No warmup handler" in result.error

    async def test_warmup_if_needed(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test conditional warmup based on interval."""
        handler = AsyncMock()
        warmup_manager.register_warmup_handler("test-provider", handler)

        # First warmup should execute
        result1 = await warmup_manager.warmup_if_needed("test-provider")
        assert result1 is not None

        # Second warmup should not execute (too soon)
        result2 = await warmup_manager.warmup_if_needed("test-provider")
        assert result2 is None

    async def test_warmup_before_failover(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test warmup before failover."""
        handler = AsyncMock()
        warmup_manager.register_warmup_handler("target-provider", handler)

        result = await warmup_manager.warmup_before_failover("target-provider")

        assert result is not None
        handler.assert_called_once()

    def test_get_warmup_status(self, warmup_manager: ProviderWarmupManager) -> None:
        """Test getting warmup status."""
        warmup_manager.register_warmup_handler("test-provider", AsyncMock())

        status = warmup_manager.get_warmup_status("test-provider")

        assert status["provider_id"] == "test-provider"
        assert status["has_handler"] is True
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Request Hedging Tests
# =============================================================================


class TestHedgedRequest:
    """Tests for HedgedRequest dataclass."""

    def test_hedged_request_creation(self) -> None:
        """Test creating a hedged request."""
        request = HedgedRequest(
            request_id="req-123",
            providers=["provider-a", "provider-b"],
        )

        assert request.request_id == "req-123"
        assert len(request.providers) == 2
        assert request.winning_provider is None
        assert request.constitutional_hash == CONSTITUTIONAL_HASH


class TestRequestHedgingManager:
    """Tests for RequestHedgingManager."""

    @pytest.fixture
    def hedging_manager(self) -> RequestHedgingManager:
        """Create a hedging manager for testing."""
        return RequestHedgingManager(default_hedge_count=2, hedge_delay_ms=50)

    def test_manager_creation(self, hedging_manager: RequestHedgingManager) -> None:
        """Test creating a hedging manager."""
        assert hedging_manager._default_hedge_count == 2
        assert hedging_manager._hedge_delay_ms == 50

    async def test_execute_hedged_first_wins(self, hedging_manager: RequestHedgingManager) -> None:
        """Test hedged execution where first provider wins."""

        async def execute_fn(provider_id: str) -> str:
            if provider_id == "fast-provider":
                return "fast result"
            await asyncio.sleep(0.2)
            return "slow result"

        winner, result = await hedging_manager.execute_hedged(
            request_id="req-1",
            providers=["fast-provider", "slow-provider"],
            execute_fn=execute_fn,
            hedge_count=2,
        )

        assert winner == "fast-provider"
        assert result == "fast result"

    async def test_execute_hedged_second_wins_on_failure(
        self, hedging_manager: RequestHedgingManager
    ) -> None:
        """Test hedged execution where second provider wins after first fails."""

        async def execute_fn(provider_id: str) -> str:
            if provider_id == "failing-provider":
                raise RuntimeError("Provider failed")
            return "success result"

        winner, result = await hedging_manager.execute_hedged(
            request_id="req-2",
            providers=["failing-provider", "working-provider"],
            execute_fn=execute_fn,
            hedge_count=2,
        )

        assert winner == "working-provider"
        assert result == "success result"

    async def test_execute_hedged_all_fail(self, hedging_manager: RequestHedgingManager) -> None:
        """Test hedged execution when all providers fail."""

        async def execute_fn(provider_id: str) -> str:
            raise RuntimeError(f"{provider_id} failed")

        with pytest.raises(RuntimeError, match="All hedged providers failed"):
            await hedging_manager.execute_hedged(
                request_id="req-3",
                providers=["provider-a", "provider-b"],
                execute_fn=execute_fn,
                hedge_count=2,
            )

    async def test_execute_hedged_no_providers(
        self, hedging_manager: RequestHedgingManager
    ) -> None:
        """Test hedged execution with no providers."""
        with pytest.raises(ValueError, match="No providers available"):
            await hedging_manager.execute_hedged(
                request_id="req-4",
                providers=[],
                execute_fn=AsyncMock(),
                hedge_count=2,
            )

    def test_get_hedging_stats_empty(self, hedging_manager: RequestHedgingManager) -> None:
        """Test hedging stats with no requests."""
        stats = hedging_manager.get_hedging_stats()

        assert stats["total_hedged_requests"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_hedging_stats_with_data(
        self, hedging_manager: RequestHedgingManager
    ) -> None:
        """Test hedging stats after some requests."""

        async def execute_fn(provider_id: str) -> str:
            return f"result from {provider_id}"

        # Execute a few hedged requests
        await hedging_manager.execute_hedged("req-1", ["provider-a", "provider-b"], execute_fn)
        await hedging_manager.execute_hedged("req-2", ["provider-a", "provider-b"], execute_fn)

        stats = hedging_manager.get_hedging_stats()

        assert stats["total_hedged_requests"] == 2
        assert stats["successful_requests"] == 2
        assert stats["success_rate"] == 1.0


# =============================================================================
# LLM Failover Orchestrator Tests
# =============================================================================


class TestLLMFailoverOrchestrator:
    """Tests for LLMFailoverOrchestrator."""

    @pytest.fixture
    def orchestrator(self) -> LLMFailoverOrchestrator:
        """Create an orchestrator for testing."""
        reset_llm_failover_orchestrator()
        return LLMFailoverOrchestrator()

    def test_orchestrator_creation(self, orchestrator: LLMFailoverOrchestrator) -> None:
        """Test creating an orchestrator."""
        assert orchestrator.health_scorer is not None
        assert orchestrator.failover_manager is not None
        assert orchestrator.warmup_manager is not None
        assert orchestrator.hedging_manager is not None

    async def test_get_llm_circuit_breaker(self, orchestrator: LLMFailoverOrchestrator) -> None:
        """Test getting LLM-specific circuit breaker."""
        cb = await orchestrator.get_llm_circuit_breaker("openai-gpt-4")

        assert cb is not None
        # Config name is from the template (base provider type)
        # The circuit breaker key in registry would be "llm:openai-gpt-4"
        assert cb.config.name == "llm:openai"

    async def test_record_request_result_success(
        self, orchestrator: LLMFailoverOrchestrator
    ) -> None:
        """Test recording a successful request."""
        await orchestrator.record_request_result(
            provider_id="test-provider",
            latency_ms=100.0,
            success=True,
        )

        health = orchestrator.health_scorer.get_health_score("test-provider")
        assert health.metrics.successful_requests == 1

    async def test_record_request_result_failure(
        self, orchestrator: LLMFailoverOrchestrator
    ) -> None:
        """Test recording a failed request."""
        await orchestrator.record_request_result(
            provider_id="test-provider",
            latency_ms=500.0,
            success=False,
            error_type="timeout",
        )

        health = orchestrator.health_scorer.get_health_score("test-provider")
        assert health.metrics.failed_requests == 1

    async def test_execute_with_failover_success(
        self, orchestrator: LLMFailoverOrchestrator
    ) -> None:
        """Test executing with failover on success."""
        orchestrator.failover_manager.set_primary_provider("tenant-1", "provider-a")

        async def execute_fn(provider_id: str) -> str:
            return f"result from {provider_id}"

        provider, result = await orchestrator.execute_with_failover(
            tenant_id="tenant-1",
            requirements=[],
            execute_fn=execute_fn,
        )

        assert provider == "provider-a"
        assert result == "result from provider-a"

    async def test_execute_with_failover_on_error(
        self, orchestrator: LLMFailoverOrchestrator
    ) -> None:
        """Test executing with failover when primary fails."""
        orchestrator.failover_manager.set_primary_provider("tenant-1", "provider-a")
        orchestrator.failover_manager.set_fallback_chain("provider-a", ["provider-b"])

        call_count = {"a": 0, "b": 0}

        async def execute_fn(provider_id: str) -> str:
            if provider_id == "provider-a":
                call_count["a"] += 1
                raise RuntimeError("Provider A failed")
            call_count["b"] += 1
            return f"result from {provider_id}"

        provider, result = await orchestrator.execute_with_failover(
            tenant_id="tenant-1",
            requirements=[],
            execute_fn=execute_fn,
        )

        assert provider == "provider-b"
        assert result == "result from provider-b"
        assert call_count["a"] == 1
        assert call_count["b"] == 1

    async def test_execute_with_hedging(self) -> None:
        """Test executing with hedging for critical requests."""
        # Create registry and clear default profiles for isolated testing
        fresh_registry = CapabilityRegistry()
        fresh_registry._profiles.clear()  # Clear auto-registered defaults

        # Register test providers only
        profile_a = ProviderCapabilityProfile(
            provider_id="provider-a",
            model_id="model-a",
            display_name="Provider A",
            provider_type="test",
            context_length=10000,
            max_output_tokens=1000,
        )
        profile_b = ProviderCapabilityProfile(
            provider_id="provider-b",
            model_id="model-b",
            display_name="Provider B",
            provider_type="test",
            context_length=10000,
            max_output_tokens=1000,
        )
        fresh_registry.register_profile(profile_a)
        fresh_registry.register_profile(profile_b)

        # Create orchestrator with fresh registry
        fresh_orchestrator = LLMFailoverOrchestrator(capability_registry=fresh_registry)

        async def execute_fn(provider_id: str) -> str:
            return f"result from {provider_id}"

        provider, result = await fresh_orchestrator.execute_with_failover(
            tenant_id="tenant-1",
            requirements=[],
            execute_fn=execute_fn,
            critical=True,
            hedge_count=2,
        )

        assert provider in ["provider-a", "provider-b"]
        assert "result from" in result

    def test_get_orchestrator_status(self, orchestrator: LLMFailoverOrchestrator) -> None:
        """Test getting orchestrator status."""
        status = orchestrator.get_orchestrator_status()

        assert "health_scores" in status
        assert "failover_stats" in status
        assert "hedging_stats" in status
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstances:
    """Tests for global instance accessors."""

    def test_get_llm_failover_orchestrator(self) -> None:
        """Test getting global orchestrator."""
        reset_llm_failover_orchestrator()
        orchestrator = get_llm_failover_orchestrator()

        assert orchestrator is not None
        assert isinstance(orchestrator, LLMFailoverOrchestrator)

    def test_get_llm_failover_orchestrator_singleton(self) -> None:
        """Test orchestrator is singleton."""
        reset_llm_failover_orchestrator()
        o1 = get_llm_failover_orchestrator()
        o2 = get_llm_failover_orchestrator()

        assert o1 is o2

    def test_reset_llm_failover_orchestrator(self) -> None:
        """Test resetting the global orchestrator."""
        o1 = get_llm_failover_orchestrator()
        reset_llm_failover_orchestrator()
        o2 = get_llm_failover_orchestrator()

        assert o1 is not o2


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional compliance in LLM failover system."""

    def test_circuit_config_has_hash(self) -> None:
        """Test circuit config includes constitutional hash."""
        config = get_llm_circuit_config("openai")
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_health_metrics_has_hash(self) -> None:
        """Test health metrics includes constitutional hash."""
        metrics = HealthMetrics()
        assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    def test_health_score_has_hash(self) -> None:
        """Test health score includes constitutional hash."""
        score = ProviderHealthScore(
            provider_id="test",
            health_score=1.0,
            latency_score=1.0,
            error_score=1.0,
            quality_score=1.0,
            availability_score=1.0,
            is_healthy=True,
            is_degraded=False,
            is_unhealthy=False,
            metrics=HealthMetrics(),
        )
        assert score.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failover_event_has_hash(self) -> None:
        """Test failover event includes constitutional hash."""
        event = FailoverEvent(
            event_id="test",
            from_provider="a",
            to_provider="b",
            reason="test",
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_warmup_result_has_hash(self) -> None:
        """Test warmup result includes constitutional hash."""
        result = WarmupResult(
            provider_id="test",
            success=True,
            latency_ms=100.0,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_hedged_request_has_hash(self) -> None:
        """Test hedged request includes constitutional hash."""
        request = HedgedRequest(
            request_id="test",
            providers=["a", "b"],
        )
        assert request.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failover_stats_has_hash(self) -> None:
        """Test failover stats includes constitutional hash."""
        manager = ProactiveFailoverManager(
            ProviderHealthScorer(),
            CapabilityRegistry(),
        )
        stats = manager.get_failover_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_orchestrator_status_has_hash(self) -> None:
        """Test orchestrator status includes constitutional hash."""
        reset_llm_failover_orchestrator()
        orchestrator = LLMFailoverOrchestrator()
        status = orchestrator.get_orchestrator_status()
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH
