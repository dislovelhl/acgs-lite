"""ACGS-Lite Cloud Run Server.

Minimal Starlette server for deploying ACGS-Lite governance on Google Cloud Run.
Receives GitLab webhook events, validates against constitutional rules, and
exports audit trail to Cloud Logging.

Endpoints:
    POST /webhook     — GitLab webhook events (MR governance)
    GET  /health      — Health check with constitutional hash
    GET  /governance/summary — Constitution governance posture summary

Environment variables:
    CONSTITUTION_PATH  — Path to constitution YAML (optional, uses default)
    GITLAB_TOKEN       — GitLab API access token
    GITLAB_PROJECT_ID  — GitLab project numeric ID
    GITLAB_WEBHOOK_SECRET — Webhook secret for signature verification
    GCP_PROJECT_ID     — GCP project for Cloud Logging (optional, uses ADC)
    PORT               — Server port (default: 8080)

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import logging
import os
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.integrations.gitlab import GitLabGovernanceBot, GitLabWebhookHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

_CONSTITUTION_PATH = os.environ.get("CONSTITUTION_PATH", "")
_GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
_GITLAB_PROJECT_ID = os.environ.get("GITLAB_PROJECT_ID", "0")
_GITLAB_WEBHOOK_SECRET = os.environ.get("GITLAB_WEBHOOK_SECRET", "")
_GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")


def _load_constitution() -> Constitution:
    """Load constitution from CONSTITUTION_PATH or use default.

    Returns:
        Constitution instance loaded from YAML or the built-in default.
    """
    if _CONSTITUTION_PATH:
        try:
            return Constitution.from_yaml(_CONSTITUTION_PATH)
        except (FileNotFoundError, ValueError):
            logger.warning(
                "Failed to load constitution from %s, using default",
                _CONSTITUTION_PATH,
                exc_info=True,
            )
    return Constitution.default()


# ---------------------------------------------------------------------------
# Cloud Logging exporter (optional, best-effort)
# ---------------------------------------------------------------------------

_cloud_exporter: Any = None


def _init_cloud_exporter() -> Any:
    """Initialize Cloud Logging exporter if the library is available.

    Returns:
        CloudLoggingAuditExporter instance or None if unavailable.
    """
    try:
        from acgs_lite.integrations.cloud_logging import CloudLoggingAuditExporter

        return CloudLoggingAuditExporter(project_id=_GCP_PROJECT_ID)
    except (ImportError, Exception):
        logger.info("Cloud Logging not available, audit entries will only be logged locally")
        return None


def _export_audit_entries(audit_log: AuditLog) -> None:
    """Export new audit entries to Cloud Logging if exporter is available.

    Args:
        audit_log: The AuditLog containing entries to export.
    """
    global _cloud_exporter
    if _cloud_exporter is None:
        return

    entries = audit_log.entries
    if entries:
        try:
            _cloud_exporter.export_batch(entries)
        except Exception:
            logger.error("Failed to export audit entries to Cloud Logging", exc_info=True)


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_constitution = _load_constitution()
_audit_log = AuditLog()

_bot: GitLabGovernanceBot | None = None
_webhook_handler: GitLabWebhookHandler | None = None


def _get_bot() -> GitLabGovernanceBot | None:
    """Lazy-initialize the GitLab governance bot.

    Returns:
        GitLabGovernanceBot instance or None if credentials are missing.
    """
    global _bot
    if _bot is not None:
        return _bot

    if not _GITLAB_TOKEN or _GITLAB_PROJECT_ID == "0":
        logger.warning("GITLAB_TOKEN or GITLAB_PROJECT_ID not set, webhook processing disabled")
        return None

    try:
        _bot = GitLabGovernanceBot(
            token=_GITLAB_TOKEN,
            project_id=int(_GITLAB_PROJECT_ID),
            constitution=_constitution,
        )
        return _bot
    except (ImportError, ValueError):
        logger.error("Failed to initialize GitLab governance bot", exc_info=True)
        return None


def _get_webhook_handler() -> GitLabWebhookHandler | None:
    """Lazy-initialize the webhook handler.

    Returns:
        GitLabWebhookHandler instance or None if bot is unavailable.
    """
    global _webhook_handler
    if _webhook_handler is not None:
        return _webhook_handler

    bot = _get_bot()
    if bot is None:
        return None

    secret = _GITLAB_WEBHOOK_SECRET or "default-secret"
    _webhook_handler = GitLabWebhookHandler(webhook_secret=secret, bot=bot)
    return _webhook_handler


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def webhook_endpoint(request: Request) -> JSONResponse:
    """Handle incoming GitLab webhook events.

    Delegates to GitLabWebhookHandler for signature verification,
    event routing, and governance pipeline execution.

    Args:
        request: Starlette Request object.

    Returns:
        JSONResponse with governance result or error.
    """
    handler = _get_webhook_handler()
    if handler is None:
        return JSONResponse(
            {"error": "Webhook handler not configured. Set GITLAB_TOKEN and GITLAB_PROJECT_ID."},
            status_code=503,
        )

    response = await handler.handle(request)

    # Export audit entries after processing
    bot = _get_bot()
    if bot is not None:
        _export_audit_entries(bot.audit_log)

        _audit_log.record(
            AuditEntry(
                id=f"webhook-{request.headers.get('X-Gitlab-Event', 'unknown')}",
                type="webhook_processed",
                agent_id="cloud-run-server",
                action="webhook event processed",
                valid=True,
                constitutional_hash=_constitution.hash,
            )
        )

    return response  # type: ignore[return-value]


async def health_endpoint(request: Request) -> JSONResponse:
    """Health check endpoint for Cloud Run.

    Returns service status and the constitutional hash for
    governance chain verification.

    Args:
        request: Starlette Request object.

    Returns:
        JSONResponse with health status and constitutional hash.
    """
    bot = _get_bot()
    webhook_configured = bot is not None

    return JSONResponse(
        {
            "status": "healthy",
            "constitutional_hash": _constitution.hash,
            "version": "0.2.0",
            "webhook_configured": webhook_configured,
            "rules_loaded": len(_constitution.rules),
        }
    )


async def governance_summary_endpoint(request: Request) -> JSONResponse:
    """Return the constitution's governance posture summary.

    Provides a structured overview of the active ruleset for
    dashboards, monitoring, and agent introspection.

    Args:
        request: Starlette Request object.

    Returns:
        JSONResponse with governance summary dict.
    """
    summary = _constitution.governance_summary()
    return JSONResponse(
        {
            "constitutional_hash": _constitution.hash,
            "summary": summary,
        }
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

_cloud_exporter = _init_cloud_exporter()

app = Starlette(
    routes=[
        Route("/webhook", webhook_endpoint, methods=["POST"]),
        Route("/health", health_endpoint, methods=["GET"]),
        Route("/governance/summary", governance_summary_endpoint, methods=["GET"]),
    ],
)
