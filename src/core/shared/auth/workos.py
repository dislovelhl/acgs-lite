"""WorkOS integration helpers for SSO administration and event handling.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from src.core.shared.config import settings
from src.core.shared.types import JSONDict

WORKOS_SIGNATURE_HEADER = "WorkOS-Signature"
WORKOS_WEBHOOK_DEFAULT_TOLERANCE_SECONDS = 180
_WORKOS_DISALLOWED_PLACEHOLDERS = frozenset(
    {
        "replace_me",
        "your_api_key",
        "your_webhook_secret",
        "your_client_id",
        "placeholder",
    }
)

WorkOSPortalIntent = Literal[
    "audit_logs",
    "certificate_renewal",
    "domain_verification",
    "dsync",
    "log_streams",
    "sso",
]


class WorkOSConfigurationError(ValueError):
    """Raised when WorkOS integration is not configured correctly."""


class WorkOSAPIError(RuntimeError):
    """Raised when WorkOS API calls fail."""


class WorkOSWebhookVerificationError(ValueError):
    """Raised when WorkOS webhook signatures are invalid."""


class WorkOSWebhookEvent(BaseModel):
    """Subset of WorkOS webhook event envelope."""

    id: str = Field(..., min_length=1)
    event: str = Field(..., min_length=1)
    data: JSONDict = Field(default_factory=dict)
    created_at: str = Field(..., min_length=1)


def _secret_value(secret: object) -> str:
    if hasattr(secret, "get_secret_value"):
        return str(secret.get_secret_value())
    return str(secret)


def _normalize_config_value(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


def _ensure_not_placeholder(value: str, field_name: str) -> str:
    normalized = _normalize_config_value(value)
    normalized_placeholders = {
        _normalize_config_value(placeholder) for placeholder in _WORKOS_DISALLOWED_PLACEHOLDERS
    }
    if normalized in normalized_placeholders:
        raise WorkOSConfigurationError(f"{field_name} uses a placeholder value.")
    return value


def _get_workos_client_id() -> str:
    configured_client_id = settings.sso.workos_client_id
    client_id = configured_client_id.strip() if configured_client_id else ""
    if not client_id:
        raise WorkOSConfigurationError("WORKOS_CLIENT_ID is not configured.")
    return _ensure_not_placeholder(client_id, "WORKOS_CLIENT_ID")


def _get_workos_api_key() -> str:
    configured_api_key = settings.sso.workos_api_key
    if not configured_api_key:
        raise WorkOSConfigurationError("WORKOS_API_KEY is not configured.")
    api_key = _secret_value(configured_api_key).strip()
    if not api_key:
        raise WorkOSConfigurationError("WORKOS_API_KEY is empty.")
    return _ensure_not_placeholder(api_key, "WORKOS_API_KEY")


def _get_workos_webhook_secret() -> str:
    configured_secret = settings.sso.workos_webhook_secret
    if not configured_secret:
        raise WorkOSConfigurationError("WORKOS_WEBHOOK_SECRET is not configured.")
    webhook_secret = _secret_value(configured_secret).strip()
    if not webhook_secret:
        raise WorkOSConfigurationError("WORKOS_WEBHOOK_SECRET is empty.")
    return _ensure_not_placeholder(webhook_secret, "WORKOS_WEBHOOK_SECRET")


def _get_workos_base_url() -> str:
    configured_base_url = settings.sso.workos_api_base_url.strip()
    if not configured_base_url:
        raise WorkOSConfigurationError("WORKOS_API_BASE_URL is not configured.")
    if not configured_base_url.lower().startswith("https://"):
        raise WorkOSConfigurationError("WORKOS_API_BASE_URL must use HTTPS.")
    return configured_base_url.rstrip("/")


def is_workos_enabled() -> bool:
    """Return True when WorkOS is enabled and minimally configured."""
    if not settings.sso.workos_enabled:
        return False

    try:
        _get_workos_client_id()
        _get_workos_api_key()
    except WorkOSConfigurationError:
        return False
    return True


async def generate_workos_admin_portal_link(
    organization_id: str,
    *,
    intent: WorkOSPortalIntent,
    return_url: str | None = None,
    success_url: str | None = None,
    intent_options: JSONDict | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    """Generate a short-lived WorkOS Admin Portal link."""
    if not settings.sso.workos_enabled:
        raise WorkOSConfigurationError("WorkOS integration is disabled.")

    api_key = _get_workos_api_key()
    base_url = _get_workos_base_url()

    resolved_return_url = return_url or settings.sso.workos_portal_return_url
    resolved_success_url = success_url or settings.sso.workos_portal_success_url

    payload: JSONDict = {
        "intent": intent,
        "organization": organization_id,
        "return_url": resolved_return_url,
        "success_url": resolved_success_url,
        "intent_options": intent_options,
    }
    filtered_payload = {key: value for key, value in payload.items() if value is not None}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            f"{base_url}/portal/generate_link",
            json=filtered_payload,
            headers=headers,
        )

    if response.status_code >= 400:
        response_preview = response.text[:500]
        raise WorkOSAPIError(
            f"WorkOS portal link generation failed: {response.status_code} {response_preview}"
        )

    response_data = response.json()
    link = response_data.get("link")
    if not isinstance(link, str) or not link:
        raise WorkOSAPIError("WorkOS response did not include a valid portal link.")
    return link


async def list_workos_events(
    event_types: list[str],
    *,
    organization_id: str | None = None,
    after: str | None = None,
    range_start: str | None = None,
    range_end: str | None = None,
    limit: int = 100,
    timeout_seconds: float = 10.0,
) -> JSONDict:
    """List WorkOS events using cursor-based pagination."""
    if not settings.sso.workos_enabled:
        raise WorkOSConfigurationError("WorkOS integration is disabled.")
    if not event_types:
        raise WorkOSConfigurationError("At least one event type is required.")

    api_key = _get_workos_api_key()
    base_url = _get_workos_base_url()

    params: JSONDict = {
        "events": event_types,
        "organization_id": organization_id,
        "after": after,
        "range_start": range_start,
        "range_end": range_end,
        "limit": limit,
    }
    filtered_params = {key: value for key, value in params.items() if value is not None}

    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(
            f"{base_url}/events",
            params=filtered_params,
            headers=headers,
        )

    if response.status_code >= 400:
        response_preview = response.text[:500]
        raise WorkOSAPIError(
            f"WorkOS events query failed: {response.status_code} {response_preview}"
        )

    response_data = response.json()
    if not isinstance(response_data, dict):
        raise WorkOSAPIError("WorkOS events response was not a JSON object.")

    return response_data


def _parse_workos_signature_header(header_value: str) -> tuple[int, str]:
    parsed_values: dict[str, str] = {}
    for part in header_value.split(","):
        token = part.strip()
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        parsed_values[key] = value

    timestamp_raw = parsed_values.get("t")
    signature_hash = parsed_values.get("v1")

    if not timestamp_raw or not signature_hash:
        raise WorkOSWebhookVerificationError(
            "WorkOS signature header must include both 't' and 'v1' values."
        )

    try:
        timestamp_ms = int(timestamp_raw)
    except ValueError as exc:
        raise WorkOSWebhookVerificationError("WorkOS signature timestamp is invalid.") from exc

    return timestamp_ms, signature_hash


def verify_workos_webhook_signature(
    event_body: bytes,
    event_signature: str,
    *,
    secret: str,
    tolerance_seconds: int = WORKOS_WEBHOOK_DEFAULT_TOLERANCE_SECONDS,
) -> None:
    """Verify WorkOS webhook signature against payload bytes."""
    timestamp_ms, expected_hash = _parse_workos_signature_header(event_signature)
    event_body_text = event_body.decode("utf-8")

    signed_content = f"{timestamp_ms}.{event_body_text}"
    calculated_hash = hmac.new(
        secret.encode("utf-8"),
        signed_content.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, calculated_hash):
        raise WorkOSWebhookVerificationError("WorkOS webhook signature hash mismatch.")

    event_age_seconds = time.time() - (timestamp_ms / 1000)
    if abs(event_age_seconds) > tolerance_seconds:
        raise WorkOSWebhookVerificationError("WorkOS webhook timestamp outside tolerance window.")


def parse_and_verify_workos_webhook(
    event_body: bytes,
    event_signature: str,
    *,
    tolerance_seconds: int = WORKOS_WEBHOOK_DEFAULT_TOLERANCE_SECONDS,
) -> WorkOSWebhookEvent:
    """Validate WorkOS webhook signature and parse event payload."""
    secret = _get_workos_webhook_secret()
    verify_workos_webhook_signature(
        event_body=event_body,
        event_signature=event_signature,
        secret=secret,
        tolerance_seconds=tolerance_seconds,
    )

    try:
        payload_obj = json.loads(event_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkOSWebhookVerificationError("WorkOS webhook payload is not valid JSON.") from exc

    if not isinstance(payload_obj, dict):
        raise WorkOSWebhookVerificationError("WorkOS webhook payload must be a JSON object.")

    return WorkOSWebhookEvent.model_validate(payload_obj)
