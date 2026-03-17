"""
Production Error Handler Middleware
Constitutional Hash: cdd01ef066bc6cf2

Provides a FastAPI middleware to catch unhandled exceptions,
log the full stack trace server-side, and return a sanitized
error message to the client in production environments.
"""

import os
import traceback
from collections.abc import Callable

from fastapi.responses import JSONResponse

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware:
    """
    Middleware to sanitize error responses in production.
    """

    def __init__(self, app, debug: bool | None = None):
        self.app = app
        if debug is None:
            env = os.environ.get(
                "AGENT_RUNTIME_ENVIRONMENT", os.environ.get("ENVIRONMENT", "production")
            ).lower()
            self.debug = env in ("development", "dev", "local", "test")
        else:
            self.debug = debug

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            # Log the full stack trace server-side securely
            error_msg = f"Unhandled exception processing {scope['method']} {scope['path']}"
            logger.error(f"{error_msg}: {exc}", exc_info=True)

            if self.debug:
                # In debug mode, return full details
                detail = {
                    "error": "Internal Server Error",
                    "message": str(exc),
                    "traceback": traceback.format_exc().splitlines(),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
            else:
                # In production, return a generic message — never leak internals
                detail = {
                    "error": "Internal Server Error",
                    "message": "An unexpected error occurred. Please try again or contact support.",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }

            response = JSONResponse(status_code=500, content=detail)

            # Send the response directly
            await response(scope, receive, send)
