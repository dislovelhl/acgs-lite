"""
Base middleware class for ACGS-2 Message Processing Pipeline.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .context import PipelineContext
from .exceptions import TimeoutException


@dataclass
class MiddlewareConfig:
    """Base configuration for middleware.

    Attributes:
        enabled: Whether this middleware is active
        timeout_ms: Timeout for middleware execution
        fail_closed: Whether to fail on error (True) or continue (False)
        metrics_enabled: Whether to collect metrics for this middleware
    """

    enabled: bool = True
    timeout_ms: int = 1000
    fail_closed: bool = True
    metrics_enabled: bool = True


class BaseMiddleware(ABC):
    """Abstract base class for all pipeline middleware.

    Middleware form a chain where each middleware can:
    1. Process the context
    2. Modify the context
    3. Call the next middleware
    4. Short-circuit the pipeline by setting early_result

    Example:
        class MyMiddleware(BaseMiddleware):
            async def process(self, context: PipelineContext) -> PipelineContext:
                # Do work before next middleware
                context = await self._call_next(context)
                # Do work after next middleware
                return context
    """

    def __init__(self, config: MiddlewareConfig | None = None):
        self.config = config or MiddlewareConfig()
        self._next: BaseMiddleware | None = None
        self._name = self.__class__.__name__

    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process the context through this middleware.

        Implementations should:
        1. Perform their specific processing
        2. Call _call_next() to continue the chain (unless short-circuiting)
        3. Return the modified context

        Args:
            context: The pipeline context containing message and state

        Returns:
            Modified pipeline context

        Raises:
            PipelineException: If processing fails and fail_closed is True
        """
        ...

    async def _call_next(self, context: PipelineContext) -> PipelineContext:
        """Call the next middleware in the chain.

        Args:
            context: Current pipeline context

        Returns:
            Context from next middleware
        """
        if self._next and self._next.config.enabled:
            return await self._next.process(context)
        return context

    def set_next(self, middleware: "BaseMiddleware") -> "BaseMiddleware":
        """Set the next middleware in the chain.

        Args:
            middleware: The next middleware

        Returns:
            The middleware passed in (for chaining)
        """
        self._next = middleware
        return middleware

    async def execute_with_timeout(
        self,
        context: PipelineContext,
    ) -> PipelineContext:
        """Execute middleware with timeout protection.

        Args:
            context: Pipeline context

        Returns:
            Modified context

        Raises:
            TimeoutException: If execution exceeds timeout_ms
        """
        if not self.config.enabled:
            return await self._call_next(context)

        try:
            return await asyncio.wait_for(
                self.process(context),
                timeout=self.config.timeout_ms / 1000.0,
            )
        except TimeoutError as err:
            if self.config.fail_closed:
                raise TimeoutException(
                    message=f"{self._name} timed out after {self.config.timeout_ms}ms",
                    middleware=self._name,
                    timeout_ms=self.config.timeout_ms,
                ) from err
            # Continue to next middleware on timeout if not fail_closed
            return await self._call_next(context)

    def __repr__(self) -> str:
        return f"{self._name}(enabled={self.config.enabled}, timeout={self.config.timeout_ms}ms)"
