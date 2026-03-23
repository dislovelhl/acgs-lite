from __future__ import annotations

"""ACGS-2 Enhanced Agent Bus API Application.

Constitutional Hash: cdd01ef066bc6cf2
"""

import os  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from importlib import import_module  # noqa: E402
from typing import Any  # noqa: E402

import pybreaker  # noqa: E402
from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.responses import ORJSONResponse  # noqa: E402

from enhanced_agent_bus.exceptions import (  # noqa: E402
    AgentBusError,
    AgentError,
    BusNotStartedError,
    BusOperationError,
    ConstitutionalError,
    MACIError,
    MessageError,
    MessageTimeoutError,
    OPAConnectionError,
    PolicyError,
)

from ..api_exceptions import (  # noqa: E402
    agent_bus_error_handler,
    agent_error_handler,
    bus_not_started_handler,
    bus_operation_error_handler,
    constitutional_error_handler,
    global_exception_handler,
    maci_error_handler,
    message_error_handler,
    message_timeout_handler,
    opa_connection_handler,
    policy_error_handler,
    rate_limit_exceeded_handler,
)
from ..batch_processor import BatchMessageProcessor  # noqa: E402
from ..message_processor import MessageProcessor  # noqa: E402
from ..persistence.executor import DurableWorkflowExecutor, WorkflowContext  # noqa: E402
from ..persistence.postgres_repository import PostgresWorkflowRepository  # noqa: E402
from ..persistence.repository import InMemoryWorkflowRepository  # noqa: E402
from .config import (  # noqa: E402
    API_VERSION,
    BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS,
    BATCH_PROCESSOR_MAX_CONCURRENCY,
    BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS,
    CIRCUIT_BREAKER_FAIL_MAX,
    CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS,
    DEFAULT_API_PORT,
    DEFAULT_WORKERS,
)
from .dependencies import get_agent_bus, get_batch_processor  # noqa: E402
from .middleware import (  # noqa: E402
    correlation_id_middleware,
    logger,
    setup_all_middleware,
)
from .rate_limiting import (  # noqa: E402
    RATE_LIMITING_AVAILABLE,
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
    limiter,
    require_rate_limiting_dependencies,
)
from .routes.agent_health import router as agent_health_router  # noqa: E402
from .routes.badge import router as badge_router  # noqa: E402
from .routes.batch import router as batch_router  # noqa: E402
from .routes.governance import router as governance_router  # noqa: E402
from .routes.health import router as health_router  # noqa: E402
from .routes.messages import router as messages_router  # noqa: E402
from .routes.policies import router as policies_router  # noqa: E402
from .routes.public_v1 import router as public_v1_router  # noqa: E402
from .routes.signup import router as signup_router  # noqa: E402
from .routes.stats import router as stats_router  # noqa: E402
from .routes.usage import router as usage_router  # noqa: E402
from .routes.widget_js import router as widget_js_router  # noqa: E402
from .routes.workflows import router as workflows_router  # noqa: E402
from .routes.z3 import router as z3_router  # noqa: E402

_API_APP_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


def _normalize_workflow_dsn(db_url: str) -> str:
    """Normalize workflow DB DSN for asyncpg pool compatibility."""
    if db_url.startswith("postgresql+asyncpg://"):
        return db_url.replace("postgresql+asyncpg://", "postgresql://")
    return db_url


def _load_visual_studio_router() -> APIRouter | None:
    """Load optional Visual Studio router when available."""
    try:
        module = import_module("..visual_studio.api", package=__package__)
    except ImportError:
        return None

    router = getattr(module, "router", None)
    return router if isinstance(router, APIRouter) else None


def _load_copilot_router() -> APIRouter | None:
    """Load optional Policy Copilot router when available."""
    try:
        module = import_module("..policy_copilot.api", package=__package__)
    except ImportError:
        return None

    router = getattr(module, "router", None)
    return router if isinstance(router, APIRouter) else None


def _load_sessions_module() -> Any | None:
    """Load optional sessions module when available."""
    try:
        return import_module("..routes.sessions", package=__package__)
    except ImportError:
        return None


