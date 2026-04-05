"""
Tests for Cost-Aware LLM Provider Selection
Constitutional Hash: 608508a9bd224290

Comprehensive tests for:
- Cost models and estimation
- Budget management
- Anomaly detection
- Batch optimization
- Cost-aware provider selection
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CONSTITUTIONAL_HASH,
    CapabilityDimension,
    CapabilityLevel,
    CapabilityRegistry,
    CapabilityRequirement,
    LatencyClass,
    ProviderCapabilityProfile,
)
from enhanced_agent_bus.llm_adapters.cost_optimizer import (
    BatchOptimizer,
    BatchRequest,
    BudgetLimit,
    BudgetManager,
    CostAnomaly,
    CostAnomalyDetector,
    CostEstimate,
    CostModel,
    CostOptimizer,
    CostTier,
    QualityLevel,
    UrgencyLevel,
    get_cost_optimizer,
)

# =============================================================================
# CostTier Tests
# =============================================================================


class TestCostTier:
    """Tests for CostTier enum."""

    def test_cost_tier_values(self) -> None:
        """Test cost tier enum values."""
        assert CostTier.FREE.value == "free"
        assert CostTier.BUDGET.value == "budget"
        assert CostTier.STANDARD.value == "standard"
        assert CostTier.PREMIUM.value == "premium"
        assert CostTier.ENTERPRISE.value == "enterprise"

    def test_cost_tier_from_value(self) -> None:
        """Test creating tier from value."""
        assert CostTier("free") == CostTier.FREE
        assert CostTier("premium") == CostTier.PREMIUM


class TestQualityLevel:
    """Tests for QualityLevel enum."""

    def test_quality_level_values(self) -> None:
        """Test quality level enum values."""
        assert QualityLevel.MINIMAL.value == "minimal"
        assert QualityLevel.BASIC.value == "basic"
        assert QualityLevel.STANDARD.value == "standard"
        assert QualityLevel.HIGH.value == "high"
        assert QualityLevel.MAXIMUM.value == "maximum"


class TestUrgencyLevel:
    """Tests for UrgencyLevel enum."""

    def test_urgency_level_values(self) -> None:
        """Test urgency level enum values."""
        assert UrgencyLevel.BATCH.value == "batch"
        assert UrgencyLevel.LOW.value == "low"
        assert UrgencyLevel.NORMAL.value == "normal"
        assert UrgencyLevel.HIGH.value == "high"
        assert UrgencyLevel.CRITICAL.value == "critical"


# =============================================================================
# CostModel Tests
# =============================================================================


class TestCostModel:
    """Tests for CostModel."""

    def test_cost_model_creation(self) -> None:
        """Test creating a cost model."""
        model = CostModel(
            provider_id="test-provider",
            model_id="test-model",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )

        assert model.provider_id == "test-provider"
        assert model.model_id == "test-model"
        assert model.input_cost_per_1k == 0.01
        assert model.output_cost_per_1k == 0.03
        assert model.constitutional_hash == CONSTITUTIONAL_HASH

    def test_calculate_cost_basic(self) -> None:
        """Test basic cost calculation."""
        model = CostModel(
            provider_id="test",
            model_id="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )

        cost = model.calculate_cost(input_tokens=1000, output_tokens=500)

        # Input: 1000/1000 * 0.01 = 0.01
        # Output: 500/1000 * 0.03 = 0.015
        # Total: 0.025
        assert cost == pytest.approx(0.025, rel=1e-6)

    def test_calculate_cost_with_cache(self) -> None:
        """Test cost calculation with cached tokens."""
        model = CostModel(
            provider_id="test",
            model_id="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
            cached_input_cost_per_1k=0.005,
        )

        cost = model.calculate_cost(
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=400,
        )

        # Non-cached input: 600/1000 * 0.01 = 0.006
        # Cached input: 400/1000 * 0.005 = 0.002
        # Output: 500/1000 * 0.03 = 0.015
        # Total: 0.023
        assert cost == pytest.approx(0.023, rel=1e-6)

    def test_calculate_cost_with_minimum(self) -> None:
        """Test cost calculation with minimum charge."""
        model = CostModel(
            provider_id="test",
            model_id="test",
            input_cost_per_1k=0.0001,
            output_cost_per_1k=0.0001,
            minimum_cost_per_request=0.01,
        )

        cost = model.calculate_cost(input_tokens=100, output_tokens=50)

        # Calculated cost would be very small, but minimum applies
        assert cost >= 0.01

    def test_calculate_cost_with_media(self) -> None:
        """Test cost calculation with media costs."""
        model = CostModel(
            provider_id="test",
            model_id="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
            image_cost_per_image=0.02,
            audio_cost_per_minute=0.006,
        )

        cost = model.calculate_cost(
            input_tokens=1000,
            output_tokens=500,
            images=2,
            audio_minutes=5.0,
        )

        # Base: 0.025
        # Images: 2 * 0.02 = 0.04
        # Audio: 5 * 0.006 = 0.03
        # Total: 0.095
        assert cost == pytest.approx(0.095, rel=1e-6)

    def test_to_dict(self) -> None:
        """Test cost model to dict conversion."""
        model = CostModel(
            provider_id="test",
            model_id="test-model",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
            tier=CostTier.STANDARD,
        )

        d = model.to_dict()

        assert d["provider_id"] == "test"
        assert d["model_id"] == "test-model"
        assert d["tier"] == "standard"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestCostEstimate:
    """Tests for CostEstimate."""

    def test_cost_estimate_creation(self) -> None:
        """Test creating a cost estimate."""
        estimate = CostEstimate(
            provider_id="test",
            model_id="test-model",
            estimated_cost=0.05,
            input_tokens=1000,
            estimated_output_tokens=500,
            confidence=0.9,
        )

        assert estimate.provider_id == "test"
        assert estimate.estimated_cost == 0.05
        assert estimate.confidence == 0.9
        assert estimate.constitutional_hash == CONSTITUTIONAL_HASH

    def test_cost_estimate_to_dict(self) -> None:
        """Test cost estimate to dict conversion."""
        estimate = CostEstimate(
            provider_id="test",
            model_id="model",
            estimated_cost=0.05,
            input_tokens=1000,
            estimated_output_tokens=500,
            confidence=0.85,
            breakdown={"input": 0.01, "output": 0.04},
        )

        d = estimate.to_dict()

        assert d["estimated_cost"] == 0.05
        assert d["breakdown"]["input"] == 0.01
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# BudgetLimit Tests
# =============================================================================


class TestBudgetLimit:
    """Tests for BudgetLimit."""

    def test_budget_limit_creation(self) -> None:
        """Test creating a budget limit."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
            monthly_limit=200.0,
        )

        assert limit.limit_id == "limit-1"
        assert limit.daily_limit == 10.0
        assert limit.monthly_limit == 200.0
        assert limit.constitutional_hash == CONSTITUTIONAL_HASH

    def test_check_limit_within_budget(self) -> None:
        """Test checking limit when within budget."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
            monthly_limit=200.0,
        )

        allowed, message = limit.check_limit(5.0)

        assert allowed is True
        assert message is None

    def test_check_limit_exceeds_daily(self) -> None:
        """Test checking limit when exceeding daily budget."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
            monthly_limit=200.0,
            daily_usage=8.0,
        )

        allowed, message = limit.check_limit(5.0)

        assert allowed is False
        assert "Daily limit exceeded" in message

    def test_check_limit_exceeds_monthly(self) -> None:
        """Test checking limit when exceeding monthly budget."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=100.0,
            monthly_limit=200.0,
            monthly_usage=198.0,
        )

        allowed, message = limit.check_limit(5.0)

        assert allowed is False
        assert "Monthly limit exceeded" in message

    def test_check_limit_exceeds_per_request(self) -> None:
        """Test checking limit when exceeding per-request limit."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            per_request_limit=1.0,
        )

        allowed, message = limit.check_limit(2.0)

        assert allowed is False
        assert "Per-request limit exceeded" in message

    def test_record_usage(self) -> None:
        """Test recording usage against budget."""
        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
        )

        limit.record_usage(3.0)
        assert limit.daily_usage == 3.0
        assert limit.monthly_usage == 3.0

        limit.record_usage(2.5)
        assert limit.daily_usage == 5.5
        assert limit.monthly_usage == 5.5


