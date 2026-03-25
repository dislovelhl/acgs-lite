# Constitutional Hash: 608508a9bd224290
# Sprint 58 — llm_adapters/cost/budget.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/llm_adapters/cost/budget.py

Targets ≥95% line coverage of:
  BudgetManager: add_limit, remove_limit, get_limits_for_tenant,
                 check_budget, record_cost, get_usage_summary
  _UsageSummary TypedDict (exercised via get_usage_summary)
"""

from __future__ import annotations

import asyncio

import pytest

from enhanced_agent_bus.llm_adapters.cost.budget import BudgetManager
from enhanced_agent_bus.llm_adapters.cost.models import BudgetLimit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_limit(
    limit_id: str,
    tenant_id: str | None = None,
    operation_type: str | None = None,
    daily_limit: float | None = 10.0,
    monthly_limit: float | None = 100.0,
    per_request_limit: float | None = None,
    daily_usage: float = 0.0,
    monthly_usage: float = 0.0,
) -> BudgetLimit:
    return BudgetLimit(
        limit_id=limit_id,
        tenant_id=tenant_id,
        operation_type=operation_type,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        per_request_limit=per_request_limit,
        daily_usage=daily_usage,
        monthly_usage=monthly_usage,
    )


# ---------------------------------------------------------------------------
# BudgetManager.__init__
# ---------------------------------------------------------------------------


class TestBudgetManagerInit:
    def test_initial_state(self):
        mgr = BudgetManager()
        assert mgr._limits == {}
        assert mgr._tenant_limits == {}
        assert mgr._global_limits == []
        assert mgr._lock is not None


# ---------------------------------------------------------------------------
# BudgetManager.add_limit
# ---------------------------------------------------------------------------


class TestAddLimit:
    def test_add_tenant_limit_new_tenant(self):
        mgr = BudgetManager()
        limit = _make_limit("l1", tenant_id="tenant-a")
        mgr.add_limit(limit)

        assert "l1" in mgr._limits
        assert "tenant-a" in mgr._tenant_limits
        assert "l1" in mgr._tenant_limits["tenant-a"]
        assert mgr._global_limits == []

    def test_add_tenant_limit_existing_tenant(self):
        mgr = BudgetManager()
        l1 = _make_limit("l1", tenant_id="tenant-a")
        l2 = _make_limit("l2", tenant_id="tenant-a")
        mgr.add_limit(l1)
        mgr.add_limit(l2)

        assert len(mgr._tenant_limits["tenant-a"]) == 2
        assert "l1" in mgr._tenant_limits["tenant-a"]
        assert "l2" in mgr._tenant_limits["tenant-a"]

    def test_add_global_limit(self):
        mgr = BudgetManager()
        limit = _make_limit("g1", tenant_id=None)
        mgr.add_limit(limit)

        assert "g1" in mgr._limits
        assert "g1" in mgr._global_limits
        assert mgr._tenant_limits == {}

    def test_add_multiple_global_limits(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1"))
        mgr.add_limit(_make_limit("g2"))
        assert len(mgr._global_limits) == 2


# ---------------------------------------------------------------------------
# BudgetManager.remove_limit
# ---------------------------------------------------------------------------


class TestRemoveLimit:
    def test_remove_nonexistent_limit_is_noop(self):
        mgr = BudgetManager()
        # Should not raise
        mgr.remove_limit("does-not-exist")

    def test_remove_tenant_limit(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="tenant-a")
        mgr.add_limit(limiter)

        mgr.remove_limit("l1")

        assert "l1" not in mgr._limits
        assert "l1" not in mgr._tenant_limits.get("tenant-a", [])

    def test_remove_global_limit(self):
        mgr = BudgetManager()
        g = _make_limit("g1", tenant_id=None)
        mgr.add_limit(g)

        mgr.remove_limit("g1")

        assert "g1" not in mgr._limits
        assert "g1" not in mgr._global_limits

    def test_remove_limit_with_tenant_not_in_tenant_limits(self):
        """Cover branch: limit.tenant_id set but tenant not in _tenant_limits."""
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="tenant-x")
        mgr.add_limit(limiter)
        # Manually clear the tenant tracking to simulate inconsistency
        mgr._tenant_limits.pop("tenant-x")
        # Should not raise; falls through to global_limits branch (elif)
        mgr.remove_limit("l1")
        assert "l1" not in mgr._limits

    def test_remove_limit_tenant_id_but_not_in_global(self):
        """Limit has tenant_id so elif branch (global_limits) is NOT taken."""
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1")
        mgr.add_limit(limiter)
        # Remove normally via the tenant branch
        mgr.remove_limit("l1")
        assert "l1" not in mgr._global_limits

    def test_remove_one_of_several_tenant_limits(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("l1", tenant_id="t1"))
        mgr.add_limit(_make_limit("l2", tenant_id="t1"))
        mgr.remove_limit("l1")
        assert "l1" not in mgr._tenant_limits["t1"]
        assert "l2" in mgr._tenant_limits["t1"]


# ---------------------------------------------------------------------------
# BudgetManager.get_limits_for_tenant
# ---------------------------------------------------------------------------


class TestGetLimitsForTenant:
    def test_returns_global_limits(self):
        mgr = BudgetManager()
        g = _make_limit("g1", tenant_id=None, operation_type=None)
        mgr.add_limit(g)

        result = mgr.get_limits_for_tenant("any-tenant")
        assert len(result) == 1
        assert result[0].limit_id == "g1"

    def test_returns_tenant_limits(self):
        mgr = BudgetManager()
        t = _make_limit("t1", tenant_id="tenant-a")
        mgr.add_limit(t)

        result = mgr.get_limits_for_tenant("tenant-a")
        assert any(lim.limit_id == "t1" for lim in result)

    def test_tenant_without_limits_returns_only_global(self):
        mgr = BudgetManager()
        g = _make_limit("g1", tenant_id=None)
        mgr.add_limit(g)

        result = mgr.get_limits_for_tenant("unknown-tenant")
        assert len(result) == 1

    def test_empty_manager_returns_empty(self):
        mgr = BudgetManager()
        assert mgr.get_limits_for_tenant("t") == []

    def test_operation_type_filter_none_limit(self):
        """Limit with operation_type=None matches any operation_type."""
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None, operation_type=None))
        result = mgr.get_limits_for_tenant("t", operation_type="chat")
        assert len(result) == 1

    def test_operation_type_filter_matching(self):
        """Limit with matching operation_type is included."""
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None, operation_type="chat"))
        result = mgr.get_limits_for_tenant("t", operation_type="chat")
        assert len(result) == 1

    def test_operation_type_filter_not_matching(self):
        """Limit with non-matching operation_type is excluded."""
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None, operation_type="embed"))
        result = mgr.get_limits_for_tenant("t", operation_type="chat")
        assert len(result) == 0

    def test_operation_type_none_request_matches_none_limit(self):
        """operation_type=None on call matches limit.operation_type=None."""
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None, operation_type=None))
        result = mgr.get_limits_for_tenant("t", operation_type=None)
        assert len(result) == 1

    def test_combines_global_and_tenant_limits(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None))
        mgr.add_limit(_make_limit("t1", tenant_id="tenant-a"))
        result = mgr.get_limits_for_tenant("tenant-a")
        ids = {lim.limit_id for lim in result}
        assert ids == {"g1", "t1"}

    def test_dangling_limit_id_is_skipped(self):
        """If a limit_id is in tenant_limits but not in _limits, it is skipped."""
        mgr = BudgetManager()
        mgr._tenant_limits["orphan-tenant"] = ["missing-id"]
        result = mgr.get_limits_for_tenant("orphan-tenant")
        assert result == []


# ---------------------------------------------------------------------------
# BudgetManager.check_budget
# ---------------------------------------------------------------------------


class TestCheckBudget:
    async def test_no_limits_returns_allowed(self):
        mgr = BudgetManager()
        allowed, msg = await mgr.check_budget("t1", 5.0)
        assert allowed is True
        assert msg is None

    async def test_within_limits_returns_allowed(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("l1", tenant_id="t1", daily_limit=100.0))
        allowed, msg = await mgr.check_budget("t1", 5.0)
        assert allowed is True
        assert msg is None

    async def test_exceeds_daily_limit_returns_blocked(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("l1", tenant_id="t1", daily_limit=10.0, daily_usage=9.0))
        allowed, msg = await mgr.check_budget("t1", 2.0)
        assert allowed is False
        assert msg is not None
        assert "Daily limit" in msg

    async def test_exceeds_per_request_limit(self):
        mgr = BudgetManager()
        mgr.add_limit(
            _make_limit(
                "l1", tenant_id="t1", per_request_limit=1.0, daily_limit=None, monthly_limit=None
            )
        )
        allowed, msg = await mgr.check_budget("t1", 2.0)
        assert allowed is False
        assert "Per-request" in msg

    async def test_exceeds_monthly_limit(self):
        mgr = BudgetManager()
        mgr.add_limit(
            _make_limit(
                "l1",
                tenant_id="t1",
                daily_limit=None,
                monthly_limit=10.0,
                monthly_usage=9.0,
            )
        )
        allowed, msg = await mgr.check_budget("t1", 5.0)
        assert allowed is False
        assert "Monthly limit" in msg

    async def test_uses_operation_type_filter(self):
        """A limit scoped to 'embed' does not block a 'chat' request."""
        mgr = BudgetManager()
        mgr.add_limit(
            _make_limit(
                "l1",
                tenant_id="t1",
                operation_type="embed",
                daily_limit=1.0,
                daily_usage=0.9,
            )
        )
        allowed, _msg = await mgr.check_budget("t1", 0.5, operation_type="chat")
        assert allowed is True

    async def test_first_blocking_limit_short_circuits(self):
        """Returns on the first limit that blocks; second limit not checked."""
        mgr = BudgetManager()
        # Global blocking limit
        mgr.add_limit(_make_limit("g1", tenant_id=None, daily_limit=1.0, daily_usage=1.0))
        # Tenant limit that would allow
        mgr.add_limit(_make_limit("t1", tenant_id="t1", daily_limit=100.0))
        allowed, _msg = await mgr.check_budget("t1", 0.1)
        assert allowed is False


# ---------------------------------------------------------------------------
# BudgetManager.record_cost
# ---------------------------------------------------------------------------


class TestRecordCost:
    async def test_record_cost_updates_usage(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", daily_limit=50.0, monthly_limit=500.0)
        mgr.add_limit(limiter)

        await mgr.record_cost("t1", 3.0)

        limit = mgr._limits["l1"]
        assert limit.daily_usage == pytest.approx(3.0)
        assert limit.monthly_usage == pytest.approx(3.0)

    async def test_record_cost_no_limits_is_noop(self):
        """No limits means no error, nothing recorded."""
        mgr = BudgetManager()
        # Should not raise
        await mgr.record_cost("t1", 5.0)

    async def test_record_cost_with_operation_type(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", operation_type="chat")
        mgr.add_limit(limiter)

        # Matching operation type => recorded
        await mgr.record_cost("t1", 2.0, operation_type="chat")
        assert mgr._limits["l1"].daily_usage == pytest.approx(2.0)

    async def test_record_cost_unmatched_operation_type_not_recorded(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", operation_type="embed")
        mgr.add_limit(limiter)

        await mgr.record_cost("t1", 2.0, operation_type="chat")
        assert mgr._limits["l1"].daily_usage == pytest.approx(0.0)

    async def test_record_cost_accumulates(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1")
        mgr.add_limit(limiter)

        await mgr.record_cost("t1", 1.5)
        await mgr.record_cost("t1", 2.5)

        limit = mgr._limits["l1"]
        assert limit.daily_usage == pytest.approx(4.0)
        assert limit.monthly_usage == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# BudgetManager.get_usage_summary
# ---------------------------------------------------------------------------


class TestGetUsageSummary:
    def test_empty_summary_no_limits(self):
        mgr = BudgetManager()
        summary = mgr.get_usage_summary("t1")
        assert summary["tenant_id"] == "t1"
        assert summary["limits"] == []
        assert summary["total_daily_usage"] == pytest.approx(0.0)
        assert summary["total_monthly_usage"] == pytest.approx(0.0)

    def test_summary_with_single_limit(self):
        mgr = BudgetManager()
        limiter = _make_limit(
            "l1",
            tenant_id="t1",
            daily_limit=10.0,
            monthly_limit=100.0,
            daily_usage=2.0,
            monthly_usage=5.0,
        )
        mgr.add_limit(limiter)

        summary = mgr.get_usage_summary("t1")
        assert summary["tenant_id"] == "t1"
        assert len(summary["limits"]) == 1
        entry = summary["limits"][0]
        assert entry["limit_id"] == "l1"
        assert entry["daily_limit"] == pytest.approx(10.0)
        assert entry["daily_usage"] == pytest.approx(2.0)
        assert entry["monthly_limit"] == pytest.approx(100.0)
        assert entry["monthly_usage"] == pytest.approx(5.0)
        assert entry["operation_type"] is None
        assert summary["total_daily_usage"] == pytest.approx(2.0)
        assert summary["total_monthly_usage"] == pytest.approx(5.0)

    def test_summary_with_multiple_limits_aggregates(self):
        mgr = BudgetManager()
        mgr.add_limit(_make_limit("g1", tenant_id=None, daily_usage=1.0, monthly_usage=3.0))
        mgr.add_limit(_make_limit("t1", tenant_id="tenant-a", daily_usage=2.0, monthly_usage=7.0))

        summary = mgr.get_usage_summary("tenant-a")
        assert summary["total_daily_usage"] == pytest.approx(3.0)
        assert summary["total_monthly_usage"] == pytest.approx(10.0)
        assert len(summary["limits"]) == 2

    def test_summary_includes_operation_type(self):
        """get_usage_summary calls get_limits_for_tenant with operation_type=None,
        which only matches limits whose operation_type is also None."""
        mgr = BudgetManager()
        # operation_type=None means "applies to all" — will appear in summary
        limiter = _make_limit("l1", tenant_id="t1", operation_type=None)
        mgr.add_limit(limiter)

        summary = mgr.get_usage_summary("t1")
        assert len(summary["limits"]) == 1
        # operation_type stored on the limit object is reflected in the summary entry
        assert summary["limits"][0]["operation_type"] is None

    def test_summary_returns_plain_dict(self):
        mgr = BudgetManager()
        summary = mgr.get_usage_summary("t1")
        assert isinstance(summary, dict)


# ---------------------------------------------------------------------------
# Concurrency / lock integrity
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_concurrent_record_and_check(self):
        """Multiple concurrent calls must not corrupt state."""
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", daily_limit=1000.0, monthly_limit=10000.0)
        mgr.add_limit(limiter)

        async def do_record():
            await mgr.record_cost("t1", 0.1)

        tasks = [asyncio.create_task(do_record()) for _ in range(20)]
        await asyncio.gather(*tasks)

        limit = mgr._limits["l1"]
        assert limit.daily_usage == pytest.approx(2.0, abs=1e-9)

    async def test_concurrent_check_budget(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", daily_limit=100.0)
        mgr.add_limit(limiter)

        results = await asyncio.gather(*[mgr.check_budget("t1", 1.0) for _ in range(10)])
        for allowed, msg in results:
            assert allowed is True
            assert msg is None


# ---------------------------------------------------------------------------
# Integration: full add → check → record → summary cycle
# ---------------------------------------------------------------------------


class TestIntegrationCycle:
    async def test_full_cycle_tenant_limit(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", daily_limit=5.0, monthly_limit=50.0)
        mgr.add_limit(limiter)

        allowed, _ = await mgr.check_budget("t1", 4.0)
        assert allowed is True

        await mgr.record_cost("t1", 4.0)

        allowed, msg = await mgr.check_budget("t1", 2.0)
        assert allowed is False
        assert msg is not None

        summary = mgr.get_usage_summary("t1")
        assert summary["total_daily_usage"] == pytest.approx(4.0)

    async def test_remove_then_unlimited(self):
        mgr = BudgetManager()
        limiter = _make_limit("l1", tenant_id="t1", daily_limit=1.0)
        mgr.add_limit(limiter)

        allowed, _ = await mgr.check_budget("t1", 5.0)
        assert allowed is False

        mgr.remove_limit("l1")

        allowed, _ = await mgr.check_budget("t1", 5.0)
        assert allowed is True

    async def test_global_limit_applies_to_all_tenants(self):
        mgr = BudgetManager()
        g = _make_limit("g1", tenant_id=None, daily_limit=2.0, daily_usage=1.9)
        mgr.add_limit(g)

        for tenant in ("t1", "t2", "t3"):
            allowed, _msg = await mgr.check_budget(tenant, 0.5)
            assert allowed is False, f"Expected blocked for {tenant}"
