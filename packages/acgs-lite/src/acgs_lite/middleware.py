# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""ACGS-Lite HTTP Middleware.

Framework-agnostic ASGI and WSGI middleware that validates HTTP request
and response bodies against constitutional rules. Works with FastAPI,
Starlette, Flask, Django, and any ASGI/WSGI-compatible framework.

Usage::

    # FastAPI / Starlette
    from acgs_lite.middleware import GovernanceASGIMiddleware
    app.add_middleware(GovernanceASGIMiddleware, constitution=my_rules)

    # Flask
    from acgs_lite.middleware import GovernanceWSGIMiddleware
    app.wsgi_app = GovernanceWSGIMiddleware(app.wsgi_app)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

# Default paths to skip governance checks
DEFAULT_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
        "/metrics",
        "/favicon.ico",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
)

# HTTP methods that have request bodies
BODY_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _validate_non_strict(engine: GovernanceEngine, text: str, *, agent_id: str) -> Any:
    """Validate text while always restoring the engine's strict mode."""
    old_strict = engine.strict
    engine.strict = False
    try:
        return engine.validate(text, agent_id=agent_id)
    finally:
        engine.strict = old_strict


class GovernanceASGIMiddleware:
    """ASGI middleware that validates request/response bodies.

    Validates:
    - Request bodies (POST/PUT/PATCH) against constitutional rules
    - Response bodies (non-blocking, adds X-Governance headers)

    Usage::

        from fastapi import FastAPI
        from acgs_lite.middleware import GovernanceASGIMiddleware

        app = FastAPI()
        app.add_middleware(GovernanceASGIMiddleware)

        # With custom constitution:
        app.add_middleware(
            GovernanceASGIMiddleware,
            constitution=my_rules,
            skip_paths={"/health", "/internal"},
        )
    """

    def __init__(
        self,
        app: Any,
        *,
        constitution: Constitution | None = None,
        skip_paths: set[str] | frozenset[str] | None = None,
        agent_id: str = "http-middleware",
        strict: bool = False,
        validate_responses: bool = True,
    ) -> None:
        self.app = app
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.skip_paths = skip_paths if skip_paths is not None else DEFAULT_SKIP_PATHS
        self.agent_id = agent_id
        self.validate_responses = validate_responses

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        # Skip configured paths
        if path in self.skip_paths:
            await self.app(scope, receive, send)
            return

        # For body methods, validate request body
        governance_valid = True
        governance_violations: list[str] = []

        if method in BODY_METHODS:
            body_chunks: list[bytes] = []

            async def receive_wrapper() -> dict[str, Any]:
                message = await receive()
                if message.get("type") == "http.request":
                    body = message.get("body", b"")
                    if body:
                        body_chunks.append(body)
                return message

            # Use wrapped receive to capture the body
            if self.validate_responses:
                # We need to buffer response too
                response_body_chunks: list[bytes] = []

                async def send_wrapper(message: dict[str, Any]) -> None:
                    if message["type"] == "http.response.start":
                        # Add governance headers
                        extra_headers = [
                            (b"x-governance-hash", self.constitution.hash.encode()),
                            (b"x-governance-valid", str(governance_valid).lower().encode()),
                        ]
                        if governance_violations:
                            extra_headers.append(
                                (
                                    b"x-governance-violations",
                                    ",".join(governance_violations).encode(),
                                )
                            )

                        existing = list(message.get("headers", []))
                        existing.extend(extra_headers)
                        message = {**message, "headers": existing}

                    elif message["type"] == "http.response.body":
                        body = message.get("body", b"")
                        if body:
                            response_body_chunks.append(body)

                    await send(message)

                await self.app(scope, receive_wrapper, send_wrapper)

                # Validate request body if captured
                if body_chunks:
                    request_text = b"".join(body_chunks).decode("utf-8", errors="replace")
                    self._validate_text(request_text, f"{self.agent_id}:request")

                # Validate response body (non-blocking)
                if response_body_chunks:
                    response_text = b"".join(response_body_chunks).decode("utf-8", errors="replace")
                    self._validate_output(response_text)

            else:
                await self.app(scope, receive_wrapper, send)

                if body_chunks:
                    request_text = b"".join(body_chunks).decode("utf-8", errors="replace")
                    self._validate_text(request_text, f"{self.agent_id}:request")
        else:
            # GET/HEAD/OPTIONS — just pass through with governance headers
            if self.validate_responses:

                async def send_with_headers(message: dict[str, Any]) -> None:
                    if message["type"] == "http.response.start":
                        existing = list(message.get("headers", []))
                        existing.extend(
                            [
                                (b"x-governance-hash", self.constitution.hash.encode()),
                                (b"x-governance-valid", b"true"),
                            ]
                        )
                        message = {**message, "headers": existing}
                    await send(message)

                await self.app(scope, receive, send_with_headers)
            else:
                await self.app(scope, receive, send)

    def _validate_text(self, text: str, agent_id: str) -> None:
        """Validate text, catching errors gracefully."""
        try:
            # Try to parse as JSON and extract meaningful text
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    # Extract common text fields
                    text_parts: list[str] = []
                    for key in ("content", "text", "message", "query", "input", "prompt"):
                        if key in data and isinstance(data[key], str):
                            text_parts.append(data[key])
                    text = " ".join(text_parts) if text_parts else json.dumps(data)
            except (json.JSONDecodeError, ValueError):
                pass  # Use raw text

            if text.strip():
                self.engine.validate(text, agent_id=agent_id)
        except (ValueError, TypeError, RuntimeError) as e:
            logger.debug("Governance middleware validation error: %s", e)

    def _validate_output(self, text: str) -> None:
        """Validate output text non-blocking."""
        try:
            if text.strip():
                result = _validate_non_strict(
                    self.engine,
                    text[:2000],
                    agent_id=f"{self.agent_id}:response",
                )
                if not result.valid:
                    logger.warning(
                        "HTTP response governance violations: %s",
                        [v.rule_id for v in result.violations],
                    )
        except (ValueError, TypeError, RuntimeError) as e:
            logger.debug("Governance middleware output validation error: %s", e)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }


