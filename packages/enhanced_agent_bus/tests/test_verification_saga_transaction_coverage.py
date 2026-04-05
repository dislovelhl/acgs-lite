# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/verification/saga_transaction.py

Targets ≥95% line coverage of the saga_transaction module.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.verification.saga_transaction import (
    SAGA_COMPENSATION_ERRORS,
    SAGA_STEP_EXECUTION_ERRORS,
    ConstitutionalSaga,
    SagaStatus,
    SagaStep,
    SagaTransaction,
)

# ---------------------------------------------------------------------------
# SagaStatus enum
# ---------------------------------------------------------------------------


class TestSagaStatus:
    def test_all_values_defined(self):
        assert SagaStatus.PENDING.value == "pending"
        assert SagaStatus.RUNNING.value == "running"
        assert SagaStatus.COMPLETED.value == "completed"
        assert SagaStatus.COMPENSATING.value == "compensating"
        assert SagaStatus.ROLLED_BACK.value == "rolled_back"
        assert SagaStatus.FAILED.value == "failed"

    def test_enum_members_count(self):
        assert len(SagaStatus) == 6

    def test_enum_identity(self):
        assert SagaStatus.PENDING is SagaStatus.PENDING
        assert SagaStatus.FAILED is not SagaStatus.COMPLETED


# ---------------------------------------------------------------------------
# Module-level error tuples
# ---------------------------------------------------------------------------


class TestErrorTuples:
    def test_step_execution_errors_tuple(self):
        assert RuntimeError in SAGA_STEP_EXECUTION_ERRORS
        assert ValueError in SAGA_STEP_EXECUTION_ERRORS
        assert TypeError in SAGA_STEP_EXECUTION_ERRORS
        assert KeyError in SAGA_STEP_EXECUTION_ERRORS
        assert AttributeError in SAGA_STEP_EXECUTION_ERRORS
        assert asyncio.TimeoutError in SAGA_STEP_EXECUTION_ERRORS

    def test_compensation_errors_tuple(self):
        assert RuntimeError in SAGA_COMPENSATION_ERRORS
        assert ValueError in SAGA_COMPENSATION_ERRORS
        assert TypeError in SAGA_COMPENSATION_ERRORS
        assert KeyError in SAGA_COMPENSATION_ERRORS
        assert AttributeError in SAGA_COMPENSATION_ERRORS
        assert asyncio.TimeoutError in SAGA_COMPENSATION_ERRORS


# ---------------------------------------------------------------------------
# SagaStep dataclass
# ---------------------------------------------------------------------------


class TestSagaStep:
    def test_create_minimal_step(self):
        async def action(**kw):
            return "ok"

        step = SagaStep(name="step1", action=action)
        assert step.name == "step1"
        assert step.action is action
        assert step.compensation is None
        assert step.status == SagaStatus.PENDING
        assert step.result is None
        assert step.error is None

    def test_create_step_with_compensation(self):
        async def action(**kw):
            return "ok"

        async def comp(result):
            pass

        step = SagaStep(name="step2", action=action, compensation=comp)
        assert step.compensation is comp

    def test_step_status_mutation(self):
        async def action(**kw):
            return None

        step = SagaStep(name="s", action=action)
        step.status = SagaStatus.RUNNING
        assert step.status == SagaStatus.RUNNING

    def test_step_error_field(self):
        async def action(**kw):
            return None

        step = SagaStep(name="s", action=action)
        step.error = "something went wrong"
        assert step.error == "something went wrong"

    def test_step_result_field(self):
        async def action(**kw):
            return None

        step = SagaStep(name="s", action=action)
        step.result = {"key": "value"}
        assert step.result == {"key": "value"}


# ---------------------------------------------------------------------------
# SagaTransaction.__init__
# ---------------------------------------------------------------------------


