"""
Tests for max_retries edge cases in Saga Orchestration.
Constitutional Hash: 608508a9bd224290

Covers:
- Step succeeds on the Nth retry (within max_retries)
- Step exhausts all retries and fails
- max_retries=0 fails immediately without retrying
- Compensation respects max_compensation_retries
- Timeout per-attempt counted against retries
"""

import asyncio

import pytest

from enterprise_sso.saga_orchestration import (
    CompensationStrategy,
    SagaContext,
    SagaDefinition,
    SagaOrchestrator,
    SagaStatus,
    SagaStepDefinition,
    SagaStepResult,
    SagaStepStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flaky_action(fail_first_n: int, call_counter: list[int]) -> object:
    """Return an async action that fails for the first *fail_first_n* calls."""

    async def action(ctx: SagaContext) -> SagaStepResult:
        call_counter[0] += 1
        if call_counter[0] <= fail_first_n:
            return SagaStepResult(success=False, error=f"Transient failure #{call_counter[0]}")
        return SagaStepResult(success=True, data={"attempt": call_counter[0]})

    return action


async def _always_succeed(ctx: SagaContext) -> SagaStepResult:
    return SagaStepResult(success=True)


async def _always_fail_comp(ctx: SagaContext) -> SagaStepResult:
    return SagaStepResult(success=False, error="Compensation unavailable")


# ---------------------------------------------------------------------------
# max_retries edge cases
# ---------------------------------------------------------------------------


class TestMaxRetriesEdgeCases:
    """Verify retry counting and exhaustion semantics."""

    async def test_step_succeeds_on_last_allowed_retry(
        self, orchestrator: SagaOrchestrator
    ) -> None:
        """Step fails twice then succeeds on the 3rd attempt (max_retries=2)."""
        call_counter = [0]

        definition = SagaDefinition(
            name="retry_success_saga",
            description="Succeeds on last retry",
            steps=[
                SagaStepDefinition(
                    name="flaky_step",
                    description="Flaky step that succeeds eventually",
                    action=_make_flaky_action(fail_first_n=2, call_counter=call_counter),
                    compensation=_always_succeed,
                    max_retries=2,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("retry_success_saga", "tenant-retry")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert result.status == SagaStatus.COMPLETED
        assert call_counter[0] == 3  # 2 failures + 1 success

    async def test_step_fails_when_max_retries_exhausted(
        self, orchestrator: SagaOrchestrator
    ) -> None:
        """Step never succeeds within max_retries — saga compensates."""
        call_counter = [0]

        definition = SagaDefinition(
            name="retry_fail_saga",
            description="Always fails",
            steps=[
                SagaStepDefinition(
                    name="always_fail_step",
                    description="Step that always fails",
                    action=_make_flaky_action(fail_first_n=99, call_counter=call_counter),
                    compensation=_always_succeed,
                    max_retries=2,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("retry_fail_saga", "tenant-retry")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        assert result.status in (SagaStatus.COMPENSATED, SagaStatus.PARTIALLY_COMPENSATED)
        assert result.failed_step == "always_fail_step"
        # 1 initial attempt + 2 retries = 3 total calls
        assert call_counter[0] == 3

    async def test_max_retries_zero_fails_immediately(self, orchestrator: SagaOrchestrator) -> None:
        """With max_retries=0, a failing step is attempted exactly once."""
        call_counter = [0]

        definition = SagaDefinition(
            name="no_retry_saga",
            description="Zero retries",
            steps=[
                SagaStepDefinition(
                    name="no_retry_step",
                    description="Fails with no retry",
                    action=_make_flaky_action(fail_first_n=99, call_counter=call_counter),
                    compensation=_always_succeed,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("no_retry_saga", "tenant-zero")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        assert call_counter[0] == 1  # Single attempt only

    async def test_retry_count_recorded_on_step_execution(
        self, orchestrator: SagaOrchestrator
    ) -> None:
        """Verify retry_count is persisted correctly on the step execution record."""
        call_counter = [0]

        definition = SagaDefinition(
            name="retry_count_saga",
            description="Check retry count is stored",
            steps=[
                SagaStepDefinition(
                    name="counted_step",
                    description="Tracked step",
                    action=_make_flaky_action(fail_first_n=1, call_counter=call_counter),
                    compensation=_always_succeed,
                    max_retries=3,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("retry_count_saga", "tenant-count")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        # Fetch persisted saga and check retry_count on the step
        persisted = await orchestrator.get_saga(saga.saga_id)
        assert persisted is not None
        step_exec = persisted.steps[0]
        assert step_exec.status == SagaStepStatus.COMPLETED
        assert step_exec.retry_count == 1  # Failed once, succeeded on retry

    async def test_saga_timeout_counts_as_retry(self, orchestrator: SagaOrchestrator) -> None:
        """A step that times out consumes a retry slot."""
        call_counter = [0]

        async def slow_then_fast(ctx: SagaContext) -> SagaStepResult:
            call_counter[0] += 1
            if call_counter[0] == 1:
                await asyncio.sleep(10)  # Will time out
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="timeout_retry_saga",
            description="Timeout on first call, success on retry",
            steps=[
                SagaStepDefinition(
                    name="timeout_step",
                    description="Times out first, then succeeds",
                    action=slow_then_fast,
                    compensation=_always_succeed,
                    timeout_seconds=1,
                    max_retries=1,
                    retry_delay_seconds=0,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("timeout_retry_saga", "tenant-timeout")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is True
        assert call_counter[0] == 2  # Timed-out call + successful retry

    async def test_compensation_retries_on_failure(self, orchestrator: SagaOrchestrator) -> None:
        """Compensation retries up to max_compensation_retries before marking as failed."""
        comp_calls = [0]

        async def flaky_comp(ctx: SagaContext) -> SagaStepResult:
            comp_calls[0] += 1
            if comp_calls[0] < 3:
                return SagaStepResult(success=False, error="Comp failure")
            return SagaStepResult(success=True)

        async def always_fail_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Action failed")

        async def pass_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="comp_retry_saga",
            description="Compensation retries",
            max_compensation_retries=3,
            steps=[
                SagaStepDefinition(
                    name="succeeds_step",
                    description="Completes, then needs compensation",
                    action=pass_action,
                    compensation=flaky_comp,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=0,
                ),
                SagaStepDefinition(
                    name="fails_step",
                    description="Triggers compensation of preceding step",
                    action=always_fail_action,
                    compensation=_always_succeed,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=1,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("comp_retry_saga", "tenant-comp")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        # Compensation ultimately succeeded (3 attempts, max_compensation_retries=3)
        assert "succeeds_step" in result.compensated_steps
        assert comp_calls[0] == 3

    async def test_compensation_skip_strategy_on_exhaustion(
        self, orchestrator: SagaOrchestrator
    ) -> None:
        """CompensationStrategy.SKIP treats exhausted compensation as non-blocking."""

        async def always_fail_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=False, error="Action failed")

        async def pass_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="skip_comp_saga",
            description="Skip compensation on failure",
            max_compensation_retries=1,
            steps=[
                SagaStepDefinition(
                    name="completed_step",
                    description="Needs compensation but skips on failure",
                    action=pass_action,
                    compensation=_always_fail_comp,
                    compensation_strategy=CompensationStrategy.SKIP,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=0,
                ),
                SagaStepDefinition(
                    name="failing_step",
                    description="Triggers compensation flow",
                    action=always_fail_action,
                    compensation=_always_succeed,
                    max_retries=0,
                    retry_delay_seconds=0,
                    order=1,
                ),
            ],
        )

        orchestrator.register_saga(definition)
        saga = await orchestrator.create_saga("skip_comp_saga", "tenant-skip")
        result = await orchestrator.execute(saga.saga_id)

        assert result.success is False
        # SKIP strategy: completed_step compensation is counted as done even though it failed
        assert "completed_step" in result.compensated_steps
