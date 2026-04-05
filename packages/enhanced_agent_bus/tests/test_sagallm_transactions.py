"""
Tests for enhanced_agent_bus.verification.sagallm_transactions

Covers: SagaLLMEngine lifecycle, action execution with retries,
        compensation (LIFO), checkpoints, context manager,
        convenience function, and dataclass serialization.
"""

import pytest

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

# ---------------------------------------------------------------------------
# Dataclass serialization
# ---------------------------------------------------------------------------


class TestDataclassSerialization:
    def test_saga_action_to_dict(self):
        async def noop():
            return None

        action = SagaAction(
            action_id="a1",
            action_type=TransactionAction.GOVERNANCE_DECISION,
            description="test",
            execute_func=noop,
        )
        d = action.to_dict()
        assert d["action_id"] == "a1"
        assert d["action_type"] == "governance_decision"
        assert d["executed_at"] is None

    def test_transaction_checkpoint_to_dict(self):
        cp = TransactionCheckpoint(
            checkpoint_id="cp1",
            checkpoint_name="pre",
            state_before={"x": 1},
            actions_executed=["a1"],
        )
        d = cp.to_dict()
        assert d["checkpoint_id"] == "cp1"
        assert d["actions_executed"] == ["a1"]

    def test_saga_transaction_to_dict(self):
        txn = SagaTransaction(transaction_id="t1", description="desc")
        d = txn.to_dict()
        assert d["transaction_id"] == "t1"
        assert d["state"] == "initialized"
        assert d["started_at"] is None


class TestTransactionStateEnum:
    def test_all_states_exist(self):
        assert TransactionState.INITIALIZED.value == "initialized"
        assert TransactionState.COMPENSATED.value == "compensated"
        assert TransactionState.TIMED_OUT.value == "timed_out"


# ---------------------------------------------------------------------------
# SagaLLMEngine basics
# ---------------------------------------------------------------------------


class TestSagaLLMEngineBasics:
    @pytest.fixture()
    def engine(self):
        return SagaLLMEngine()

    def test_create_transaction(self, engine):
        txn = engine.create_transaction("test txn", {"meta": True})
        assert txn.description == "test txn"
        assert txn.state == TransactionState.INITIALIZED
        assert txn.transaction_id in engine._active_transactions

    def test_add_action_to_initialized_txn(self, engine):
        txn = engine.create_transaction("t")

        async def run():
            return "ok"

        action = engine.add_action(
            txn,
            TransactionAction.POLICY_VALIDATION,
            "validate",
            run,
        )
        assert len(txn.actions) == 1
        assert action.action_type == TransactionAction.POLICY_VALIDATION

    def test_add_action_to_non_initialized_raises(self, engine):
        txn = engine.create_transaction("t")
        txn.state = TransactionState.ACTIVE

        async def run():
            return "ok"

        with pytest.raises(ValueError, match="Cannot add actions"):
            engine.add_action(txn, TransactionAction.AUDIT_LOGGING, "a", run)

    def test_add_checkpoint(self, engine):
        txn = engine.create_transaction("t")
        cp = engine.add_checkpoint(txn, "before_exec", {"stage": "init"})
        assert cp.checkpoint_name == "before_exec"
        assert len(txn.checkpoints) == 1

    def test_get_transaction_active(self, engine):
        txn = engine.create_transaction("t")
        assert engine.get_transaction(txn.transaction_id) is txn

    def test_get_transaction_not_found(self, engine):
        assert engine.get_transaction("nonexistent") is None

    def test_list_active_and_completed(self, engine):
        engine.create_transaction("t1")
        engine.create_transaction("t2")
        assert len(engine.list_active_transactions()) == 2
        assert len(engine.list_completed_transactions()) == 0

    @pytest.mark.asyncio
    async def test_get_engine_status(self, engine):
        status = await engine.get_engine_status()
        assert status["engine"] == "SagaLLM Transaction Engine"
        assert status["status"] == "operational"


# ---------------------------------------------------------------------------
# Execution happy path
# ---------------------------------------------------------------------------


class TestExecutionHappyPath:
    @pytest.fixture()
    def engine(self):
        return SagaLLMEngine()

    @pytest.mark.asyncio
    async def test_single_action_success(self, engine):
        txn = engine.create_transaction("single action")

        async def run():
            return {"done": True}

        engine.add_action(txn, TransactionAction.GOVERNANCE_DECISION, "exec", run)
        success = await engine.execute_transaction(txn)
        assert success is True
        assert txn.state == TransactionState.COMPLETED
        assert txn.transaction_id in engine._completed_transactions

    @pytest.mark.asyncio
    async def test_multiple_actions_success(self, engine):
        txn = engine.create_transaction("multi")
        results = []

        async def step(name):
            async def _run():
                results.append(name)
                return name

            return _run

        engine.add_action(txn, TransactionAction.CONSTITUTIONAL_CHECK, "s1", await step("s1"))
        engine.add_action(txn, TransactionAction.GOVERNANCE_DECISION, "s2", await step("s2"))
        success = await engine.execute_transaction(txn)
        assert success is True
        assert results == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_execute_non_initialized_raises(self, engine):
        txn = engine.create_transaction("t")
        txn.state = TransactionState.ACTIVE
        with pytest.raises(ValueError, match="Cannot execute"):
            await engine.execute_transaction(txn)