visual_studio_router = _load_visual_studio_router()
copilot_router = _load_copilot_router()

# pybreaker is a required dependency — always available
CIRCUIT_BREAKER_AVAILABLE = True

# Global state
agent_bus: MessageProcessor | dict | None = None
batch_processor: BatchMessageProcessor | None = None
message_circuit_breaker: pybreaker.CircuitBreaker | None = None
workflow_executor: DurableWorkflowExecutor | None = None
workflow_repository: PostgresWorkflowRepository | None = None


_CORE_ROUTERS: tuple[APIRouter, ...] = (
    health_router,
    agent_health_router,
    messages_router,
    batch_router,
    policies_router,
    governance_router,
    public_v1_router,
    badge_router,
    signup_router,
    stats_router,
    usage_router,
    widget_js_router,
    workflows_router,
    z3_router,
)


def _register_builtin_workflows(executor: DurableWorkflowExecutor) -> DurableWorkflowExecutor:
    """Register stable built-in workflows required by the HTTP API."""

    @executor.workflow("builtin.echo")
    async def builtin_echo_workflow(ctx: WorkflowContext) -> dict[str, Any]:
        payload = ctx.input or {}
        return {
            "echo": payload,
            "workflow_id": ctx.workflow_id,
            "tenant_id": ctx.tenant_id,
        }

    return executor


def _is_development_like_environment() -> bool:
    """Return whether current environment is development-like."""
    environment = os.environ.get("ENVIRONMENT", "").lower()
    return environment in ("development", "dev", "test", "testing", "ci")


def _initialize_agent_bus_state() -> MessageProcessor | dict:
    """Initialize primary message processor, with mock fallback in development."""
    logger.info("Initializing Enhanced Agent Bus Message Processor...")
    try:
        bus = MessageProcessor()
        logger.info("Enhanced Agent Bus initialized successfully")
        return bus
    except _API_APP_OPERATION_ERRORS as e:
        logger.error(f"Failed to initialize agent bus: {e}")
        if _is_development_like_environment():
            environment = os.environ.get("ENVIRONMENT", "").lower()
            logger.warning(
                f"MessageProcessor not available, using mock mode (ENVIRONMENT={environment})",
            )
            return {"status": "mock_initialized", "mode": "development"}
        raise


async def _initialize_workflow_components(
    app: FastAPI,
) -> tuple[DurableWorkflowExecutor | None, PostgresWorkflowRepository | None]:
    """Initialize durable workflow repository and executor."""
    logger.info("Initializing Durable Workflow Executor...")
    try:
        db_url = os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
        )
        normalized_dsn = _normalize_workflow_dsn(db_url)

        repository = PostgresWorkflowRepository(dsn=normalized_dsn)
        await repository.initialize()
        executor = _register_builtin_workflows(DurableWorkflowExecutor(repository=repository))
        app.state.workflow_executor = executor
        logger.info("Durable Workflow Executor initialized successfully")
        return executor, repository
    except ImportError:
        if _is_development_like_environment():
            logger.warning(
                "asyncpg not installed, using in-memory Workflow Executor in development"
            )
            repository = InMemoryWorkflowRepository()
            executor = _register_builtin_workflows(DurableWorkflowExecutor(repository=repository))
            app.state.workflow_executor = executor
            return executor, None
        logger.warning("asyncpg not installed, skipping Workflow Executor initialization")
    except Exception as e:
        if _is_development_like_environment():
            logger.warning(
                "Workflow repository unavailable, using in-memory Workflow Executor in "
                f"development: {e}"
            )
            repository = InMemoryWorkflowRepository()
            executor = _register_builtin_workflows(DurableWorkflowExecutor(repository=repository))
            app.state.workflow_executor = executor
            return executor, None
        logger.error(f"Failed to initialize Durable Workflow Executor: {e}")

    return None, None


