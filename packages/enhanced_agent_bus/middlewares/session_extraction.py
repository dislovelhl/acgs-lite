"""
ACGS-2 Session Extraction Middleware
Constitutional Hash: 608508a9bd224290

FastAPI middleware for automatic session context extraction and management.
Extracts session identification from requests and loads session governance configuration.
"""

from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

SESSION_LOAD_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)

# Constitutional compliance
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Header names for session identification
SESSION_ID_HEADER = "X-Session-ID"
TENANT_ID_HEADER = "X-Tenant-ID"
CONSTITUTIONAL_HASH_HEADER = "X-Constitutional-Hash"

# URL patterns that don't require session context
PUBLIC_PATHS = [
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/sessions",  # Session creation endpoint
]


def extract_session_id_from_request(request: Request) -> str | None:
    """Extract session ID from request.

    Constitutional Hash: 608508a9bd224290

    Attempts to extract session ID from:
    1. X-Session-ID header
    2. Path parameter (session_id)
    3. Query parameter (session_id)
    4. Cookie (acgs_session_id)

    Args:
        request: Starlette/FastAPI request object.

    Returns:
        Session ID if found, None otherwise.
    """
    # Try X-Session-ID header first (most common)
    _raw = request.headers.get(SESSION_ID_HEADER)
    if _raw:
        session_id: str = str(_raw)
        logger.debug(f"Session ID from header: {session_id[:8]}...")
        return session_id

    # Try path parameter (e.g., /sessions/{session_id}/...)
    if "session_id" in request.path_params:
        session_id = str(request.path_params["session_id"])
        logger.debug(f"Session ID from path: {session_id[:8]}...")
        return session_id

    # Try query parameter
    _raw = request.query_params.get("session_id")
    if _raw:
        session_id = str(_raw)
        logger.debug(f"Session ID from query: {session_id[:8]}...")
        return session_id

    # Try cookie
    _raw = request.cookies.get("acgs_session_id")
    if _raw:
        session_id = str(_raw)
        logger.debug(f"Session ID from cookie: {session_id[:8]}...")
        return session_id

    return None


def extract_tenant_id_from_request(request: Request) -> str | None:
    """Extract tenant ID from request.

    Args:
        request: Starlette/FastAPI request object.

    Returns:
        Tenant ID if found, None otherwise.
    """
    # Try header
    _raw = request.headers.get(TENANT_ID_HEADER)
    if _raw:
        return str(_raw)

    # Try from tenant context in state (set by TenantMiddleware)
    if hasattr(request.state, "tenant_context"):
        val = getattr(request.state.tenant_context, "tenant_id", None)
        return str(val) if val is not None else None

    # Try path parameter
    if "tenant_id" in request.path_params:
        return str(request.path_params["tenant_id"])

    # Try query parameter
    _raw = request.query_params.get("tenant_id")
    return str(_raw) if _raw is not None else None


class SessionContext:
    """Session context container for request processing.

    Constitutional Hash: 608508a9bd224290

    Contains session ID, governance configuration, and tenant isolation context.
    """

    def __init__(
        self,
        session_id: str,
        tenant_id: str,
        governance_config: dict | None = None,
        session_data: dict | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """Initialize session context.

        Args:
            session_id: Unique session identifier.
            tenant_id: Tenant ID for isolation.
            governance_config: Session governance configuration.
            session_data: Full session data.
            constitutional_hash: Constitutional compliance hash.
        """
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.governance_config = governance_config or {}
        self.session_data = session_data or {}
        self.constitutional_hash = constitutional_hash

    @property
    def risk_level(self) -> str:
        """Get session risk level."""
        return str(self.governance_config.get("risk_level", "low"))

    @property
    def automation_level(self) -> str:
        """Get session automation level."""
        return str(self.governance_config.get("automation_level", "full"))

    @property
    def enabled_policies(self) -> list[str]:
        """Get enabled policy IDs."""
        val = self.governance_config.get("enabled_policies", [])
        return list(val)

    @property
    def policy_id(self) -> str | None:
        """Get active policy ID."""
        val = self.governance_config.get("policy_id")
        return str(val) if val is not None else None

    @property
    def agent_type(self) -> str | None:
        """Get session agent type."""
        val = self.session_data.get("agent_type")
        return str(val) if val is not None else None

    @property
    def operation_type(self) -> str | None:
        """Get session operation type."""
        val = self.session_data.get("operation_type")
        return str(val) if val is not None else None

    def validate(self) -> bool:
        """Validate session context.

        Returns:
            True if context is valid.
        """
        return bool(
            self.session_id and self.tenant_id and self.constitutional_hash == CONSTITUTIONAL_HASH
        )

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "governance_config": self.governance_config,
            "risk_level": self.risk_level,
            "automation_level": self.automation_level,
            "enabled_policies": self.enabled_policies,
            "policy_id": self.policy_id,
            "agent_type": self.agent_type,
            "operation_type": self.operation_type,
            "constitutional_hash": self.constitutional_hash,
        }


class SessionExtractionMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for session context extraction.

    Constitutional Hash: 608508a9bd224290

    This middleware:
    1. Extracts session ID from incoming requests
    2. Loads session data from the session manager
    3. Validates tenant isolation
    4. Sets session context for the request duration
    5. Adds session headers to response

    Usage:
        from fastapi import FastAPI
        from middleware.session_extraction import SessionExtractionMiddleware

        app = FastAPI()
        app.add_middleware(SessionExtractionMiddleware, session_manager=manager)
    """

    def __init__(
        self,
        app: Callable,
        session_manager: Any | None = None,
        require_session: bool = False,
        public_paths: list[str] | None = None,
        session_header: str = SESSION_ID_HEADER,
        validate_tenant: bool = True,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: ASGI application.
            session_manager: Session manager instance for loading sessions.
            require_session: Whether to require session for non-public paths.
            public_paths: Paths that don't require session context.
            session_header: Header name for session ID.
            validate_tenant: Whether to validate tenant ID matches session.
        """
        super().__init__(app)
        self.session_manager = session_manager
        self.require_session = require_session
        self.public_paths = public_paths or PUBLIC_PATHS
        self.session_header = session_header
        self.validate_tenant = validate_tenant

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require session)."""
        return any(path.startswith(public_path) for public_path in self.public_paths)

    async def _load_session(self, session_id: str) -> dict | None:
        """Load session from session manager.

        Args:
            session_id: Session ID to load.

        Returns:
            Session data if found, None otherwise.
        """
        if not self.session_manager:
            logger.warning("No session manager configured")
            return None

        try:
            # Try async get method
            if hasattr(self.session_manager, "get_session"):
                result = await self.session_manager.get_session(session_id)
                return dict(result) if result is not None else None
            # Try sync get method
            elif hasattr(self.session_manager, "get"):
                result = self.session_manager.get(session_id)
                return dict(result) if result is not None else None
            else:
                logger.error("Session manager has no get method")
                return None
        except SESSION_LOAD_ERRORS as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process the request with session context.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response with session context headers.
        """
        path = request.url.path

        # Skip session context for public paths
        if self._is_public_path(path):
            return await call_next(request)

        # Extract session ID
        session_id = extract_session_id_from_request(request)

        if not session_id:
            if self.require_session:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "session_required",
                        "message": f"Missing {self.session_header} header",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
            # Continue without session context
            return await call_next(request)

        # Extract tenant ID
        tenant_id = extract_tenant_id_from_request(request)
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "tenant_required",
                    "message": f"Missing {TENANT_ID_HEADER} header",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Load session data
        session_data = await self._load_session(session_id)

        if not session_data:
            if self.require_session:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "session_not_found",
                        "message": f"Session {session_id} not found",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
            # Continue without session context
            return await call_next(request)

        # Validate tenant isolation
        if self.validate_tenant:
            session_tenant = session_data.get("tenant_id")
            if session_tenant and session_tenant != tenant_id:
                logger.warning(f"Tenant mismatch: request={tenant_id}, session={session_tenant}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "tenant_mismatch",
                        "message": "Session belongs to different tenant",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )

        # Validate constitutional hash if provided
        request_hash = request.headers.get(CONSTITUTIONAL_HASH_HEADER)
        if request_hash and request_hash != CONSTITUTIONAL_HASH:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "constitutional_hash_mismatch",
                    "message": "Invalid constitutional hash",
                    "expected": CONSTITUTIONAL_HASH,
                    "received": request_hash,
                },
            )

        # Create session context
        governance_config = session_data.get("governance_config", {})
        context = SessionContext(
            session_id=session_id,
            tenant_id=tenant_id,
            governance_config=governance_config,
            session_data=session_data,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Validate context
        if not context.validate():
            return JSONResponse(
                status_code=403,
                content={
                    "error": "invalid_session_context",
                    "message": "Session context validation failed",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Store context in request state for access in handlers
        request.state.session_context = context

        # Process request
        response = await call_next(request)

        # Add session context to response headers
        response.headers["X-Session-ID"] = session_id
        response.headers["X-Constitutional-Hash"] = CONSTITUTIONAL_HASH

        return response


class SessionContextDependency:
    """FastAPI dependency for session context.

    Constitutional Hash: 608508a9bd224290

    Usage:
        from fastapi import Depends
        from middleware.session_extraction import SessionContextDependency

        get_session = SessionContextDependency()

        @app.get("/items")
        async def list_items(ctx: SessionContext = Depends(get_session)):
            return await repository.list_items()
    """

    def __init__(
        self,
        required: bool = True,
        session_manager: Any | None = None,
    ) -> None:
        """Initialize the dependency.

        Args:
            required: Whether session context is required.
            session_manager: Session manager for loading sessions.
        """
        self.required = required
        self.session_manager = session_manager

    async def __call__(self, request: Request) -> SessionContext | None:
        """Get session context from request.

        Args:
            request: FastAPI request.

        Returns:
            SessionContext if available.

        Raises:
            HTTPException: If required and not available.
        """
        from fastapi import HTTPException

        # Try from request state (set by middleware)
        if hasattr(request.state, "session_context"):
            ctx = request.state.session_context
            return ctx if isinstance(ctx, SessionContext) else None

        # Try to extract directly
        session_id = extract_session_id_from_request(request)
        tenant_id = extract_tenant_id_from_request(request)

        if session_id and tenant_id:
            # Create minimal context without loading full session
            return SessionContext(
                session_id=session_id,
                tenant_id=tenant_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        if self.required:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "session_required",
                    "message": "Session context not available",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return None


class SessionGovernanceDependency:
    """FastAPI dependency for session governance configuration.

    Constitutional Hash: 608508a9bd224290

    Provides access to session governance configuration for policy enforcement.

    Usage:
        from fastapi import Depends
        from middleware.session_extraction import SessionGovernanceDependency

        get_governance = SessionGovernanceDependency()

        @app.post("/actions")
        async def perform_action(
            governance: dict = Depends(get_governance)
        ):
            if governance["automation_level"] == "none":
                return {"error": "Manual approval required"}
            # ... perform action
    """

    def __init__(self, session_manager: Any | None = None) -> None:
        """Initialize the dependency.

        Args:
            session_manager: Session manager for loading sessions.
        """
        self.session_manager = session_manager

    async def __call__(self, request: Request) -> dict:
        """Get governance configuration from request.

        Args:
            request: FastAPI request.

        Returns:
            Governance configuration dictionary.
        """
        # Default governance config
        default_config = {
            "risk_level": "low",
            "automation_level": "full",
            "enabled_policies": [],
            "policy_id": None,
            "policy_overrides": {},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        # Try from session context in request state
        if hasattr(request.state, "session_context"):
            ctx = request.state.session_context
            return {
                "risk_level": ctx.risk_level,
                "automation_level": ctx.automation_level,
                "enabled_policies": ctx.enabled_policies,
                "policy_id": ctx.policy_id,
                "policy_overrides": ctx.governance_config.get("policy_overrides", {}),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }

        return default_config


# Singleton dependency instances for convenience
get_session_context = SessionContextDependency(required=True)
get_optional_session_context = SessionContextDependency(required=False)
get_session_governance = SessionGovernanceDependency()


__all__ = [
    "CONSTITUTIONAL_HASH",
    "SESSION_ID_HEADER",
    "TENANT_ID_HEADER",
    "SessionContext",
    "SessionContextDependency",
    "SessionExtractionMiddleware",
    "SessionGovernanceDependency",
    "extract_session_id_from_request",
    "extract_tenant_id_from_request",
    "get_optional_session_context",
    "get_session_context",
    "get_session_governance",
]
