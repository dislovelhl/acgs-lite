# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/llm_adapters/cost/models.py

Targets ≥95% line coverage of all six dataclasses:
  CostModel, CostEstimate, BudgetLimit, CostAnomaly, BatchRequest, BatchResult
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CONSTITUTIONAL_HASH,
    CapabilityDimension,
    CapabilityRequirement,
)
from enhanced_agent_bus.llm_adapters.cost.enums import (
    CostTier,
    QualityLevel,
    UrgencyLevel,
)
from enhanced_agent_bus.llm_adapters.cost.models import (
    BatchRequest,
    BatchResult,
    BudgetLimit,
    CostAnomaly,
    CostEstimate,
    CostModel,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

PROVIDER = "test-provider"
MODEL = "test-model"


def _make_cost_model(**kwargs) -> CostModel:
    defaults = dict(
        provider_id=PROVIDER,
        model_id=MODEL,
        input_cost_per_1k=1.0,
        output_cost_per_1k=2.0,
    )
    defaults.update(kwargs)
    return CostModel(**defaults)


def _make_budget(**kwargs) -> BudgetLimit:
    defaults = dict(
        limit_id="lim-1",
        tenant_id="tenant-1",
        operation_type="inference",
    )
    defaults.update(kwargs)
    return BudgetLimit(**defaults)


# =============================================================================
# CostModel tests
# =============================================================================


class TestCostModelDefaults:
    def test_required_fields_stored(self):
        m = _make_cost_model()
        assert m.provider_id == PROVIDER
        assert m.model_id == MODEL
        assert m.input_cost_per_1k == 1.0
        assert m.output_cost_per_1k == 2.0

    def test_optional_defaults(self):
        m = _make_cost_model()
        assert m.cached_input_cost_per_1k == 0.0
        assert m.image_cost_per_image == 0.0
        assert m.audio_cost_per_minute == 0.0
        assert m.video_cost_per_minute == 0.0
        assert m.minimum_cost_per_request == 0.0
        assert m.tier == CostTier.STANDARD
        assert m.currency == "USD"
        assert m.volume_discounts == []
        assert m.quality_mapping == {}

    def test_constitutional_hash_set(self):
        m = _make_cost_model()
        assert m.constitutional_hash == CONSTITUTIONAL_HASH

    def test_effective_date_set_automatically(self):
        before = datetime.now(UTC)
        m = _make_cost_model()
        after = datetime.now(UTC)
        assert before <= m.effective_date <= after

    def test_custom_tier(self):
        m = _make_cost_model(tier=CostTier.PREMIUM)
        assert m.tier == CostTier.PREMIUM

    def test_custom_currency(self):
        m = _make_cost_model(currency="EUR")
        assert m.currency == "EUR"


class TestCostModelCalculateCost:
    def test_basic_input_output(self):
        m = _make_cost_model(input_cost_per_1k=1.0, output_cost_per_1k=2.0)
        # 1000 input → $1.00; 1000 output → $2.00 → total $3.00
        cost = m.calculate_cost(input_tokens=1000, output_tokens=1000)
        assert cost == pytest.approx(3.0)

    def test_zero_tokens(self):
        m = _make_cost_model()
        cost = m.calculate_cost(input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_cached_input_reduces_non_cached(self):
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=0.0,
            cached_input_cost_per_1k=0.5,
        )
        # 800 non-cached + 200 cached; 1000 input total
        cost = m.calculate_cost(input_tokens=1000, output_tokens=0, cached_tokens=200)
        expected = (800 / 1000) * 1.0 + (200 / 1000) * 0.5
        assert cost == pytest.approx(expected)

    def test_cached_tokens_capped_at_input(self):
        """cached_tokens > input_tokens → non_cached_input should be 0 (max(0,...))."""
        m = _make_cost_model(input_cost_per_1k=1.0, output_cost_per_1k=0.0)
        cost = m.calculate_cost(input_tokens=100, output_tokens=0, cached_tokens=500)
        # non_cached = max(0, 100-500) = 0; cached portion: (500/1000)*0 (cached=0)
        assert cost >= 0.0

    def test_image_cost(self):
        m = _make_cost_model(
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            image_cost_per_image=0.05,
        )
        cost = m.calculate_cost(input_tokens=0, output_tokens=0, images=3)
        assert cost == pytest.approx(0.15)

    def test_audio_cost(self):
        m = _make_cost_model(
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            audio_cost_per_minute=0.10,
        )
        cost = m.calculate_cost(input_tokens=0, output_tokens=0, audio_minutes=2.5)
        assert cost == pytest.approx(0.25)

    def test_video_cost(self):
        m = _make_cost_model(
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            video_cost_per_minute=0.20,
        )
        cost = m.calculate_cost(input_tokens=0, output_tokens=0, video_minutes=1.0)
        assert cost == pytest.approx(0.20)

    def test_all_media_costs_combined(self):
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=2.0,
            image_cost_per_image=0.05,
            audio_cost_per_minute=0.10,
            video_cost_per_minute=0.20,
        )
        cost = m.calculate_cost(
            input_tokens=1000,
            output_tokens=1000,
            images=2,
            audio_minutes=1.0,
            video_minutes=0.5,
        )
        expected = 1.0 + 2.0 + 0.10 + 0.10 + 0.10
        assert cost == pytest.approx(expected)

    def test_volume_discount_applied(self):
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=0.0,
            volume_discounts=[(5000, 0.10)],  # 10% off when >=5000 tokens
        )
        # 3000 input + 3000 output = 6000 tokens → discount applies
        cost = m.calculate_cost(input_tokens=3000, output_tokens=3000)
        base = (3000 / 1000) * 1.0  # = 3.0
        expected = base * 0.90
        assert cost == pytest.approx(expected)

    def test_volume_discount_not_applied_below_threshold(self):
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=0.0,
            volume_discounts=[(5000, 0.10)],
        )
        cost = m.calculate_cost(input_tokens=1000, output_tokens=1000)
        assert cost == pytest.approx(1.0)  # no discount

    def test_highest_volume_discount_chosen(self):
        """Multiple thresholds → highest applicable threshold wins (sorted reverse)."""
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=0.0,
            volume_discounts=[(1000, 0.05), (5000, 0.20)],
        )
        # 6000 total tokens → both thresholds met; only highest (5000 → 20%) applied
        cost = m.calculate_cost(input_tokens=3000, output_tokens=3000)
        base = 3.0
        assert cost == pytest.approx(base * 0.80)

    def test_minimum_cost_applied(self):
        m = _make_cost_model(
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            minimum_cost_per_request=0.001,
        )
        cost = m.calculate_cost(input_tokens=0, output_tokens=0)
        assert cost == pytest.approx(0.001)

    def test_minimum_cost_not_applied_when_above(self):
        m = _make_cost_model(
            input_cost_per_1k=1.0,
            output_cost_per_1k=0.0,
            minimum_cost_per_request=0.001,
        )
        cost = m.calculate_cost(input_tokens=1000, output_tokens=0)
        assert cost == pytest.approx(1.0)

    def test_calculate_cost_no_volume_discounts(self):
        """Empty volume_discounts list: no discount branch executed."""
        m = _make_cost_model(input_cost_per_1k=2.0, output_cost_per_1k=4.0)
        cost = m.calculate_cost(input_tokens=500, output_tokens=500)
        expected = (500 / 1000) * 2.0 + (500 / 1000) * 4.0
        assert cost == pytest.approx(expected)


