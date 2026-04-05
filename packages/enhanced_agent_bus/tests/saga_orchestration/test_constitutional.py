"""
Tests for Constitutional Compliance in Saga Orchestration.
Constitutional Hash: 608508a9bd224290
"""

import uuid

import pytest

from enterprise_sso.saga_orchestration import (
    CONSTITUTIONAL_HASH,
    SagaDefinition,
    SagaEvent,
    SagaEventType,
    SagaExecutionResult,
    SagaOrchestrator,
    SagaStatus,
)

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance in saga orchestration."""

    def test_constitutional_hash_defined(self):
        """Test that constitutional hash is properly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    async def test_saga_includes_constitutional_hash(
        self, orchestrator: SagaOrchestrator, simple_saga_definition: SagaDefinition
    ):
        """Test that sagas include constitutional hash."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )
        assert saga.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_saga_context_includes_constitutional_hash(
        self, orchestrator: SagaOrchestrator, simple_saga_definition: SagaDefinition
    ):
        """Test that saga context includes constitutional hash."""
        orchestrator.register_saga(simple_saga_definition)

        saga = await orchestrator.create_saga(
            definition_name="simple_saga",
            tenant_id="tenant-001",
        )
        assert saga.context is not None
        assert saga.context.constitutional_hash == CONSTITUTIONAL_HASH

    def test_saga_event_includes_constitutional_hash(self):
        """Test that saga events include constitutional hash."""
        event = SagaEvent(
            event_id=str(uuid.uuid4()),
            saga_id=str(uuid.uuid4()),
            event_type=SagaEventType.SAGA_STARTED,
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_execution_result_includes_constitutional_hash(self):
        """Test that execution results include constitutional hash."""
        result = SagaExecutionResult(
            saga_id=str(uuid.uuid4()),
            success=True,
            status=SagaStatus.COMPLETED,
            completed_steps=["step1"],
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