def _initialize_batch_processor_state(
    message_processor: MessageProcessor | dict,
) -> BatchMessageProcessor | None:
    """Initialize batch message processor with defensive error handling."""
    logger.info("Initializing Batch Message Processor...")
    try:
        processor = BatchMessageProcessor(
            message_processor=message_processor,
            max_concurrency=BATCH_PROCESSOR_MAX_CONCURRENCY,
            enable_deduplication=True,
            cache_results=True,
            item_timeout=BATCH_PROCESSOR_ITEM_TIMEOUT_SECONDS,
            slow_item_threshold=BATCH_PROCESSOR_SLOW_ITEM_THRESHOLD_SECONDS,
        )
        logger.info("Batch Message Processor initialized successfully")
        return processor
    except _API_APP_OPERATION_ERRORS as e:
        logger.warning(f"BatchMessageProcessor not available: {e}")
        return None


async def _initialize_session_manager_if_available() -> None:
    """Initialize session manager when router dependency is installed."""
    sessions_module = _load_sessions_module()
    if sessions_module is None:
        logger.debug("Session Governance API router not available")
        return

    init_session_manager = getattr(sessions_module, "init_session_manager", None)
    if init_session_manager is None:
        logger.debug("Session Governance API router not available")
        return

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    if await init_session_manager(redis_url=redis_url):
        logger.info(f"Session context manager connected to Redis at {redis_url}")
    else:
        logger.warning("Session context manager failed to connect to Redis")


async def _stop_cache_warmer_if_running() -> None:
    """Stop cache warmer on shutdown when available and active."""
    try:
        from .. import CACHE_WARMING_AVAILABLE, get_cache_warmer

        if (
            CACHE_WARMING_AVAILABLE
            and get_cache_warmer is not None
            and (warmer := get_cache_warmer()).is_warming
        ):
            logger.info("Cancelling ongoing cache warming...")
            warmer.cancel()
    except _API_APP_OPERATION_ERRORS as e:
        logger.error(f"Failed to stop cache warmer: {e}")


async def _shutdown_session_manager_if_available() -> None:
    """Shutdown session manager when dependency is installed."""
    sessions_module = _load_sessions_module()
    if sessions_module is None:
        logger.debug("Session Governance API router not available on shutdown")
        return

    shutdown_session_manager = getattr(sessions_module, "shutdown_session_manager", None)
    if shutdown_session_manager is None:
        logger.debug("Session Governance API router not available on shutdown")
        return

    try:
        await shutdown_session_manager()
        logger.info("Session context manager disconnected")
    except ImportError:
        logger.debug("Session Governance API router not available on shutdown")


async def _close_workflow_repository_if_available(
    repository: PostgresWorkflowRepository | None,
) -> None:
    """Close workflow repository during shutdown when initialized."""
    try:
        if repository:
            await repository.close()
            logger.info("Workflow Repository closed")
    except Exception as e:
        logger.error(f"Error closing Workflow Repository: {e}")


def _bind_runtime_state(app: FastAPI, *, bus: MessageProcessor | dict) -> None:
    """Bind initialized runtime dependencies onto FastAPI state."""
    global agent_bus, batch_processor, message_circuit_breaker

    agent_bus = bus
    app.state.agent_bus = bus

    batch_processor = _initialize_batch_processor_state(bus)
    app.state.batch_processor = batch_processor

    message_circuit_breaker = pybreaker.CircuitBreaker(
        fail_max=CIRCUIT_BREAKER_FAIL_MAX,
        reset_timeout=CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS,
        name="message_processing",
    )
    app.state.message_circuit_breaker = message_circuit_breaker
    logger.info("Circuit breaker enabled for message processing")


async def _startup_runtime(app: FastAPI) -> None:
    """Initialize runtime state required during application startup."""
    global workflow_executor, workflow_repository

    bus = _initialize_agent_bus_state()
    _bind_runtime_state(app, bus=bus)
    workflow_executor, workflow_repository = await _initialize_workflow_components(app)
    await _initialize_session_manager_if_available()


async def _shutdown_runtime() -> None:
    """Shutdown runtime state in the inverse order of startup."""
    await _stop_cache_warmer_if_running()
    await _shutdown_session_manager_if_available()
    await _close_workflow_repository_if_available(workflow_repository)
    logger.info("Enhanced Agent Bus stopped")


