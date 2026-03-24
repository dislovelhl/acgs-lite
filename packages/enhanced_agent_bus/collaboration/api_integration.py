"""
FastAPI Integration for Collaboration Server.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.collaboration import (
    CollaborationConfig,
    CollaborationServer,
)
from enhanced_agent_bus.collaboration.models import (
    CollaborationError,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

_ALLOWED_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"})


class CollaborationAPI:
    """
    FastAPI integration for the collaboration server.

    Provides HTTP endpoints and WebSocket support for real-time collaboration.
    """

    def __init__(
        self,
        config: CollaborationConfig | None = None,
        redis_client: object | None = None,
        audit_client: object | None = None,
        secret_key: str | None = None,
    ):
        self.config = config or CollaborationConfig()
        self.redis = redis_client
        self.audit_client = audit_client
        resolved_secret_key = secret_key or os.getenv("COLLABORATION_SECRET_KEY", "")
        if not resolved_secret_key:
            raise ValueError("COLLABORATION_SECRET_KEY is required for collaboration API")
        self.secret_key = resolved_secret_key
        self.server: CollaborationServer | None = None
        self.security = HTTPBearer()

    async def initialize(self) -> None:
        """Initialize the collaboration server."""
        self.server = CollaborationServer(
            config=self.config,
            redis_client=self.redis,
            audit_client=self.audit_client,
            auth_validator=self._validate_token,
        )
        await self.server.initialize()
        logger.info("Collaboration API initialized")

    async def shutdown(self) -> None:
        """Shutdown the collaboration server."""
        if self.server:
            await self.server.shutdown()

    def _validate_token(self, token: str) -> JSONDict | None:
        """Validate JWT token and return user data."""
        import importlib

        try:
            jwt_module = importlib.import_module("jwt")
        except ModuleNotFoundError:
            logger.error("PyJWT is not installed")
            return None

        try:
            jwt_algorithm = os.environ.get("JWT_ALGORITHM", "RS256")
            if jwt_algorithm not in _ALLOWED_JWT_ALGORITHMS:
                raise ValueError(
                    f"Unsupported JWT_ALGORITHM={jwt_algorithm!r}. "
                    f"Allowed: {sorted(_ALLOWED_JWT_ALGORITHMS)}"
                )

            payload = jwt_module.decode(token, self.secret_key, algorithms=[jwt_algorithm])
            return {
                "user_id": payload.get("sub"),
                "tenant_id": payload.get("tenant_id"),
                "permissions": payload.get("permissions", []),
            }
        except jwt_module.ExpiredSignatureError:
            logger.warning("Collaboration token has expired")
            return None
        except jwt_module.InvalidTokenError as e:
            # Covers DecodeError, InvalidSignatureError, InvalidAlgorithmError, etc.
            logger.warning("Invalid collaboration token", extra={"error": str(e)})
            return None
        except Exception as e:
            # Unexpected programming error (e.g. wrong key type, broken secret config)
            logger.error(
                "Unexpected token validation error",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            return None

    async def get_current_user(
        self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())
    ) -> JSONDict:
        """Dependency to get current user from token."""
        user = self._validate_token(credentials.credentials)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        return user

    def _ensure_server_initialized(self) -> None:
        """Helper method to check server initialization."""
        if not self.server:
            raise HTTPException(status_code=503, detail="Server not initialized")

    async def _handle_health_check(self) -> JSONDict:
        """Health check endpoint handler."""
        self._ensure_server_initialized()
        return await self.server.health_check()

    async def _handle_list_sessions(self, user: dict) -> list[JSONDict]:
        """List all active collaboration sessions handler."""
        self._ensure_server_initialized()
        return await self.server.presence.get_all_sessions()

    async def _handle_get_session(self, document_id: str, user: dict) -> JSONDict:
        """Get session details for a document handler."""
        self._ensure_server_initialized()
        stats = await self.server.presence.get_session_stats(document_id)
        if not stats.get("exists"):
            raise HTTPException(status_code=404, detail="Session not found")
        return stats

    async def _handle_get_session_users(self, document_id: str, user: dict) -> list[JSONDict]:
        """Get active users in a session handler."""
        self._ensure_server_initialized()
        users = await self.server.presence.get_all_users(document_id)
        return [u.to_dict() for u in users]

    async def _handle_lock_document(self, document_id: str, user: dict) -> dict[str, bool]:
        """Lock a document for exclusive editing handler."""
        self._ensure_server_initialized()
        session = await self.server.presence.get_session(document_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            result = await self.server.permissions.lock_document(
                document_id, user["user_id"], session
            )
            return {"locked": result}
        except CollaborationError as e:
            raise HTTPException(status_code=403, detail=e.message) from e

    async def _handle_unlock_document(self, document_id: str, user: dict) -> dict[str, bool]:
        """Unlock a document handler."""
        self._ensure_server_initialized()
        session = await self.server.presence.get_session(document_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            result = await self.server.permissions.unlock_document(
                document_id, user["user_id"], session
            )
            return {"unlocked": result}
        except CollaborationError as e:
            raise HTTPException(status_code=403, detail=e.message) from e

    async def _handle_get_document_history(
        self, document_id: str, since_version: int, user: dict
    ) -> list[JSONDict]:
        """Get edit history for a document handler."""
        self._ensure_server_initialized()
        history = await self.server.sync.get_operation_history(document_id, since_version)
        return [op.to_dict() for op in history]

    def register_routes(self, app: FastAPI) -> None:
        """Register HTTP routes with FastAPI app using table-driven approach."""

        # Table-driven route registration
        routes = [
            {
                "method": "get",
                "path": "/collaboration/health",
                "handler": self._handle_health_check,
                "auth_required": False,
            },
            {
                "method": "get",
                "path": "/collaboration/sessions",
                "handler": self._handle_list_sessions,
                "auth_required": True,
            },
            {
                "method": "get",
                "path": "/collaboration/sessions/{document_id}",
                "handler": self._handle_get_session,
                "auth_required": True,
            },
            {
                "method": "get",
                "path": "/collaboration/sessions/{document_id}/users",
                "handler": self._handle_get_session_users,
                "auth_required": True,
            },
            {
                "method": "post",
                "path": "/collaboration/sessions/{document_id}/lock",
                "handler": self._handle_lock_document,
                "auth_required": True,
            },
            {
                "method": "post",
                "path": "/collaboration/sessions/{document_id}/unlock",
                "handler": self._handle_unlock_document,
                "auth_required": True,
            },
            {
                "method": "get",
                "path": "/collaboration/documents/{document_id}/history",
                "handler": self._handle_get_document_history,
                "auth_required": True,
                "extra_params": {"since_version": int},
            },
        ]

        self._register_route_table(app, routes)

    def _register_route_table(self, app: FastAPI, routes: list[dict]) -> None:
        """Register routes from table configuration."""
        for route_config in routes:
            self._register_single_route(app, route_config)

    def _register_single_route(self, app: FastAPI, config: dict) -> None:
        """Register a single route based on configuration."""
        method = config["method"]
        path = config["path"]
        handler = config["handler"]
        auth_required = config.get("auth_required", False)

        # Determine route type and create appropriate function
        route_func = self._create_route_function(path, handler, auth_required)

        # Register the route with FastAPI
        getattr(app, method)(path)(route_func)

    def _create_route_function(self, path: str, handler, auth_required: bool):
        """Create the appropriate route function based on path and auth requirements."""
        if self._is_history_endpoint(path):
            return self._create_history_route(handler, auth_required)
        elif self._has_document_id(path):
            return self._create_document_route(handler, auth_required)
        else:
            return self._create_simple_route(handler, auth_required)

    def _is_history_endpoint(self, path: str) -> bool:
        """Check if path is the history endpoint."""
        return "document_id" in path and "history" in path

    def _has_document_id(self, path: str) -> bool:
        """Check if path contains document_id parameter."""
        return "document_id" in path

    def _create_history_route(self, handler, auth_required: bool):
        """Create route function for history endpoint."""
        if auth_required:

            async def route_func(
                document_id: str,
                since_version: int = 0,
                user: dict = Depends(self.get_current_user),
            ):
                return await handler(document_id, since_version, user)
        else:

            async def route_func(document_id: str, since_version: int = 0):
                return await handler(document_id, since_version)

        return route_func

    def _create_document_route(self, handler, auth_required: bool):
        """Create route function for document-based endpoints."""
        if auth_required:

            async def route_func(document_id: str, user: dict = Depends(self.get_current_user)):
                return await handler(document_id, user)
        else:

            async def route_func(document_id: str):
                return await handler(document_id)

        return route_func

    def _create_simple_route(self, handler, auth_required: bool):
        """Create route function for simple endpoints."""
        if auth_required:

            async def route_func(user: dict = Depends(self.get_current_user)):
                return await handler(user)
        else:

            async def route_func():
                return await handler()

        return route_func

    def _socket_app_is_mounted(self, app: FastAPI, path: str) -> bool:
        """Return True when *path* is already mounted on *app*."""
        routes = getattr(getattr(app, "router", None), "routes", None)
        if not isinstance(routes, list):
            return False
        return any(getattr(route, "path", None) == path for route in routes)

    def _mount_socket_app(self, app: FastAPI, path: str) -> None:
        """Mount the Socket.IO ASGI app when the collaboration server is ready."""
        if self.server is None or self._socket_app_is_mounted(app, path):
            return
        app.mount(path, self.server.get_asgi_app())

    def mount_to_app(self, app: FastAPI, path: str = "/collaboration") -> None:
        """
        Mount the collaboration server to a FastAPI app.

        This mounts both the HTTP routes and the Socket.io ASGI app.
        """
        # Register HTTP routes
        self.register_routes(app)

        # Mount immediately when the caller pre-initialized the server.
        self._mount_socket_app(app, path)

        async def startup() -> None:
            if self.server is None:
                await self.initialize()
            self._mount_socket_app(app, path)

        async def shutdown() -> None:
            await self.shutdown()

        app.add_event_handler("startup", startup)
        app.add_event_handler("shutdown", shutdown)


# ============================================================================
# Standalone Application
# ============================================================================


def create_collaboration_app(
    config: CollaborationConfig | None = None,
    redis_client: object | None = None,
    audit_client: object | None = None,
    secret_key: str | None = None,
) -> FastAPI:
    """
    Create a standalone FastAPI app with collaboration support.

    Usage:
        app = create_collaboration_app()
        uvicorn.run(app, host="0.0.0.0", port=8001)
    """
    api = CollaborationAPI(
        config=config,
        redis_client=redis_client,
        audit_client=audit_client,
        secret_key=secret_key,
    )

    @asynccontextmanager
    async def app_lifespan(app: FastAPI):
        await api.initialize()
        api._mount_socket_app(app, "/collaboration")
        try:
            yield
        finally:
            await api.shutdown()

    app = FastAPI(
        title="ACGS-2 Collaboration Service",
        description="Real-time collaboration for policy and workflow editing",
        version="1.0.0",
        lifespan=app_lifespan,
    )

    api.register_routes(app)

    return app


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    app = create_collaboration_app()
    uvicorn.run(app, host="127.0.0.1", port=8001)