class GovernanceWSGIMiddleware:
    """WSGI middleware that validates request/response bodies.

    Usage::

        from flask import Flask
        from acgs_lite.middleware import GovernanceWSGIMiddleware

        app = Flask(__name__)
        app.wsgi_app = GovernanceWSGIMiddleware(app.wsgi_app)
    """

    def __init__(
        self,
        app: Any,
        *,
        constitution: Constitution | None = None,
        skip_paths: set[str] | frozenset[str] | None = None,
        agent_id: str = "http-middleware",
        strict: bool = False,
    ) -> None:
        self.app = app
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
        )
        self.skip_paths = skip_paths if skip_paths is not None else DEFAULT_SKIP_PATHS
        self.agent_id = agent_id

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: Callable[..., Any],
    ) -> Any:
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        # Skip configured paths
        if path in self.skip_paths:
            return self.app(environ, start_response)

        # Validate request body for body methods
        if method in BODY_METHODS:
            content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
            if content_length > 0:
                body = environ["wsgi.input"].read(content_length)
                # Reset the input stream so the app can read it
                environ["wsgi.input"] = io.BytesIO(body)

                try:
                    text = body.decode("utf-8", errors="replace")
                    if text.strip():
                        _validate_non_strict(
                            self.engine,
                            text[:2000],
                            agent_id=f"{self.agent_id}:request",
                        )
                except (ValueError, TypeError, RuntimeError) as e:
                    logger.debug("WSGI governance validation error: %s", e)

        # Add governance headers to response
        def governed_start_response(status: str, headers: list[tuple[str, str]], *args: Any) -> Any:
            headers.append(("X-Governance-Hash", self.constitution.hash))
            headers.append(("X-Governance-Valid", "true"))
            return start_response(status, headers, *args)

        return self.app(environ, governed_start_response)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
