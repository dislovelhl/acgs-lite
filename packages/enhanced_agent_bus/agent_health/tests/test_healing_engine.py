"""
Unit tests for HealingEngine — constitutional tier-routing.
Constitutional Hash: 608508a9bd224290

Marked @pytest.mark.constitutional for 95%+ coverage gate.

TDD RED: All tests fail until healing_engine.py is implemented.

Coverage:
- ADVISORY tier (Tier 1): QuarantineManager → HITLRequestor; GracefulRestarter never called
- BOUNDED tier (Tier 2): SupervisorNotifier + approval await; falls back to ADVISORY on SLA timeout
- HUMAN_APPROVED tier (Tier 3): GracefulRestarter autonomously; no HITL / supervisor
- Override modes: SUPPRESS_HEALING, FORCE_RESTART, FORCE_QUARANTINE
- Audit log written BEFORE action dispatch (FR-009 / spec constraint)
- HITL deduplication (spec edge case 2)
- All external deps mocked; no real Redis or HTTP
"""

from __future__ import annotations

import pytest

pytest.importorskip("fakeredis")

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# RED: This import fails until healing_engine.py is created.
from enhanced_agent_bus.agent_health.healing_engine import HealingEngine
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_ID = "test-agent-healing-001"
CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    tier: AutonomyTier = AutonomyTier.ADVISORY,
    state: HealthState = HealthState.DEGRADED,
) -> AgentHealthRecord:
    return AgentHealthRecord(
        agent_id=AGENT_ID,
        health_state=state,
        consecutive_failure_count=6,
        memory_usage_pct=55.0,
        last_error_type="ValueError",
        last_event_at=datetime.now(UTC),
        autonomy_tier=tier,
    )


def _make_override(mode: OverrideMode) -> HealingOverride:
    return HealingOverride(
        agent_id=AGENT_ID,
        mode=mode,
        reason="operator test override",
        issued_by="test-operator",
        issued_at=datetime.now(UTC),
    )


def _fake_audit_event() -> MagicMock:
    event = MagicMock()
    event.chain_hash = "fake-chain-hash-001"
    return event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> AsyncMock:
    m = AsyncMock()
    m.get_override.return_value = None  # no active override by default
    m.save_healing_action.return_value = None
    return m


@pytest.fixture
def audit_log_client() -> AsyncMock:
    m = AsyncMock()
    m.log.return_value = _fake_audit_event()
    return m


@pytest.fixture
def restarter() -> AsyncMock:
    m = AsyncMock()
    m.execute.return_value = None
    return m


@pytest.fixture
def quarantine_manager() -> AsyncMock:
    m = AsyncMock()
    m.execute.return_value = None
    return m


@pytest.fixture
def hitl_requestor() -> AsyncMock:
    m = AsyncMock()
    m.execute.return_value = "review-001"
    return m


@pytest.fixture
def supervisor_notifier() -> AsyncMock:
    m = AsyncMock()
    m.notify.return_value = None
    return m


@pytest.fixture
def thresholds() -> AgentHealthThresholds:
    return AgentHealthThresholds()


def _make_engine(
    store: AsyncMock,
    audit_log_client: AsyncMock,
    restarter: AsyncMock,
    quarantine_manager: AsyncMock,
    hitl_requestor: AsyncMock,
    supervisor_notifier: AsyncMock,
    thresholds: AgentHealthThresholds,
    bounded_approval_awaiter=None,
) -> HealingEngine:
    return HealingEngine(
        store=store,
        audit_log_client=audit_log_client,
        restarter=restarter,
        quarantine_manager=quarantine_manager,
        hitl_requestor=hitl_requestor,
        supervisor_notifier=supervisor_notifier,
        thresholds=thresholds,
        bounded_approval_awaiter=bounded_approval_awaiter,
    )