class TestCostModelToDict:
    def test_to_dict_keys(self):
        m = _make_cost_model()
        d = m.to_dict()
        expected_keys = {
            "provider_id",
            "model_id",
            "input_cost_per_1k",
            "output_cost_per_1k",
            "cached_input_cost_per_1k",
            "tier",
            "currency",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        m = _make_cost_model(tier=CostTier.BUDGET, currency="GBP")
        d = m.to_dict()
        assert d["provider_id"] == PROVIDER
        assert d["tier"] == CostTier.BUDGET.value
        assert d["currency"] == "GBP"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_tier_value_is_string(self):
        m = _make_cost_model(tier=CostTier.ENTERPRISE)
        d = m.to_dict()
        assert isinstance(d["tier"], str)
        assert d["tier"] == "enterprise"

    def test_quality_mapping_not_in_dict(self):
        """to_dict intentionally omits quality_mapping."""
        m = _make_cost_model(quality_mapping={QualityLevel.HIGH: []})
        d = m.to_dict()
        assert "quality_mapping" not in d


# =============================================================================
# CostEstimate tests
# =============================================================================


class TestCostEstimate:
    def _make(self, **kwargs):
        defaults = dict(
            provider_id=PROVIDER,
            model_id=MODEL,
            estimated_cost=0.05,
            input_tokens=1000,
            estimated_output_tokens=200,
            confidence=0.85,
        )
        defaults.update(kwargs)
        return CostEstimate(**defaults)

    def test_required_fields(self):
        e = self._make()
        assert e.provider_id == PROVIDER
        assert e.model_id == MODEL
        assert e.estimated_cost == pytest.approx(0.05)
        assert e.input_tokens == 1000
        assert e.estimated_output_tokens == 200
        assert e.confidence == pytest.approx(0.85)

    def test_defaults(self):
        e = self._make()
        assert e.currency == "USD"
        assert e.breakdown == {}
        assert e.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_breakdown(self):
        e = self._make(breakdown={"input": 0.03, "output": 0.02})
        assert e.breakdown["input"] == pytest.approx(0.03)

    def test_to_dict_keys(self):
        e = self._make()
        d = e.to_dict()
        expected = {
            "provider_id",
            "model_id",
            "estimated_cost",
            "input_tokens",
            "estimated_output_tokens",
            "confidence",
            "currency",
            "breakdown",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected

    def test_to_dict_values(self):
        e = self._make(confidence=0.9, currency="EUR")
        d = e.to_dict()
        assert d["confidence"] == pytest.approx(0.9)
        assert d["currency"] == "EUR"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_breakdown_empty(self):
        e = self._make()
        d = e.to_dict()
        assert d["breakdown"] == {}

    def test_to_dict_breakdown_non_empty(self):
        breakdown = {"input": 0.01, "output": 0.04}
        e = self._make(breakdown=breakdown)
        d = e.to_dict()
        assert d["breakdown"] == breakdown

    def test_confidence_zero(self):
        e = self._make(confidence=0.0)
        assert e.confidence == 0.0

    def test_confidence_one(self):
        e = self._make(confidence=1.0)
        assert e.confidence == 1.0


# =============================================================================
# BudgetLimit tests
# =============================================================================


class TestBudgetLimitDefaults:
    def test_required_fields(self):
        b = _make_budget()
        assert b.limit_id == "lim-1"
        assert b.tenant_id == "tenant-1"
        assert b.operation_type == "inference"

    def test_optional_defaults(self):
        b = _make_budget()
        assert b.daily_limit is None
        assert b.monthly_limit is None
        assert b.per_request_limit is None
        assert b.action_on_exceed == "block"
        assert b.daily_usage == 0.0
        assert b.monthly_usage == 0.0
        assert b.constitutional_hash == CONSTITUTIONAL_HASH

    def test_global_limit_tenant_none(self):
        b = _make_budget(tenant_id=None)
        assert b.tenant_id is None

    def test_all_operations_type_none(self):
        b = _make_budget(operation_type=None)
        assert b.operation_type is None


class TestBudgetLimitCheckLimit:
    def test_no_limits_always_passes(self):
        b = _make_budget()
        ok, msg = b.check_limit(999.0)
        assert ok is True
        assert msg is None

    def test_per_request_exceeded(self):
        b = _make_budget(per_request_limit=0.10)
        ok, msg = b.check_limit(0.20)
        assert ok is False
        assert "Per-request limit exceeded" in msg

    def test_per_request_exactly_at_limit_passes(self):
        b = _make_budget(per_request_limit=0.10)
        ok, msg = b.check_limit(0.10)
        # 0.10 > 0.10 is False → should pass
        assert ok is True
        assert msg is None

    def test_per_request_just_above_limit_fails(self):
        b = _make_budget(per_request_limit=0.10)
        ok, _msg = b.check_limit(0.1001)
        assert ok is False

    def test_daily_limit_exceeded(self):
        b = _make_budget(daily_limit=5.0, daily_usage=4.90)
        ok, msg = b.check_limit(0.20)
        assert ok is False
        assert "Daily limit exceeded" in msg

    def test_daily_limit_exactly_at_boundary_passes(self):
        b = _make_budget(daily_limit=5.0, daily_usage=4.80)
        ok, msg = b.check_limit(0.20)
        # 4.80 + 0.20 = 5.00 which equals limit → 5.00 > 5.00 is False → pass
        assert ok is True
        assert msg is None

    def test_monthly_limit_exceeded(self):
        b = _make_budget(monthly_limit=100.0, monthly_usage=99.90)
        ok, msg = b.check_limit(0.20)
        assert ok is False
        assert "Monthly limit exceeded" in msg

    def test_monthly_limit_exactly_at_boundary_passes(self):
        b = _make_budget(monthly_limit=100.0, monthly_usage=99.80)
        ok, _msg = b.check_limit(0.20)
        assert ok is True

    def test_per_request_checked_before_daily(self):
        """Per-request check is first; if it fails, daily is not evaluated."""
        b = _make_budget(per_request_limit=0.05, daily_limit=10.0, daily_usage=0.0)
        ok, msg = b.check_limit(0.10)
        assert ok is False
        assert "Per-request" in msg

    def test_daily_checked_before_monthly(self):
        b = _make_budget(daily_limit=1.0, daily_usage=0.9, monthly_limit=200.0, monthly_usage=0.0)
        ok, msg = b.check_limit(0.20)
        assert ok is False
        assert "Daily" in msg

    def test_all_limits_within(self):
        b = _make_budget(
            per_request_limit=1.0,
            daily_limit=100.0,
            daily_usage=10.0,
            monthly_limit=1000.0,
            monthly_usage=100.0,
        )
        ok, msg = b.check_limit(0.50)
        assert ok is True
        assert msg is None

    def test_zero_cost_always_passes_with_all_limits(self):
        b = _make_budget(
            per_request_limit=0.0,  # 0 > 0 is False → passes
            daily_limit=0.0,
            daily_usage=0.0,
            monthly_limit=0.0,
            monthly_usage=0.0,
        )
        ok, _msg = b.check_limit(0.0)
        assert ok is True


class TestBudgetLimitRecordUsage:
    def test_record_usage_increments(self):
        b = _make_budget()
        b.record_usage(1.50)
        assert b.daily_usage == pytest.approx(1.50)
        assert b.monthly_usage == pytest.approx(1.50)

    def test_record_usage_accumulates(self):
        b = _make_budget()
        b.record_usage(1.00)
        b.record_usage(2.00)
        assert b.daily_usage == pytest.approx(3.00)
        assert b.monthly_usage == pytest.approx(3.00)

    def test_record_usage_updates_last_reset(self):
        b = _make_budget()
        before = datetime.now(UTC)
        b.record_usage(0.5)
        after = datetime.now(UTC)
        assert before <= b.last_reset <= after

    def test_record_usage_resets_daily_on_new_day(self):
        """Simulate last_reset being yesterday → daily usage resets."""
        b = _make_budget()
        b.daily_usage = 10.0
        b.monthly_usage = 50.0
        yesterday = datetime.now(UTC) - timedelta(days=1)
        b.last_reset = yesterday

        b.record_usage(1.0)
        # daily should reset to 0 then add 1.0
        assert b.daily_usage == pytest.approx(1.0)
        # monthly should NOT reset (same month, assuming test runs within same month)
        # monthly was 50 + 1 = 51 (no reset)
        assert b.monthly_usage == pytest.approx(51.0)

    def test_record_usage_resets_monthly_on_new_month(self):
        """Simulate last_reset being a different month → both monthly resets."""
        b = _make_budget()
        b.daily_usage = 5.0
        b.monthly_usage = 300.0

        # Use a date from two months ago
        two_months_ago = datetime.now(UTC) - timedelta(days=62)
        b.last_reset = two_months_ago

        b.record_usage(2.0)
        # Monthly usage reset to 0 then += 2.0
        assert b.monthly_usage == pytest.approx(2.0)

    def test_record_usage_zero(self):
        b = _make_budget()
        b.record_usage(0.0)
        assert b.daily_usage == pytest.approx(0.0)
        assert b.monthly_usage == pytest.approx(0.0)


# =============================================================================
# CostAnomaly tests
# =============================================================================


class TestCostAnomaly:
    def _make(self, **kwargs):
        defaults = dict(
            anomaly_id="anom-1",
            tenant_id="tenant-1",
            provider_id=PROVIDER,
            detected_at=datetime.now(UTC),
            anomaly_type="spike",
            severity="high",
            description="Cost spike detected",
            expected_cost=1.0,
            actual_cost=5.0,
            deviation_percentage=400.0,
        )
        defaults.update(kwargs)
        return CostAnomaly(**defaults)

    def test_required_fields(self):
        a = self._make()
        assert a.anomaly_id == "anom-1"
        assert a.tenant_id == "tenant-1"
        assert a.provider_id == PROVIDER
        assert a.anomaly_type == "spike"
        assert a.severity == "high"
        assert a.expected_cost == pytest.approx(1.0)
        assert a.actual_cost == pytest.approx(5.0)
        assert a.deviation_percentage == pytest.approx(400.0)

    def test_constitutional_hash_default(self):
        a = self._make()
        assert a.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_constitutional_hash(self):
        a = self._make(constitutional_hash="custom-hash")
        assert a.constitutional_hash == "custom-hash"

    def test_anomaly_type_unusual_pattern(self):
        a = self._make(anomaly_type="unusual_pattern")
        assert a.anomaly_type == "unusual_pattern"

    def test_anomaly_type_budget_warning(self):
        a = self._make(anomaly_type="budget_warning")
        assert a.anomaly_type == "budget_warning"

    def test_severity_low(self):
        a = self._make(severity="low")
        assert a.severity == "low"

    def test_severity_medium(self):
        a = self._make(severity="medium")
        assert a.severity == "medium"

    def test_severity_critical(self):
        a = self._make(severity="critical")
        assert a.severity == "critical"

    def test_detected_at_stored(self):
        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        a = self._make(detected_at=dt)
        assert a.detected_at == dt


# =============================================================================
# BatchRequest tests
# =============================================================================


class TestBatchRequest:
    def _req(self) -> CapabilityRequirement:
        return CapabilityRequirement(dimension=CapabilityDimension.CONTEXT_LENGTH, min_value=1000)

    def _make(self, **kwargs):
        defaults = dict(
            request_id="req-1",
            tenant_id="tenant-1",
            content="Hello world",
            requirements=[],
            urgency=UrgencyLevel.NORMAL,
            quality=QualityLevel.STANDARD,
            max_wait_time=timedelta(seconds=30),
        )
        defaults.update(kwargs)
        return BatchRequest(**defaults)

    def test_required_fields(self):
        r = self._make()
        assert r.request_id == "req-1"
        assert r.tenant_id == "tenant-1"
        assert r.content == "Hello world"
        assert r.urgency == UrgencyLevel.NORMAL
        assert r.quality == QualityLevel.STANDARD
        assert r.max_wait_time == timedelta(seconds=30)

    def test_defaults(self):
        r = self._make()
        assert r.estimated_tokens == 0
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_auto(self):
        before = datetime.now(UTC)
        r = self._make()
        after = datetime.now(UTC)
        assert before <= r.created_at <= after

    def test_max_wait_time_none(self):
        r = self._make(max_wait_time=None)
        assert r.max_wait_time is None

    def test_requirements_with_items(self):
        req = self._req()
        r = self._make(requirements=[req])
        assert len(r.requirements) == 1

    def test_all_urgency_levels(self):
        for level in UrgencyLevel:
            r = self._make(urgency=level)
            assert r.urgency == level

    def test_all_quality_levels(self):
        for level in QualityLevel:
            r = self._make(quality=level)
            assert r.quality == level

    def test_estimated_tokens_custom(self):
        r = self._make(estimated_tokens=512)
        assert r.estimated_tokens == 512

    def test_custom_constitutional_hash(self):
        r = self._make(constitutional_hash="override")
        assert r.constitutional_hash == "override"


# =============================================================================
# BatchResult tests
# =============================================================================


class TestBatchResult:
    def _make(self, **kwargs):
        defaults = dict(
            batch_id="batch-1",
            requests=["req-1", "req-2"],
            provider_id=PROVIDER,
            total_cost=0.10,
            cost_per_request=0.05,
            savings_percentage=15.0,
        )
        defaults.update(kwargs)
        return BatchResult(**defaults)

    def test_required_fields(self):
        r = self._make()
        assert r.batch_id == "batch-1"
        assert r.requests == ["req-1", "req-2"]
        assert r.provider_id == PROVIDER
        assert r.total_cost == pytest.approx(0.10)
        assert r.cost_per_request == pytest.approx(0.05)
        assert r.savings_percentage == pytest.approx(15.0)

    def test_defaults(self):
        r = self._make()
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_processed_at_auto(self):
        before = datetime.now(UTC)
        r = self._make()
        after = datetime.now(UTC)
        assert before <= r.processed_at <= after

    def test_empty_requests(self):
        r = self._make(requests=[])
        assert r.requests == []

    def test_single_request(self):
        r = self._make(requests=["req-only"])
        assert len(r.requests) == 1

    def test_many_requests(self):
        ids = [f"req-{i}" for i in range(100)]
        r = self._make(requests=ids)
        assert len(r.requests) == 100

    def test_zero_savings(self):
        r = self._make(savings_percentage=0.0)
        assert r.savings_percentage == 0.0

    def test_full_savings(self):
        r = self._make(savings_percentage=100.0)
        assert r.savings_percentage == pytest.approx(100.0)

    def test_custom_processed_at(self):
        dt = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        r = self._make(processed_at=dt)
        assert r.processed_at == dt

    def test_custom_constitutional_hash(self):
        r = self._make(constitutional_hash="custom")
        assert r.constitutional_hash == "custom"


# =============================================================================
# Module-level __all__ export test
# =============================================================================


class TestModuleExports:
    def test_all_classes_exported(self):
        from enhanced_agent_bus.llm_adapters.cost import models

        expected = {
            "CostModel",
            "CostEstimate",
            "BudgetLimit",
            "CostAnomaly",
            "BatchRequest",
            "BatchResult",
        }
        assert set(models.__all__) == expected


# =============================================================================
# Integration-style: combined scenarios
# =============================================================================


class TestCostModelIntegration:
    def test_free_model_zero_cost(self):
        m = _make_cost_model(
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            tier=CostTier.FREE,
        )
        cost = m.calculate_cost(input_tokens=10000, output_tokens=10000)
        assert cost == 0.0

    def test_enterprise_model_with_volume_discount(self):
        m = _make_cost_model(
            input_cost_per_1k=0.10,
            output_cost_per_1k=0.20,
            tier=CostTier.ENTERPRISE,
            volume_discounts=[(10000, 0.15), (50000, 0.25)],
        )
        # 60000 tokens total → 25% discount
        cost = m.calculate_cost(input_tokens=30000, output_tokens=30000)
        base = (30000 / 1000) * 0.10 + (30000 / 1000) * 0.20
        expected = base * 0.75
        assert cost == pytest.approx(expected)

    def test_budget_model_minimum_charge(self):
        m = _make_cost_model(
            input_cost_per_1k=0.001,
            output_cost_per_1k=0.001,
            tier=CostTier.BUDGET,
            minimum_cost_per_request=0.01,
        )
        # Very few tokens → cost < minimum
        cost = m.calculate_cost(input_tokens=1, output_tokens=1)
        assert cost == pytest.approx(0.01)

    def test_to_dict_roundtrip_values(self):
        m = _make_cost_model(
            input_cost_per_1k=3.14,
            output_cost_per_1k=6.28,
            cached_input_cost_per_1k=1.57,
            tier=CostTier.PREMIUM,
        )
        d = m.to_dict()
        assert d["input_cost_per_1k"] == pytest.approx(3.14)
        assert d["output_cost_per_1k"] == pytest.approx(6.28)
        assert d["cached_input_cost_per_1k"] == pytest.approx(1.57)
        assert d["tier"] == "premium"


class TestBudgetLimitIntegration:
    def test_check_then_record(self):
        b = _make_budget(daily_limit=10.0, monthly_limit=100.0)
        ok, _ = b.check_limit(5.0)
        assert ok is True
        b.record_usage(5.0)
        assert b.daily_usage == pytest.approx(5.0)

        ok, _ = b.check_limit(5.0)
        assert ok is True  # 5+5 = 10 which is not > 10
        b.record_usage(5.0)

        ok, _ = b.check_limit(0.01)
        assert ok is False  # 10 + 0.01 > 10

    def test_record_usage_multiple_times_in_same_day(self):
        b = _make_budget()
        for _ in range(10):
            b.record_usage(0.10)
        assert b.daily_usage == pytest.approx(1.0)
        assert b.monthly_usage == pytest.approx(1.0)


class TestCostEstimateIntegration:
    def test_estimate_with_full_breakdown(self):
        e = CostEstimate(
            provider_id="openai",
            model_id="gpt-4o",
            estimated_cost=0.15,
            input_tokens=5000,
            estimated_output_tokens=1000,
            confidence=0.75,
            breakdown={"input": 0.05, "output": 0.10},
        )
        d = e.to_dict()
        assert d["breakdown"]["input"] == pytest.approx(0.05)
        assert d["breakdown"]["output"] == pytest.approx(0.10)
        assert d["estimated_cost"] == pytest.approx(0.15)


class TestBatchRequestIntegration:
    def test_batch_request_with_requirements(self):
        reqs = [
            CapabilityRequirement(
                dimension=CapabilityDimension.CONTEXT_LENGTH,
                min_value=16000,
            ),
            CapabilityRequirement(
                dimension=CapabilityDimension.STREAMING,
                min_value=True,
            ),
        ]
        r = BatchRequest(
            request_id="batch-req-1",
            tenant_id="tenant-x",
            content="Analyze this document",
            requirements=reqs,
            urgency=UrgencyLevel.LOW,
            quality=QualityLevel.HIGH,
            max_wait_time=timedelta(minutes=5),
            estimated_tokens=2048,
        )
        assert len(r.requirements) == 2
        assert r.estimated_tokens == 2048
        assert r.urgency == UrgencyLevel.LOW
        assert r.quality == QualityLevel.HIGH


class TestEnumsUsedInModels:
    def test_cost_tier_values(self):
        assert CostTier.FREE.value == "free"
        assert CostTier.BUDGET.value == "budget"
        assert CostTier.STANDARD.value == "standard"
        assert CostTier.PREMIUM.value == "premium"
        assert CostTier.ENTERPRISE.value == "enterprise"

    def test_quality_level_values(self):
        assert QualityLevel.MINIMAL.value == "minimal"
        assert QualityLevel.BASIC.value == "basic"
        assert QualityLevel.STANDARD.value == "standard"
        assert QualityLevel.HIGH.value == "high"
        assert QualityLevel.MAXIMUM.value == "maximum"

    def test_urgency_level_values(self):
        assert UrgencyLevel.BATCH.value == "batch"
        assert UrgencyLevel.LOW.value == "low"
        assert UrgencyLevel.NORMAL.value == "normal"
        assert UrgencyLevel.HIGH.value == "high"
        assert UrgencyLevel.CRITICAL.value == "critical"

    def test_cost_model_with_all_tiers(self):
        for tier in CostTier:
            m = _make_cost_model(tier=tier)
            d = m.to_dict()
            assert d["tier"] == tier.value
