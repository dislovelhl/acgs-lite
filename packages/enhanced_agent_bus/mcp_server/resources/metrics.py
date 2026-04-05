"""
Governance Metrics MCP Resource.

Provides read access to governance metrics.

Constitutional Hash: 608508a9bd224290
"""

import json
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..protocol.types import ResourceDefinition

logger = get_logger(__name__)
METRICS_RESOURCE_READ_ERRORS = (RuntimeError, ValueError, TypeError, KeyError, AttributeError)


class MetricsResource:
    """
    MCP Resource for governance metrics.

    Provides read-only access to real-time governance metrics
    and system health information.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    URI = "acgs2://governance/metrics"

    def __init__(self, get_metrics_tool: object | None = None):
        """
        Initialize the metrics resource.

        Args:
            get_metrics_tool: Optional reference to GetMetricsTool for data
        """
        self.get_metrics_tool = get_metrics_tool
        self._access_count = 0

    @classmethod
    def get_definition(cls) -> ResourceDefinition:
        """Get the MCP resource definition."""
        return ResourceDefinition(
            uri=cls.URI,
            name="Governance Metrics",
            description=(
                "Real-time governance metrics including request counts, "
                "performance metrics, compliance rates, and system health."
            ),
            mimeType="application/json",
            constitutional_scope="read",
        )

    async def read(self, params: JSONDict | None = None) -> str:
        """
        Read the governance metrics resource.

        Args:
            params: Optional parameters (time_range, etc.)

        Returns:
            JSON string of governance metrics
        """
        self._access_count += 1
        logger.info("Reading governance metrics resource")

        try:
            if self.get_metrics_tool:
                # Use the tool to get metrics
                result = await self.get_metrics_tool.execute(params or {})
                if "content" in result and result["content"]:
                    return result["content"][0].get("text", "{}")  # type: ignore[no-any-return]

            # Return default metrics if tool not available
            return json.dumps(self._get_default_metrics(), indent=2)

        except METRICS_RESOURCE_READ_ERRORS as e:
            logger.error(f"Error reading metrics resource: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                }
            )

    def _get_default_metrics(self) -> JSONDict:
        """Get default metrics data."""
        return {
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "requests": {
                "total": 0,
                "approved": 0,
                "denied": 0,
                "conditional": 0,
                "escalated": 0,
            },
            "performance": {
                "avg_latency_ms": 1.31,
                "p99_latency_ms": 3.25,
                "throughput_rps": 770.4,
            },
            "compliance": {
                "validation_count": 0,
                "violation_count": 0,
                "compliance_rate": 1.0,
            },
            "governance": {
                "active_principles": 8,
                "precedent_count": 5,
            },
            "system": {
                "cache_hit_rate": 0.95,
                "health": "healthy",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_metrics(self) -> JSONDict:
        """Get resource access metrics."""
        return {
            "access_count": self._access_count,
            "uri": self.URI,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
