"""FastAPI dependency providers for the ACGS-2 Enhanced Agent Bus API.

Constitutional Hash: cdd01ef066bc6cf2

Dependency providers read shared state from ``request.app.state`` which is
populated during the application lifespan startup phase.  Route handlers
use ``Depends()`` to declare their requirements, avoiding module-level
global state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from ..batch_processor import BatchMessageProcessor
    from ..message_processor import MessageProcessor
    from ..persistence.executor import DurableWorkflowExecutor


def get_workflow_executor(request: Request) -> DurableWorkflowExecutor:
    """Dependency provider for durable workflow executor."""
    executor = getattr(request.app.state, "workflow_executor", None)
    if not executor:
        raise HTTPException(status_code=503, detail="Durable Workflow Executor not initialized")
    return executor  # type: ignore[no-any-return]


def get_agent_bus(request: Request) -> MessageProcessor | dict:
    """Dependency provider for agent bus.

    Reads the bus instance from ``request.app.state`` and raises **503**
    when the bus has not been initialised during the lifespan startup phase.
    """
    bus = getattr(request.app.state, "agent_bus", None)
    if not bus:
        raise HTTPException(status_code=503, detail="Agent bus not initialized")
    return bus  # type: ignore[no-any-return]


def get_batch_processor(request: Request) -> BatchMessageProcessor:
    """Dependency provider for batch processor.

    Reads the processor from ``request.app.state`` and raises **503** when it
    has not been initialised during the lifespan startup phase.
    """
    processor = getattr(request.app.state, "batch_processor", None)
    if not processor:
        raise HTTPException(status_code=503, detail="Batch processor not initialized")
    return processor  # type: ignore[no-any-return]


__all__ = [
    "get_agent_bus",
    "get_batch_processor",
    "get_workflow_executor",
]