def _configure_application_state(application: FastAPI) -> None:
    """Initialize non-runtime FastAPI application state."""
    application.state.limiter = limiter
    application.state.failed_tasks = []


def _register_core_routers(application: FastAPI) -> None:
    """Register the stable built-in router set."""
    for router in _CORE_ROUTERS:
        application.include_router(router)


def _register_feature_routers(application: FastAPI) -> None:
    """Register optional feature routers when present."""
    if visual_studio_router is not None:
        application.include_router(visual_studio_router)
        logger.info("Visual Studio API router registered")

    if copilot_router is not None:
        application.include_router(copilot_router)
        logger.info("Policy Copilot API router registered")

    _register_optional_routers(application)


def _configure_application(application: FastAPI) -> FastAPI:
    """Apply state, middleware, exception handlers, and routers to the app."""
    _configure_application_state(application)
    setup_all_middleware(application)
    _register_exception_handlers(application)
    application.middleware("http")(correlation_id_middleware)
    application.exception_handler(Exception)(global_exception_handler)
    _register_core_routers(application)
    _register_feature_routers(application)
    return application


@asynccontextmanager
async def _lifespan_context(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global workflow_executor, workflow_repository

    await _startup_runtime(app)

    yield

    await _shutdown_runtime()


def _register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers."""
    rate_limit_handler = (
        _rate_limit_exceeded_handler if RATE_LIMITING_AVAILABLE else rate_limit_exceeded_handler
    )
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    handlers = [
        (MessageTimeoutError, message_timeout_handler),
        (BusNotStartedError, bus_not_started_handler),
        (OPAConnectionError, opa_connection_handler),
        (ConstitutionalError, constitutional_error_handler),
        (MACIError, maci_error_handler),
        (PolicyError, policy_error_handler),
        (AgentError, agent_error_handler),
        (MessageError, message_error_handler),
        (BusOperationError, bus_operation_error_handler),
        (AgentBusError, agent_bus_error_handler),
    ]

    for exc_class, handler in handlers:
        app.add_exception_handler(exc_class, handler)  # type: ignore[arg-type]

    if RATE_LIMITING_AVAILABLE:
        logger.info("Rate limiting enabled: 60/minute per client")
    else:
        logger.info("Rate limiting not available (slowapi not installed)")


def _register_optional_routers(application: FastAPI) -> None:
    """Register optional routers that may not be available."""
    try:
        from ..constitutional.review_api import router as constitutional_review_router

        application.include_router(constitutional_review_router)
        logger.info("Constitutional Review API router registered")
    except ImportError:
        logger.debug("Constitutional Review API router not available")

    try:
        from ..circuit_breaker import create_circuit_health_router

        if circuit_health_router := create_circuit_health_router():
            application.include_router(circuit_health_router)
            logger.info("Circuit Breaker Health router registered")
    except ImportError:
        logger.debug("Circuit Breaker Health router not available")

    sessions_module = _load_sessions_module()
    sessions_router = getattr(sessions_module, "router", None) if sessions_module else None
    if isinstance(sessions_router, APIRouter):
        application.include_router(sessions_router)
        logger.info("Session Governance API router registered")
    else:
        logger.debug("Session Governance API router not available")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    require_rate_limiting_dependencies()
    application = FastAPI(
        title="ACGS-2 Enhanced Agent Bus API",
        description="API for the ACGS-2 Enhanced Agent Bus with Constitutional Compliance",
        version=API_VERSION,
        default_response_class=ORJSONResponse,
        lifespan=_lifespan_context,
    )
    return _configure_application(application)


# Create the default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",  # nosec B104 - Intentional for container deployment
        port=DEFAULT_API_PORT,
        reload=False,
        log_level="warning",
        workers=DEFAULT_WORKERS,
        loop="uvloop",
        http="httptools",
        access_log=False,
    )


__all__ = [
    "agent_bus",
    "agent_health_router",
    "app",
    "batch_processor",
    "create_app",
    "get_agent_bus",
    "get_batch_processor",
    "message_circuit_breaker",
]
