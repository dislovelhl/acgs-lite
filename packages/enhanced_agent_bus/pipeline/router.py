"""
Pipeline Message Router for ACGS-2.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from dataclasses import dataclass, field

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import AgentMessage
from enhanced_agent_bus.validators import ValidationResult

from .context import PipelineContext
from .middleware import BaseMiddleware

PIPELINE_PROCESSING_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)


@dataclass
class PipelineConfig:
    """Configuration for the pipeline router.

    Attributes:
        middlewares: List of middleware instances to execute
        max_concurrent: Maximum concurrent pipeline executions
        metrics_enabled: Whether to collect metrics
        version: Pipeline version for tracking
        use_default_middlewares: Whether to use default middleware chain if none provided
    """

    middlewares: list[BaseMiddleware] = field(default_factory=list)
    max_concurrent: int = 100
    metrics_enabled: bool = True
    version: str = "2.0.0"
    use_default_middlewares: bool = True

    def __post_init__(self):
        """Initialize default middlewares if none provided and flag is set."""
        if not self.middlewares and self.use_default_middlewares:
            self.middlewares = self._create_default_middlewares()

    def _create_default_middlewares(self) -> list[BaseMiddleware]:
        """Create the default middleware chain.

        Order: Session → Security → ToolPrivilege → TemporalPolicy

        Returns:
            List of middleware instances
        """
        # Import here to avoid circular imports
        from ..middlewares.security import SecurityMiddleware
        from ..middlewares.temporal_policy import TemporalPolicyMiddleware
        from ..middlewares.tool_privilege import ToolPrivilegeMiddleware

        return [
            SecurityMiddleware(),
            ToolPrivilegeMiddleware(),  # After security; before temporal policy
            TemporalPolicyMiddleware(),  # After tool privilege
        ]

    def validate(self) -> None:
        """Validate pipeline configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")

        if not self.middlewares:
            raise ValueError("At least one middleware is required")

        # Validate middleware chain
        for i, mw in enumerate(self.middlewares):
            if not isinstance(mw, BaseMiddleware):
                raise ValueError(f"Middleware at index {i} is not a BaseMiddleware")

    def build_chain(self) -> BaseMiddleware | None:
        """Build the middleware chain.

        Returns:
            First middleware in the chain, or None if no middlewares
        """
        if not self.middlewares:
            return None

        # Link middlewares in reverse order
        for i in range(len(self.middlewares) - 1, 0, -1):
            self.middlewares[i - 1].set_next(self.middlewares[i])

        return self.middlewares[0]


class PipelineMessageRouter:
    """Modern message router using middleware pipeline architecture.

    This router replaces the monolithic MessageProcessor with a composable
    pipeline of middleware components, each handling a specific concern.

    Example:
        config = PipelineConfig(
            middlewares=[
                SessionExtractionMiddleware(...),
                SecurityMiddleware(...),
                CacheMiddleware(...),
                VerificationMiddleware(...),
                StrategyMiddleware(...),
                MetricsMiddleware(...),
            ]
        )
        router = PipelineMessageRouter(config)
        result = await router.process(message)
    """

    def __init__(self, config: PipelineConfig | None = None):
        """Initialize the pipeline router.

        Args:
            config: Pipeline configuration (uses default if None)
        """
        if config is None:
            config = PipelineConfig()
        config.validate()
        self._config = config
        self._chain_head = config.build_chain()
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._metrics = {
            "processed": 0,
            "failed": 0,
            "total_latency_ms": 0.0,
        }

    async def process(self, message: AgentMessage) -> ValidationResult:
        """Process a message through the middleware pipeline.

        Args:
            message: The agent message to process

        Returns:
            ValidationResult with validation status and metadata

        Raises:
            PipelineException: If processing fails
        """
        async with self._semaphore:
            context = PipelineContext(message=message)

            try:
                if self._chain_head:
                    context = await self._chain_head.process(context)

                context.finalize()

                # Check for early result (short-circuit)
                if context.early_result:
                    self._metrics["processed"] += 1
                    return context.early_result

                # Return strategy result or validation result
                result = context.to_validation_result()
                self._metrics["processed"] += 1
                self._metrics["total_latency_ms"] += context.metrics.total_time_ms

                return result

            except PIPELINE_PROCESSING_ERRORS:
                self._metrics["failed"] += 1
                raise

    async def process_batch(
        self,
        messages: list[AgentMessage],
        continue_on_error: bool = True,
    ) -> list[ValidationResult]:
        """Process a batch of messages.

        Args:
            messages: List of messages to process
            continue_on_error: Whether to continue processing on individual errors

        Returns:
            List of validation results (same order as input)
        """
        tasks = [self.process(msg) for msg in messages]

        if continue_on_error:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Convert exceptions to failed validation results
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    processed_results.append(
                        ValidationResult(
                            is_valid=False,
                            errors=[str(result)],
                            metadata={"error_type": type(result).__name__},
                        )
                    )
                else:
                    processed_results.append(result)
            return processed_results
        else:
            return await asyncio.gather(*tasks)

    def get_metrics(self) -> JSONDict:
        """Get router metrics.

        Returns:
            Dictionary with processed count, failed count, avg latency
        """
        processed = self._metrics["processed"]
        return {
            "processed": processed,
            "failed": self._metrics["failed"],
            "avg_latency_ms": (
                self._metrics["total_latency_ms"] / processed if processed > 0 else 0.0
            ),
            "pipeline_version": self._config.version,
            "middleware_count": len(self._config.middlewares),
            "active_middlewares": sum(1 for mw in self._config.middlewares if mw.config.enabled),
        }

    def get_middleware_info(self) -> list[JSONDict]:
        """Get information about configured middlewares.

        Returns:
            List of middleware info dictionaries
        """
        return [
            {
                "name": mw.__class__.__name__,
                "enabled": mw.config.enabled,
                "timeout_ms": mw.config.timeout_ms,
                "fail_closed": mw.config.fail_closed,
            }
            for mw in self._config.middlewares
        ]
