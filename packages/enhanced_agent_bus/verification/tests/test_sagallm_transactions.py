"""
Tests for SagaLLM Transaction System (sagallm_transactions.py)
Constitutional Hash: 608508a9bd224290

Covers:
- TransactionState and TransactionAction enums
- SagaAction, TransactionCheckpoint, SagaTransaction dataclasses
- SagaLLMEngine: full lifecycle including retry, compensation, timeout
- saga_transaction context manager
- create_governance_transaction convenience function
- get_saga_engine global accessor
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.verification.sagallm_transactions import (
    SagaAction,
    SagaLLMEngine,
    SagaTransaction,
    TransactionAction,
    TransactionCheckpoint,
    TransactionState,
    create_governance_transaction,
    get_saga_engine,
    saga_transaction,
)

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestTransactionState:
    def test_all_states_defined(self):
        names = {s.name for s in TransactionState}
        expected = {
            "INITIALIZED",
            "ACTIVE",
            "COMPENSATING",
            "COMPENSATED",
            "COMPLETED",
            "FAILED",
            "TIMED_OUT",
        }
        assert names == expected

    def test_state_values(self):
        assert TransactionState.INITIALIZED.value == "initialized"
        assert TransactionState.ACTIVE.value == "active"
        assert TransactionState.COMPENSATING.value == "compensating"
        assert TransactionState.COMPENSATED.value == "compensated"
        assert TransactionState.COMPLETED.value == "completed"
        assert TransactionState.FAILED.value == "failed"
        assert TransactionState.TIMED_OUT.value == "timed_out"


class TestTransactionAction:
    def test_all_actions_defined(self):
        names = {a.name for a in TransactionAction}
        expected = {
            "GOVERNANCE_DECISION",
            "POLICY_VALIDATION",
            "ACCESS_CONTROL",
            "AUDIT_LOGGING",
            "RESOURCE_ALLOCATION",
            "CONSTITUTIONAL_CHECK",
        }
        assert names == expected

    def test_action_values(self):
        assert TransactionAction.GOVERNANCE_DECISION.value == "governance_decision"
        assert TransactionAction.POLICY_VALIDATION.value == "policy_validation"
        assert TransactionAction.ACCESS_CONTROL.value == "access_control"
        assert TransactionAction.AUDIT_LOGGING.value == "audit_logging"
        assert TransactionAction.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert TransactionAction.CONSTITUTIONAL_CHECK.value == "constitutional_check"


# ---------------------------------------------------------------------------
# SagaAction dataclass
# ---------------------------------------------------------------------------


class TestSagaAction:
    def _make_action(self) -> SagaAction:
        return SagaAction(
            action_id="action-1",
            action_type=TransactionAction.GOVERNANCE_DECISION,
            description="Test action",
            execute_func=AsyncMock(return_value={"ok": True}),
            compensate_func=AsyncMock(return_value={"reverted": True}),
        )

    def test_defaults(self):
        action = self._make_action()
        assert action.timeout_s == 30.0
        assert action.retry_count == 0
        assert action.max_retries == 3
        assert action.executed_at is None
        assert action.compensated_at is None
        assert action.execution_result is None
        assert action.compensation_result is None
        assert action.metadata == {}
        assert action.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict_without_timestamps(self):
        action = self._make_action()
        d = action.to_dict()
        assert d["action_id"] == "action-1"
        assert d["action_type"] == "governance_decision"
        assert d["description"] == "Test action"
        assert d["timeout_s"] == 30.0
        assert d["retry_count"] == 0
        assert d["max_retries"] == 3
        assert d["executed_at"] is None
        assert d["compensated_at"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_timestamps(self):
        action = self._make_action()
        now = datetime.now(UTC)
        action.executed_at = now
        action.compensated_at = now
        d = action.to_dict()
        assert d["executed_at"] == now.isoformat()
        assert d["compensated_at"] == now.isoformat()

    def test_constitutional_hash_present(self):
        action = self._make_action()
        assert action.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# TransactionCheckpoint dataclass
# ---------------------------------------------------------------------------


class TestTransactionCheckpoint:
    def _make_checkpoint(self) -> TransactionCheckpoint:
        return TransactionCheckpoint(
            checkpoint_id="cp-1",
            checkpoint_name="pre_validation",
            state_before={"policy": "enabled"},
            actions_executed=["action-1"],
        )

    def test_defaults(self):
        cp = self._make_checkpoint()
        assert isinstance(cp.created_at, datetime)
        assert cp.metadata == {}
        assert cp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self):
        cp = self._make_checkpoint()
        d = cp.to_dict()
        assert d["checkpoint_id"] == "cp-1"
        assert d["checkpoint_name"] == "pre_validation"
        assert d["state_before"] == {"policy": "enabled"}
        assert d["actions_executed"] == ["action-1"]
        assert "created_at" in d
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# SagaTransaction dataclass
# ---------------------------------------------------------------------------


class TestSagaTransaction:
    def _make_transaction(self) -> SagaTransaction:
        return SagaTransaction(
            transaction_id="txn-1",
            description="Test transaction",
        )

    def test_defaults(self):
        txn = self._make_transaction()
        assert txn.state == TransactionState.INITIALIZED
        assert txn.actions == []
        assert txn.checkpoints == []
        assert txn.started_at is None
        assert txn.completed_at is None
        assert txn.failed_at is None
        assert txn.failure_reason is None
        assert txn.compensation_log == []
        assert txn.metadata == {}
        assert txn.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self):
        txn = self._make_transaction()
        d = txn.to_dict()
        assert d["transaction_id"] == "txn-1"
        assert d["description"] == "Test transaction"
        assert d["state"] == "initialized"
        assert d["actions"] == []
        assert d["checkpoints"] == []
        assert d["started_at"] is None
        assert d["completed_at"] is None
        assert d["failed_at"] is None
        assert d["failure_reason"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_timestamps(self):
        txn = self._make_transaction()
        now = datetime.now(UTC)
        txn.started_at = now
        txn.completed_at = now
        txn.failed_at = now
        txn.failure_reason = "test failure"
        d = txn.to_dict()
        assert d["started_at"] == now.isoformat()
        assert d["completed_at"] == now.isoformat()
        assert d["failed_at"] == now.isoformat()
        assert d["failure_reason"] == "test failure"


# ---------------------------------------------------------------------------
# SagaLLMEngine - initialization and basic operations
# ---------------------------------------------------------------------------


class TestSagaLLMEngineInit:
    def test_default_init(self):
        engine = SagaLLMEngine()
        assert engine.max_transaction_time == 300.0
        assert engine.default_action_timeout == 30.0
        assert engine.compensation_timeout == 60.0
        assert engine._active_transactions == {}
        assert engine._completed_transactions == {}

    def test_custom_init(self):
        engine = SagaLLMEngine(
            max_transaction_time=120.0,
            default_action_timeout=10.0,
            compensation_timeout=20.0,
        )
        assert engine.max_transaction_time == 120.0
        assert engine.default_action_timeout == 10.0
        assert engine.compensation_timeout == 20.0


class TestSagaLLMEngineCreateTransaction:
    def test_creates_transaction(self):
        engine = SagaLLMEngine()
        txn = engine.create_transaction("Test")
        assert txn.description == "Test"
        assert txn.state == TransactionState.INITIALIZED
        assert txn.transaction_id in engine._active_transactions

    def test_creates_with_metadata(self):
        engine = SagaLLMEngine()
        txn = engine.create_transaction("Test", {"key": "value"})
        assert txn.metadata == {"key": "value"}

    def test_creates_with_no_metadata(self):
        engine = SagaLLMEngine()
        txn = engine.create_transaction("Test")
        assert txn.metadata == {}

    def test_unique_ids(self):
        engine = SagaLLMEngine()
        ids = {engine.create_transaction(f"T{i}").transaction_id for i in range(5)}
        assert len(ids) == 5


class TestSagaLLMEngineAddAction:
    def setup_method(self):
        self.engine = SagaLLMEngine()
        self.txn = self.engine.create_transaction("Test")

    def test_add_action_returns_saga_action(self):
        action = self.engine.add_action(
            self.txn,
            TransactionAction.POLICY_VALIDATION,
            "Validate",
            AsyncMock(),
        )
        assert isinstance(action, SagaAction)
        assert action.action_type == TransactionAction.POLICY_VALIDATION
        assert len(self.txn.actions) == 1

    def test_add_action_with_compensation(self):
        execute = AsyncMock()
        compensate = AsyncMock()
        action = self.engine.add_action(
            self.txn,
            TransactionAction.GOVERNANCE_DECISION,
            "Decide",
            execute,
            compensate,
        )
        assert action.compensate_func is compensate

    def test_add_action_custom_timeout(self):
        action = self.engine.add_action(
            self.txn,
            TransactionAction.AUDIT_LOGGING,
            "Log",
            AsyncMock(),
            timeout_s=5.0,
        )
        assert action.timeout_s == 5.0

    def test_add_action_uses_engine_default_timeout(self):
        engine = SagaLLMEngine(default_action_timeout=15.0)
        txn = engine.create_transaction("T")
        action = engine.add_action(txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock())
        assert action.timeout_s == 15.0

    def test_add_action_custom_max_retries(self):
        action = self.engine.add_action(
            self.txn,
            TransactionAction.ACCESS_CONTROL,
            "Check",
            AsyncMock(),
            max_retries=1,
        )
        assert action.max_retries == 1

    def test_add_action_with_metadata(self):
        action = self.engine.add_action(
            self.txn,
            TransactionAction.RESOURCE_ALLOCATION,
            "Allocate",
            AsyncMock(),
            metadata={"priority": "high"},
        )
        assert action.metadata == {"priority": "high"}

    def test_add_action_raises_when_not_initialized(self):
        self.txn.state = TransactionState.ACTIVE
        with pytest.raises(ValueError, match="Cannot add actions"):
            self.engine.add_action(self.txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock())

    def test_add_multiple_actions(self):
        for i in range(3):
            self.engine.add_action(
                self.txn, TransactionAction.AUDIT_LOGGING, f"Action {i}", AsyncMock()
            )
        assert len(self.txn.actions) == 3


class TestSagaLLMEngineAddCheckpoint:
    def setup_method(self):
        self.engine = SagaLLMEngine()
        self.txn = self.engine.create_transaction("Test")

    def test_add_checkpoint_returns_checkpoint(self):
        cp = self.engine.add_checkpoint(
            self.txn,
            "pre_step",
            {"counter": 0},
        )
        assert isinstance(cp, TransactionCheckpoint)
        assert cp.checkpoint_name == "pre_step"
        assert len(self.txn.checkpoints) == 1

    def test_checkpoint_captures_executed_actions(self):
        action = self.engine.add_action(
            self.txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock()
        )
        action.executed_at = datetime.now(UTC)  # Mark as executed
        cp = self.engine.add_checkpoint(self.txn, "after_log", {})
        assert action.action_id in cp.actions_executed

    def test_checkpoint_excludes_unexecuted_actions(self):
        self.engine.add_action(self.txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock())
        cp = self.engine.add_checkpoint(self.txn, "before_execution", {})
        assert cp.actions_executed == []

    def test_checkpoint_with_metadata(self):
        cp = self.engine.add_checkpoint(self.txn, "step", {}, metadata={"note": "important"})
        assert cp.metadata == {"note": "important"}


# ---------------------------------------------------------------------------
# SagaLLMEngine - execute_transaction
# ---------------------------------------------------------------------------


class TestSagaLLMEngineExecute:
    def setup_method(self):
        self.engine = SagaLLMEngine()

    async def test_execute_empty_transaction_succeeds(self):
        txn = self.engine.create_transaction("Empty")
        result = await self.engine.execute_transaction(txn)
        assert result is True
        assert txn.state == TransactionState.COMPLETED
        assert txn.completed_at is not None

    async def test_execute_moves_to_completed(self):
        txn = self.engine.create_transaction("Test")
        self.engine.add_action(
            txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock(return_value="ok")
        )
        result = await self.engine.execute_transaction(txn)
        assert result is True
        assert txn.state == TransactionState.COMPLETED
        assert txn.transaction_id in self.engine._completed_transactions
        assert txn.transaction_id not in self.engine._active_transactions

    async def test_execute_sets_started_at(self):
        txn = self.engine.create_transaction("T")
        await self.engine.execute_transaction(txn)
        assert txn.started_at is not None

    async def test_execute_raises_if_not_initialized(self):
        txn = self.engine.create_transaction("T")
        txn.state = TransactionState.ACTIVE
        with pytest.raises(ValueError, match="Cannot execute transaction"):
            await self.engine.execute_transaction(txn)

    async def test_execute_action_failure_triggers_compensation(self):
        txn = self.engine.create_transaction("T")
        execute = AsyncMock(side_effect=ValueError("execute failed"))
        compensate = AsyncMock(return_value="compensated")
        self.engine.add_action(
            txn,
            TransactionAction.GOVERNANCE_DECISION,
            "Fail",
            execute,
            compensate,
            max_retries=0,
        )
        result = await self.engine.execute_transaction(txn)
        assert result is False
        assert txn.state == TransactionState.COMPENSATED

    async def test_execute_timeout_triggers_compensation(self):
        txn = self.engine.create_transaction("T")

        async def slow():
            await asyncio.sleep(100)

        self.engine.add_action(
            txn,
            TransactionAction.POLICY_VALIDATION,
            "Slow",
            slow,
            max_retries=0,
            timeout_s=0.01,
        )
        result = await self.engine.execute_transaction(txn)
        assert result is False
        assert txn.state in (TransactionState.TIMED_OUT, TransactionState.COMPENSATED)

    async def test_execute_multi_action_all_succeed(self):
        txn = self.engine.create_transaction("Multi")
        for _ in range(3):
            self.engine.add_action(
                txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock(return_value="ok")
            )
        result = await self.engine.execute_transaction(txn)
        assert result is True
        assert all(a.executed_at is not None for a in txn.actions)

    async def test_execute_partial_failure_compensates_executed(self):
        txn = self.engine.create_transaction("Partial")
        compensate_1 = AsyncMock(return_value="comp1")
        self.engine.add_action(
            txn,
            TransactionAction.CONSTITUTIONAL_CHECK,
            "Check",
            AsyncMock(return_value="ok"),
            compensate_1,
        )
        self.engine.add_action(
            txn,
            TransactionAction.GOVERNANCE_DECISION,
            "Fail",
            AsyncMock(side_effect=RuntimeError("fail")),
            None,
            max_retries=0,
        )
        result = await self.engine.execute_transaction(txn)
        assert result is False
        # First action was executed, so compensation should have been attempted
        compensate_1.assert_awaited()

    async def test_execute_operation_error_triggers_compensation(self):
        txn = self.engine.create_transaction("T")
        self.engine.add_action(
            txn,
            TransactionAction.POLICY_VALIDATION,
            "Err",
            AsyncMock(side_effect=AttributeError("bad attr")),
            max_retries=0,
        )
        result = await self.engine.execute_transaction(txn)
        assert result is False
        assert txn.state == TransactionState.COMPENSATED

    async def test_execute_timeout_error_sets_timed_out_state(self):
        """Cover lines 302-306: TimeoutError raised in the for-loop body."""
        txn = self.engine.create_transaction("timeout_outer")

        async def raise_timeout(t, a, idx):
            raise TimeoutError("outer timeout")

        self.engine.add_action(txn, TransactionAction.POLICY_VALIDATION, "T", AsyncMock())
        original = self.engine._execute_action_with_retry
        self.engine._execute_action_with_retry = raise_timeout
        try:
            result = await self.engine.execute_transaction(txn)
        finally:
            self.engine._execute_action_with_retry = original

        assert result is False
        assert txn.state == TransactionState.COMPENSATED  # compensate runs after TIMED_OUT set

    async def test_execute_operation_error_outer_handler(self):
        """Cover lines 308-315: RuntimeError propagated from _execute_action_with_retry."""
        txn = self.engine.create_transaction("op_error_outer")

        async def raise_runtime(t, a, idx):
            raise RuntimeError("unexpected propagation")

        self.engine.add_action(txn, TransactionAction.POLICY_VALIDATION, "T", AsyncMock())
        original = self.engine._execute_action_with_retry
        self.engine._execute_action_with_retry = raise_runtime
        try:
            result = await self.engine.execute_transaction(txn)
        finally:
            self.engine._execute_action_with_retry = original

        assert result is False
        assert txn.state == TransactionState.COMPENSATED
        assert txn.failure_reason is not None


# ---------------------------------------------------------------------------
# SagaLLMEngine - _execute_action_with_retry
# ---------------------------------------------------------------------------


class TestExecuteActionWithRetry:
    def setup_method(self):
        self.engine = SagaLLMEngine(default_action_timeout=5.0)

    def _make_txn_action(self, execute_func, max_retries=3):
        engine = self.engine
        txn = engine.create_transaction("retry_test")
        action = engine.add_action(
            txn,
            TransactionAction.POLICY_VALIDATION,
            "Test",
            execute_func,
            max_retries=max_retries,
        )
        return txn, action

    async def test_success_first_attempt(self):
        execute = AsyncMock(return_value="done")
        txn, action = self._make_txn_action(execute)
        result = await self.engine._execute_action_with_retry(txn, action, 0)
        assert result is True
        assert action.executed_at is not None
        assert action.execution_result == "done"
        assert action.retry_count == 0
        execute.assert_awaited_once()

    async def test_retry_on_value_error(self):
        execute = AsyncMock(side_effect=[ValueError("fail"), "ok"])
        txn, action = self._make_txn_action(execute, max_retries=1)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.engine._execute_action_with_retry(txn, action, 0)
        assert result is True

    async def test_fail_after_max_retries_value_error(self):
        execute = AsyncMock(side_effect=ValueError("always fails"))
        txn, action = self._make_txn_action(execute, max_retries=1)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await self.engine._execute_action_with_retry(txn, action, 0)
        assert result is False
        assert execute.await_count == 2  # initial + 1 retry

    async def test_fail_after_max_retries_timeout(self):
        # Patch asyncio.wait_for in the module to always raise TimeoutError,
        # and asyncio.sleep to skip backoff.  max_retries=1 → 2 TimeoutErrors → False.
        txn = self.engine.create_transaction("T")
        action = self.engine.add_action(
            txn,
            TransactionAction.POLICY_VALIDATION,
            "Slow",
            AsyncMock(),
            max_retries=1,
            timeout_s=0.01,
        )
        module = "enhanced_agent_bus.verification.sagallm_transactions"
        with (
            patch(f"{module}.asyncio.wait_for", side_effect=asyncio.TimeoutError),
            patch(f"{module}.asyncio.sleep", new=AsyncMock()),
        ):
            result = await self.engine._execute_action_with_retry(txn, action, 0)
        assert result is False

    async def test_zero_max_retries_fails_immediately(self):
        execute = AsyncMock(side_effect=RuntimeError("fail"))
        txn, action = self._make_txn_action(execute, max_retries=0)
        result = await self.engine._execute_action_with_retry(txn, action, 0)
        assert result is False
        execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# SagaLLMEngine - _compensate_transaction
# ---------------------------------------------------------------------------


class TestCompensateTransaction:
    def setup_method(self):
        self.engine = SagaLLMEngine()

    async def test_compensation_lifo_order(self):
        order = []
        txn = self.engine.create_transaction("lifo")
        for i in range(3):
            action = self.engine.add_action(
                txn,
                TransactionAction.AUDIT_LOGGING,
                f"A{i}",
                AsyncMock(),
                AsyncMock(side_effect=lambda _i=i: order.append(_i)),
            )
            action.executed_at = datetime.now(UTC)

        await self.engine._compensate_transaction(txn)
        assert order == [2, 1, 0]  # LIFO

    async def test_compensation_skips_unexecuted_actions(self):
        compensate = AsyncMock()
        txn = self.engine.create_transaction("T")
        self.engine.add_action(
            txn, TransactionAction.AUDIT_LOGGING, "Unexecuted", AsyncMock(), compensate
        )
        # executed_at is None → skip
        await self.engine._compensate_transaction(txn)
        compensate.assert_not_awaited()

    async def test_compensation_no_compensate_func(self):
        txn = self.engine.create_transaction("T")
        action = self.engine.add_action(
            txn, TransactionAction.AUDIT_LOGGING, "NoComp", AsyncMock(), None
        )
        action.executed_at = datetime.now(UTC)
        await self.engine._compensate_transaction(txn)
        assert txn.state == TransactionState.COMPENSATED
        assert any(e["status"] == "no_compensation" for e in txn.compensation_log)

    async def test_compensation_failure_logged(self):
        txn = self.engine.create_transaction("T")
        action = self.engine.add_action(
            txn,
            TransactionAction.GOVERNANCE_DECISION,
            "Comp Fail",
            AsyncMock(),
            AsyncMock(side_effect=RuntimeError("comp error")),
        )
        action.executed_at = datetime.now(UTC)
        await self.engine._compensate_transaction(txn)
        assert txn.state == TransactionState.COMPENSATED
        assert any(e["status"] == "compensation_failed" for e in txn.compensation_log)

    async def test_compensation_sets_state_compensated(self):
        txn = self.engine.create_transaction("T")
        await self.engine._compensate_transaction(txn)
        assert txn.state == TransactionState.COMPENSATED

    async def test_compensation_sets_compensated_at(self):
        txn = self.engine.create_transaction("T")
        compensate = AsyncMock(return_value="done")
        action = self.engine.add_action(
            txn, TransactionAction.AUDIT_LOGGING, "Log", AsyncMock(), compensate
        )
        action.executed_at = datetime.now(UTC)
        await self.engine._compensate_transaction(txn)
        assert action.compensated_at is not None
        assert action.compensation_result == "done"


# ---------------------------------------------------------------------------
# SagaLLMEngine - query methods
# ---------------------------------------------------------------------------


class TestSagaLLMEngineQueryMethods:
    def setup_method(self):
        self.engine = SagaLLMEngine()

    def test_get_transaction_active(self):
        txn = self.engine.create_transaction("T")
        found = self.engine.get_transaction(txn.transaction_id)
        assert found is txn

    async def test_get_transaction_completed(self):
        txn = self.engine.create_transaction("T")
        await self.engine.execute_transaction(txn)
        found = self.engine.get_transaction(txn.transaction_id)
        assert found is txn

    def test_get_transaction_not_found(self):
        result = self.engine.get_transaction("nonexistent-id")
        assert result is None

    def test_list_active_transactions(self):
        t1 = self.engine.create_transaction("T1")
        t2 = self.engine.create_transaction("T2")
        active = self.engine.list_active_transactions()
        assert t1 in active
        assert t2 in active

    async def test_list_completed_transactions(self):
        txn = self.engine.create_transaction("T")
        await self.engine.execute_transaction(txn)
        completed = self.engine.list_completed_transactions()
        assert txn in completed

    async def test_get_engine_status(self):
        self.engine.create_transaction("Active T")
        status = await self.engine.get_engine_status()
        assert status["status"] == "operational"
        assert status["engine"] == "SagaLLM Transaction Engine"
        assert status["active_transactions"] >= 1
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_engine_status_counts_completed(self):
        txn = self.engine.create_transaction("T")
        await self.engine.execute_transaction(txn)
        status = await self.engine.get_engine_status()
        assert status["completed_transactions"] >= 1

    async def test_engine_status_includes_config(self):
        engine = SagaLLMEngine(max_transaction_time=99.0)
        status = await engine.get_engine_status()
        assert status["max_transaction_time"] == 99.0


# ---------------------------------------------------------------------------
# saga_transaction context manager
# ---------------------------------------------------------------------------


class TestSagaTransactionContextManager:
    async def test_context_manager_success(self):
        engine = SagaLLMEngine()
        async with saga_transaction(engine, "ctx test") as txn:
            engine.add_action(
                txn,
                TransactionAction.AUDIT_LOGGING,
                "Log",
                AsyncMock(return_value="logged"),
            )
        assert txn.state == TransactionState.COMPLETED

    async def test_context_manager_creates_transaction(self):
        engine = SagaLLMEngine()
        async with saga_transaction(engine, "metadata test", {"k": "v"}) as txn:
            pass
        assert txn.metadata == {"k": "v"}

    async def test_context_manager_raises_on_failure(self):
        engine = SagaLLMEngine()
        with pytest.raises(RuntimeError, match="failed and was compensated"):
            async with saga_transaction(engine, "fail test") as txn:
                engine.add_action(
                    txn,
                    TransactionAction.GOVERNANCE_DECISION,
                    "Fail",
                    AsyncMock(side_effect=ValueError("exec fail")),
                    max_retries=0,
                )

    async def test_context_manager_propagates_sagallm_errors(self):
        engine = SagaLLMEngine()
        with pytest.raises(RuntimeError):
            async with saga_transaction(engine, "error test"):
                raise RuntimeError("inner error")


# ---------------------------------------------------------------------------
# create_governance_transaction convenience function
# ---------------------------------------------------------------------------


class TestCreateGovernanceTransaction:
    async def test_creates_transaction_with_actions(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "approve policy X")
        assert txn.description == "Governance Decision: approve policy X"
        assert len(txn.actions) == 3

    async def test_action_types(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "test decision")
        types = [a.action_type for a in txn.actions]
        assert TransactionAction.CONSTITUTIONAL_CHECK in types
        assert TransactionAction.GOVERNANCE_DECISION in types
        assert TransactionAction.AUDIT_LOGGING in types

    async def test_transaction_has_governance_metadata(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "my decision")
        assert txn.metadata.get("type") == "governance"
        assert txn.metadata.get("decision") == "my decision"

    async def test_execute_governance_transaction(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "execute test")
        result = await engine.execute_transaction(txn)
        assert result is True
        assert txn.state == TransactionState.COMPLETED

    async def test_audit_action_has_no_compensate(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "audit test")
        audit_action = next(
            a for a in txn.actions if a.action_type == TransactionAction.AUDIT_LOGGING
        )
        assert audit_action.compensate_func is None

    async def test_compensation_closures_execute(self):
        """Cover lines 501/517: compensate_validation and compensate_decision closures."""
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "comp closure test")

        # Directly invoke the compensation funcs to cover those closures
        constitutional_action = next(
            a for a in txn.actions if a.action_type == TransactionAction.CONSTITUTIONAL_CHECK
        )
        governance_action = next(
            a for a in txn.actions if a.action_type == TransactionAction.GOVERNANCE_DECISION
        )
        assert constitutional_action.compensate_func is not None
        assert governance_action.compensate_func is not None

        comp_result_1 = await constitutional_action.compensate_func()
        comp_result_2 = await governance_action.compensate_func()
        assert comp_result_1["status"] == "validation_rolled_back"
        assert comp_result_2["status"] == "decision_reverted"


# ---------------------------------------------------------------------------
# get_saga_engine global accessor
# ---------------------------------------------------------------------------


class TestGetSagaEngine:
    def test_returns_engine_instance(self):
        engine = get_saga_engine()
        assert isinstance(engine, SagaLLMEngine)

    def test_returns_same_instance(self):
        e1 = get_saga_engine()
        e2 = get_saga_engine()
        assert e1 is e2


# ---------------------------------------------------------------------------
# Constitutional hash enforcement
# ---------------------------------------------------------------------------


class TestConstitutionalHashEnforcement:
    def test_saga_action_has_hash(self):
        action = SagaAction(
            action_id="x",
            action_type=TransactionAction.AUDIT_LOGGING,
            description="d",
            execute_func=AsyncMock(),
        )
        assert action.constitutional_hash == CONSTITUTIONAL_HASH

    def test_checkpoint_has_hash(self):
        cp = TransactionCheckpoint(
            checkpoint_id="cp",
            checkpoint_name="n",
            state_before={},
            actions_executed=[],
        )
        assert cp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_transaction_has_hash(self):
        txn = SagaTransaction(transaction_id="t", description="d")
        assert txn.constitutional_hash == CONSTITUTIONAL_HASH

    def test_engine_status_has_hash(self):
        engine = SagaLLMEngine()

        async def _check():
            status = await engine.get_engine_status()
            assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

        asyncio.run(_check())
