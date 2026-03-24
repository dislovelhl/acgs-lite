"""Constitutional Hash: cdd01ef066bc6cf2
ACGS-2 API Gateway — Proxy catch-all endpoint

Extracted from main.py: reverse proxy to Agent Bus service.
This router MUST be included LAST so the catch-all route does not shadow other routes.
"""

import asyncio
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, ValidationError

from src.core.shared.config import settings
from src.core.shared.security.auth import (
    UserClaims,
    get_current_user_optional,
)
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Service URLs from centralized config
AGENT_BUS_URL = settings.services.agent_bus_url

# Shared httpx client for proxy requests (Constitutional Hash: cdd01ef066bc6cf2)
_proxy_client: httpx.AsyncClient | None = None
_proxy_client_lock = asyncio.Lock()


async def get_proxy_client() -> httpx.AsyncClient:
    """Get or create the shared httpx proxy client (thread-safe)."""
    global _proxy_client
    if _proxy_client is not None and not _proxy_client.is_closed:
        return _proxy_client
    async with _proxy_client_lock:
        # Double-check after acquiring lock
        if _proxy_client is None or _proxy_client.is_closed:
            _proxy_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
    return _proxy_client


async def close_proxy_client() -> None:
    """Gracefully close the shared httpx proxy client."""
    global _proxy_client
    async with _proxy_client_lock:
        if _proxy_client is not None and not _proxy_client.is_closed:
            await _proxy_client.aclose()
            _proxy_client = None


HOP_BY_HOP_HEADERS = frozenset(
    {
        "host",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
    }
)

# SECURITY: Allowlist of headers forwarded to Agent Bus (H-3 fix).
# Using an allowlist instead of a blocklist prevents internal header injection.
_PROXY_FORWARD_HEADERS = frozenset(
    {
        "accept",
        "accept-encoding",
        "accept-language",
        "content-type",
        "user-agent",
        "x-request-id",
        "x-correlation-id",
        "x-idempotency-key",
    }
)

# Maximum proxy request body size (1 MB)
MAX_PROXY_BODY_SIZE = 1 * 1024 * 1024


class ProxyRequestPayload(BaseModel):
    """Validates proxy request JSON payloads have a well-formed structure."""

    model_config = {"extra": "allow"}


proxy_router = APIRouter()


# Proxy to Agent Bus (catch-all route - must be last)
@proxy_router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_to_agent_bus(
    request: Request,
    path: str,
    user: UserClaims = Depends(get_current_user_optional),
) -> ORJSONResponse:
    """Proxy requests to the Agent Bus service (auth required)"""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    incoming_tenant = request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-ID")
    if incoming_tenant and incoming_tenant != user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"Tenant mismatch: token tenant '{user.tenant_id}' != header tenant '{incoming_tenant}'",
        )

    # SECURITY: Hardened path traversal protection
    # Use allowlist approach - only alphanumeric, hyphens, underscores, and forward slashes
    if not re.match(r"^[\w\-/]+$", path):
        raise HTTPException(status_code=400, detail="Invalid path characters")
    normalized_path = path.replace("\\", "/")
    if ".." in normalized_path or normalized_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")

    allowed_prefixes = ("api/v1/agents", "api/v1/messages", "api/v1/deliberations")
    if not any(normalized_path.startswith(prefix) for prefix in allowed_prefixes):
        raise HTTPException(status_code=403, detail="Proxy to this path not allowed")

    target_url = f"{AGENT_BUS_URL}/{normalized_path}"

    try:
        body_bytes = await request.body()

        # Validate payload size
        if len(body_bytes) > MAX_PROXY_BODY_SIZE:
            raise HTTPException(status_code=413, detail="Payload too large")

        # Validate JSON structure if content-type is JSON
        content_type = request.headers.get("content-type", "")
        if content_type.startswith("application/json") and body_bytes:
            try:
                json_data = json.loads(body_bytes)
                if isinstance(json_data, dict):
                    ProxyRequestPayload(**json_data)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=422, detail="Invalid JSON payload") from e
            except ValidationError as e:
                raise HTTPException(status_code=422, detail="Invalid JSON payload") from e

        # SECURITY: Use allowlist — only forward known-safe headers to Agent Bus.
        # This prevents clients from injecting internal headers (H-3 fix).
        safe_headers = {
            k: v for k, v in request.headers.items() if k.lower() in _PROXY_FORWARD_HEADERS
        }
        # Inject authenticated identity headers (gateway-controlled, not client-settable)
        safe_headers["X-Tenant-ID"] = user.tenant_id
        safe_headers["X-User-ID"] = user.sub

        # NOTE: autonomy tier enforcement is handled by AutonomyTierEnforcementMiddleware

        client = await get_proxy_client()
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=safe_headers,
            content=body_bytes,
            params=dict(request.query_params),
        )

        return ORJSONResponse(
            status_code=response.status_code,
            content=(
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text
            ),
        )

    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=502, detail="Service unavailable") from e
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        LookupError,
    ) as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