class TestSagaTransactionInit:
    def test_default_transaction_id_is_uuid(self):
        txn = SagaTransaction()
        # Should be a valid UUID string
        parsed = uuid.UUID(txn.transaction_id)
        assert str(parsed) == txn.transaction_id

    def test_explicit_transaction_id(self):
        txn = SagaTransaction(transaction_id="my-txn-123")
        assert txn.transaction_id == "my-txn-123"

    def test_initial_status_is_pending(self):
        txn = SagaTransaction()
        assert txn.status == SagaStatus.PENDING

    def test_steps_initially_empty(self):
        txn = SagaTransaction()
        assert txn.steps == []

    def test_completed_steps_initially_empty(self):
        txn = SagaTransaction()
        assert txn._completed_steps == []


# ---------------------------------------------------------------------------
# SagaTransaction.add_step
# ---------------------------------------------------------------------------


class TestSagaTransactionAddStep:
    def test_add_single_step_returns_self(self):
        txn = SagaTransaction()

        async def action(**kw):
            return None

        result = txn.add_step("step1", action)
        assert result is txn

    def test_add_step_appends_to_steps(self):
        txn = SagaTransaction()

        async def action(**kw):
            return None

        txn.add_step("step1", action)
        assert len(txn.steps) == 1
        assert txn.steps[0].name == "step1"

    def test_add_multiple_steps(self):
        txn = SagaTransaction()

        async def a1(**kw):
            return 1

        async def a2(**kw):
            return 2

        async def a3(**kw):
            return 3

        txn.add_step("s1", a1).add_step("s2", a2).add_step("s3", a3)
        assert len(txn.steps) == 3
        assert txn.steps[0].name == "s1"
        assert txn.steps[2].name == "s3"

    def test_add_step_with_compensation(self):
        txn = SagaTransaction()

        async def action(**kw):
            return None

        async def comp(result):
            pass

        txn.add_step("step1", action, comp)
        assert txn.steps[0].compensation is comp

    def test_add_step_without_compensation(self):
        txn = SagaTransaction()

        async def action(**kw):
            return None

        txn.add_step("step1", action)
        assert txn.steps[0].compensation is None


# ---------------------------------------------------------------------------
# SagaTransaction.execute — success path
# ---------------------------------------------------------------------------


class TestSagaTransactionExecuteSuccess:
    async def test_execute_no_steps_returns_none(self):
        txn = SagaTransaction()
        result = await txn.execute()
        assert result is None
        assert txn.status == SagaStatus.COMPLETED

    async def test_execute_single_step_returns_result(self):
        txn = SagaTransaction()

        async def action(**kw):
            return "step_result"

        txn.add_step("step1", action)
        result = await txn.execute()
        assert result == "step_result"
        assert txn.status == SagaStatus.COMPLETED

    async def test_execute_multiple_steps_returns_last(self):
        txn = SagaTransaction()

        async def a1(**kw):
            return "first"

        async def a2(**kw):
            return "second"

        async def a3(**kw):
            return "third"

        txn.add_step("s1", a1).add_step("s2", a2).add_step("s3", a3)
        result = await txn.execute()
        assert result == "third"

    async def test_execute_sets_running_during_execution(self):
        statuses = []
        txn = SagaTransaction()

        async def action(**kw):
            statuses.append(txn.status)
            return "ok"

        txn.add_step("step", action)
        await txn.execute()
        assert SagaStatus.RUNNING in statuses

    async def test_execute_step_receives_last_result(self):
        received = {}
        txn = SagaTransaction()

        async def a1(**kw):
            return 42

        async def a2(last_result=None, **kw):
            received["last"] = last_result
            return last_result * 2

        txn.add_step("s1", a1).add_step("s2", a2)
        await txn.execute()
        assert received["last"] == 42

    async def test_execute_passes_kwargs_to_action(self):
        received = {}
        txn = SagaTransaction()

        async def action(last_result=None, **kw):
            received.update(kw)
            return "done"

        txn.add_step("step", action)
        await txn.execute(foo="bar", num=7)
        assert received["foo"] == "bar"
        assert received["num"] == 7

    async def test_execute_marks_each_step_completed(self):
        txn = SagaTransaction()

        async def a(**kw):
            return None

        txn.add_step("s1", a).add_step("s2", a)
        await txn.execute()
        for step in txn.steps:
            assert step.status == SagaStatus.COMPLETED

    async def test_execute_populates_completed_steps(self):
        txn = SagaTransaction()

        async def a(**kw):
            return None

        txn.add_step("s1", a).add_step("s2", a)
        await txn.execute()
        assert len(txn._completed_steps) == 2


