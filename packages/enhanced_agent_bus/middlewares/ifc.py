"""
Information Flow Control (IFC) Middleware for ACGS-2 Pipeline.

Enforces Fides-inspired information flow control policies based on
confidentiality and integrity labels.

Policies enforced:
1. No-write-down: SECRET data cannot flow to PUBLIC channels.
2. No-read-up: UNTRUSTED data cannot flow to TRUSTED contexts.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..ifc.labels import IFCLabel, IFCViolation
from ..pipeline.context import PipelineContext
from ..pipeline.exceptions import SecurityException
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig

logger = get_logger(__name__)


@dataclass
class IFCConfig(MiddlewareConfig):
    """Configuration for IFC enforcement middleware."""

    # Clearance level of the pipeline receiver (e.g. user, external API)
    # Default to PUBLIC/MEDIUM for safety.
    receiver_clearance: IFCLabel = field(default_factory=IFCLabel)

    # Whether to log violations without blocking (audit mode)
    audit_only: bool = False


class IFCMiddleware(BaseMiddleware):
    """Middleware that enforces Information Flow Control (IFC) policies.

    Gates message delivery based on the IFC label of the message and the
    clearance level of the receiver.
    """

    def __init__(
        self,
        config: IFCConfig | None = None,
    ):
        super().__init__(config or IFCConfig())
        self.ifc_config = config or IFCConfig()

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Enforce IFC policies on the current message.

        Args:
            context: Pipeline context containing the message and its IFC label.

        Returns:
            Context if policies are satisfied.

        Raises:
            SecurityException: If an IFC violation is detected and audit_only is False.
        """
        # Get message label from context
        message_label = context.ifc_label
        receiver_label = self.ifc_config.receiver_clearance

        # Check if flow is permitted
        if not message_label.can_flow_to(receiver_label):
            violation = IFCViolation(
                source_label=message_label,
                target_label=receiver_label,
                policy="IFC Enforcement",
                detail=f"Message {context.message.message_id} violated flow policy",
            )

            logger.warning(
                "IFC violation detected",
                extra={
                    "trace_id": context.trace_id,
                    "violation": violation.to_dict(),
                    "audit_only": self.ifc_config.audit_only,
                },
            )

            context.add_violation("ifc", violation.to_dict())

            if not self.ifc_config.audit_only:
                if self.config.fail_closed:
                    raise SecurityException(
                        message="Information Flow Control policy violation",
                        detection_method="IFCMiddleware",
                        details=violation.to_dict(),
                    )

        return await self._call_next(context)