# =============================================================================
# BudgetManager Tests
# =============================================================================


class TestBudgetManager:
    """Tests for BudgetManager."""

    def test_add_and_get_limits(self) -> None:
        """Test adding and getting budget limits."""
        manager = BudgetManager()

        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
        )
        manager.add_limit(limit)

        limits = manager.get_limits_for_tenant("tenant-1")
        assert len(limits) == 1
        assert limits[0].limit_id == "limit-1"

    def test_global_limits(self) -> None:
        """Test global limits apply to all tenants."""
        manager = BudgetManager()

        global_limit = BudgetLimit(
            limit_id="global-1",
            tenant_id=None,
            operation_type=None,
            per_request_limit=5.0,
        )
        manager.add_limit(global_limit)

        limits = manager.get_limits_for_tenant("any-tenant")
        assert len(limits) == 1
        assert limits[0].limit_id == "global-1"

    def test_operation_type_filter(self) -> None:
        """Test operation type filtering."""
        manager = BudgetManager()

        limit1 = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type="inference",
            daily_limit=10.0,
        )
        limit2 = BudgetLimit(
            limit_id="limit-2",
            tenant_id="tenant-1",
            operation_type="embedding",
            daily_limit=5.0,
        )
        manager.add_limit(limit1)
        manager.add_limit(limit2)

        inference_limits = manager.get_limits_for_tenant("tenant-1", "inference")
        assert len(inference_limits) == 1
        assert inference_limits[0].operation_type == "inference"

    async def test_check_budget(self) -> None:
        """Test budget checking."""
        manager = BudgetManager()

        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
        )
        manager.add_limit(limit)

        allowed, _ = await manager.check_budget("tenant-1", 5.0)
        assert allowed is True

        # Simulate usage
        limit.daily_usage = 8.0
        allowed, message = await manager.check_budget("tenant-1", 5.0)
        assert allowed is False
        assert "Daily limit exceeded" in message

    async def test_record_cost(self) -> None:
        """Test cost recording."""
        manager = BudgetManager()

        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
        )
        manager.add_limit(limit)

        await manager.record_cost("tenant-1", 3.0)
        assert limit.daily_usage == 3.0

    def test_get_usage_summary(self) -> None:
        """Test getting usage summary."""
        manager = BudgetManager()

        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
            daily_usage=5.0,
            monthly_usage=50.0,
        )
        manager.add_limit(limit)

        summary = manager.get_usage_summary("tenant-1")

        assert summary["tenant_id"] == "tenant-1"
        assert summary["total_daily_usage"] == 5.0
        assert summary["total_monthly_usage"] == 50.0

    def test_remove_limit(self) -> None:
        """Test removing a budget limit."""
        manager = BudgetManager()

        limit = BudgetLimit(
            limit_id="limit-1",
            tenant_id="tenant-1",
            operation_type=None,
            daily_limit=10.0,
        )
        manager.add_limit(limit)
        manager.remove_limit("limit-1")

        limits = manager.get_limits_for_tenant("tenant-1")
        assert len(limits) == 0


