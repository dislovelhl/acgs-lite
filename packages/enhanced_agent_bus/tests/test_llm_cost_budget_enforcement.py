"""
Tests for LLM cost budget enforcement.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.llm_adapters.cost.budget import BudgetManager
from enhanced_agent_bus.llm_adapters.cost.enums import CostTier
from enhanced_agent_bus.llm_adapters.cost.models import BudgetLimit, CostModel

# =============================================================================
# CostModel.calculate_cost
# =============================================================================


def test_cost_model_basic_calculation() -> None:
    """CostModel must correctly compute input + output token costs."""
    model = CostModel(
        provider_id="openai",
        model_id="gpt-4",
        input_cost_per_1k=0.03,
        output_cost_per_1k=0.06,
    )
    cost = model.calculate_cost(input_tokens=1000, output_tokens=500)
    assert cost == pytest.approx(0.03 + 0.03, rel=1e-5)


def test_cost_model_cached_tokens_cheaper() -> None:
    """Cached tokens should use cached_input_cost_per_1k, which is typically lower."""
    model = CostModel(
        provider_id="anthropic",
        model_id="claude-3",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.015,
        cached_input_cost_per_1k=0.0003,
    )
    # 500 cached, 500 non-cached
    cost = model.calculate_cost(input_tokens=1000, output_tokens=0, cached_tokens=500)
    expected = (500 / 1000) * 0.003 + (500 / 1000) * 0.0003
    assert cost == pytest.approx(expected, rel=1e-5)


def test_cost_model_minimum_charge_applied() -> None:
    """minimum_cost_per_request must floor the computed cost."""
    model = CostModel(
        provider_id="provider",
        model_id="small-model",
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.001,
        minimum_cost_per_request=0.01,
    )
    cost = model.calculate_cost(input_tokens=1, output_tokens=1)
    assert cost >= 0.01


# =============================================================================
# BudgetLimit.check_limit
# =============================================================================


def test_budget_limit_allows_request_within_daily_limit() -> None:
    """Requests within daily budget must be allowed."""
    limit = BudgetLimit(
        limit_id="lim-1",
        tenant_id="tenant-X",
        operation_type=None,
        daily_limit=10.0,
    )
    allowed, msg = limit.check_limit(cost=5.0)
    assert allowed is True
    assert msg is None


def test_budget_limit_blocks_when_daily_limit_exceeded() -> None:
    """Requests that would exceed daily budget must be blocked."""
    limit = BudgetLimit(
        limit_id="lim-2",
        tenant_id="tenant-X",
        operation_type=None,
        daily_limit=10.0,
        daily_usage=8.0,
    )
    allowed, msg = limit.check_limit(cost=3.0)  # 8.0 + 3.0 > 10.0
    assert allowed is False
    assert msg is not None
    assert "Daily limit exceeded" in msg


def test_budget_limit_blocks_per_request_overrun() -> None:
    """A single request exceeding per_request_limit must be blocked immediately."""
    limit = BudgetLimit(
        limit_id="lim-3",
        tenant_id=None,
        operation_type=None,
        per_request_limit=1.00,
    )
    allowed, msg = limit.check_limit(cost=1.50)
    assert allowed is False
    assert "Per-request limit exceeded" in msg


def test_budget_limit_blocks_when_monthly_limit_exceeded() -> None:
    """Monthly budget overrun must be blocked."""
    limit = BudgetLimit(
        limit_id="lim-4",
        tenant_id="tenant-Y",
        operation_type=None,
        monthly_limit=100.0,
        monthly_usage=99.0,
    )
    allowed, msg = limit.check_limit(cost=5.0)  # 99.0 + 5.0 > 100.0
    assert allowed is False
    assert "Monthly limit exceeded" in msg


# =============================================================================
# BudgetManager per-tenant isolation
# =============================================================================


async def test_budget_manager_per_tenant_isolation() -> None:
    """Usage recorded for tenant-A must not affect tenant-B's budget check."""
    manager = BudgetManager()

    limit_a = BudgetLimit(
        limit_id="limit-A",
        tenant_id="tenant-A",
        operation_type=None,
        daily_limit=10.0,
    )
    limit_b = BudgetLimit(
        limit_id="limit-B",
        tenant_id="tenant-B",
        operation_type=None,
        daily_limit=10.0,
    )
    manager.add_limit(limit_a)
    manager.add_limit(limit_b)

    # Record heavy usage for tenant-A
    await manager.record_cost("tenant-A", cost=9.5)

    # tenant-A is now near its limit
    allowed_a, _ = await manager.check_budget("tenant-A", cost=1.0)  # would hit 10.5
    assert allowed_a is False

    # tenant-B is unaffected
    allowed_b, _ = await manager.check_budget("tenant-B", cost=1.0)
    assert allowed_b is True


async def test_budget_manager_allows_within_limit() -> None:
    """Requests well within budget must pass."""
    manager = BudgetManager()
    manager.add_limit(
        BudgetLimit(
            limit_id="global-lim",
            tenant_id="tenant-Z",
            operation_type=None,
            daily_limit=100.0,
        )
    )

    allowed, msg = await manager.check_budget("tenant-Z", cost=50.0)
    assert allowed is True
    assert msg is None