# ---------------------------------------------------------------------------
# SagaTransaction.execute — failure / rollback path
# ---------------------------------------------------------------------------


class TestSagaTransactionExecuteFailure:
    async def test_execute_raises_on_runtime_error(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise RuntimeError("boom")

        txn.add_step("bad", bad)
        with pytest.raises(RuntimeError, match="boom"):
            await txn.execute()

    async def test_execute_sets_rolled_back_on_failure(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise ValueError("bad value")

        txn.add_step("bad", bad)
        with pytest.raises(ValueError):
            await txn.execute()
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_execute_sets_failed_step_status(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise TypeError("type error")

        txn.add_step("bad", bad)
        with pytest.raises(TypeError):
            await txn.execute()
        assert txn.steps[0].status == SagaStatus.FAILED

    async def test_execute_stores_error_message_on_step(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise RuntimeError("error message")

        txn.add_step("bad", bad)
        with pytest.raises(RuntimeError):
            await txn.execute()
        assert txn.steps[0].error == "error message"

    async def test_execute_calls_compensation_on_failure(self):
        compensated = []
        txn = SagaTransaction()

        async def good(**kw):
            return "good_result"

        async def comp(result):
            compensated.append(result)

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("good", good, comp)
        txn.add_step("bad", bad)

        with pytest.raises(RuntimeError):
            await txn.execute()

        assert "good_result" in compensated

    async def test_execute_compensation_lifo_order(self):
        order = []
        txn = SagaTransaction()

        async def a1(**kw):
            return "r1"

        async def c1(result):
            order.append("comp1")

        async def a2(**kw):
            return "r2"

        async def c2(result):
            order.append("comp2")

        async def a3(**kw):
            raise RuntimeError("fail step 3")

        txn.add_step("s1", a1, c1).add_step("s2", a2, c2).add_step("s3", a3)

        with pytest.raises(RuntimeError):
            await txn.execute()

        # LIFO: comp2 before comp1
        assert order == ["comp2", "comp1"]

    async def test_key_error_triggers_rollback(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise KeyError("missing_key")

        txn.add_step("bad", bad)
        with pytest.raises(KeyError):
            await txn.execute()
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_attribute_error_triggers_rollback(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise AttributeError("no attr")

        txn.add_step("bad", bad)
        with pytest.raises(AttributeError):
            await txn.execute()
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_timeout_error_triggers_rollback(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise TimeoutError()

        txn.add_step("bad", bad)
        with pytest.raises(asyncio.TimeoutError):
            await txn.execute()
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_only_completed_steps_compensated(self):
        compensated = []
        txn = SagaTransaction()

        async def good(**kw):
            return "done"

        async def comp(result):
            compensated.append("comp_good")

        async def fail(**kw):
            raise RuntimeError("fail")

        # fail step has no compensation
        txn.add_step("good", good, comp).add_step("fail", fail)
        with pytest.raises(RuntimeError):
            await txn.execute()

        # Only the completed "good" step should be compensated
        assert compensated == ["comp_good"]

    async def test_no_compensation_on_first_step_failure(self):
        compensated = []
        txn = SagaTransaction()

        async def bad(**kw):
            raise RuntimeError("first step fails immediately")

        async def comp(result):
            compensated.append("should not be called")

        txn.add_step("bad", bad, comp)
        with pytest.raises(RuntimeError):
            await txn.execute()

        # Step never completed so compensation should NOT be called
        assert compensated == []


# ---------------------------------------------------------------------------
# SagaTransaction._compensate — compensation error handling
# ---------------------------------------------------------------------------


class TestSagaTransactionCompensate:
    async def test_compensate_swallows_compensation_errors(self):
        """Compensation errors should be caught and logged, not re-raised."""
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        async def bad_comp(result):
            raise RuntimeError("comp failed")

        async def bad(**kw):
            raise RuntimeError("step failed")

        txn.add_step("good", good, bad_comp).add_step("bad", bad)

        # The RuntimeError from the step should propagate, not the compensation error
        with pytest.raises(RuntimeError, match="step failed"):
            await txn.execute()
        # Status should still be ROLLED_BACK despite compensation error
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_compensate_logs_compensation_failure(self):
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        async def bad_comp(result):
            raise ValueError("comp value error")

        async def bad(**kw):
            raise RuntimeError("step failed")

        txn.add_step("good", good, bad_comp).add_step("bad", bad)

        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await txn.execute()
            # error should have been logged for the compensation failure
            assert mock_logger.error.called

    async def test_compensate_step_without_compensation_logs_debug(self):
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        # No compensation provided
        async def bad(**kw):
            raise RuntimeError("step failed")

        txn.add_step("good", good).add_step("bad", bad)

        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await txn.execute()
            assert mock_logger.debug.called

    async def test_compensate_all_compensation_errors_tuple_members(self):
        """Each compensation error type should be caught."""
        comp_errors = [
            RuntimeError("runtime"),
            ValueError("value"),
            TypeError("type"),
            KeyError("key"),
            AttributeError("attr"),
            TimeoutError(),
        ]
        for err in comp_errors:
            txn = SagaTransaction()

            async def good(**kw):
                return "ok"

            async def bad(**kw):
                raise RuntimeError("step failed")

            err_to_raise = err

            async def bad_comp(result, _err=err_to_raise):
                raise _err

            txn.add_step("good", good, bad_comp).add_step("bad", bad)
            # Should not raise from compensation
            with pytest.raises(RuntimeError, match="step failed"):
                await txn.execute()

    async def test_compensate_sets_compensating_status(self):
        statuses_during_comp = []
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        async def comp(result):
            statuses_during_comp.append(txn.status)

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("good", good, comp).add_step("bad", bad)
        with pytest.raises(RuntimeError):
            await txn.execute()

        assert SagaStatus.COMPENSATING in statuses_during_comp

    async def test_compensate_multiple_steps_all_compensated(self):
        compensated = []
        txn = SagaTransaction()

        async def a1(**kw):
            return "r1"

        async def c1(result):
            compensated.append("c1")

        async def a2(**kw):
            return "r2"

        async def c2(result):
            compensated.append("c2")

        async def a3(**kw):
            return "r3"

        async def c3(result):
            compensated.append("c3")

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("s1", a1, c1)
        txn.add_step("s2", a2, c2)
        txn.add_step("s3", a3, c3)
        txn.add_step("bad", bad)

        with pytest.raises(RuntimeError):
            await txn.execute()

        assert set(compensated) == {"c1", "c2", "c3"}
        assert compensated == ["c3", "c2", "c1"]  # LIFO

    async def test_compensate_mixed_with_and_without_compensation(self):
        compensated = []
        txn = SagaTransaction()

        async def a1(**kw):
            return "r1"

        async def c1(result):
            compensated.append("c1")

        async def a2(**kw):  # no compensation
            return "r2"

        async def a3(**kw):
            return "r3"

        async def c3(result):
            compensated.append("c3")

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("s1", a1, c1)
        txn.add_step("s2", a2)  # no comp
        txn.add_step("s3", a3, c3)
        txn.add_step("bad", bad)

        with pytest.raises(RuntimeError):
            await txn.execute()

        # c3 before c1, s2 has no compensation so skipped
        assert compensated == ["c3", "c1"]


# ---------------------------------------------------------------------------
# SagaTransaction logging
# ---------------------------------------------------------------------------


class TestSagaTransactionLogging:
    async def test_execute_logs_start(self):
        txn = SagaTransaction(transaction_id="test-log-txn")
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            await txn.execute()
            assert mock_logger.info.called
            first_call_args = mock_logger.info.call_args_list[0][0][0]
            assert "test-log-txn" in first_call_args

    async def test_execute_logs_completion(self):
        txn = SagaTransaction(transaction_id="test-complete-txn")
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            await txn.execute()
            # Should have info logged for both start and completion
            assert mock_logger.info.call_count >= 2

    async def test_execute_logs_step_failure(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise RuntimeError("test error")

        txn.add_step("bad_step", bad)
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await txn.execute()
            assert mock_logger.error.called

    async def test_compensate_logs_warning(self):
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("good", good).add_step("bad", bad)
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await txn.execute()
            assert mock_logger.warning.called

    async def test_compensate_logs_completion(self):
        txn = SagaTransaction()

        async def bad(**kw):
            raise RuntimeError("fail")

        txn.add_step("bad", bad)
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await txn.execute()
            # One of the info calls should mention compensation completed
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("compensation" in c.lower() or "Compensation" in c for c in info_calls)


# ---------------------------------------------------------------------------
# ConstitutionalSaga
# ---------------------------------------------------------------------------


class TestConstitutionalSaga:
    def test_init_no_auditor(self):
        saga = ConstitutionalSaga()
        assert saga.auditor is None
        assert isinstance(saga, SagaTransaction)

    def test_init_with_auditor(self):
        mock_auditor = MagicMock()
        saga = ConstitutionalSaga(auditor=mock_auditor)
        assert saga.auditor is mock_auditor

    def test_init_with_none_auditor(self):
        saga = ConstitutionalSaga(auditor=None)
        assert saga.auditor is None

    def test_inherits_saga_transaction(self):
        saga = ConstitutionalSaga()
        assert isinstance(saga, SagaTransaction)
        assert saga.status == SagaStatus.PENDING
        assert saga.steps == []

    def test_transaction_id_auto_generated(self):
        saga = ConstitutionalSaga()
        parsed = uuid.UUID(saga.transaction_id)
        assert str(parsed) == saga.transaction_id

    async def test_execute_governance_calls_execute(self):
        saga = ConstitutionalSaga()
        decision_data = {"key": "value", "action": "approve"}

        async def action(last_result=None, data=None, **kw):
            return data

        saga.add_step("validate", action)
        result = await saga.execute_governance(decision_data)
        assert result == decision_data

    async def test_execute_governance_no_steps(self):
        saga = ConstitutionalSaga()
        result = await saga.execute_governance({"action": "test"})
        assert result is None
        assert saga.status == SagaStatus.COMPLETED

    async def test_execute_governance_passes_data_as_kwarg(self):
        received = {}
        saga = ConstitutionalSaga()

        async def action(last_result=None, **kw):
            received.update(kw)
            return kw.get("data")

        saga.add_step("check", action)
        await saga.execute_governance({"x": 1})
        assert received.get("data") == {"x": 1}

    async def test_execute_governance_propagates_exception(self):
        saga = ConstitutionalSaga()

        async def bad(last_result=None, **kw):
            raise RuntimeError("governance failure")

        saga.add_step("bad", bad)
        with pytest.raises(RuntimeError, match="governance failure"):
            await saga.execute_governance({"action": "fail"})

    async def test_execute_governance_with_auditor(self):
        mock_auditor = AsyncMock()
        saga = ConstitutionalSaga(auditor=mock_auditor)

        async def action(last_result=None, **kw):
            return "audited_result"

        saga.add_step("step", action)
        result = await saga.execute_governance({"foo": "bar"})
        assert result == "audited_result"

    async def test_constitutional_saga_can_add_steps(self):
        saga = ConstitutionalSaga()

        async def a(**kw):
            return "done"

        result = saga.add_step("s", a)
        assert result is saga
        assert len(saga.steps) == 1

    async def test_execute_governance_rollback_on_failure(self):
        compensated = []
        saga = ConstitutionalSaga()

        async def good(last_result=None, **kw):
            return "ok"

        async def comp(result):
            compensated.append(result)

        async def bad(last_result=None, **kw):
            raise ValueError("governance error")

        saga.add_step("good", good, comp)
        saga.add_step("bad", bad)

        with pytest.raises(ValueError):
            await saga.execute_governance({"x": "y"})

        assert saga.status == SagaStatus.ROLLED_BACK
        assert "ok" in compensated


# ---------------------------------------------------------------------------
# Edge cases and integration scenarios
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_execute_single_step_no_result(self):
        txn = SagaTransaction()

        async def action(**kw):
            return None

        txn.add_step("step", action)
        result = await txn.execute()
        assert result is None
        assert txn.status == SagaStatus.COMPLETED

    async def test_execute_chain_result_propagation(self):
        txn = SagaTransaction()

        async def a1(**kw):
            return [1, 2, 3]

        async def a2(last_result=None, **kw):
            return [x * 2 for x in last_result]

        async def a3(last_result=None, **kw):
            return sum(last_result)

        txn.add_step("s1", a1).add_step("s2", a2).add_step("s3", a3)
        result = await txn.execute()
        assert result == 12  # sum([2, 4, 6])

    async def test_step_with_false_result(self):
        txn = SagaTransaction()

        async def action(**kw):
            return False

        txn.add_step("step", action)
        result = await txn.execute()
        assert result is False
        assert txn.status == SagaStatus.COMPLETED

    async def test_step_with_zero_result(self):
        txn = SagaTransaction()

        async def action(**kw):
            return 0

        txn.add_step("step", action)
        result = await txn.execute()
        assert result == 0

    async def test_step_with_empty_dict_result(self):
        txn = SagaTransaction()

        async def action(**kw):
            return {}

        txn.add_step("step", action)
        result = await txn.execute()
        assert result == {}

    async def test_multiple_failures_only_first_triggers_compensation(self):
        """Once a step fails and compensation runs, transaction is done."""
        compensated = []
        txn = SagaTransaction()

        async def good(**kw):
            return "ok"

        async def comp(result):
            compensated.append("comp")

        async def fail1(**kw):
            raise RuntimeError("first failure")

        txn.add_step("good", good, comp).add_step("fail1", fail1)

        with pytest.raises(RuntimeError, match="first failure"):
            await txn.execute()

        assert compensated == ["comp"]
        assert txn.status == SagaStatus.ROLLED_BACK

    async def test_transaction_id_uniqueness(self):
        ids = {SagaTransaction().transaction_id for _ in range(10)}
        assert len(ids) == 10  # All unique

    async def test_execute_with_no_kwargs(self):
        txn = SagaTransaction()

        async def action(**kw):
            return "no_kwargs"

        txn.add_step("step", action)
        result = await txn.execute()
        assert result == "no_kwargs"

    async def test_execute_with_many_kwargs(self):
        received = {}
        txn = SagaTransaction()

        async def action(last_result=None, **kw):
            received.update(kw)
            return "ok"

        txn.add_step("step", action)
        await txn.execute(a=1, b=2, c=3, d=4, e=5)
        assert received == {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}

    async def test_constitutional_hash_in_logs(self):
        """Verify that the constitutional hash appears in log messages."""
        txn = SagaTransaction()
        with patch("enhanced_agent_bus.verification.saga_transaction.logger") as mock_logger:
            await txn.execute()
            all_calls = str(mock_logger.mock_calls)
            assert CONSTITUTIONAL_HASH in all_calls