# ---------------------------------------------------------------------------
# Compensation (failure path)
# ---------------------------------------------------------------------------


class TestCompensation:
    @pytest.fixture()
    def engine(self):
        return SagaLLMEngine()

    @pytest.mark.asyncio
    async def test_compensation_on_action_failure(self, engine):
        txn = engine.create_transaction("compensate test")
        compensated = []

        async def good():
            return "ok"

        async def comp_good():
            compensated.append("good_comp")
            return "compensated"

        async def bad():
            raise ValueError("boom")

        engine.add_action(
            txn,
            TransactionAction.CONSTITUTIONAL_CHECK,
            "good",
            good,
            comp_good,
            max_retries=0,
        )
        engine.add_action(
            txn,
            TransactionAction.GOVERNANCE_DECISION,
            "bad",
            bad,
            None,
            max_retries=0,
        )

        success = await engine.execute_transaction(txn)
        assert success is False
        assert txn.state == TransactionState.COMPENSATED
        assert "good_comp" in compensated

    @pytest.mark.asyncio
    async def test_compensation_logged_for_no_compensate_func(self, engine):
        txn = engine.create_transaction("no comp func")

        async def good():
            return "ok"

        async def bad():
            raise ValueError("fail")

        engine.add_action(
            txn, TransactionAction.AUDIT_LOGGING, "good_no_comp", good, None, max_retries=0
        )
        engine.add_action(
            txn, TransactionAction.GOVERNANCE_DECISION, "bad", bad, None, max_retries=0
        )

        success = await engine.execute_transaction(txn)
        assert success is False
        assert any(entry.get("status") == "no_compensation" for entry in txn.compensation_log)

    @pytest.mark.asyncio
    async def test_compensation_failure_logged(self, engine):
        txn = engine.create_transaction("comp fail")

        async def good():
            return "ok"

        async def comp_fail():
            raise RuntimeError("comp broke")

        async def bad():
            raise ValueError("fail")

        engine.add_action(txn, TransactionAction.AUDIT_LOGGING, "g", good, comp_fail, max_retries=0)
        engine.add_action(txn, TransactionAction.GOVERNANCE_DECISION, "b", bad, None, max_retries=0)

        success = await engine.execute_transaction(txn)
        assert success is False
        assert any(entry.get("status") == "compensation_failed" for entry in txn.compensation_log)


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self):
        engine = SagaLLMEngine()
        txn = engine.create_transaction("retry test")
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("flaky")
            return "ok"

        engine.add_action(txn, TransactionAction.GOVERNANCE_DECISION, "flaky", flaky, max_retries=3)
        success = await engine.execute_transaction(txn)
        assert success is True
        assert call_count == 3


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestSagaTransactionContextManager:
    @pytest.mark.asyncio
    async def test_context_manager_success(self):
        engine = SagaLLMEngine()

        async def run():
            return "ok"

        async with saga_transaction(engine, "ctx test") as txn:
            engine.add_action(txn, TransactionAction.POLICY_VALIDATION, "s", run)

        assert txn.state == TransactionState.COMPLETED

    @pytest.mark.asyncio
    async def test_context_manager_failure_raises(self):
        engine = SagaLLMEngine()

        async def fail():
            raise ValueError("boom")

        with pytest.raises(RuntimeError, match="compensated"):
            async with saga_transaction(engine, "fail ctx") as txn:
                engine.add_action(
                    txn, TransactionAction.GOVERNANCE_DECISION, "f", fail, max_retries=0
                )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


class TestCreateGovernanceTransaction:
    @pytest.mark.asyncio
    async def test_creates_transaction_with_standard_actions(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "deploy new policy")
        assert len(txn.actions) == 3
        types = [a.action_type for a in txn.actions]
        assert TransactionAction.CONSTITUTIONAL_CHECK in types
        assert TransactionAction.GOVERNANCE_DECISION in types
        assert TransactionAction.AUDIT_LOGGING in types

    @pytest.mark.asyncio
    async def test_execute_governance_transaction(self):
        engine = SagaLLMEngine()
        txn = await create_governance_transaction(engine, "execute policy")
        success = await engine.execute_transaction(txn)
        assert success is True


# ---------------------------------------------------------------------------
# Global engine
# ---------------------------------------------------------------------------


class TestGetSagaEngine:
    def test_returns_engine_instance(self):
        engine = get_saga_engine()
        assert isinstance(engine, SagaLLMEngine)
