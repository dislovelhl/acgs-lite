"""
Validate Constitutional Compliance MCP Tool.

This tool validates actions against ACGS-2 constitutional principles.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from ..adapters.agent_bus import AgentBusAdapter

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..protocol.types import ToolDefinition, ToolInputSchema

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of constitutional compliance validation."""

    compliant: bool
    confidence: float
    principles_checked: list[str]
    violations: list[JSONDict]
    recommendations: list[str]
    constitutional_hash: str
    validation_timestamp: str
    latency_ms: float

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "compliant": self.compliant,
            "confidence": self.confidence,
            "principles_checked": self.principles_checked,
            "violations": self.violations,
            "recommendations": self.recommendations,
            "constitutional_hash": self.constitutional_hash,
            "validation_timestamp": self.validation_timestamp,
            "latency_ms": self.latency_ms,
        }


class ValidateComplianceTool:
    """
    MCP Tool for validating constitutional compliance.

    Integrates with the ACGS-2 Enhanced Agent Bus to perform real-time
    constitutional validation of proposed actions.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    # Core constitutional principles
    PRINCIPLES: ClassVar[dict[str, str]] = {
        "beneficence": "Actions should benefit users and society",
        "non_maleficence": "Actions should not cause harm",
        "autonomy": "Respect user autonomy and informed consent",
        "justice": "Ensure fair and equitable treatment",
        "transparency": "Be transparent about AI decision-making",
        "accountability": "Maintain accountability for AI actions",
        "privacy": "Protect user privacy and data",
        "safety": "Prioritize safety in all operations",
    }

    def __init__(self, agent_bus_adapter: AgentBusAdapter | None = None):
        """
        Initialize the validation tool.

        Args:
            agent_bus_adapter: Optional adapter to the EnhancedAgentBus
        """
        self.agent_bus_adapter = agent_bus_adapter
        self._validation_count = 0
        self._violation_count = 0

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        """Get the MCP tool definition."""
        return ToolDefinition(
            name="validate_constitutional_compliance",
            description=(
                "Validate an action against ACGS-2 constitutional principles "
                f"(hash: {cls.CONSTITUTIONAL_HASH}). Returns compliance status, "
                "confidence score, any violations detected, and recommendations."
            ),
            inputSchema=ToolInputSchema(
                type="object",
                properties={
                    "action": {
                        "type": "string",
                        "description": "The action to validate (e.g., 'send_email', 'access_data')",
                    },
                    "context": {
                        "type": "object",
                        "description": "Context for the action including user info, data involved, etc.",
                        "properties": {
                            "user_id": {"type": "string"},
                            "resource_type": {"type": "string"},
                            "data_sensitivity": {
                                "type": "string",
                                "enum": ["public", "internal", "confidential", "restricted"],
                            },
                            "purpose": {"type": "string"},
                            "consent_obtained": {"type": "boolean"},
                        },
                    },
                    "strict_mode": {
                        "type": "boolean",
                        "description": "If true, fail-closed on any uncertainty",
                        "default": True,
                    },
                    "principles_to_check": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific principles to check (default: all)",
                    },
                },
                required=["action", "context"],
            ),
            constitutional_required=True,
        )

    async def execute(self, arguments: JSONDict) -> JSONDict:
        """
        Execute the constitutional compliance validation.

        Args:
            arguments: Tool arguments including action, context, and options

        Returns:
            Validation result as a dictionary
        """
        start_time = datetime.now(UTC)
        self._validation_count += 1

        action = arguments.get("action", "")
        context = arguments.get("context", {})
        strict_mode = arguments.get("strict_mode", True)
        principles_to_check = arguments.get(
            "principles_to_check",
            list(self.PRINCIPLES.keys()),
        )

        logger.info(f"Validating action '{action}' against {len(principles_to_check)} principles")

        try:
            # If we have an agent bus adapter, use it for real validation
            if self.agent_bus_adapter:
                result = await self._validate_via_agent_bus(
                    action, context, strict_mode, principles_to_check
                )
            else:
                # Fallback to local validation logic
                result = await self._validate_locally(
                    action, context, strict_mode, principles_to_check
                )

            # Calculate latency
            end_time = datetime.now(UTC)
            latency_ms = (end_time - start_time).total_seconds() * 1000

            validation_result = ValidationResult(
                compliant=result["compliant"],
                confidence=result["confidence"],
                principles_checked=principles_to_check,
                violations=result.get("violations", []),
                recommendations=result.get("recommendations", []),
                constitutional_hash=self.CONSTITUTIONAL_HASH,
                validation_timestamp=end_time.isoformat(),
                latency_ms=latency_ms,
            )

            if not validation_result.compliant:
                self._violation_count += 1

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(validation_result.to_dict(), indent=2),
                    }
                ],
                "isError": False,
            }

        except Exception as e:
            logger.error(f"Validation error: {e}")

            if strict_mode:
                # Fail closed - deny on error
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "compliant": False,
                                    "confidence": 0.0,
                                    "error": str(e),
                                    "fail_closed": True,
                                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                                },
                                indent=2,
                            ),
                        }
                    ],
                    "isError": True,
                }
            raise

    async def _validate_via_agent_bus(
        self,
        action: str,
        context: JSONDict,
        strict_mode: bool,
        principles: list[str],
    ) -> JSONDict:
        """Validate using the EnhancedAgentBus adapter."""
        return await self.agent_bus_adapter.validate_action(
            action=action,
            context=context,
            strict_mode=strict_mode,
        )

    async def _validate_locally(
        self,
        action: str,
        context: JSONDict,
        strict_mode: bool,
        principles: list[str],
    ) -> JSONDict:
        """
        Perform local validation when agent bus is not available.

        This provides basic rule-based validation.
        """
        violations = []
        recommendations = []
        confidence = 1.0

        # Check each principle
        for principle in principles:
            violation = self._check_principle(principle, action, context)
            if violation:
                violations.append(violation)
                confidence -= 0.1

        # Privacy checks
        if context.get("data_sensitivity") in ["confidential", "restricted"]:
            if not context.get("consent_obtained"):
                violations.append(
                    {
                        "principle": "privacy",
                        "severity": "high",
                        "description": "Sensitive data access without explicit consent",
                    }
                )
                recommendations.append(
                    "Obtain explicit user consent before accessing sensitive data"
                )

        # Safety checks for high-risk actions
        high_risk_actions = ["delete", "modify", "execute", "deploy", "admin"]
        if any(risk in action.lower() for risk in high_risk_actions):
            if not context.get("authorization_verified"):
                violations.append(
                    {
                        "principle": "safety",
                        "severity": "medium",
                        "description": "High-risk action without verified authorization",
                    }
                )
                recommendations.append(
                    "Implement additional authorization checks for high-risk actions"
                )

        # Transparency check
        if context.get("automated_decision") and not context.get("explanation_provided"):
            violations.append(
                {
                    "principle": "transparency",
                    "severity": "low",
                    "description": "Automated decision without explanation capability",
                }
            )
            recommendations.append("Provide explanations for automated decisions")

        # Calculate compliance
        compliant = len(violations) == 0
        if strict_mode and violations:
            confidence = 0.0

        return {
            "compliant": compliant,
            "confidence": max(0.0, min(1.0, confidence)),
            "violations": violations,
            "recommendations": recommendations,
        }

    def _check_principle(
        self,
        principle: str,
        action: str,
        context: JSONDict,
    ) -> JSONDict | None:
        """Check a specific constitutional principle."""
        # Harmful action patterns
        harmful_patterns = [
            "harm",
            "attack",
            "exploit",
            "abuse",
            "deceive",
            "manipulate",
            "discriminate",
            "violate",
        ]

        action_lower = action.lower()
        purpose = context.get("purpose", "").lower()

        if principle == "non_maleficence":
            for pattern in harmful_patterns:
                if pattern in action_lower or pattern in purpose:
                    return {
                        "principle": "non_maleficence",
                        "severity": "critical",
                        "description": f"Action may cause harm: detected '{pattern}'",
                    }

        if principle == "autonomy":
            if context.get("override_user_preference"):
                return {
                    "principle": "autonomy",
                    "severity": "medium",
                    "description": "Action overrides explicit user preference",
                }

        if principle == "justice":
            if context.get("discriminatory_criteria"):
                return {
                    "principle": "justice",
                    "severity": "high",
                    "description": "Action uses discriminatory criteria",
                }

        return None

    def get_metrics(self) -> JSONDict:
        """Get tool metrics."""
        return {
            "validation_count": self._validation_count,
            "violation_count": self._violation_count,
            "violation_rate": (
                self._violation_count / self._validation_count
                if self._validation_count > 0
                else 0.0
            ),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
