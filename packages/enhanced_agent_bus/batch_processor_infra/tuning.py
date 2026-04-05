"""
Auto-tuning and Adaptive Batch Size for ACGS-2.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class TuningState:
    current_batch_size: int
    min_batch_size: int = 1
    max_batch_size: int = 100
    adjustment_factor: float = 1.1
    slow_threshold_ms: float = 500.0


class BatchAutoTuner:
    def __init__(self, initial_batch_size: int = 10):
        self._state = TuningState(current_batch_size=initial_batch_size)

    def adjust_from_stats(self, success_rate: float, avg_latency_ms: float) -> int:
        old_size = self._state.current_batch_size

        if success_rate > 95 and avg_latency_ms < self._state.slow_threshold_ms:
            self._state.current_batch_size = min(
                self._state.max_batch_size,
                int(self._state.current_batch_size * self._state.adjustment_factor) + 1,
            )
        elif success_rate < 80 or avg_latency_ms > self._state.slow_threshold_ms * 2:
            self._state.current_batch_size = max(
                self._state.min_batch_size,
                int(self._state.current_batch_size / self._state.adjustment_factor),
            )

        if old_size != self._state.current_batch_size:
            logger.info(f"Auto-tuned batch size: {old_size} -> {self._state.current_batch_size}")

        return self._state.current_batch_size

    @property
    def batch_size(self) -> int:
        return self._state.current_batch_size
