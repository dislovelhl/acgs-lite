"""Flywheel run orchestration steps backed by saga persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.persistence.repository import WorkflowRepository
from enhanced_agent_bus.saga_persistence.models import FlywheelRunStage, SagaState
from enhanced_agent_bus.saga_persistence.repository import SagaStateRepository

from .dataset_builder import DatasetSnapshotBuilder, FeedbackEventSource
from .models import DatasetSnapshot

logger = get_logger(__name__)


class FlywheelRunOrchestrationError(RuntimeError):
    """Base error for flywheel run orchestration failures."""


class FlywheelRunNotFoundError(FlywheelRunOrchestrationError):
    """Raised when a flywheel run does not exist."""


class FlywheelRunPausedError(FlywheelRunOrchestrationError):
    """Raised when an operator-paused flywheel run is asked to continue."""


class FlywheelRunTerminalStateError(FlywheelRunOrchestrationError):
    """Raised when a terminal flywheel run is asked to execute more work."""


class FlywheelRunOrchestrator:
    """Run bounded flywheel stages while keeping mutable state in saga persistence."""

    def __init__(
        self,
        workflow_repository: WorkflowRepository,
        saga_repository: SagaStateRepository,
        feedback_source: FeedbackEventSource,
        *,
        artifact_root: str | Path,
    ) -> None:
        self._workflow_repository = workflow_repository
        self._saga_repository = saga_repository
        self._feedback_source = feedback_source
        self._artifact_root = Path(artifact_root)

    async def run_dataset_build_step(
        self,
        run_id: str,
        *,
        limit: int = 1000,
    ) -> DatasetSnapshot:
        """Build a redacted dataset snapshot for a flywheel run and advance the run state."""
        run = await self._saga_repository.get_flywheel_run(run_id)
        if run is None:
            raise FlywheelRunNotFoundError(f"Flywheel run {run_id!r} was not found")
        if run.paused:
            raise FlywheelRunPausedError(f"Flywheel run {run_id!r} is paused")
        if run.state.is_terminal():
            raise FlywheelRunTerminalStateError(
                f"Flywheel run {run_id!r} is already terminal: {run.state.value}"
            )

        if run.state == SagaState.INITIALIZED:
            started = await self._saga_repository.start_flywheel_run(run.run_id)
            if not started:
                raise FlywheelRunOrchestrationError(
                    f"Failed to transition flywheel run {run_id!r} to RUNNING"
                )
            run = await self._saga_repository.get_flywheel_run(run_id) or run

        builder = DatasetSnapshotBuilder(
            self._workflow_repository,
            self._feedback_source,
            artifact_root=self._artifact_root,
        )
        try:
            snapshot = await builder.build_snapshot(
                tenant_id=run.tenant_id,
                workload_key=run.workload_key,
                limit=limit,
            )
        except Exception as exc:
            await self._saga_repository.stop_flywheel_run(
                run.run_id,
                reason=f"dataset_build_failed:{type(exc).__name__}",
            )
            logger.warning(
                "flywheel_dataset_build_step_failed",
                run_id=run.run_id,
                tenant_id=run.tenant_id,
                workload_key=run.workload_key,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        run.dataset_snapshot_id = snapshot.snapshot_id
        run.stage = FlywheelRunStage.CANDIDATE_GENERATION
        run.current_step_index = max(run.current_step_index, 1)
        run.context["dataset_snapshot"] = {
            "snapshot_id": snapshot.snapshot_id,
            "record_count": snapshot.record_count,
            "artifact_manifest_uri": snapshot.artifact_manifest_uri,
            "window_started_at": (
                snapshot.window_started_at.isoformat() if snapshot.window_started_at else None
            ),
            "window_ended_at": (
                snapshot.window_ended_at.isoformat() if snapshot.window_ended_at else None
            ),
            "source_counts": dict(snapshot.source_counts),
        }
        run.metadata["latest_dataset_snapshot_id"] = snapshot.snapshot_id
        run.metadata["dataset_manifest_uri"] = snapshot.artifact_manifest_uri
        run.metadata["dataset_build_completed_at"] = datetime.now(UTC).isoformat()
        run.updated_at = datetime.now(UTC)
        run.version += 1

        saved = await self._saga_repository.save_flywheel_run(run)
        if not saved:
            raise FlywheelRunOrchestrationError(
                f"Failed to persist flywheel run {run_id!r} after dataset build"
            )

        await self._saga_repository.save_flywheel_checkpoint(
            run.run_id,
            "dataset_build_completed",
            is_constitutional=True,
            metadata={
                "dataset_snapshot_id": snapshot.snapshot_id,
                "artifact_manifest_uri": snapshot.artifact_manifest_uri,
                "record_count": snapshot.record_count,
            },
        )

        logger.info(
            "flywheel_dataset_build_step_completed",
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            workload_key=run.workload_key,
            dataset_snapshot_id=snapshot.snapshot_id,
            record_count=snapshot.record_count,
        )
        return snapshot


__all__ = [
    "FlywheelRunNotFoundError",
    "FlywheelRunOrchestrationError",
    "FlywheelRunOrchestrator",
    "FlywheelRunPausedError",
    "FlywheelRunTerminalStateError",
]
