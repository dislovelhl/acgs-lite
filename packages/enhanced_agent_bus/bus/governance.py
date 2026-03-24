"""
Adaptive governance integration for EnhancedAgentBus.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..utils import get_iso_timestamp

if TYPE_CHECKING:
    from enhanced_agent_bus.models import AgentMessage

    from ..components import GovernanceValidator

logger = get_logger(__name__)


class GovernanceIntegration:
    """
    Handles adaptive governance evaluation for message processing.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        governance: GovernanceValidator,
        get_registered_agents: Callable[[], list[str]],
        metrics: JSONDict,
    ) -> None:
        """
        Initialize governance integration.

        Args:
            governance: GovernanceValidator component.
            get_registered_agents: Callable to get registered agents list.
            metrics: Metrics dictionary reference.
        """
        self._governance = governance
        self._get_registered_agents = get_registered_agents
        self._metrics = metrics

    async def evaluate_with_adaptive_governance(self, msg: AgentMessage) -> tuple[bool, str]:
        """
        Evaluate message with adaptive governance.

        Args:
            msg: Message to evaluate.

        Returns:
            Tuple of (allowed: bool, reasoning: str).
        """
        context = {
            "active_agents": self._get_registered_agents(),
            "time": get_iso_timestamp(),
            "current_metrics": dict(self._metrics),
        }
        return await self._governance.evaluate_adaptive_governance(msg, context)

    def provide_feedback(self, msg: AgentMessage, success: bool) -> None:
        """
        Provide feedback to adaptive governance system.

        Args:
            msg: The processed message.
            success: Whether delivery was successful.
        """
        if self._governance:
            self._governance.provide_feedback(msg, success)
