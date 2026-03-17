"""
Tool Runner Sandbox Guardrail Component.

Layer 3 of OWASP guardrails: isolated execution environment for tool calls
and external integrations using Docker or Firecracker.

Constitutional Hash: cdd01ef066bc6cf2
"""

import time
from dataclasses import dataclass, field

from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .models import GuardrailResult, Violation
from .sandbox_providers import (
    DockerSandboxProvider,
    FirecrackerSandboxProvider,
    MockSandboxProvider,
    SandboxExecutionRequest,
    SandboxProvider,
    SandboxProviderType,
    SandboxResourceLimits,
    SandboxSecurityConfig,
)

logger = get_logger(__name__)
SANDBOX_INITIALIZATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    ConnectionError,
)


@dataclass
class SandboxConfig:
    """Configuration for tool runner sandbox."""

    enabled: bool = True
    use_firecracker: bool = False  # For production
    use_docker: bool = True  # For development
    timeout_ms: int = 10000
    memory_limit_mb: int = 512
    cpu_limit: float = 0.5
    network_isolation: bool = True
    provider_type: SandboxProviderType = SandboxProviderType.DOCKER
    security_config: SandboxSecurityConfig = field(default_factory=SandboxSecurityConfig)
    resource_limits: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)


class ToolRunnerSandbox(GuardrailComponent):
    """Tool Runner Sandbox: Layer 3 of OWASP guardrails.

    Isolated execution environment for tool calls and external integrations.
    Supports both Docker (development) and Firecracker (production) isolation.
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._provider: SandboxProvider | None = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the sandbox provider.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        try:
            # Select provider type based on configuration
            if self.config.use_firecracker:
                provider_type = SandboxProviderType.FIRECRACKER
            elif self.config.use_docker:
                provider_type = SandboxProviderType.DOCKER
            else:
                provider_type = SandboxProviderType.MOCK

            # Create provider based on type
            if provider_type == SandboxProviderType.DOCKER:
                self._provider = DockerSandboxProvider(
                    default_image="python:3.11-slim",
                    container_prefix="acgs2-guardrail",
                )
            elif provider_type == SandboxProviderType.FIRECRACKER:
                self._provider = FirecrackerSandboxProvider()
            else:
                self._provider = MockSandboxProvider()

            self._initialized = await self._provider.initialize()

            if not self._initialized:
                # Fall back to mock provider
                logger.warning(
                    f"Failed to initialize {provider_type} provider, falling back to mock"
                )
                self._provider = MockSandboxProvider()
                self._initialized = await self._provider.initialize()

            return self._initialized

        except SANDBOX_INITIALIZATION_ERRORS as e:
            logger.error(f"Failed to initialize sandbox: {e}")
            # Fall back to mock provider
            self._provider = MockSandboxProvider()
            self._initialized = await self._provider.initialize()
            return self._initialized

    async def cleanup(self) -> None:
        """Clean up sandbox resources."""
        if self._provider:
            await self._provider.cleanup()
            self._initialized = False

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.TOOL_RUNNER_SANDBOX

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Execute in sandboxed environment."""
        start_time = time.time()
        violations = []
        trace_id = context.get("trace_id", "")
        sandbox_result: JSONDict = {}

        try:
            if not self.config.enabled:
                return GuardrailResult(
                    action=SafetyAction.ALLOW,
                    allowed=True,
                    trace_id=trace_id,
                )

            # OPTIMIZATION: Only sandbox if specifically requested or if data appears to be an action  # noqa: E501
            should_sandbox = context.get("should_sandbox", False)
            if not should_sandbox and isinstance(data, dict):
                # Heuristic: check for keys indicating executable content
                sandbox_trigger_keys = {
                    "code",
                    "script",
                    "command",
                    "action_type",
                    "execute",
                    "eval",
                    "run",
                }
                should_sandbox = any(k in data for k in sandbox_trigger_keys)

            if not should_sandbox:
                return GuardrailResult(
                    action=SafetyAction.ALLOW,
                    allowed=True,
                    trace_id=trace_id,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            # Sandbox the execution
            sandbox_result = await self._execute_in_sandbox(data, context)

            if sandbox_result["success"]:
                action = SafetyAction.ALLOW
                allowed = True
            else:
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="sandbox_execution_failed",
                        severity=ViolationSeverity.HIGH,
                        message=f"Sandbox execution failed: {sandbox_result.get('error', 'Unknown error')}",  # noqa: E501
                        details=sandbox_result,
                        trace_id=trace_id,
                    )
                )
                action = SafetyAction.BLOCK
                allowed = False

        except (TimeoutError, RuntimeError, ValueError, TypeError) as e:
            logger.error(f"Sandbox error: {e}")
            violations.append(
                Violation(
                    layer=self.get_layer(),
                    violation_type="sandbox_error",
                    severity=ViolationSeverity.CRITICAL,
                    message=f"Sandbox execution error: {e!s}",
                    trace_id=trace_id,
                )
            )
            action = SafetyAction.BLOCK
            allowed = False

        processing_time = (time.time() - start_time) * 1000

        return GuardrailResult(
            action=action,
            allowed=allowed,
            violations=violations,
            modified_data=sandbox_result.get("output") if sandbox_result.get("success") else None,
            processing_time_ms=processing_time,
            trace_id=trace_id,
        )

    async def _execute_in_sandbox(self, data: GuardrailInput, context: JSONDict) -> JSONDict:
        """Execute code/data in sandboxed environment using configured provider.

        Args:
            data: Input data to process in sandbox
            context: Execution context including trace_id

        Returns:
            Dictionary with execution results
        """
        if not self._initialized:
            await self.initialize()

        if not self._provider:
            return {
                "success": False,
                "error": "No sandbox provider available",
                "output": None,
            }

        trace_id = context.get("trace_id", "")

        # Prepare resource limits from config
        resource_limits = SandboxResourceLimits(
            cpu_limit=self.config.cpu_limit,
            memory_limit_mb=self.config.memory_limit_mb,
            timeout_seconds=self.config.timeout_ms / 1000,
            network_disabled=self.config.network_isolation,
        )

        # Prepare security config
        security_config = self.config.security_config

        # Create execution request
        request = SandboxExecutionRequest(
            code="# Default execution - pass through data\noutput = data",
            data={"input": data} if not isinstance(data, dict) else data,
            context=context,
            trace_id=trace_id,
            resource_limits=resource_limits,
            security_config=security_config,
        )

        # Execute in sandbox
        result = await self._provider.execute(request)

        return result.to_dict()
