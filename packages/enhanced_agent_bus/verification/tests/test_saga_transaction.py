"""
Tests for SagaTransaction and ConstitutionalSaga modules.
Constitutional Hash: 608508a9bd224290

Covers:
- SagaStatus enum
- SagaStep dataclass
- SagaTransaction: add_step, execute (success, failure, LIFO compensation)
- ConstitutionalSaga: execute_governance
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.verification.saga_transaction import (
    ConstitutionalSaga,
    SagaStatus,
    SagaStep,
    SagaTransaction,
)

pytestmark = [pytest.mark.unit, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestSagaStatus:
    def test_all_statuses_defined(self):
        expected = {"PENDING", "RUNNING", "COMPLETED", "COMPENSATING", "ROLLED_BACK", "FAILED"}
        actual = {s.name for s in SagaStatus}
        assert expected == actual

    def test_values(self):
        assert SagaStatus.PENDING.value == "pending"
        assert SagaStatus.COMPLETED.value == "completed"
        assert SagaStatus.ROLLED_BACK.value == "rolled_back"


# ---------------------------------------------------------------------------
# SagaStep dataclass tests
# ---------------------------------------------------------------------------


class TestSagaStep:
    def test_default_status(self):
        step = SagaStep(name="step1", action=AsyncMock())
        assert step.status == SagaStatus.PENDING
        assert step.result is None
        assert step.error is None
        assert step.compensation is None

    def test_with_compensation(self):
        comp = AsyncMock()
        step = SagaStep(name="step1", action=AsyncMock(), compensation=comp)
        assert step.compensation is comp


# ---------------------------------------------------------------------------
# SagaTransaction tests
# ---------------------------------------------------------------------------


class TestSagaTransaction:
    def test_default_transaction_id_generated(self):
        tx = SagaTransaction()
        assert tx.transaction_id is not None
        assert len(tx.transaction_id) > 0

    def test_custom_transaction_id(self):
        tx = SagaTransaction(transaction_id="my-tx-001")
        assert tx.transaction_id == "my-tx-001"

    def test_initial_status_pending(self):
        tx = SagaTransaction()
        assert tx.status == SagaStatus.PENDING

    def test_add_step_returns_self_for_chaining(self):
        tx = SagaTransaction()
        result = tx.add_step("step1", AsyncMock())
        assert result is tx

    def test_add_multiple_steps(self):
        tx = SagaTransaction()
        tx.add_step("step1", AsyncMock()).add_step("step2", AsyncMock())
        assert len(tx.steps) == 2

    async def test_execute_single_step_success(self):
        action = AsyncMock(return_value="result-1")
        tx = SagaTransaction()
        tx.add_step("step1", action)
        result = await tx.execute()
        assert result == "result-1"
        assert tx.status == SagaStatus.COMPLETED

    async def test_execute_multiple_steps_in_order(self):
        order = []

        async def step_a(**kwargs):
            order.append("a")
            return "a"

        async def step_b(**kwargs):
            order.append("b")
            return "b"

        tx = SagaTransaction()
        tx.add_step("a", step_a).add_step("b", step_b)
        result = await tx.execute()
        assert order == ["a", "b"]
        assert result == "b"

    async def test_execute_passes_last_result_to_next_step(self):
        received = {}

        async def step_a(**kwargs):
            return "value-from-a"

        async def step_b(**kwargs):
            received["last"] = kwargs.get("last_result")
            return "value-from-b"

        tx = SagaTransaction()
        tx.add_step("a", step_a).add_step("b", step_b)
        await tx.execute()
        assert received["last"] == "value-from-a"

    async def test_execute_step_failure_triggers_compensation(self):
        compensated = []

        async def step_a(**kwargs):
            return "a-done"

        async def comp_a(result):
            compensated.append("comp-a")

        async def step_b(**kwargs):
            raise RuntimeError("Step B failed")

        tx = SagaTransaction()
        tx.add_step("a", step_a, compensation=comp_a)
        tx.add_step("b", step_b)

        with pytest.raises(RuntimeError, match="Step B failed"):
            await tx.execute()

        assert "comp-a" in compensated

    async def test_compensation_is_lifo(self):
        comp_order = []

        async def step_a(**kwargs):
            return "a"

        async def step_b(**kwargs):
            return "b"

        async def step_c(**kwargs):
            raise RuntimeError("c failed")

        async def comp_a(result):
            comp_order.append("comp-a")

        async def comp_b(result):
            comp_order.append("comp-b")

        tx = SagaTransaction()
        tx.add_step("a", step_a, compensation=comp_a)
        tx.add_step("b", step_b, compensation=comp_b)
        tx.add_step("c", step_c)

        with pytest.raises(RuntimeError):
            await tx.execute()

        assert comp_order == ["comp-b", "comp-a"]

    async def test_status_after_failure_is_rolled_back(self):
        async def failing_step(**kwargs):
            raise ValueError("Oops")

        tx = SagaTransaction()
        tx.add_step("fail", failing_step)

        with pytest.raises(ValueError):
            await tx.execute()

        assert tx.status == SagaStatus.ROLLED_BACK

    async def test_step_without_compensation_skipped_during_rollback(self):
        """Steps without compensation should not raise during rollback."""

        async def step_a(**kwargs):
            return "a"

        async def step_b(**kwargs):
            raise RuntimeError("fail")

        tx = SagaTransaction()
        tx.add_step("a", step_a)  # no compensation
        tx.add_step("b", step_b)

        with pytest.raises(RuntimeError):
            await tx.execute()

        # If no exception raised during compensation, test passes
        assert tx.status == SagaStatus.ROLLED_BACK

    async def test_compensation_failure_does_not_raise(self):
        """Compensation failure should be logged but not re-raised."""

        async def step_a(**kwargs):
            return "a"

        async def comp_a(result):
            raise RuntimeError("Compensation also fails")

        async def step_b(**kwargs):
            raise RuntimeError("Primary failure")

        tx = SagaTransaction()
        tx.add_step("a", step_a, compensation=comp_a)
        tx.add_step("b", step_b)

        # Should raise from the original step, not from compensation
        with pytest.raises(RuntimeError, match="Primary failure"):
            await tx.execute()

    async def test_execute_sets_step_statuses(self):
        async def step_a(**kwargs):
            return "a"

        tx = SagaTransaction()
        tx.add_step("a", step_a)
        await tx.execute()
        assert tx.steps[0].status == SagaStatus.COMPLETED

    async def test_failed_step_stores_error(self):
        async def step_fail(**kwargs):
            raise ValueError("Explicit error")

        tx = SagaTransaction()
        tx.add_step("fail", step_fail)

        with pytest.raises(ValueError):
            await tx.execute()

        assert tx.steps[0].error == "Explicit error"
        assert tx.steps[0].status == SagaStatus.FAILED

    async def test_execute_with_no_steps_returns_none(self):
        tx = SagaTransaction()
        result = await tx.execute()
        assert result is None
        assert tx.status == SagaStatus.COMPLETED

    async def test_kwargs_passed_through_to_action(self):
        received = {}

        async def action(**kwargs):
            received.update(kwargs)
            return "ok"

        tx = SagaTransaction()
        tx.add_step("a", action)
        await tx.execute(custom_key="custom_val")
        assert received.get("custom_key") == "custom_val"


# ---------------------------------------------------------------------------
# ConstitutionalSaga tests
# ---------------------------------------------------------------------------


class TestConstitutionalSaga:
    def test_initialization_no_auditor(self):
        saga = ConstitutionalSaga()
        assert saga.auditor is None

    def test_initialization_with_auditor(self):
        auditor = MagicMock()
        saga = ConstitutionalSaga(auditor=auditor)
        assert saga.auditor is auditor

    def test_inherits_from_saga_transaction(self):
        saga = ConstitutionalSaga()
        assert isinstance(saga, SagaTransaction)

    async def test_execute_governance_with_steps(self):
        result_holder = {}

        async def gov_step(**kwargs):
            result_holder["data"] = kwargs.get("data")
            return "gov-result"

        saga = ConstitutionalSaga()
        saga.add_step("governance", gov_step)
        result = await saga.execute_governance(decision_data={"policy": "allow_all"})
        assert result_holder["data"] == {"policy": "allow_all"}

    async def test_execute_governance_empty_returns_none(self):
        saga = ConstitutionalSaga()
        result = await saga.execute_governance(decision_data={})
        assert result is None

    async def test_execute_governance_propagates_failure(self):
        async def failing_step(**kwargs):
            raise RuntimeError("governance failure")

        saga = ConstitutionalSaga()
        saga.add_step("fail", failing_step)

        with pytest.raises(RuntimeError, match="governance failure"):
            await saga.execute_governance(decision_data={})
