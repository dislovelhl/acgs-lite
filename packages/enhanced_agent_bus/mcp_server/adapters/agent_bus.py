"""
EnhancedAgentBus Adapter for MCP Integration.

Bridges MCP tools/resources with the Enhanced Agent Bus.

Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_AGENT_BUS_ADAPTER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AgentBusAdapter:
    """
    Adapter for integrating MCP with EnhancedAgentBus.

    Provides a clean interface for MCP tools to interact with
    the agent bus governance system.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(
        self,
        agent_bus: object | None = None,
        mcp_agent_id: str = "mcp-server",
    ):
        """
        Initialize the agent bus adapter.

        Args:
            agent_bus: Reference to EnhancedAgentBus instance
            mcp_agent_id: Agent ID for the MCP server
        """
        self.agent_bus = agent_bus
        self.mcp_agent_id = mcp_agent_id
        self._request_count = 0
        self._connected = False

    async def connect(self) -> bool:
        """
        Establish connection to the agent bus.

        Returns:
            True if connection successful
        """
        if self.agent_bus is None:
            logger.warning("No agent bus instance provided, running in standalone mode")
            return False

        try:
            # Register MCP server as an agent using the agent bus API
            result = await self.agent_bus.register_agent(
                agent_id=self.mcp_agent_id,
                agent_type="mcp_server",
                capabilities=["governance", "validation", "audit"],
            )

            if result:
                self._connected = True
                logger.info(f"MCP adapter connected to agent bus as {self.mcp_agent_id}")
                return True
            else:
                logger.warning(f"Agent registration failed for {self.mcp_agent_id}")
                return False

        except _AGENT_BUS_ADAPTER_ERRORS as e:
            logger.error(f"Failed to connect to agent bus: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the agent bus."""
        if self.agent_bus and self._connected:
            try:
                await self.agent_bus.deregister_agent(self.mcp_agent_id)
                self._connected = False
                logger.info("MCP adapter disconnected from agent bus")
            except _AGENT_BUS_ADAPTER_ERRORS as e:
                logger.error(f"Error during disconnect: {e}")

    async def validate_action(
        self,
        action: str,
        context: JSONDict,
        strict_mode: bool = True,
    ) -> JSONDict:
        """
        Validate an action through the agent bus.

        Args:
            action: The action to validate
            context: Action context
            strict_mode: Whether to use strict validation

        Returns:
            Validation result dictionary
        """
        self._request_count += 1

        if not self._connected or self.agent_bus is None:
            # Return simulated validation for standalone mode
            return await self._validate_standalone(action, context, strict_mode)

        try:
            from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

            # Create governance request message
            message = AgentMessage(
                from_agent=self.mcp_agent_id,
                to_agent="constitutional_validator",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={
                    "action": action,
                    "context": context,
                    "strict_mode": strict_mode,
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                },
                priority=Priority.HIGH if strict_mode else Priority.MEDIUM,
            )

            # Send through agent bus
            response = await self.agent_bus.send_message(message)

            return self._parse_validation_response(response)

        except _AGENT_BUS_ADAPTER_ERRORS as e:
            logger.error(f"Agent bus validation error: {e}")
            if strict_mode:
                return self._build_fail_closed_validation_result(str(e))
            raise
        except Exception as e:
            logger.exception(f"Unexpected agent bus validation error: {e}")
            if strict_mode:
                return self._build_fail_closed_validation_result(str(e))
            raise

    async def _validate_standalone(
        self,
        action: str,
        context: JSONDict,
        strict_mode: bool,
    ) -> JSONDict:
        """Perform standalone validation without agent bus."""
        violations = []
        confidence = 1.0

        # Basic validation rules
        if context.get("data_sensitivity") in ["confidential", "restricted"]:
            if not context.get("consent_obtained"):
                violations.append(
                    {
                        "principle": "privacy",
                        "severity": "high",
                        "description": "Sensitive data access requires consent",
                    }
                )
                confidence -= 0.3

        high_risk_patterns = ["delete", "drop", "admin", "root", "exec"]
        if any(p in action.lower() for p in high_risk_patterns):
            if not context.get("authorization_verified"):
                violations.append(
                    {
                        "principle": "safety",
                        "severity": "high",
                        "description": "High-risk action requires authorization",
                    }
                )
                confidence -= 0.3

        return {
            "compliant": len(violations) == 0,
            "confidence": max(0.0, confidence),
            "violations": violations,
            "recommendations": [v["description"] for v in violations] if violations else [],
            "standalone_mode": True,
        }

    def _parse_validation_response(self, response: object) -> JSONDict:
        """Parse the agent bus response into validation result."""
        if hasattr(response, "content"):
            return response.content
        if isinstance(response, dict):
            return response
        return {
            "compliant": False,
            "confidence": 0.0,
            "violations": [
                {
                    "principle": "system",
                    "severity": "medium",
                    "description": "Unable to parse validation response",
                }
            ],
            "recommendations": [],
        }

    async def submit_governance_request(
        self,
        action: str,
        context: JSONDict,
        priority: str,
        requester_id: str,
        wait_for_approval: bool = True,
        timeout_seconds: int = 30,
    ) -> JSONDict:
        """
        Submit a governance request through the agent bus.

        Args:
            action: The action requiring governance
            context: Action context
            priority: Request priority
            requester_id: ID of the requester
            wait_for_approval: Whether to wait for approval
            timeout_seconds: Timeout for waiting

        Returns:
            Governance decision result
        """
        self._request_count += 1

        if not self._connected or self.agent_bus is None:
            # Simulate governance in standalone mode
            validation = await self._validate_standalone(action, context, True)
            return {
                "status": "approved" if validation["compliant"] else "denied",
                "validation_result": validation,
                "conditions": [],
                "standalone_mode": True,
            }

        try:
            from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

            priority_map = {
                "low": Priority.LOW,
                "medium": Priority.MEDIUM,
                "high": Priority.HIGH,
                "critical": Priority.CRITICAL,
            }

            message = AgentMessage(
                from_agent=self.mcp_agent_id,
                to_agent="governance_coordinator",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={
                    "action": action,
                    "context": context,
                    "requester_id": requester_id,
                    "wait_for_approval": wait_for_approval,
                    "timeout_seconds": timeout_seconds,
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                },
                priority=priority_map.get(priority, Priority.MEDIUM),
            )

            response = await self.agent_bus.send_message(message)

            if hasattr(response, "content"):
                return response.content
            return response

        except _AGENT_BUS_ADAPTER_ERRORS as e:
            logger.error(f"Governance request error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "validation_result": None,
                "conditions": [],
            }
        except Exception as e:
            logger.exception(f"Unexpected governance request error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "validation_result": None,
                "conditions": [],
            }

    def _build_fail_closed_validation_result(self, error_message: str) -> JSONDict:
        """Return the canonical fail-closed response for validation errors."""
        return {
            "compliant": False,
            "confidence": 0.0,
            "violations": [
                {
                    "principle": "system",
                    "severity": "high",
                    "description": f"Validation system error: {error_message}",
                }
            ],
            "recommendations": ["Retry validation when system recovers"],
            "fail_closed": True,
        }

    def get_metrics(self) -> JSONDict:
        """Get adapter metrics."""
        return {
            "request_count": self._request_count,
            "connected": self._connected,
            "agent_id": self.mcp_agent_id,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