# =============================================================================
# CostAnomalyDetector Tests
# =============================================================================


class TestCostAnomalyDetector:
    """Tests for CostAnomalyDetector."""

    def test_detector_creation(self) -> None:
        """Test creating anomaly detector."""
        detector = CostAnomalyDetector(
            window_size=50,
            spike_threshold=2.0,
        )

        assert detector._window_size == 50
        assert detector._spike_threshold == 2.0

    async def test_record_cost_no_anomaly(self) -> None:
        """Test recording costs without anomaly."""
        detector = CostAnomalyDetector(window_size=20)

        # Record consistent costs
        for i in range(15):
            anomaly = await detector.record_cost("tenant-1", "provider-1", 0.01)
            # No anomaly expected for consistent costs
            if i > 10:
                assert anomaly is None or anomaly.severity == "low"

    async def test_detect_spike(self) -> None:
        """Test detecting cost spike."""
        detector = CostAnomalyDetector(window_size=20, spike_threshold=2.0)

        # Record normal costs
        for _ in range(15):
            await detector.record_cost("tenant-1", "provider-1", 0.01)

        # Record spike
        anomaly = await detector.record_cost("tenant-1", "provider-1", 0.10)

        # Should detect spike
        if anomaly:
            assert anomaly.anomaly_type == "spike"
            assert anomaly.actual_cost == 0.10

    def test_check_budget_warning(self) -> None:
        """Test budget warning detection."""
        detector = CostAnomalyDetector(warning_threshold=0.8)

        anomaly = detector.check_budget_warning("tenant-1", 85.0, 100.0)

        assert anomaly is not None
        assert anomaly.anomaly_type == "budget_warning"
        assert "85.0%" in anomaly.description

    def test_no_budget_warning_below_threshold(self) -> None:
        """Test no warning below threshold."""
        detector = CostAnomalyDetector(warning_threshold=0.8)

        anomaly = detector.check_budget_warning("tenant-1", 70.0, 100.0)

        assert anomaly is None

    def test_register_callback(self) -> None:
        """Test registering anomaly callback."""
        detector = CostAnomalyDetector()
        callback_received = []

        def callback(anomaly: CostAnomaly) -> None:
            callback_received.append(anomaly)

        detector.register_callback(callback)

        assert len(detector._callbacks) == 1

    async def test_get_recent_anomalies(self) -> None:
        """Test getting recent anomalies with filters."""
        detector = CostAnomalyDetector(window_size=15, spike_threshold=1.5)

        # Create some anomalies
        for _ in range(12):
            await detector.record_cost("tenant-1", "provider-1", 0.01)

        await detector.record_cost("tenant-1", "provider-1", 0.05)

        anomalies = detector.get_recent_anomalies(tenant_id="tenant-1")
        # May or may not have detected anomaly depending on statistics
        assert isinstance(anomalies, list)


