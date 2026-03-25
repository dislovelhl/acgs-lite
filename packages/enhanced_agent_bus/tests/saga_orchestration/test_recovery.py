"""
Tests for Saga Recovery Service.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enterprise_sso.saga_orchestration import (
    Saga,
    SagaContext,
    SagaDefinition,
    SagaOrchestrator,
    SagaRecoveryService,
    SagaStatus,
    SagaStepDefinition,
    SagaStepExecution,
    SagaStepResult,
    SagaStepStatus,
    SagaStore,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSagaRecoveryService:
    """Tests for saga recovery service."""

    async def test_start_and_stop_recovery_service(
        self,
        orchestrator: SagaOrchestrator,
    ):
        """Test starting and stopping recovery service."""
        recovery = SagaRecoveryService(orchestrator)

        await recovery.start(check_interval_seconds=1)
        assert recovery._running is True

        await recovery.stop()
        assert recovery._running is False

    async def test_recovery_of_pending_compensations(
        self,
        orchestrator: SagaOrchestrator,
        saga_store: SagaStore,
    ):
        """Test recovery of sagas pending compensation."""

        async def step1_action(ctx: SagaContext) -> SagaStepResult:
            return SagaStepResult(success=True)

        async def step1_compensation(ctx: SagaContext) -> SagaStepResult:
            ctx.data["recovered"] = True
            return SagaStepResult(success=True)

        definition = SagaDefinition(
            name="recovery_saga",
            description="Test recovery",
            steps=[
                SagaStepDefinition(
                    name="step1",
                    description="Step 1",
                    action=step1_action,
                    compensation=step1_compensation,
                    order=0,
                ),
            ],
        )

        orchestrator.register_saga(definition)

        # Create a saga in COMPENSATING state
        context = SagaContext(
            saga_id="recovery-001",
            tenant_id="tenant-001",
            correlation_id="corr-001",
        )

        saga = Saga(
            saga_id="recovery-001",
            tenant_id="tenant-001",
            name="recovery_saga",
            description="Test recovery",
            status=SagaStatus.COMPENSATING,
            context=context,
            steps=[
                SagaStepExecution(
                    step_name="step1",
                    status=SagaStepStatus.COMPLETED,
                ),
            ],
        )

        await saga_store.save(saga)

        recovery = SagaRecoveryService(orchestrator)
        await recovery._recover_pending_compensations()

        recovered_saga = await saga_store.get("recovery-001")
        assert recovered_saga is not None
        assert recovered_saga.status == SagaStatus.COMPENSATED
