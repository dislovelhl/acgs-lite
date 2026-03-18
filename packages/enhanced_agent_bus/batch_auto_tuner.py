from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from typing import Any

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger("enhanced_agent_bus.batch_auto_tuner")
sys.modules.setdefault("enhanced_agent_bus.batch_auto_tuner", sys.modules[__name__])


@dataclass(slots=True)
class AutoTunerConfig:
    target_p99_latency_ms: float = 10.0
    min_batch_size: int = 10
    max_batch_size: int = 1000
    history_size: int = 10
    adjustment_factor: float = 0.2


class BatchAutoTuner:
    def __init__(self, config: AutoTunerConfig, initial_batch_size: int | None = None) -> None:
        self.config = config
        initial = initial_batch_size if initial_batch_size is not None else config.min_batch_size
        self.current_batch_size = max(config.min_batch_size, min(config.max_batch_size, initial))
        self._history: deque[dict[str, float]] = deque(maxlen=config.history_size)
        self._total_batches_analyzed = 0
        self._total_adjustments = 0

    def get_recommended_batch_size(self) -> int:
        return self.current_batch_size

    def record_batch_performance(
        self,
        batch_size: int,
        p99_latency_ms: float,
        p95_latency_ms: float,
        p50_latency_ms: float,
        success_rate: float,
    ) -> None:
        self._history.append(
            {
                "batch_size": float(batch_size),
                "p99_latency_ms": p99_latency_ms,
                "p95_latency_ms": p95_latency_ms,
                "p50_latency_ms": p50_latency_ms,
                "success_rate": success_rate,
            }
        )
        self._total_batches_analyzed += 1
        if len(self._history) >= min(3, self.config.history_size):
            self._update_batch_size_recommendation()

    def _update_batch_size_recommendation(self) -> None:
        if len(self._history) < 3:
            return
        avg_p99 = sum(item["p99_latency_ms"] for item in self._history) / len(self._history)
        new_size = self.current_batch_size
        factor = self.config.adjustment_factor
        if avg_p99 > self.config.target_p99_latency_ms:
            new_size = int(self.current_batch_size * (1.0 - factor))
        elif avg_p99 < self.config.target_p99_latency_ms * 0.8:
            new_size = int(self.current_batch_size * (1.0 + factor))
        else:
            return
        new_size = max(self.config.min_batch_size, min(self.config.max_batch_size, new_size))
        if new_size == self.current_batch_size:
            return
        old_size = self.current_batch_size
        self.current_batch_size = new_size
        self._total_adjustments += 1
        logger.info("Adjusted batch size from %s to %s", old_size, new_size)

    def get_statistics(self) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "current_batch_size": self.current_batch_size,
            "total_batches_analyzed": self._total_batches_analyzed,
            "total_adjustments": self._total_adjustments,
            "history_size": len(self._history),
        }
        if not self._history:
            return stats
        avg_p99 = sum(item["p99_latency_ms"] for item in self._history) / len(self._history)
        avg_success = sum(item["success_rate"] for item in self._history) / len(self._history)
        stats.update(
            {
                "target_p99_latency_ms": self.config.target_p99_latency_ms,
                "min_batch_size": self.config.min_batch_size,
                "max_batch_size": self.config.max_batch_size,
                "average_p99_latency_ms": avg_p99,
                "average_success_rate": avg_success,
            }
        )
        return stats

    def reset(self) -> None:
        self._history.clear()
        self._total_batches_analyzed = 0
        self._total_adjustments = 0
        logger.info("Batch auto tuner reset")