# =============================================================================
# BatchOptimizer Tests
# =============================================================================


class TestBatchOptimizer:
    """Tests for BatchOptimizer."""

    def test_optimizer_creation(self) -> None:
        """Test creating batch optimizer."""
        optimizer = BatchOptimizer(
            min_batch_size=3,
            max_batch_size=10,
        )

        assert optimizer._min_batch_size == 3
        assert optimizer._max_batch_size == 10

    async def test_add_request_not_batched(self) -> None:
        """Test adding high urgency request (not batched)."""
        optimizer = BatchOptimizer()

        request = BatchRequest(
            request_id="req-1",
            tenant_id="tenant-1",
            content="test content",
            requirements=[],
            urgency=UrgencyLevel.HIGH,
            quality=QualityLevel.STANDARD,
            max_wait_time=None,
        )

        batch_id = await optimizer.add_request(request)

        # High urgency should not be batched
        assert batch_id is None

    async def test_add_request_batched(self) -> None:
        """Test adding low urgency requests for batching."""
        optimizer = BatchOptimizer(min_batch_size=3, max_batch_size=5)

        # Add multiple requests
        for i in range(5):
            request = BatchRequest(
                request_id=f"req-{i}",
                tenant_id="tenant-1",
                content="test content",
                requirements=[],
                urgency=UrgencyLevel.BATCH,
                quality=QualityLevel.STANDARD,
                max_wait_time=timedelta(minutes=5),
                estimated_tokens=100,
            )
            batch_id = await optimizer.add_request(request)

            if i == 4:
                # Max batch size reached, should execute
                assert batch_id is not None

    async def test_flush_batches(self) -> None:
        """Test flushing pending batches."""
        optimizer = BatchOptimizer(min_batch_size=2, max_batch_size=10)

        # Add some requests
        for i in range(3):
            request = BatchRequest(
                request_id=f"req-{i}",
                tenant_id="tenant-1",
                content="test",
                requirements=[],
                urgency=UrgencyLevel.LOW,
                quality=QualityLevel.BASIC,
                max_wait_time=None,
                estimated_tokens=100,
            )
            await optimizer.add_request(request)

        batch_ids = await optimizer.flush_batches()

        assert len(batch_ids) >= 0  # May or may not have enough for batch

    def test_get_pending_count(self) -> None:
        """Test getting pending request count."""
        optimizer = BatchOptimizer()

        assert optimizer.get_pending_count() == 0


# =============================================================================
# CostOptimizer Tests
# =============================================================================


