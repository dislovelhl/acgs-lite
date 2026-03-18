"""
Runtime Safety Guardrails Orchestrator.

Coordinates all guardrail layers in the OWASP-compliant security pipeline.
Implements 6-layer protection with fail-closed security.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .agent_engine import AgentEngine, AgentEngineConfig
from .audit_log import AuditLog, AuditLogConfig
from .base import GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .input_sanitizer import InputSanitizer, InputSanitizerConfig
from .models import GuardrailResult, Violation
from .output_verifier import OutputVerifier, OutputVerifierConfig
from .rate_limiter import RateLimiter, RateLimiterConfig
from .sandbox import SandboxConfig, ToolRunnerSandbox

logger = get_logger(__name__)


@dataclass
class RuntimeSafetyGuardrailsConfig:
    """Configuration for the complete runtime safety guardrails system."""

    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)
    input_sanitizer: InputSanitizerConfig = field(default_factory=InputSanitizerConfig)
    agent_engine: AgentEngineConfig = field(default_factory=AgentEngineConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    output_verifier: OutputVerifierConfig = field(default_factory=OutputVerifierConfig)
    audit_log: AuditLogConfig = field(default_factory=AuditLogConfig)

    strict_mode: bool = False
    fail_closed: bool = True  # Block on any error
    timeout_ms: int = 15000  # Total timeout for all layers


class RuntimeSafetyGuardrails:
    """
    OWASP-compliant Runtime Safety Guardrails System.

    Implements 6-layer security architecture for comprehensive protection:
    1. Rate Limiter - OWASP DoS protection and abuse prevention
    2. Input Sanitizer - Clean and validate incoming requests
    3. Agent Engine - Constitutional governance validation
    4. Tool Runner Sandbox - Isolated execution environment
    5. Output Verifier - Post-execution content validation
    6. Audit Log - Immutable compliance trail

    Features OWASP Top 10 protection, rate limiting, comprehensive injection detection,
    and multi-layer validation with fail-closed security.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, config: RuntimeSafetyGuardrailsConfig | None = None):
        self.config = config or RuntimeSafetyGuardrailsConfig()

        # Initialize guardrail layers (OWASP ordered)
        self.layers: dict[GuardrailLayer, GuardrailComponent] = {
            GuardrailLayer.RATE_LIMITER: RateLimiter(self.config.rate_limiter),
            GuardrailLayer.INPUT_SANITIZER: InputSanitizer(self.config.input_sanitizer),
            GuardrailLayer.AGENT_ENGINE: AgentEngine(self.config.agent_engine),
            GuardrailLayer.TOOL_RUNNER_SANDBOX: ToolRunnerSandbox(self.config.sandbox),
            GuardrailLayer.OUTPUT_VERIFIER: OutputVerifier(self.config.output_verifier),
            GuardrailLayer.AUDIT_LOG: AuditLog(self.config.audit_log),
        }

    def reset(self):
        """Reset all guardrail layers for testing."""
        for layer in self.layers.values():
            if hasattr(layer, "reset"):
                layer.reset()

    async def process_request(
        self, request_data: GuardrailInput, context: JSONDict | None = None
    ) -> JSONDict:
        """
        Process a request through all guardrail layers.

        Args:
            request_data: The request data to process
            context: Optional context information

        Returns:
            Dict containing processing results and final decision
        """
        context = context or {}
        trace_id = context.get("trace_id", self._generate_trace_id())
        context["trace_id"] = trace_id

        start_time = time.monotonic()
        layer_results: dict[str, JSONDict] = {}
        current_data: GuardrailInput = request_data
        final_allowed = True
        all_violations: list[Violation] = []

        try:
            # Process through each layer in order
            layer_order = [
                GuardrailLayer.RATE_LIMITER,
                GuardrailLayer.INPUT_SANITIZER,
                GuardrailLayer.AGENT_ENGINE,
                GuardrailLayer.TOOL_RUNNER_SANDBOX,
                GuardrailLayer.OUTPUT_VERIFIER,
            ]

            for layer_type in layer_order:
                if not self.layers[layer_type].config.enabled:
                    continue

                layer = self.layers[layer_type]

                # Create layer context
                layer_context = context.copy()
                layer_context["current_data"] = current_data

                # Process through layer
                try:
                    result = await asyncio.wait_for(
                        layer.process(current_data, layer_context),
                        timeout=self.config.timeout_ms / 1000,
                    )
                except TimeoutError:
                    result = GuardrailResult(
                        action=SafetyAction.BLOCK,
                        allowed=False,
                        violations=[
                            Violation(
                                layer=layer_type,
                                violation_type="timeout",
                                severity=ViolationSeverity.CRITICAL,
                                message=f"Layer {layer_type.value} timed out",
                                trace_id=trace_id,
                            )
                        ],
                    )

                layer_results[layer_type.value] = result.to_dict()

                # Update current data if modified
                if result.modified_data is not None:
                    current_data = result.modified_data

                # Collect violations
                all_violations.extend(result.violations)

                # Check if we should continue
                if not result.allowed:
                    final_allowed = False
                    if self.config.fail_closed:
                        break  # Stop processing on first block

            # Always log to audit (final layer)
            audit_layer = self.layers[GuardrailLayer.AUDIT_LOG]
            audit_context = context.copy()
            audit_context.update(
                {
                    "action": SafetyAction.ALLOW if final_allowed else SafetyAction.BLOCK,
                    "allowed": final_allowed,
                    "violations": all_violations,
                    "processing_time_ms": (time.monotonic() - start_time) * 1000,
                }
            )

            await audit_layer.process(current_data, audit_context)

        except (TimeoutError, RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Guardrails processing error: {e}")
            final_allowed = False
            all_violations.append(
                Violation(
                    layer=GuardrailLayer.AUDIT_LOG,  # Generic error
                    violation_type="system_error",
                    severity=ViolationSeverity.CRITICAL,
                    message=f"Guardrails system error: {e!s}",
                    trace_id=trace_id,
                )
            )

        total_time = (time.monotonic() - start_time) * 1000

        return {
            "allowed": final_allowed,
            "final_data": current_data,
            "violations": [v.to_dict() for v in all_violations],
            "layer_results": layer_results,
            "trace_id": trace_id,
            "total_processing_time_ms": total_time,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def _generate_trace_id(self) -> str:
        """Generate a unique trace ID."""
        timestamp = datetime.now(UTC).isoformat()
        data = f"{timestamp}-{CONSTITUTIONAL_HASH}-{id(self)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    async def get_metrics(self) -> JSONDict:
        """Get comprehensive guardrails metrics."""
        metrics: JSONDict = {
            "system": {
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "layers_enabled": [
                    layer.value
                    for layer, component in self.layers.items()
                    if getattr(component.config, "enabled", True)
                ],
            }
        }

        # Collect metrics from each layer
        for layer_type, component in self.layers.items():
            try:
                layer_metrics = await component.get_metrics()
                metrics[layer_type.value] = layer_metrics
            except (RuntimeError, ValueError, TypeError, AttributeError) as e:
                logger.error(f"Error getting metrics for {layer_type.value}: {e}")
                metrics[layer_type.value] = {"error": str(e)}

        return metrics

    def get_layer(self, layer_type: GuardrailLayer) -> GuardrailComponent | None:
        """Get a specific guardrail layer component."""
        return self.layers.get(layer_type)
