"""
ACGS-2 Enhanced Agent Bus — PQC Dual-Verify Enforcer
Constitutional Hash: 608508a9bd224290

Enforcer that decides whether a governance decision may be verified using a
classical-only signature during the Phase 4 dual-verify window.

Rules:
  - key_type == 'classical' AND window active:
      Accept; emit audit event with classical_verification_used=True.
  - key_type == 'classical' AND window closed:
      Raise DualVerifyWindowError(error_code='CLASSICAL_KEY_RETIRED').
  - key_type in ('pqc', 'hybrid'):
      Always accept, regardless of window state.

Window state is fetched via HTTP GET /api/v1/admin/pqc/dual-verify-window from
the Policy Registry service, cached locally for 10 seconds to minimise latency.
A 1-second grace period is applied at the window boundary to handle clock skew.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.tools.pqc_migration.phase4.exceptions import DualVerifyWindowError
except ImportError:

    class DualVerifyWindowError(Exception):
        """Stub for standalone mode."""

        def __init__(self, message: str = "", *, error_code: str = "") -> None:
            super().__init__(message)
            self.error_code = error_code


from enhanced_agent_bus.observability.structured_logging import get_logger

_CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

logger = get_logger(__name__)

# Local cache TTL (seconds) — avoids HTTP round-trip on every verify() call
_CACHE_TTL_SECONDS = 10
# Grace period at window boundary (seconds) — accepts classical just after window_end
_GRACE_PERIOD_SECONDS = 1


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass
class GovernanceDecision:
    """
    Minimal governance decision container for dual-verify enforcement.

    Attributes:
        decision_id: Unique identifier for the governance decision.
        metadata:    Optional additional metadata for audit logging.
    """

    decision_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Enforcer
# ---------------------------------------------------------------------------


class DualVerifyEnforcer:
    """
    Enforces dual-verify window rules for governance decisions.

    Usage::

        enforcer = DualVerifyEnforcer(dual_verify_service_url="http://policy-registry:8003")
        result = await enforcer.verify(decision, key_type="classical")  # True or raises

    Args:
        dual_verify_service_url: Base URL of the Policy Registry service that
                                 hosts the GET /api/v1/admin/pqc/dual-verify-window endpoint.
        http_client:             Optional pre-constructed async HTTP client.  If
                                 None, an httpx.AsyncClient is created lazily.
    """

    def __init__(
        self,
        dual_verify_service_url: str,
        http_client: Any | None = None,
    ) -> None:
        self._service_url = dual_verify_service_url.rstrip("/")
        self._http_client = http_client

        # Local cache state
        self._cached_window_end: datetime | None = None
        self._cache_fetched_at: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(
        self,
        decision: GovernanceDecision,
        key_type: Literal["classical", "pqc", "hybrid"],
    ) -> bool:
        """
        Determine whether a governance decision may be verified.

        Args:
            decision: The governance decision to evaluate.
            key_type: The cryptographic key type used to sign the decision.

        Returns:
            True if the decision is accepted.

        Raises:
            DualVerifyWindowError: If key_type is 'classical' and the dual-verify
                window has closed (error_code='CLASSICAL_KEY_RETIRED').
        """
        if key_type in ("pqc", "hybrid"):
            await self._emit_audit_event(
                {
                    "event_type": "dual_verify_accept",
                    "key_type": key_type,
                    "window_active": None,  # irrelevant for PQC/hybrid
                    "decision_id": decision.decision_id,
                }
            )
            return True

        # Classical: check window state
        window_active = await self._is_window_active()

        await self._emit_audit_event(
            {
                "event_type": "dual_verify_classical_check",
                "key_type": key_type,
                "window_active": window_active,
                "decision_id": decision.decision_id,
            }
        )

        if window_active:
            logger.info(
                "dual_verify_classical_accepted",
                decision_id=decision.decision_id,
                classical_verification_used=True,
                window_active=True,
                constitutional_hash=_CONSTITUTIONAL_HASH,
            )
            return True

        raise DualVerifyWindowError(
            "Classical-only signatures are no longer accepted: "
            "the dual-verify window has closed. "
            "Migrate to PQC or hybrid signing.",
            error_code="CLASSICAL_KEY_RETIRED",
            detail={
                "decision_id": decision.decision_id,
                "window_end": self._cached_window_end.isoformat()
                if self._cached_window_end
                else None,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _is_window_active(self) -> bool:
        """
        Return True when the current UTC time is within the dual-verify window.

        Uses a local cache (TTL=10s) to minimise HTTP round-trips.
        A 1-second grace period is applied at the window boundary to handle
        clock skew between services.
        """
        await self._refresh_cache_if_stale()

        if self._cached_window_end is None:
            # No window config — treat as closed (fail-safe)
            return False

        now = datetime.now(UTC)
        # Accept if within window OR within the 1-second grace period
        effective_end = self._cached_window_end + timedelta(seconds=_GRACE_PERIOD_SECONDS)
        return now <= effective_end

    async def _refresh_cache_if_stale(self) -> None:
        """Refresh _cached_window_end via HTTP if the local cache has expired."""
        now = datetime.now(UTC)
        if (
            self._cached_window_end is not None
            and self._cache_fetched_at is not None
            and (now - self._cache_fetched_at).total_seconds() < _CACHE_TTL_SECONDS
        ):
            return  # Cache is fresh

        await self._fetch_window_from_service()

    async def _fetch_window_from_service(self) -> None:
        """
        Fetch current window configuration from the Policy Registry service.

        Updates _cached_window_end and _cache_fetched_at.
        On HTTP error, logs a warning and preserves stale cache rather than
        failing open or closed.
        """
        url = f"{self._service_url}/api/v1/admin/pqc/dual-verify-window"
        client = await self._get_http_client()

        try:
            response = await client.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            window_end_str: str | None = data.get("window_end")
            if window_end_str:
                self._cached_window_end = datetime.fromisoformat(window_end_str)
            else:
                self._cached_window_end = None
            self._cache_fetched_at = datetime.now(UTC)
        except (ConnectionError, TimeoutError, httpx.HTTPError, TypeError, ValueError) as exc:
            logger.warning(
                "dual_verify_window_fetch_failed",
                url=url,
                error=str(exc),
            )
            # Preserve stale cache; do not update _cache_fetched_at so we retry soon

    async def _get_http_client(self) -> Any:
        """Return the HTTP client, creating an httpx.AsyncClient lazily if needed."""
        if self._http_client is None:
            import httpx

            self._http_client = httpx.AsyncClient(timeout=2.0)
        return self._http_client

    async def _emit_audit_event(self, event: dict[str, Any]) -> None:
        """Emit a structured audit log entry for every verify() call."""
        logger.info(
            "dual_verify_audit",
            **event,
            constitutional_hash=_CONSTITUTIONAL_HASH,
        )


__all__ = [
    "DualVerifyEnforcer",
    "DualVerifyWindowError",
    "GovernanceDecision",
]