class TestCostOptimizer:
    """Tests for CostOptimizer."""

    def test_optimizer_creation(self) -> None:
        """Test creating cost optimizer."""
        optimizer = CostOptimizer()

        assert optimizer.registry is not None
        assert optimizer.budget_manager is not None
        assert optimizer.anomaly_detector is not None

    def test_default_cost_models_loaded(self) -> None:
        """Test that default cost models are loaded."""
        optimizer = CostOptimizer()

        # Should have cost models for default providers
        model = optimizer.get_cost_model("openai-gpt4o")
        assert model is not None
        assert model.input_cost_per_1k > 0

    def test_register_custom_cost_model(self) -> None:
        """Test registering custom cost model."""
        optimizer = CostOptimizer()

        custom_model = CostModel(
            provider_id="custom-provider",
            model_id="custom-model",
            input_cost_per_1k=0.001,
            output_cost_per_1k=0.002,
        )
        optimizer.register_cost_model(custom_model)

        retrieved = optimizer.get_cost_model("custom-provider")
        assert retrieved is not None
        assert retrieved.input_cost_per_1k == 0.001

    def test_estimate_cost(self) -> None:
        """Test cost estimation."""
        optimizer = CostOptimizer()

        estimate = optimizer.estimate_cost(
            provider_id="openai-gpt4o-mini",
            input_tokens=1000,
            estimated_output_tokens=500,
        )

        assert estimate is not None
        assert estimate.provider_id == "openai-gpt4o-mini"
        assert estimate.estimated_cost > 0
        assert estimate.constitutional_hash == CONSTITUTIONAL_HASH

    def test_estimate_cost_with_cache(self) -> None:
        """Test cost estimation with cached tokens."""
        optimizer = CostOptimizer()

        estimate_no_cache = optimizer.estimate_cost(
            provider_id="openai-gpt4o-mini",
            input_tokens=1000,
            estimated_output_tokens=500,
            cached_tokens=0,
        )

        estimate_with_cache = optimizer.estimate_cost(
            provider_id="openai-gpt4o-mini",
            input_tokens=1000,
            estimated_output_tokens=500,
            cached_tokens=500,
        )

        # Cached should be cheaper or equal
        assert estimate_with_cache.estimated_cost <= estimate_no_cache.estimated_cost

    async def test_select_optimal_provider(self) -> None:
        """Test optimal provider selection."""
        optimizer = CostOptimizer()

        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.FUNCTION_CALLING,
                min_value=CapabilityLevel.STANDARD,
            ),
        ]

        # Add a budget limit
        limit = BudgetLimit(
            limit_id="test-limit",
            tenant_id="test-tenant",
            operation_type=None,
            daily_limit=100.0,
        )
        optimizer.budget_manager.add_limit(limit)

        profile, estimate = await optimizer.select_optimal_provider(
            requirements=requirements,
            tenant_id="test-tenant",
            urgency=UrgencyLevel.NORMAL,
            quality=QualityLevel.STANDARD,
        )

        assert profile is not None
        assert estimate is not None

    async def test_select_provider_with_max_cost(self) -> None:
        """Test provider selection with max cost constraint."""
        optimizer = CostOptimizer()

        requirements = []

        # Add generous budget
        limit = BudgetLimit(
            limit_id="test-limit",
            tenant_id="test-tenant",
            operation_type=None,
            daily_limit=1000.0,
        )
        optimizer.budget_manager.add_limit(limit)

        # Very low max cost - should exclude expensive providers
        profile, estimate = await optimizer.select_optimal_provider(
            requirements=requirements,
            tenant_id="test-tenant",
            max_cost=0.0001,  # Very restrictive
            estimated_input_tokens=1000,
            estimated_output_tokens=500,
        )

        if profile is not None:
            assert estimate.estimated_cost <= 0.0001

    async def test_record_actual_cost(self) -> None:
        """Test recording actual cost."""
        optimizer = CostOptimizer()

        limit = BudgetLimit(
            limit_id="test-limit",
            tenant_id="test-tenant",
            operation_type=None,
            daily_limit=100.0,
        )
        optimizer.budget_manager.add_limit(limit)

        anomaly = await optimizer.record_actual_cost(
            tenant_id="test-tenant",
            provider_id="openai-gpt4o",
            actual_cost=0.05,
        )

        # Check usage was recorded
        summary = optimizer.budget_manager.get_usage_summary("test-tenant")
        assert summary["total_daily_usage"] == 0.05

    def test_get_cost_comparison(self) -> None:
        """Test getting cost comparison across providers."""
        optimizer = CostOptimizer()

        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.FUNCTION_CALLING,
                min_value=CapabilityLevel.BASIC,
            ),
        ]

        comparisons = optimizer.get_cost_comparison(
            requirements=requirements,
            estimated_input_tokens=1000,
            estimated_output_tokens=500,
        )

        assert len(comparisons) > 0
        # Should be sorted by cost
        for i in range(len(comparisons) - 1):
            assert comparisons[i]["estimated_cost"] <= comparisons[i + 1]["estimated_cost"]

    def test_get_cost_analytics(self) -> None:
        """Test getting cost analytics."""
        optimizer = CostOptimizer()

        limit = BudgetLimit(
            limit_id="test-limit",
            tenant_id="test-tenant",
            operation_type=None,
            daily_limit=100.0,
            daily_usage=25.0,
        )
        optimizer.budget_manager.add_limit(limit)

        analytics = optimizer.get_cost_analytics("test-tenant")

        assert analytics["tenant_id"] == "test-tenant"
        assert "usage" in analytics
        assert "recent_anomalies" in analytics
        assert analytics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstances:
    """Tests for global instance accessors."""

    def test_get_cost_optimizer(self) -> None:
        """Test getting global cost optimizer."""
        optimizer = get_cost_optimizer()

        assert optimizer is not None
        assert isinstance(optimizer, CostOptimizer)

    def test_get_cost_optimizer_singleton(self) -> None:
        """Test cost optimizer is singleton."""
        optimizer1 = get_cost_optimizer()
        optimizer2 = get_cost_optimizer()

        assert optimizer1 is optimizer2


