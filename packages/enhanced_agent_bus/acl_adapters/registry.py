from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Any, TypeVar

from .base import CONSTITUTIONAL_HASH, ACLAdapter, AdapterConfig

AdapterT = TypeVar("AdapterT", bound=ACLAdapter[Any, Any])


class AdapterRegistry:
    _instance: AdapterRegistry | None = None
    _adapters: dict[str, ACLAdapter[Any, Any]] = {}
    _lock = threading.RLock()

    def __new__(cls) -> "AdapterRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def get_or_create(
        self,
        name: str,
        adapter_cls: type[AdapterT],
        config: AdapterConfig | None = None,
    ) -> AdapterT:
        with self._lock:
            existing = self._adapters.get(name)
            if existing is not None:
                return existing  # type: ignore[return-value]
            adapter = adapter_cls(name, config=config)
            self._adapters[name] = adapter
            return adapter

    def get(self, name: str) -> ACLAdapter[Any, Any] | None:
        return self._adapters.get(name)

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._adapters.pop(name, None) is not None

    def list_adapters(self) -> list[str]:
        return sorted(self._adapters.keys())

    def clear(self) -> None:
        with self._lock:
            self._adapters.clear()

    def reset_all(self) -> None:
        for adapter in list(self._adapters.values()):
            reset = getattr(adapter, "reset_circuit_breaker", None)
            if callable(reset):
                reset()
            clear_cache = getattr(adapter, "clear_cache", None)
            if callable(clear_cache):
                clear_cache()

    def get_all_health(self) -> dict[str, Any]:
        adapters = {name: adapter.get_health() for name, adapter in self._adapters.items()}
        total_count = len(adapters)
        healthy_count = sum(1 for item in adapters.values() if item.get("healthy"))
        score = healthy_count / total_count if total_count else 1.0
        if score >= 0.8:
            overall = "healthy"
        elif score == 0.0:
            overall = "unhealthy"
        else:
            overall = "degraded"
        return {
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "overall_health": overall,
            "health_score": score,
            "total_count": total_count,
            "healthy_count": healthy_count,
            "adapters": adapters,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_all_metrics(self) -> dict[str, Any]:
        adapters = {name: adapter.get_metrics() for name, adapter in self._adapters.items()}
        totals = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "cache_hits": 0,
            "fallback_uses": 0,
        }
        for metrics in adapters.values():
            for key in totals:
                totals[key] += int(metrics.get(key, 0))
        total_calls = totals["total_calls"]
        totals["success_rate"] = totals["successful_calls"] / total_calls if total_calls else 0.0
        totals["cache_hit_rate"] = totals["cache_hits"] / total_calls if total_calls else 0.0
        return {
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "totals": totals,
            "adapters": adapters,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def close_all(self) -> None:
        for adapter in list(self._adapters.values()):
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    continue


def get_registry() -> AdapterRegistry:
    return AdapterRegistry()


def get_adapter(name: str) -> ACLAdapter[Any, Any] | None:
    return get_registry().get(name)


__all__ = ["AdapterRegistry", "get_adapter", "get_registry"]
