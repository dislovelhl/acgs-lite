"""
Workflow Replay Engine - Deterministic replay from event history.

Constitutional Hash: 608508a9bd224290
"""

from uuid import UUID

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import EventType, WorkflowEvent, WorkflowInstance, WorkflowStatus
from .repository import WorkflowRepository

logger = get_logger(__name__)
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class ReplayEngine:
    """
    Deterministic replay engine for workflow recovery.

    Replays workflow from event history to reconstruct state.
    Used for:
    - Recovery after service restart
    - Debugging workflow execution
    - Audit trail verification
    """

    def __init__(self, repository: WorkflowRepository):
        self.repository = repository

    async def replay_workflow(
        self, workflow_instance_id: UUID, up_to_sequence: int | None = None
    ) -> WorkflowInstance:
        """
        Replay workflow from event history.

        Args:
            workflow_instance_id: Workflow to replay
            up_to_sequence: Optional sequence number to replay up to

        Returns:
            Reconstructed workflow instance state
        """
        events = await self.repository.get_events(workflow_instance_id)

        if up_to_sequence:
            events = [e for e in events if e.sequence_number <= up_to_sequence]

        if not events:
            raise ValueError(f"No events found for workflow {workflow_instance_id}")

        instance = await self._reconstruct_from_events(workflow_instance_id, events)
        logger.info(f"Replayed workflow {workflow_instance_id} from {len(events)} events")
        return instance

    async def _reconstruct_from_events(
        self, workflow_instance_id: UUID, events: list[WorkflowEvent]
    ) -> WorkflowInstance:
        """Reconstruct workflow state from event sequence."""
        instance: WorkflowInstance | None = None

        for event in events:
            if event.event_type == EventType.WORKFLOW_STARTED:
                instance = WorkflowInstance(
                    id=workflow_instance_id,
                    workflow_type=event.event_data.get("workflow_type", ""),
                    workflow_id=event.event_data.get("workflow_id", str(workflow_instance_id)),
                    tenant_id=event.event_data.get("tenant_id", "default"),
                    input=event.event_data.get("input"),
                    status=WorkflowStatus.RUNNING,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )

            elif event.event_type == EventType.WORKFLOW_COMPLETED:
                if instance:
                    instance.status = WorkflowStatus.COMPLETED
                    instance.output = event.event_data.get("output")

            elif event.event_type == EventType.WORKFLOW_FAILED:
                if instance:
                    instance.status = WorkflowStatus.FAILED
                    instance.error = event.event_data.get("error")

            elif event.event_type == EventType.WORKFLOW_CANCELLED:
                if instance:
                    instance.status = WorkflowStatus.CANCELLED
                    instance.error = event.event_data.get("reason")

        if not instance:
            raise ValueError("Could not reconstruct workflow - missing WORKFLOW_STARTED event")

        return instance

    async def verify_determinism(self, workflow_instance_id: UUID, expected_output: dict) -> bool:
        """
        Verify that replay produces expected output.

        Used for testing and audit verification.
        """
        replayed = await self.replay_workflow(workflow_instance_id)
        return replayed.output == expected_output

    async def get_replay_timeline(self, workflow_instance_id: UUID) -> list[dict]:
        """
        Get human-readable timeline of workflow execution.

        Returns list of events with timestamps and descriptions.
        """
        events = await self.repository.get_events(workflow_instance_id)
        timeline = []

        for event in events:
            timeline.append(
                {
                    "sequence": event.sequence_number,
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.event_type.value,
                    "data": event.event_data,
                }
            )

        return timeline