# ---------------------------------------------------------------------------
# ADVISORY (Tier 1) tests
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestAdvisoryTier:
    """ADVISORY: quarantine + HITL request; graceful restart never called."""

    async def test_advisory_calls_quarantine_then_hitl(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        record = _make_record(tier=AutonomyTier.ADVISORY)

        result = await engine.handle(AGENT_ID, HealingTrigger.FAILURE_LOOP, record)

        quarantine_manager.execute.assert_called_once_with(AGENT_ID, store)
        hitl_requestor.execute.assert_called_once()
        restarter.execute.assert_not_called()
        supervisor_notifier.notify.assert_not_called()

    async def test_advisory_returns_hitl_request_action(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        assert result is not None
        assert result.action_type == HealingActionType.HITL_REQUEST
        assert result.tier_determined_by == AutonomyTier.ADVISORY
        assert result.agent_id == AGENT_ID
        assert result.trigger == HealingTrigger.FAILURE_LOOP
        assert result.completed_at is not None
        assert result.audit_event_id != ""
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_advisory_audit_log_before_quarantine(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """FR-009: audit log entry must be written BEFORE quarantine executes."""
        call_order: list[str] = []

        async def _audit_log(*args, **kwargs):
            call_order.append("audit")
            return _fake_audit_event()

        async def _quarantine_exec(agent_id, store_):
            call_order.append("quarantine")

        audit_log_client.log.side_effect = _audit_log
        quarantine_manager.execute.side_effect = _quarantine_exec

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        assert "audit" in call_order
        assert "quarantine" in call_order
        assert call_order.index("audit") < call_order.index("quarantine")

    async def test_advisory_hitl_deduplication_engine_calls_once(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """Spec edge case 2: engine calls HITLRequestor exactly once (requestor handles dedup internally)."""
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        hitl_requestor.execute.assert_called_once()

    async def test_advisory_persists_action_to_store(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        store.save_healing_action.assert_called_once()
        saved = store.save_healing_action.call_args[0][0]
        assert isinstance(saved, HealingAction)
        assert saved.completed_at is not None

    async def test_advisory_emits_metrics(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """HEALING_ACTIONS_COUNTER must be incremented on every action."""
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        from enhanced_agent_bus.agent_health import metrics as agent_metrics

        before = agent_metrics.HEALING_ACTIONS_COUNTER.labels(
            agent_id=AGENT_ID,
            autonomy_tier=AutonomyTier.ADVISORY.value,
            action_type=HealingActionType.HITL_REQUEST.value,
            trigger=HealingTrigger.FAILURE_LOOP.value,
        )._value.get()

        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        after = agent_metrics.HEALING_ACTIONS_COUNTER.labels(
            agent_id=AGENT_ID,
            autonomy_tier=AutonomyTier.ADVISORY.value,
            action_type=HealingActionType.HITL_REQUEST.value,
            trigger=HealingTrigger.FAILURE_LOOP.value,
        )._value.get()

        assert after == before + 1.0


# ---------------------------------------------------------------------------
# BOUNDED (Tier 2) tests
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestBoundedTier:
    """BOUNDED: supervisor notify → wait for approval; escalate to ADVISORY on SLA timeout."""

    async def test_bounded_notifies_supervisor(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        async def _approve(_agent_id: str) -> bool:
            return True

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
            bounded_approval_awaiter=_approve,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.BOUNDED)
        )

        supervisor_notifier.notify.assert_called_once_with(
            AGENT_ID, AutonomyTier.BOUNDED, HealingTrigger.FAILURE_LOOP
        )

    async def test_bounded_restarts_after_approval(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        async def _approve(_agent_id: str) -> bool:
            return True

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
            bounded_approval_awaiter=_approve,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.BOUNDED)
        )

        restarter.execute.assert_called_once_with(AGENT_ID, thresholds)
        quarantine_manager.execute.assert_not_called()
        hitl_requestor.execute.assert_not_called()

        assert result is not None
        assert result.action_type == HealingActionType.GRACEFUL_RESTART
        assert result.tier_determined_by == AutonomyTier.BOUNDED

    async def test_bounded_escalates_to_advisory_on_sla_timeout(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """Spec edge case 6: supervisor approval SLA elapses → fall back to Tier 1 behavior."""

        async def _timeout(_agent_id: str) -> bool:
            raise TimeoutError

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
            bounded_approval_awaiter=_timeout,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.BOUNDED)
        )

        quarantine_manager.execute.assert_called_once_with(AGENT_ID, store)
        hitl_requestor.execute.assert_called_once()
        restarter.execute.assert_not_called()

        assert result is not None
        assert result.action_type == HealingActionType.HITL_REQUEST

    async def test_bounded_no_awaiter_escalates_to_advisory(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """No approval awaiter provided → safe fallback to ADVISORY (fail-closed)."""
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
            bounded_approval_awaiter=None,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.BOUNDED)
        )

        quarantine_manager.execute.assert_called_once_with(AGENT_ID, store)
        hitl_requestor.execute.assert_called_once()
        restarter.execute.assert_not_called()

    async def test_bounded_audit_log_before_supervisor_notify(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """FR-009: audit log entry written BEFORE supervisor notification."""
        call_order: list[str] = []

        async def _audit_log(*args, **kwargs):
            call_order.append("audit")
            return _fake_audit_event()

        async def _notify(agent_id, tier, trigger):
            call_order.append("notify")

        audit_log_client.log.side_effect = _audit_log
        supervisor_notifier.notify.side_effect = _notify

        async def _approve(_agent_id: str) -> bool:
            return True

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
            bounded_approval_awaiter=_approve,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.BOUNDED)
        )

        assert call_order.index("audit") < call_order.index("notify")


# ---------------------------------------------------------------------------
# HUMAN_APPROVED (Tier 3) tests
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestHumanApprovedTier:
    """HUMAN_APPROVED: autonomously calls GracefulRestarter; no HITL or supervisor."""

    async def test_human_approved_calls_restarter(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.MEMORY_EXHAUSTION, _make_record(AutonomyTier.HUMAN_APPROVED)
        )

        restarter.execute.assert_called_once_with(AGENT_ID, thresholds)
        quarantine_manager.execute.assert_not_called()
        hitl_requestor.execute.assert_not_called()
        supervisor_notifier.notify.assert_not_called()

        assert result is not None
        assert result.action_type == HealingActionType.GRACEFUL_RESTART
        assert result.tier_determined_by == AutonomyTier.HUMAN_APPROVED

    async def test_human_approved_audit_log_before_restart(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """FR-009: audit log written BEFORE calling GracefulRestarter."""
        call_order: list[str] = []

        async def _audit_log(*args, **kwargs):
            call_order.append("audit")
            return _fake_audit_event()

        async def _restart(agent_id, thresholds_):
            call_order.append("restart")

        audit_log_client.log.side_effect = _audit_log
        restarter.execute.side_effect = _restart

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.HUMAN_APPROVED)
        )

        assert call_order.index("audit") < call_order.index("restart")


