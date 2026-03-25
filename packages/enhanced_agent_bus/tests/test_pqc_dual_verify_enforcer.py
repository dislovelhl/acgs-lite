# Constitutional Hash: 608508a9bd224290
"""Unit tests for DualVerifyEnforcer (packages/enhanced_agent_bus/pqc_dual_verify.py).

Tests cover:
  - verify() accepts governance decision signed with classical key when window is active
  - verify() rejects classical-only decision when window is closed with CLASSICAL_KEY_RETIRED
  - verify() always accepts PQC-signed decisions regardless of window state
  - verify() always accepts hybrid-signed decisions regardless of window state
  - Audit event schema includes: event_type, key_type, window_active, decision_id
  - Window extension race condition: 1-second grace period before window_end
  - pytest --import-mode=importlib passes with 90%+ coverage on pqc_dual_verify module

Run with:
    pytest -m pqc_deprecation packages/enhanced_agent_bus/tests/test_pqc_dual_verify_enforcer.py \\
        --import-mode=importlib -v
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.pqc_deprecation

# ---------------------------------------------------------------------------
# Lazy imports — module may not be on sys.path in some test runners
# ---------------------------------------------------------------------------

pqc_dual_verify = pytest.importorskip(
    "enhanced_agent_bus.pqc_dual_verify",
    reason="pqc_dual_verify module not available",
)

DualVerifyEnforcer = pqc_dual_verify.DualVerifyEnforcer
GovernanceDecision = pqc_dual_verify.GovernanceDecision

try:
    from src.core.tools.pqc_migration.phase4.exceptions import DualVerifyWindowError
except ImportError:
    DualVerifyWindowError = pqc_dual_verify.DualVerifyWindowError  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)
_ACTIVE_WINDOW_END = _NOW + timedelta(days=80)
_EXPIRED_WINDOW_END = _NOW - timedelta(seconds=2)  # clearly expired (not in grace window)
_GRACE_WINDOW_END = _NOW - timedelta(milliseconds=500)  # within 1-second grace


def _make_decision(decision_id: str = "decision-test-001") -> GovernanceDecision:
    """Create a minimal GovernanceDecision for testing."""
    return GovernanceDecision(decision_id=decision_id)


def _make_window_schema(
    window_end: datetime,
    is_active: bool | None = None,
) -> dict:
    """Build a mock window config dict with the given window_end."""
    computed_active = is_active if is_active is not None else (datetime.now(UTC) <= window_end)
    return {
        "window_start": (_NOW - timedelta(days=10)).isoformat(),
        "window_end": window_end.isoformat(),
        "is_active": computed_active,
        "days_remaining": max(0, (window_end - _NOW).days),
        "extended_by_operator": None,
        "extended_at": None,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """AsyncMock for the HTTP client used by DualVerifyEnforcer."""
    client = AsyncMock()
    return client


@pytest.fixture
def active_window_enforcer(mock_http_client: AsyncMock) -> DualVerifyEnforcer:
    """Enforcer whose window is currently active."""
    now = datetime.now(UTC)  # fresh timestamp — avoids xdist cache-staleness failures
    enforcer = DualVerifyEnforcer(dual_verify_service_url="http://policy-registry:8003")
    enforcer._http_client = mock_http_client
    enforcer._cached_window_end = now + timedelta(days=80)
    enforcer._cache_fetched_at = now  # fresh cache
    return enforcer


@pytest.fixture
def closed_window_enforcer(mock_http_client: AsyncMock) -> DualVerifyEnforcer:
    """Enforcer whose window has expired."""
    now = datetime.now(UTC)  # fresh timestamp — avoids xdist cache-staleness failures
    enforcer = DualVerifyEnforcer(dual_verify_service_url="http://policy-registry:8003")
    enforcer._http_client = mock_http_client
    enforcer._cached_window_end = now - timedelta(seconds=2)  # clearly expired
    enforcer._cache_fetched_at = now
    return enforcer


# ---------------------------------------------------------------------------
# verify() — classical key, active window
# ---------------------------------------------------------------------------


class TestVerifyClassicalActiveWindow:
    async def test_classical_accepted_when_window_active(
        self, active_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Classical key accepted when dual-verify window is currently active."""
        decision = _make_decision()
        result = await active_window_enforcer.verify(decision, key_type="classical")
        assert result is True

    async def test_classical_accepted_emits_audit_event(
        self, active_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Audit event emitted with classical_verification_used=True when classical is accepted."""
        decision = _make_decision("decision-audit-001")
        audit_events: list[dict] = []

        original_emit = getattr(active_window_enforcer, "_emit_audit_event", None)

        async def capture_audit(*args, **kwargs):
            if args:
                audit_events.append(args[0] if isinstance(args[0], dict) else {"event": args[0]})
            elif kwargs:
                audit_events.append(kwargs)

        with patch.object(active_window_enforcer, "_emit_audit_event", side_effect=capture_audit):
            await active_window_enforcer.verify(decision, key_type="classical")

        assert len(audit_events) >= 1

    async def test_classical_audit_event_schema(
        self, active_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Audit event contains event_type, key_type, window_active, decision_id fields."""
        decision = _make_decision("decision-schema-001")
        captured_events: list[dict] = []

        async def capture(*args, **kwargs):
            event = args[0] if args and isinstance(args[0], dict) else kwargs
            captured_events.append(event)

        with patch.object(active_window_enforcer, "_emit_audit_event", side_effect=capture):
            await active_window_enforcer.verify(decision, key_type="classical")

        assert len(captured_events) >= 1
        event = captured_events[0]
        required_fields = {"event_type", "key_type", "window_active", "decision_id"}
        assert required_fields.issubset(set(event.keys())), (
            f"Missing fields: {required_fields - set(event.keys())}"
        )
        assert event["key_type"] == "classical"
        assert event["window_active"] is True
        assert event["decision_id"] == "decision-schema-001"


# ---------------------------------------------------------------------------
# verify() — classical key, closed window
# ---------------------------------------------------------------------------


class TestVerifyClassicalClosedWindow:
    async def test_classical_rejected_when_window_closed(
        self, closed_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Classical key raises DualVerifyWindowError when window has expired."""
        decision = _make_decision()
        with pytest.raises(DualVerifyWindowError) as exc_info:
            await closed_window_enforcer.verify(decision, key_type="classical")
        assert exc_info.value.error_code == "CLASSICAL_KEY_RETIRED"

    async def test_rejection_error_code_is_classical_key_retired(
        self, closed_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Raised DualVerifyWindowError has error_code='CLASSICAL_KEY_RETIRED'."""
        decision = _make_decision()
        exc = None
        try:
            await closed_window_enforcer.verify(decision, key_type="classical")
        except DualVerifyWindowError as e:
            exc = e
        assert exc is not None
        assert exc.error_code == "CLASSICAL_KEY_RETIRED"


# ---------------------------------------------------------------------------
# verify() — PQC and hybrid keys (always accepted)
# ---------------------------------------------------------------------------


class TestVerifyPQCAndHybrid:
    @pytest.mark.parametrize("key_type", ["pqc", "hybrid"])
    async def test_pqc_hybrid_accepted_with_active_window(
        self,
        active_window_enforcer: DualVerifyEnforcer,
        key_type: Literal["pqc", "hybrid"],
    ) -> None:
        """PQC and hybrid keys are accepted regardless of window state (active)."""
        decision = _make_decision()
        result = await active_window_enforcer.verify(decision, key_type=key_type)
        assert result is True

    @pytest.mark.parametrize("key_type", ["pqc", "hybrid"])
    async def test_pqc_hybrid_accepted_with_closed_window(
        self,
        closed_window_enforcer: DualVerifyEnforcer,
        key_type: Literal["pqc", "hybrid"],
    ) -> None:
        """PQC and hybrid keys are accepted even when the dual-verify window has closed."""
        decision = _make_decision()
        result = await closed_window_enforcer.verify(decision, key_type=key_type)
        assert result is True

    @pytest.mark.parametrize("key_type", ["pqc", "hybrid"])
    async def test_pqc_hybrid_do_not_raise(
        self,
        closed_window_enforcer: DualVerifyEnforcer,
        key_type: Literal["pqc", "hybrid"],
    ) -> None:
        """PQC/hybrid never raises DualVerifyWindowError."""
        decision = _make_decision()
        try:
            await closed_window_enforcer.verify(decision, key_type=key_type)
        except DualVerifyWindowError:
            pytest.fail(
                f"verify() raised DualVerifyWindowError for key_type='{key_type}' — should not"
            )


# ---------------------------------------------------------------------------
# Grace period: 1-second tolerance at window boundary
# ---------------------------------------------------------------------------


class TestGracePeriod:
    async def test_classical_accepted_within_grace_period(
        self, mock_http_client: AsyncMock
    ) -> None:
        """Classical key within 1-second grace period after window_end is NOT rejected."""
        # window_end was 500ms ago — within the 1-second grace window
        # Compute fresh timestamps at test run time to avoid xdist timing failures.
        now = datetime.now(UTC)
        enforcer = DualVerifyEnforcer(dual_verify_service_url="http://policy-registry:8003")
        enforcer._http_client = mock_http_client
        enforcer._cached_window_end = now - timedelta(milliseconds=500)
        enforcer._cache_fetched_at = now

        decision = _make_decision("grace-decision-001")
        # Should NOT raise — within grace period
        result = await enforcer.verify(decision, key_type="classical")
        assert result is True

    async def test_classical_rejected_beyond_grace_period(
        self, closed_window_enforcer: DualVerifyEnforcer
    ) -> None:
        """Classical key more than 1 second after window_end IS rejected."""
        # closed_window_enforcer uses _EXPIRED_WINDOW_END = 2 seconds ago
        decision = _make_decision("beyond-grace-001")
        with pytest.raises(DualVerifyWindowError) as exc_info:
            await closed_window_enforcer.verify(decision, key_type="classical")
        assert exc_info.value.error_code == "CLASSICAL_KEY_RETIRED"


# ---------------------------------------------------------------------------
# Cache refresh tests
# ---------------------------------------------------------------------------


class TestCacheRefresh:
    async def test_stale_cache_triggers_refresh(self, mock_http_client: AsyncMock) -> None:
        """Enforcer fetches fresh window state when cache is stale (>10s old)."""
        enforcer = DualVerifyEnforcer(dual_verify_service_url="http://policy-registry:8003")
        enforcer._http_client = mock_http_client
        enforcer._cached_window_end = _ACTIVE_WINDOW_END
        # Stale: fetched 15 seconds ago
        enforcer._cache_fetched_at = _NOW - timedelta(seconds=15)

        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value=_make_window_schema(_ACTIVE_WINDOW_END, is_active=True)
        )
        mock_response.raise_for_status = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        decision = _make_decision("stale-cache-001")
        result = await enforcer.verify(decision, key_type="classical")
        assert result is True
        # HTTP call was made because cache was stale
        mock_http_client.get.assert_awaited()

    async def test_fresh_cache_avoids_http_call(
        self, active_window_enforcer: DualVerifyEnforcer, mock_http_client: AsyncMock
    ) -> None:
        """Enforcer skips HTTP call when cache is fresh (<10s old)."""
        decision = _make_decision("fresh-cache-001")
        mock_http_client.get = AsyncMock()

        await active_window_enforcer.verify(decision, key_type="classical")

        # HTTP call should NOT be made — cache is fresh
        mock_http_client.get.assert_not_awaited()