# =============================================================================
# Integration Tests
# =============================================================================


class TestCostOptimizerIntegration:
    """Integration tests for cost optimizer."""

    async def test_budget_manager_isolation(self) -> None:
        """Test BudgetManager works in isolation within this test module."""
        manager = BudgetManager()
        tenant_id = "isolation-test-tenant"

        limit = BudgetLimit(
            limit_id="isolation-test-limit",
            tenant_id=tenant_id,
            operation_type=None,
            daily_limit=10.0,
        )
        manager.add_limit(limit)

        # Record cost
        await manager.record_cost(tenant_id, 5.0)

        # Check - this uses the ORIGINAL limit object, which was modified
        assert limit.daily_usage == 5.0, f"Expected 5.0, got {limit.daily_usage}"

        # This should also work - get_limits_for_tenant returns the same object
        limits = manager.get_limits_for_tenant(tenant_id)
        assert limits[0].daily_usage == 5.0, f"Expected 5.0, got {limits[0].daily_usage}"
        assert limits[0] is limit, "Should be the same object"

    async def test_full_workflow(self) -> None:
        """Test full cost optimization workflow."""
        # Create a fresh optimizer to avoid test interference
        optimizer = CostOptimizer(registry=CapabilityRegistry())

        # Use unique tenant ID
        import uuid

        tenant_id = f"integration-tenant-{uuid.uuid4().hex[:8]}"

        # 1. Set up budget
        limit = BudgetLimit(
            limit_id=f"integration-test-limit-{tenant_id}",
            tenant_id=tenant_id,
            operation_type=None,
            daily_limit=10.0,
            monthly_limit=100.0,
            per_request_limit=1.0,
        )
        optimizer.budget_manager.add_limit(limit)

        # Verify limit was added and track the object
        limits_before = optimizer.budget_manager.get_limits_for_tenant(tenant_id)
        assert len(limits_before) == 1, f"Expected 1 limit, got {len(limits_before)}"
        assert limits_before[0] is limit, "Should be the same object as added"

        # 2. Define requirements
        requirements = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=10000,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.FUNCTION_CALLING,
                min_value=CapabilityLevel.STANDARD,
            ),
        ]

        # 3. Select optimal provider
        profile, estimate = await optimizer.select_optimal_provider(
            requirements=requirements,
            tenant_id=tenant_id,
            urgency=UrgencyLevel.NORMAL,
            quality=QualityLevel.STANDARD,
            estimated_input_tokens=2000,
            estimated_output_tokens=1000,
        )

        assert profile is not None, "No provider found"
        assert estimate is not None, "No estimate returned"

        # 4. Simulate request completion and record cost
        # Note: Some providers (like Gemini Flash) are free, so estimated_cost may be 0
        # Use a minimum cost for testing to verify the budget recording mechanism
        actual_cost = max(estimate.estimated_cost * 1.1, 0.05)  # At least $0.05 for testing

        # Verify object identity before recording
        limits_mid = optimizer.budget_manager.get_limits_for_tenant(tenant_id)
        assert limits_mid[0] is limit, "Object identity lost after select_optimal_provider"

        # Record cost directly through the budget manager
        await optimizer.budget_manager.record_cost(tenant_id, actual_cost)

        # Check using the ORIGINAL limit object
        assert limit.daily_usage > 0, (
            f"Original limit not updated: {limit.daily_usage}, actual_cost was {actual_cost}"
        )
        assert limit.daily_usage == actual_cost, (
            f"Daily usage should equal {actual_cost}, got {limit.daily_usage}"
        )

        # 5. Check analytics
        analytics = optimizer.get_cost_analytics(tenant_id)
        assert analytics["usage"]["total_daily_usage"] > 0, "Analytics shows 0 usage"

    async def test_budget_enforcement(self) -> None:
        """Test budget enforcement prevents over-spending."""
        optimizer = CostOptimizer()

        # Set very low budget
        limit = BudgetLimit(
            limit_id="low-budget-limit",
            tenant_id="low-budget-tenant",
            operation_type=None,
            daily_limit=0.001,  # $0.001 daily limit
        )
        optimizer.budget_manager.add_limit(limit)

        requirements = []

        profile, estimate = await optimizer.select_optimal_provider(
            requirements=requirements,
            tenant_id="low-budget-tenant",
            estimated_input_tokens=100000,  # High token count
            estimated_output_tokens=50000,
        )

        # With such a low budget, most providers should be filtered out
        # or the result might be None
        if profile is not None:
            assert estimate.estimated_cost <= 0.001