# ---------------------------------------------------------------------------
# Override suppression tests
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestOverrides:
    """Operator overrides bypass tier routing."""

    async def test_suppress_healing_no_action_taken(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """US-008 / SC-005: SUPPRESS_HEALING → no action; audit log records suppression."""
        store.get_override.return_value = _make_override(OverrideMode.SUPPRESS_HEALING)

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        restarter.execute.assert_not_called()
        quarantine_manager.execute.assert_not_called()
        hitl_requestor.execute.assert_not_called()
        supervisor_notifier.notify.assert_not_called()
        assert result is None

    async def test_suppress_healing_audit_records_suppression(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        store.get_override.return_value = _make_override(OverrideMode.SUPPRESS_HEALING)

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.ADVISORY)
        )

        audit_log_client.log.assert_called_once()
        call_kwargs = audit_log_client.log.call_args
        # The action dict should mention suppression
        action_dict = call_kwargs.kwargs.get("action") or call_kwargs[1].get("action", {})
        assert "suppress" in str(action_dict).lower() or "suppress" in str(call_kwargs).lower()

    async def test_force_restart_bypasses_tier_calls_restarter(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        store.get_override.return_value = _make_override(OverrideMode.FORCE_RESTART)

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        result = await engine.handle(
            AGENT_ID,
            HealingTrigger.MANUAL,
            _make_record(AutonomyTier.ADVISORY),  # would normally quarantine
        )

        restarter.execute.assert_called_once_with(AGENT_ID, thresholds)
        quarantine_manager.execute.assert_not_called()
        hitl_requestor.execute.assert_not_called()

        assert result is not None
        assert result.action_type == HealingActionType.GRACEFUL_RESTART

    async def test_force_quarantine_bypasses_tier_calls_quarantine(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        store.get_override.return_value = _make_override(OverrideMode.FORCE_QUARANTINE)

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        result = await engine.handle(
            AGENT_ID,
            HealingTrigger.MANUAL,
            _make_record(AutonomyTier.HUMAN_APPROVED),  # would normally restart
        )

        quarantine_manager.execute.assert_called_once_with(AGENT_ID, store)
        restarter.execute.assert_not_called()
        hitl_requestor.execute.assert_not_called()

        assert result is not None
        assert result.action_type == HealingActionType.QUARANTINE

    async def test_force_restart_audit_log_before_action(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """FR-009: audit log written BEFORE FORCE_RESTART action executes."""
        store.get_override.return_value = _make_override(OverrideMode.FORCE_RESTART)
        call_order: list[str] = []

        async def _audit_log(*args, **kwargs):
            call_order.append("audit")
            return _fake_audit_event()

        async def _restart(agent_id, thresholds_):
            call_order.append("restart")

        audit_log_client.log.side_effect = _audit_log
        restarter.execute.side_effect = _restart

        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        await engine.handle(AGENT_ID, HealingTrigger.MANUAL, _make_record(AutonomyTier.ADVISORY))

        assert call_order.index("audit") < call_order.index("restart")


# ---------------------------------------------------------------------------
# Constitutional hash validation
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestConstitutionalHashValidation:
    async def test_handle_validates_constitutional_hash(
        self,
        store,
        audit_log_client,
        restarter,
        quarantine_manager,
        hitl_requestor,
        supervisor_notifier,
        thresholds,
    ) -> None:
        """HealingEngine must validate CONSTITUTIONAL_HASH == '608508a9bd224290'."""
        engine = _make_engine(
            store,
            audit_log_client,
            restarter,
            quarantine_manager,
            hitl_requestor,
            supervisor_notifier,
            thresholds,
        )
        # Smoke test: handle completes without raising on a valid hash environment
        result = await engine.handle(
            AGENT_ID, HealingTrigger.FAILURE_LOOP, _make_record(AutonomyTier.HUMAN_APPROVED)
        )
        assert result is not None
