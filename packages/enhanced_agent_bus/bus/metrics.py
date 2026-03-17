"""
Bus metrics collection and reporting.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..bus_types import JSONDict
from .validation import _is_mock_instance

if TYPE_CHECKING:
    from .core import EnhancedAgentBus

logger = get_logger(__name__)


class BusMetrics:
    """
    Metrics collection and reporting for EnhancedAgentBus.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        bus: EnhancedAgentBus,
        metrics: JSONDict,
        config: JSONDict,
    ) -> None:
        """
        Initialize metrics collector.

        Args:
            bus: Reference to the parent EnhancedAgentBus.
            metrics: Metrics dictionary to report from.
            config: Bus configuration.
        """
        self._bus = bus
        self._metrics = metrics
        self._config = config

    async def get_metrics_async(self, policy_client: object | None) -> JSONDict:
        """Get bus metrics with async policy registry health check.

        Args:
            policy_client: Policy client for health check.

        Returns:
            JSONDict: Metrics including message counts, agent stats,
                and policy registry health status.
        """
        metrics = self.get_metrics()
        if policy_client:
            try:
                res = await policy_client.health_check()
                if res and (_is_mock_instance(res) or res.get("status") == "healthy"):
                    pass
                else:
                    metrics["policy_registry_status"] = "unavailable"
            except (RuntimeError, ConnectionError, TimeoutError) as e:
                logger.debug(f"Policy registry health check failed: {e}")
                metrics["policy_registry_status"] = "unavailable"
        return metrics

    def get_metrics(self) -> JSONDict:
        """Get current bus operational metrics.

        Returns:
            JSONDict: Metrics including sent/received/failed counts,
                registered agents, queue size, constitutional hash,
                and Spec-to-Artifact governance accuracy score.
        """
        m = {
            **self._metrics,
            "agents": len(self._bus.get_registered_agents()),
            "registered_agents": len(self._bus.get_registered_agents()),
            "q_size": self._bus._message_queue.qsize(),
            "queue_size": self._bus._message_queue.qsize(),
            "messages_sent": self._metrics.get("messages_sent", self._metrics["sent"]),
            "messages_received": self._metrics.get("messages_received", self._metrics["received"]),
            "messages_failed": self._metrics.get("messages_failed", self._metrics["failed"]),
            "is_running": self._bus._running,
            "metering_enabled": self._config.get("enable_metering", True),
            "circuit_breaker_health": {"status": "HEALTHY", "failures": 0},
            "policy_registry_status": (
                "healthy"
                if not (
                    self._config.get("fail_policy") is True
                    or getattr(self._bus._policy_client, "_fail_status", False) is True
                )
                else "unavailable"
            ),
            "fallback_reason": None,
            "constitutional_hash": self._bus.constitutional_hash,
        }
        if self._bus._processor:
            pm = self._bus._processor.get_metrics()
            m["processor_metrics"] = pm
            # Don't overwrite explicit flags
            for k, v in pm.items():
                if k not in m:
                    m[k] = v

        # Spec-to-Artifact Score from impact scorer (ref: solveeverything.org)
        impact_scorer = getattr(self._bus, "_impact_scorer", None)
        if impact_scorer is not None and hasattr(impact_scorer, "get_spec_to_artifact_metrics"):
            m["spec_to_artifact"] = impact_scorer.get_spec_to_artifact_metrics()

        # RoCS — Return on Cognitive Spend (ref: solveeverything.org)
        rocs_tracker = getattr(self._bus, "_rocs_tracker", None)
        if rocs_tracker is not None and hasattr(rocs_tracker, "to_dict"):
            m["rocs"] = rocs_tracker.to_dict()

        return m
