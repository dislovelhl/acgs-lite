"""
Submit Governance Request MCP Tool.

Submits a governance request for constitutional validation and approval.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from ..adapters.agent_bus import AgentBusAdapter

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..protocol.types import ToolDefinition, ToolInputSchema

logger = get_logger(__name__)


class RequestStatus(Enum):
    """Governance request status."""

    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    DENIED = "denied"
    CONDITIONAL = "conditional"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


class RequestPriority(Enum):
    """Governance request priority."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class GovernanceRequest:
    """A governance request submission."""

    request_id: str
    action: str
    context: JSONDict
    priority: RequestPriority
    requester_id: str
    timestamp: str
    status: RequestStatus = RequestStatus.PENDING
    validation_result: JSONDict | None = None
    approval_chain: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    expiry: str | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "action": self.action,
            "context": self.context,
            "priority": self.priority.value,
            "requester_id": self.requester_id,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "validation_result": self.validation_result,
            "approval_chain": self.approval_chain,
            "conditions": self.conditions,
            "expiry": self.expiry,
        }


class SubmitGovernanceTool:
    """
    MCP Tool for submitting governance requests.

    Handles submission of actions for constitutional governance approval,
    including validation, approval workflow, and status tracking.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(
        self,
        agent_bus_adapter: AgentBusAdapter | None = None,
        auto_validate: bool = True,
    ):
        """
        Initialize the governance submission tool.

        Args:
            agent_bus_adapter: Optional adapter to the EnhancedAgentBus
            auto_validate: Whether to auto-validate before submission
        """
        self.agent_bus_adapter = agent_bus_adapter
        self.auto_validate = auto_validate
        self._pending_requests: dict[str, GovernanceRequest] = {}
        self._completed_requests: dict[str, GovernanceRequest] = {}
        self._request_count = 0

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        """Get the MCP tool definition."""
        return ToolDefinition(
            name="submit_governance_request",
            description=(
                "Submit an action for constitutional governance approval. "
                "The request goes through validation, approval workflow, "
                "and returns approval status with any conditions."
            ),
            inputSchema=ToolInputSchema(
                type="object",
                properties={
                    "action": {
                        "type": "string",
                        "description": "The action requiring governance approval",
                    },
                    "context": {
                        "type": "object",
                        "description": "Context for the action",
                        "properties": {
                            "user_id": {"type": "string"},
                            "resource_type": {"type": "string"},
                            "data_sensitivity": {
                                "type": "string",
                                "enum": ["public", "internal", "confidential", "restricted"],
                            },
                            "purpose": {"type": "string"},
                            "consent_obtained": {"type": "boolean"},
                            "impact_assessment": {"type": "object"},
                        },
                    },
                    "priority": {
                        "type": "string",
                        "description": "Request priority level",
                        "enum": ["low", "medium", "high", "critical"],
                        "default": "medium",
                    },
                    "requester_id": {
                        "type": "string",
                        "description": "ID of the requesting agent or user",
                    },
                    "wait_for_approval": {
                        "type": "boolean",
                        "description": "Wait for synchronous approval (vs async)",
                        "default": True,
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Timeout for waiting (if wait_for_approval=true)",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 300,
                    },
                    "auto_approve_if_compliant": {
                        "type": "boolean",
                        "description": "Auto-approve if validation passes",
                        "default": True,
                    },
                },
                required=["action", "context", "requester_id"],
            ),
            constitutional_required=True,
        )

    async def execute(self, arguments: JSONDict) -> JSONDict:
        """
        Execute the governance request submission.

        Args:
            arguments: Tool arguments

        Returns:
            Request status and result
        """
        self._request_count += 1

        action = arguments.get("action", "")
        context = arguments.get("context", {})
        priority_str = arguments.get("priority", "medium")
        requester_id = arguments.get("requester_id", "unknown")
        wait_for_approval = arguments.get("wait_for_approval", True)
        timeout_seconds = arguments.get("timeout_seconds", 30)
        auto_approve = arguments.get("auto_approve_if_compliant", True)

        logger.info(f"Governance request from {requester_id}: {action} (priority: {priority_str})")

        try:
            # Create request
            request = GovernanceRequest(
                request_id=f"GOV-{uuid.uuid4().hex[:8].upper()}",
                action=action,
                context=context,
                priority=RequestPriority(priority_str),
                requester_id=requester_id,
                timestamp=datetime.now(UTC).isoformat(),
            )

            self._pending_requests[request.request_id] = request

            # If we have an agent bus adapter, use it
            if self.agent_bus_adapter:
                result = await self._submit_via_agent_bus(
                    request, wait_for_approval, timeout_seconds
                )
            else:
                result = await self._submit_locally(request, auto_approve)

            # Update request status
            request.status = RequestStatus(result["status"])
            request.validation_result = result.get("validation_result")
            request.conditions = result.get("conditions", [])

            # Move to completed if not pending
            if request.status != RequestStatus.PENDING:
                self._completed_requests[request.request_id] = request
                del self._pending_requests[request.request_id]

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "request": request.to_dict(),
                                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                                "timestamp": datetime.now(UTC).isoformat(),
                            },
                            indent=2,
                        ),
                    }
                ],
                "isError": request.status == RequestStatus.DENIED,
            }

        except Exception as e:
            logger.error(f"Governance submission error: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "error": str(e),
                                "status": "error",
                                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                            },
                            indent=2,
                        ),
                    }
                ],
                "isError": True,
            }

    async def _submit_via_agent_bus(
        self,
        request: GovernanceRequest,
        wait_for_approval: bool,
        timeout_seconds: int,
    ) -> JSONDict:
        """Submit request via the EnhancedAgentBus."""
        return await self.agent_bus_adapter.submit_governance_request(
            action=request.action,
            context=request.context,
            priority=request.priority.value,
            requester_id=request.requester_id,
            wait_for_approval=wait_for_approval,
            timeout_seconds=timeout_seconds,
        )

    async def _submit_locally(
        self,
        request: GovernanceRequest,
        auto_approve: bool,
    ) -> JSONDict:
        """
        Process request locally when agent bus is not available.

        This provides basic rule-based approval.
        """
        request.status = RequestStatus.PROCESSING

        # Perform validation
        validation_result = await self._validate_request(request)

        if validation_result["compliant"]:
            if auto_approve:
                return {
                    "status": "approved",
                    "validation_result": validation_result,
                    "conditions": [],
                    "reasoning": "Auto-approved: passed constitutional validation",
                }
            else:
                return {
                    "status": "pending",
                    "validation_result": validation_result,
                    "conditions": [],
                    "reasoning": "Validation passed, awaiting manual approval",
                }
        else:
            # Check if conditional approval is possible
            if validation_result.get("confidence", 0) >= 0.7:
                conditions = self._generate_conditions(validation_result)
                return {
                    "status": "conditional",
                    "validation_result": validation_result,
                    "conditions": conditions,
                    "reasoning": "Conditionally approved with remediation requirements",
                }
            else:
                return {
                    "status": "denied",
                    "validation_result": validation_result,
                    "conditions": [],
                    "reasoning": f"Denied: {', '.join([v['description'] for v in validation_result.get('violations', [])])}",
                }

    async def _validate_request(
        self,
        request: GovernanceRequest,
    ) -> JSONDict:
        """Validate the governance request."""
        violations = []
        confidence = 1.0

        # Check for sensitive data access
        if request.context.get("data_sensitivity") in ["confidential", "restricted"]:
            if not request.context.get("consent_obtained"):
                violations.append(
                    {
                        "principle": "privacy",
                        "severity": "high",
                        "description": "Accessing sensitive data without consent",
                    }
                )
                confidence -= 0.3

        # Check for high-risk actions
        high_risk_keywords = ["delete", "drop", "admin", "root", "system"]
        if any(kw in request.action.lower() for kw in high_risk_keywords):
            if request.priority != RequestPriority.CRITICAL:
                violations.append(
                    {
                        "principle": "safety",
                        "severity": "medium",
                        "description": "High-risk action requires critical priority",
                    }
                )
                confidence -= 0.2

        # Check for impact assessment
        if request.priority in [RequestPriority.HIGH, RequestPriority.CRITICAL]:
            if not request.context.get("impact_assessment"):
                violations.append(
                    {
                        "principle": "accountability",
                        "severity": "low",
                        "description": "High-priority request without impact assessment",
                    }
                )
                confidence -= 0.1

        return {
            "compliant": len(violations) == 0,
            "confidence": max(0.0, confidence),
            "violations": violations,
            "principles_checked": ["privacy", "safety", "accountability"],
        }

    def _generate_conditions(
        self,
        validation_result: JSONDict,
    ) -> list[str]:
        """Generate conditions for conditional approval."""
        conditions = []

        for violation in validation_result.get("violations", []):
            if violation["severity"] == "high":
                conditions.append(
                    f"Must address {violation['principle']} concern: {violation['description']}"
                )
            elif violation["severity"] == "medium":
                conditions.append(f"Should implement mitigation for: {violation['description']}")

        return conditions

    def get_request_status(self, request_id: str) -> JSONDict | None:
        """Get the status of a governance request."""
        if request_id in self._pending_requests:
            return self._pending_requests[request_id].to_dict()
        if request_id in self._completed_requests:
            return self._completed_requests[request_id].to_dict()
        return None

    def get_metrics(self) -> JSONDict:
        """Get tool metrics."""
        all_requests = list(self._completed_requests.values())
        status_counts: dict[str, int] = {}
        for req in all_requests:
            status = req.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "request_count": self._request_count,
            "pending_count": len(self._pending_requests),
            "completed_count": len(self._completed_requests),
            "status_distribution": status_counts,
            "approval_rate": (
                status_counts.get("approved", 0) / len(all_requests) if all_requests else 0.0
            ),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