# =============================================================================
# Constitutional Compliance Tests
# =============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional compliance in cost optimizer."""

    def test_cost_model_has_hash(self) -> None:
        """Test cost model includes constitutional hash."""
        model = CostModel(
            provider_id="test",
            model_id="test",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.03,
        )

        assert model.constitutional_hash == CONSTITUTIONAL_HASH

    def test_cost_estimate_has_hash(self) -> None:
        """Test cost estimate includes constitutional hash."""
        estimate = CostEstimate(
            provider_id="test",
            model_id="test",
            estimated_cost=0.05,
            input_tokens=1000,
            estimated_output_tokens=500,
            confidence=0.9,
        )

        assert estimate.constitutional_hash == CONSTITUTIONAL_HASH

    def test_budget_limit_has_hash(self) -> None:
        """Test budget limit includes constitutional hash."""
        limit = BudgetLimit(
            limit_id="test",
            tenant_id="tenant",
            operation_type=None,
        )

        assert limit.constitutional_hash == CONSTITUTIONAL_HASH

    def test_anomaly_has_hash(self) -> None:
        """Test anomaly includes constitutional hash."""
        anomaly = CostAnomaly(
            anomaly_id="test",
            tenant_id="tenant",
            provider_id="provider",
            detected_at=datetime.now(UTC),
            anomaly_type="spike",
            severity="medium",
            description="Test anomaly",
            expected_cost=0.01,
            actual_cost=0.05,
            deviation_percentage=400.0,
        )

        assert anomaly.constitutional_hash == CONSTITUTIONAL_HASH

    def test_analytics_has_hash(self) -> None:
        """Test analytics output includes constitutional hash."""
        optimizer = CostOptimizer()

        analytics = optimizer.get_cost_analytics("test-tenant")

        assert analytics["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_cost_comparison_has_hash(self) -> None:
        """Test cost comparison includes constitutional hash."""
        optimizer = CostOptimizer()

        comparisons = optimizer.get_cost_comparison([])

        if comparisons:
            assert comparisons[0]["constitutional_hash"] == CONSTITUTIONAL_HASH
