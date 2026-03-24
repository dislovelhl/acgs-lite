"""
ACGS-2 Budget Management
Constitutional Hash: cdd01ef066bc6cf2

Manages budget limits for tenants and operations with cost tracking.
"""

from __future__ import annotations

import asyncio

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
from typing_extensions import TypedDict

from .models import BudgetLimit


class _UsageSummary(TypedDict):
    """Type definition for usage summary."""

    tenant_id: str
    limits: list[JSONDict]
    total_daily_usage: float
    total_monthly_usage: float


class BudgetManager:
    """
    Manages budget limits for tenants and operations.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self) -> None:
        """Initialize budget manager."""
        self._limits: dict[str, BudgetLimit] = {}
        self._tenant_limits: dict[str, list[str]] = {}  # tenant_id -> limit_ids
        self._global_limits: list[str] = []
        self._lock = asyncio.Lock()

    def add_limit(self, limit: BudgetLimit) -> None:
        """Add a budget limit."""
        self._limits[limit.limit_id] = limit

        if limit.tenant_id:
            if limit.tenant_id not in self._tenant_limits:
                self._tenant_limits[limit.tenant_id] = []
            self._tenant_limits[limit.tenant_id].append(limit.limit_id)
        else:
            self._global_limits.append(limit.limit_id)

    def remove_limit(self, limit_id: str) -> None:
        """Remove a budget limit."""
        if limit_id in self._limits:
            limit = self._limits[limit_id]
            if limit.tenant_id and limit.tenant_id in self._tenant_limits:
                self._tenant_limits[limit.tenant_id].remove(limit_id)
            elif limit_id in self._global_limits:
                self._global_limits.remove(limit_id)
            del self._limits[limit_id]

    def get_limits_for_tenant(
        self, tenant_id: str, operation_type: str | None = None
    ) -> list[BudgetLimit]:
        """Get all applicable limits for a tenant."""
        limit_ids = self._global_limits.copy()
        if tenant_id in self._tenant_limits:
            limit_ids.extend(self._tenant_limits[tenant_id])

        limits = []
        for limit_id in limit_ids:
            limit = self._limits.get(limit_id)
            if limit:
                # Check operation type filter
                if limit.operation_type is None or limit.operation_type == operation_type:
                    limits.append(limit)

        return limits

    async def check_budget(
        self,
        tenant_id: str,
        cost: float,
        operation_type: str | None = None,
    ) -> tuple[bool, str | None]:
        """Check if cost is within budget for tenant."""
        async with self._lock:
            limits = self.get_limits_for_tenant(tenant_id, operation_type)

            for limit in limits:
                allowed, message = limit.check_limit(cost)
                if not allowed:
                    return False, message

            return True, None

    async def record_cost(
        self,
        tenant_id: str,
        cost: float,
        operation_type: str | None = None,
    ) -> None:
        """Record cost against tenant budgets."""
        async with self._lock:
            limits = self.get_limits_for_tenant(tenant_id, operation_type)
            for limit in limits:
                limit.record_usage(cost)

    def get_usage_summary(self, tenant_id: str) -> JSONDict:
        """Get usage summary for a tenant."""
        limits = self.get_limits_for_tenant(tenant_id)

        summary: _UsageSummary = {
            "tenant_id": tenant_id,
            "limits": [],
            "total_daily_usage": 0.0,
            "total_monthly_usage": 0.0,
        }

        for limit in limits:
            summary["limits"].append(
                {
                    "limit_id": limit.limit_id,
                    "daily_limit": limit.daily_limit,
                    "daily_usage": limit.daily_usage,
                    "monthly_limit": limit.monthly_limit,
                    "monthly_usage": limit.monthly_usage,
                    "operation_type": limit.operation_type,
                }
            )
            summary["total_daily_usage"] += limit.daily_usage
            summary["total_monthly_usage"] += limit.monthly_usage

        return dict(summary)  # type: ignore[return-value]


__all__ = [
    "BudgetManager",
]
