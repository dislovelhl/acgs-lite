# Constitutional Hash: 608508a9bd224290
# Sprint 60 — session_context_resolver.py coverage
"""
Comprehensive tests for session_context_resolver.py targeting >=95% coverage.

Covers:
- SessionContextResolver construction (enabled/disabled)
- resolve() — all branches: disabled, fast-path, no session_id, no tenant,
  load error, ctx not found, cross-tenant, success
- extract_session_id() — all priority branches
- extract_governance_session_id() — all priority branches
- get_metrics() — zero totals and non-zero totals
- SESSION_CONTEXT_LOAD_ERRORS tuple membership
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.enums import RiskLevel
from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.core_models import AgentMessage
from enhanced_agent_bus.session_context_resolver import (
    SESSION_CONTEXT_LOAD_ERRORS,
    SessionContextResolver,
)
from enhanced_agent_bus.session_models import SessionGovernanceConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(*, enable_session_governance: bool = True) -> BusConfiguration:
    """Return a BusConfiguration with session governance toggled."""
    cfg = BusConfiguration()
    object.__setattr__(cfg, "enable_session_governance", enable_session_governance)
    return cfg


def _make_governance_config(
    session_id: str = "sess-1", tenant_id: str = "tenant-A"
) -> SessionGovernanceConfig:
    return SessionGovernanceConfig(session_id=session_id, tenant_id=tenant_id)


def _make_session_context(session_id: str = "sess-1", tenant_id: str = "tenant-A"):
    """Build a mock SessionContext with a minimal governance_config."""
    ctx = MagicMock()
    ctx.governance_config = _make_governance_config(session_id=session_id, tenant_id=tenant_id)
    ctx.governance_config.risk_level = RiskLevel.MEDIUM
    return ctx


def _make_manager(return_ctx=None):
    """Return a mock SessionContextManager whose .get() returns *return_ctx*."""
    mgr = AsyncMock()
    mgr.get = AsyncMock(return_value=return_ctx)
    return mgr


def _make_msg(**kwargs) -> AgentMessage:
    """Create an AgentMessage with sensible defaults, overrideable via kwargs."""
    defaults: dict = {
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "content": {},
        "payload": {},
        "headers": {},
        "metadata": {},
        "tenant_id": "tenant-A",
        "session_id": None,
        "session_context": None,
    }
    defaults.update(kwargs)
    return AgentMessage(**defaults)


# ---------------------------------------------------------------------------
# MODULE-LEVEL: SESSION_CONTEXT_LOAD_ERRORS
# ---------------------------------------------------------------------------


class TestSessionContextLoadErrors:
    def test_contains_expected_error_types(self):
        expected = {
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ConnectionError,
            OSError,
            asyncio.TimeoutError,
        }
        assert set(SESSION_CONTEXT_LOAD_ERRORS) == expected


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestSessionContextResolverConstruction:
    def test_enabled_when_governance_and_manager_both_present(self):
        mgr = _make_manager()
        cfg = _make_config(enable_session_governance=True)
        resolver = SessionContextResolver(cfg, mgr)
        assert resolver.enabled is True

    def test_disabled_when_governance_off(self):
        mgr = _make_manager()
        cfg = _make_config(enable_session_governance=False)
        resolver = SessionContextResolver(cfg, mgr)
        assert resolver.enabled is False

    def test_disabled_when_manager_is_none(self):
        cfg = _make_config(enable_session_governance=True)
        resolver = SessionContextResolver(cfg, None)
        assert resolver.enabled is False

    def test_disabled_when_both_off(self):
        cfg = _make_config(enable_session_governance=False)
        resolver = SessionContextResolver(cfg, None)
        assert resolver.enabled is False

    def test_initial_metrics_are_zero(self):
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, _make_manager())
        metrics = resolver.get_metrics()
        assert metrics["resolved_count"] == 0
        assert metrics["not_found_count"] == 0
        assert metrics["error_count"] == 0
        assert metrics["resolution_rate"] == 0.0


# ---------------------------------------------------------------------------
# resolve() — disabled path
# ---------------------------------------------------------------------------


class TestResolveDisabled:
    async def test_returns_none_when_disabled_governance(self):
        cfg = _make_config(enable_session_governance=False)
        resolver = SessionContextResolver(cfg, _make_manager())
        msg = _make_msg(session_id="sess-1")
        result = await resolver.resolve(msg)
        assert result is None

    async def test_returns_none_when_manager_is_none(self):
        cfg = _make_config(enable_session_governance=True)
        resolver = SessionContextResolver(cfg, None)
        msg = _make_msg(session_id="sess-1")
        result = await resolver.resolve(msg)
        assert result is None


# ---------------------------------------------------------------------------
# resolve() — fast path (context already attached)
# ---------------------------------------------------------------------------


class TestResolveFastPath:
    async def test_returns_attached_session_context(self):
        ctx = _make_session_context()
        mgr = _make_manager(return_ctx=None)  # manager should NOT be called
        cfg = _make_config(enable_session_governance=True)
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_context=ctx, session_id="sess-1")
        result = await resolver.resolve(msg)

        assert result is ctx
        mgr.get.assert_not_called()

    async def test_fast_path_increments_resolved_count(self):
        ctx = _make_session_context()
        mgr = _make_manager()
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_context=ctx)
        await resolver.resolve(msg)

        assert resolver.get_metrics()["resolved_count"] == 1


# ---------------------------------------------------------------------------
# resolve() — no session_id extracted
# ---------------------------------------------------------------------------


class TestResolveNoSessionId:
    async def test_returns_none_when_no_session_id(self):
        mgr = _make_manager()
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        # No session_id and no other source
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={})
        result = await resolver.resolve(msg)

        assert result is None
        mgr.get.assert_not_called()


# ---------------------------------------------------------------------------
# resolve() — no tenant_id
# ---------------------------------------------------------------------------


class TestResolveNoTenantId:
    async def test_returns_none_when_tenant_id_missing(self):
        mgr = _make_manager()
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        # tenant_id is empty string — falsy
        msg = _make_msg(session_id="sess-1", tenant_id="")
        result = await resolver.resolve(msg)

        assert result is None
        mgr.get.assert_not_called()

    async def test_returns_none_when_no_tenant_id_attribute(self):
        mgr = _make_manager()
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="")
        # Remove tenant_id attribute entirely
        del msg.tenant_id
        result = await resolver.resolve(msg)

        assert result is None


# ---------------------------------------------------------------------------
# resolve() — manager raises known error
# ---------------------------------------------------------------------------


class TestResolveManagerError:
    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("boom"),
            ValueError("bad value"),
            TypeError("type mismatch"),
            KeyError("key missing"),
            AttributeError("attr err"),
            ConnectionError("conn failed"),
            OSError("os error"),
            TimeoutError(),
        ],
    )
    async def test_returns_none_and_increments_error_count_on_exception(self, exc):
        mgr = AsyncMock()
        mgr.get = AsyncMock(side_effect=exc)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        result = await resolver.resolve(msg)

        assert result is None
        assert resolver.get_metrics()["error_count"] == 1


# ---------------------------------------------------------------------------
# resolve() — ctx not found
# ---------------------------------------------------------------------------


class TestResolveContextNotFound:
    async def test_returns_none_and_increments_not_found(self):
        mgr = _make_manager(return_ctx=None)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1")
        result = await resolver.resolve(msg)

        assert result is None
        assert resolver.get_metrics()["not_found_count"] == 1
        assert resolver.get_metrics()["resolved_count"] == 0


# ---------------------------------------------------------------------------
# resolve() — cross-tenant access denied (VULN-002)
# ---------------------------------------------------------------------------


class TestResolveCrossTenant:
    async def test_returns_none_on_cross_tenant(self):
        # Session belongs to tenant-B, but message is from tenant-A
        ctx = _make_session_context(tenant_id="tenant-B")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        result = await resolver.resolve(msg)

        assert result is None
        # Neither resolved nor not-found counted
        assert resolver.get_metrics()["resolved_count"] == 0
        assert resolver.get_metrics()["not_found_count"] == 0


# ---------------------------------------------------------------------------
# resolve() — success path
# ---------------------------------------------------------------------------


class TestResolveSuccess:
    async def test_returns_ctx_and_increments_resolved(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        result = await resolver.resolve(msg)

        assert result is ctx
        assert resolver.get_metrics()["resolved_count"] == 1
        assert resolver.get_metrics()["not_found_count"] == 0
        assert resolver.get_metrics()["error_count"] == 0

    async def test_manager_called_with_correct_args(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="my-session", tenant_id="tenant-A")
        await resolver.resolve(msg)

        mgr.get.assert_called_once_with("my-session", "tenant-A")


# ---------------------------------------------------------------------------
# extract_session_id() — all priority branches
# ---------------------------------------------------------------------------


class TestExtractSessionId:
    def setup_method(self):
        cfg = _make_config()
        self.resolver = SessionContextResolver(cfg, _make_manager())

    def test_priority_1_session_id_field(self):
        msg = _make_msg(session_id="from-field")
        assert self.resolver.extract_session_id(msg) == "from-field"

    def test_priority_2_header_x_session_id_uppercase(self):
        msg = _make_msg(session_id=None, headers={"X-Session-ID": "from-header"})
        assert self.resolver.extract_session_id(msg) == "from-header"

    def test_priority_2_header_x_session_id_lowercase(self):
        msg = _make_msg(session_id=None, headers={"x-session-id": "from-lower-header"})
        assert self.resolver.extract_session_id(msg) == "from-lower-header"

    def test_priority_3_conversation_id(self):
        msg = _make_msg(session_id=None, headers={})
        # Override conversation_id
        msg.conversation_id = "conv-123"
        assert self.resolver.extract_session_id(msg) == "conv-123"

    def test_priority_4_metadata_session_id(self):
        msg = _make_msg(session_id=None, headers={}, metadata={"session_id": "from-meta"})
        msg.conversation_id = ""  # make conv_id falsy
        assert self.resolver.extract_session_id(msg) == "from-meta"

    def test_priority_5_content_session_id(self):
        msg = _make_msg(
            session_id=None,
            headers={},
            metadata={},
            content={"session_id": "from-content"},
        )
        msg.conversation_id = ""
        assert self.resolver.extract_session_id(msg) == "from-content"

    def test_priority_6_payload_session_id(self):
        msg = _make_msg(
            session_id=None,
            headers={},
            metadata={},
            content={},
            payload={"session_id": "from-payload"},
        )
        msg.conversation_id = ""
        assert self.resolver.extract_session_id(msg) == "from-payload"

    def test_returns_none_when_nothing_found(self):
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={}, payload={})
        msg.conversation_id = ""
        assert self.resolver.extract_session_id(msg) is None

    def test_content_not_dict_is_skipped(self):
        msg = _make_msg(session_id=None, headers={}, metadata={}, payload={})
        msg.conversation_id = ""
        msg.content = "plain string"  # type: ignore[assignment]
        assert self.resolver.extract_session_id(msg) is None

    def test_payload_not_dict_is_skipped(self):
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={})
        msg.conversation_id = ""
        msg.payload = 42  # type: ignore[assignment]
        assert self.resolver.extract_session_id(msg) is None

    def test_metadata_not_dict_is_skipped(self):
        msg = _make_msg(session_id=None, headers={}, content={}, payload={})
        msg.conversation_id = ""
        msg.metadata = "not-a-dict"  # type: ignore[assignment]
        assert self.resolver.extract_session_id(msg) is None

    def test_session_id_field_truthy_integer_converted_to_str(self):
        msg = _make_msg(session_id=None, headers={})
        msg.session_id = 12345  # type: ignore[assignment]
        assert self.resolver.extract_session_id(msg) == "12345"

    def test_uppercase_header_takes_precedence_over_lowercase(self):
        msg = _make_msg(
            session_id=None,
            headers={"X-Session-ID": "upper", "x-session-id": "lower"},
        )
        # `or` short-circuits — uppercase wins
        assert self.resolver.extract_session_id(msg) == "upper"

    def test_headers_present_but_both_header_values_falsy(self):
        """Headers dict non-empty but both X-Session-ID values are empty — hdr is falsy."""
        msg = _make_msg(
            session_id=None,
            headers={"X-Session-ID": "", "x-session-id": ""},
            metadata={},
            content={},
            payload={},
        )
        msg.conversation_id = ""
        assert self.resolver.extract_session_id(msg) is None


# ---------------------------------------------------------------------------
# extract_governance_session_id() — all priority branches
# ---------------------------------------------------------------------------


class TestExtractGovernanceSessionId:
    def setup_method(self):
        cfg = _make_config()
        self.resolver = SessionContextResolver(cfg, _make_manager())

    def test_priority_1_session_id_field(self):
        msg = _make_msg(session_id="gov-from-field")
        assert self.resolver.extract_governance_session_id(msg) == "gov-from-field"

    def test_priority_2_header_uppercase(self):
        msg = _make_msg(session_id=None, headers={"X-Session-ID": "gov-header"})
        assert self.resolver.extract_governance_session_id(msg) == "gov-header"

    def test_priority_2_header_lowercase(self):
        msg = _make_msg(session_id=None, headers={"x-session-id": "gov-lower"})
        assert self.resolver.extract_governance_session_id(msg) == "gov-lower"

    def test_priority_3_metadata(self):
        msg = _make_msg(session_id=None, headers={}, metadata={"session_id": "gov-meta"})
        assert self.resolver.extract_governance_session_id(msg) == "gov-meta"

    def test_priority_4_content(self):
        msg = _make_msg(
            session_id=None,
            headers={},
            metadata={},
            content={"session_id": "gov-content"},
        )
        assert self.resolver.extract_governance_session_id(msg) == "gov-content"

    def test_returns_none_when_nothing_found(self):
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={})
        assert self.resolver.extract_governance_session_id(msg) is None

    def test_does_not_fall_through_to_conversation_id(self):
        """governance variant does not include conversation_id in its chain."""
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={})
        msg.conversation_id = "should-not-appear"
        assert self.resolver.extract_governance_session_id(msg) is None

    def test_does_not_fall_through_to_payload(self):
        """governance variant does not include payload in its chain."""
        msg = _make_msg(session_id=None, headers={}, metadata={}, content={})
        msg.payload = {"session_id": "in-payload"}
        assert self.resolver.extract_governance_session_id(msg) is None

    def test_metadata_not_dict_skipped(self):
        msg = _make_msg(session_id=None, headers={}, content={})
        msg.metadata = "not-a-dict"  # type: ignore[assignment]
        assert self.resolver.extract_governance_session_id(msg) is None

    def test_content_not_dict_skipped(self):
        msg = _make_msg(session_id=None, headers={}, metadata={})
        msg.content = "not-a-dict"  # type: ignore[assignment]
        assert self.resolver.extract_governance_session_id(msg) is None

    def test_headers_present_but_both_header_values_falsy(self):
        """Headers dict non-empty but both X-Session-ID values are empty — hdr is falsy."""
        msg = _make_msg(
            session_id=None,
            headers={"X-Session-ID": "", "x-session-id": ""},
            metadata={},
            content={},
        )
        assert self.resolver.extract_governance_session_id(msg) is None


# ---------------------------------------------------------------------------
# get_metrics()
# ---------------------------------------------------------------------------


class TestGetMetrics:
    def test_zero_total_gives_zero_rate(self):
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, _make_manager())
        metrics = resolver.get_metrics()
        assert metrics["resolution_rate"] == 0.0
        assert metrics["resolved_count"] == 0
        assert metrics["not_found_count"] == 0
        assert metrics["error_count"] == 0

    async def test_resolution_rate_calculation(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        # Resolve successfully twice
        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        await resolver.resolve(msg)
        await resolver.resolve(msg)

        metrics = resolver.get_metrics()
        assert metrics["resolved_count"] == 2
        assert metrics["resolution_rate"] == 1.0

    async def test_mixed_counts_give_partial_rate(self):
        mgr = _make_manager(return_ctx=None)  # not found
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        await resolver.resolve(msg)  # not found

        # Now patch manager to return context
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr.get = AsyncMock(return_value=ctx)
        await resolver.resolve(msg)  # success

        metrics = resolver.get_metrics()
        assert metrics["resolved_count"] == 1
        assert metrics["not_found_count"] == 1
        assert metrics["error_count"] == 0
        # rate = 1 / (1 + 1 + 0) = 0.5
        assert metrics["resolution_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Thread-safety: concurrent resolve() calls
# ---------------------------------------------------------------------------


class TestConcurrentResolve:
    async def test_concurrent_resolves_no_race_condition(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        tasks = [asyncio.create_task(resolver.resolve(msg)) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        assert all(r is ctx for r in results)
        assert resolver.get_metrics()["resolved_count"] == 20

    async def test_concurrent_error_increments_error_count(self):
        mgr = AsyncMock()
        mgr.get = AsyncMock(side_effect=RuntimeError("concurrent error"))
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(session_id="sess-1", tenant_id="tenant-A")
        tasks = [asyncio.create_task(resolver.resolve(msg)) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(r is None for r in results)
        assert resolver.get_metrics()["error_count"] == 5


# ---------------------------------------------------------------------------
# enabled property
# ---------------------------------------------------------------------------


class TestEnabledProperty:
    def test_enabled_true(self):
        cfg = _make_config(enable_session_governance=True)
        r = SessionContextResolver(cfg, _make_manager())
        assert r.enabled is True

    def test_enabled_false_no_manager(self):
        cfg = _make_config(enable_session_governance=True)
        r = SessionContextResolver(cfg, None)
        assert r.enabled is False

    def test_enabled_false_governance_off(self):
        cfg = _make_config(enable_session_governance=False)
        r = SessionContextResolver(cfg, _make_manager())
        assert r.enabled is False


# ---------------------------------------------------------------------------
# Session ID extraction via resolve() — integration
# ---------------------------------------------------------------------------


class TestResolveSessionIdSources:
    """Verify resolve() uses governance priority chain to find session_id."""

    async def test_resolves_from_header(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(
            session_id=None,
            headers={"X-Session-ID": "header-sess"},
            tenant_id="tenant-A",
        )
        result = await resolver.resolve(msg)
        assert result is ctx
        mgr.get.assert_called_once_with("header-sess", "tenant-A")

    async def test_resolves_from_metadata(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(
            session_id=None,
            headers={},
            metadata={"session_id": "meta-sess"},
            tenant_id="tenant-A",
        )
        result = await resolver.resolve(msg)
        assert result is ctx
        mgr.get.assert_called_once_with("meta-sess", "tenant-A")

    async def test_resolves_from_content_dict(self):
        ctx = _make_session_context(tenant_id="tenant-A")
        mgr = _make_manager(return_ctx=ctx)
        cfg = _make_config()
        resolver = SessionContextResolver(cfg, mgr)

        msg = _make_msg(
            session_id=None,
            headers={},
            metadata={},
            content={"session_id": "content-sess"},
            tenant_id="tenant-A",
        )
        result = await resolver.resolve(msg)
        assert result is ctx
        mgr.get.assert_called_once_with("content-sess", "tenant-A")
