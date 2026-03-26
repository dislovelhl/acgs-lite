"""
Module.

Constitutional Hash: 608508a9bd224290
"""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.deliberation_layer.workflows.constitutional_saga import (
    ConstitutionalSagaWorkflow,
    FileSagaPersistenceProvider,
    SagaStatus,
    SagaStep,
)
from enhanced_agent_bus.deliberation_layer.workflows.deliberation_workflow import (
    DeliberationWorkflow,
    DeliberationWorkflowInput,
    Vote,
)


@pytest.fixture
def persistence_path():
    path = Path("test_storage/workflow_states")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    if path.exists():
        shutil.rmtree("test_storage")


async def test_saga_persistence_and_resume(persistence_path):
    """Test that a saga can save its state and be resumed."""
    saga_id = "test-saga-persistence"
    provider = FileSagaPersistenceProvider(base_path=persistence_path)

    # Track execution
    executed_steps = []

    async def step_1(input_data):
        executed_steps.append("step_1")
        return {"data": 1}

    async def step_2(input_data):
        executed_steps.append("step_2")
        return {"data": 2}

    # 1. Start a saga and run first step
    saga = ConstitutionalSagaWorkflow(saga_id, persistence_provider=provider)
    saga.add_step(SagaStep(name="step_1", execute=step_1))
    saga.add_step(SagaStep(name="step_2", execute=step_2))

    # We will "manually" run one step by only adding one step first, or just interrupting.
    # Actually, ConstitutionalSagaWorkflow.execute runs everything.
    # Let's mock step_2 to fail to see if state is saved up to step 1.

    async def failing_step(input_data):
        raise RuntimeError("Interruption")

    saga2 = ConstitutionalSagaWorkflow(saga_id + "-interrupted", persistence_provider=provider)
    saga2.add_step(SagaStep(name="step_1", execute=step_1))
    saga2.add_step(SagaStep(name="failing_step", execute=failing_step))

    result = await saga2.execute()
    # If a step fails and compensation runs successfully, status is COMPENSATED
    assert result.status == SagaStatus.COMPENSATED

    # Check if state exists
    state = await provider.load_state(saga_id + "-interrupted")
    assert state is not None
    assert "step_1" in state.completed_steps
    assert state.context["step_1"]["data"] == 1

    # 2. Resume
    resumed_saga = await ConstitutionalSagaWorkflow.resume(saga_id + "-interrupted", provider)
    assert resumed_saga is not None
    assert resumed_saga.saga_id == saga_id + "-interrupted"
    assert "step_1" in resumed_saga._completed_steps


async def test_weighted_voting_consensus():
    """Test that weighted voting correctly influences consensus."""
    workflow_id = "test-weighted-voting"

    # Case 1: Equal weights, majority wins
    input_equal = DeliberationWorkflowInput(
        message_id="msg-1",
        content="test",
        from_agent="a",
        to_agent="b",
        message_type="test",
        priority="medium",
        required_votes=3,
        consensus_threshold=0.6,
        agent_weights={"v1": 1.0, "v2": 1.0, "v3": 1.0},
    )

    workflow = DeliberationWorkflow(workflow_id)

    votes_fail = [
        Vote(agent_id="v1", decision="approve", reasoning="", confidence=1.0),
        Vote(agent_id="v2", decision="reject", reasoning="", confidence=1.0),
        Vote(agent_id="v3", decision="reject", reasoning="", confidence=1.0),
    ]

    assert workflow._check_consensus(votes_fail, 3, 0.6, input_equal.agent_weights) is False

    # Case 2: Weighted, small number of agents with high weight win
    input_weighted = DeliberationWorkflowInput(
        message_id="msg-2",
        content="test",
        from_agent="a",
        to_agent="b",
        message_type="test",
        priority="medium",
        required_votes=3,
        consensus_threshold=0.6,
        agent_weights={"v1": 10.0, "v2": 1.0, "v3": 1.0},  # v1 is the "boss"
    )

    # v1 approves, v2 and v3 reject. 10/(10+1+1) = 10/12 = 0.833 > 0.6. Should pass.
    assert workflow._check_consensus(votes_fail, 3, 0.6, input_weighted.agent_weights) is True


async def test_workflow_versioning_propagation():
    """Test that versioning is correctly propagated in results."""
    input_v2 = DeliberationWorkflowInput(
        message_id="msg-v2",
        content="test",
        from_agent="a",
        to_agent="b",
        message_type="test",
        priority="medium",
        version="2.0.0",
    )

    # Mocking activities to skip real logic
    activities = MagicMock()
    activities.validate_constitutional_hash = AsyncMock(return_value={"is_valid": True})
    activities.calculate_impact_score = AsyncMock(return_value=0.5)
    activities.evaluate_opa_policy = AsyncMock(return_value={"allowed": True})
    activities.deliver_message = AsyncMock(return_value=True)
    activities.record_audit_trail = AsyncMock(return_value="0x123")

    workflow = DeliberationWorkflow("test-version", activities=activities)
    result = await workflow.run(input_v2)

    assert result.version == "2.0.0"


if __name__ == "__main__":
    pytest.main([__file__])
