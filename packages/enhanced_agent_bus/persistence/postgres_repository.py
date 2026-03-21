"""
PostgreSQL Workflow Repository - Production-grade persistence.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    import asyncpg

try:
    import asyncpg as asyncpg_module
except ImportError:
    asyncpg_module = None  # type: ignore[assignment]
from .models import (
    CheckpointData,
    EventType,
    StepStatus,
    StepType,
    WorkflowCompensation,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStatus,
    WorkflowStep,
)
from .repository import WorkflowRepository

logger = get_logger(__name__)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workflow_instances (
    id UUID PRIMARY KEY,
    workflow_type VARCHAR(255) NOT NULL,
    workflow_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    input JSONB,
    output JSONB,
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    constitutional_hash VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workflow_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id UUID PRIMARY KEY,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_name VARCHAR(255) NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    input JSONB,
    output JSONB,
    error TEXT,
    idempotency_key VARCHAR(255),
    attempt_count INT DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_events (
    id BIGSERIAL PRIMARY KEY,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    sequence_number BIGINT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workflow_instance_id, sequence_number)
);

CREATE TABLE IF NOT EXISTS workflow_compensations (
    id UUID PRIMARY KEY,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_id UUID REFERENCES workflow_steps(id) ON DELETE CASCADE,
    compensation_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    input JSONB,
    output JSONB,
    error TEXT,
    executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    id UUID PRIMARY KEY,
    workflow_instance_id UUID REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_index INT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_instances_tenant ON workflow_instances(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_status ON workflow_instances(status);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_type ON workflow_instances(workflow_type);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_instance ON workflow_steps(workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_idempotency ON workflow_steps(workflow_instance_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_workflow_events_instance_seq ON workflow_events(workflow_instance_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_workflow_compensations_instance ON workflow_compensations(workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_instance ON workflow_checkpoints(workflow_instance_id);
"""  # noqa: E501


def _serialize_json_value(value: object) -> str | None:
    """Serialize dict/list JSON payloads for asyncpg JSONB columns."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _deserialize_json_value(value: object) -> object:
    """Deserialize JSONB payloads returned as strings by asyncpg."""
    if isinstance(value, str):
        return json.loads(value)
    return value


class PostgresWorkflowRepository(WorkflowRepository):
    """Production PostgreSQL repository with connection pooling."""

    def __init__(self, dsn: str, min_connections: int = 5, max_connections: int = 20):
        if asyncpg_module is None:
            raise ImportError("asyncpg required: pip install asyncpg")
        self.dsn = dsn
        self.min_connections = min_connections
        self.max_connections = max_connections
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg_module.create_pool(
            self.dsn,
            min_size=self.min_connections,
            max_size=self.max_connections,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("PostgreSQL workflow repository initialized")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @asynccontextmanager
    async def _connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        if not self._pool:
            raise RuntimeError("Repository not initialized - call initialize() first")
        async with self._pool.acquire() as conn:
            yield conn

    async def save_workflow(self, instance: WorkflowInstance) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_instances
                    (id, workflow_type, workflow_id, tenant_id, status, input, output,
                     error, started_at, completed_at, constitutional_hash, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    output = EXCLUDED.output,
                    error = EXCLUDED.error,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    updated_at = NOW()
                """,
                instance.id,
                instance.workflow_type,
                instance.workflow_id,
                instance.tenant_id,
                instance.status,
                _serialize_json_value(instance.input),
                _serialize_json_value(instance.output),
                instance.error,
                instance.started_at,
                instance.completed_at,
                instance.constitutional_hash,
                instance.created_at,
                datetime.now(UTC),
            )

    async def get_workflow(self, instance_id: UUID) -> WorkflowInstance | None:
        async with self._connection() as conn:
            row = await conn.fetchrow("SELECT * FROM workflow_instances WHERE id = $1", instance_id)
            return self._row_to_workflow(row) if row else None

    async def get_workflow_by_business_id(
        self, workflow_id: str, tenant_id: str
    ) -> WorkflowInstance | None:
        async with self._connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflow_instances WHERE workflow_id = $1 AND tenant_id = $2",
                workflow_id,
                tenant_id,
            )
            return self._row_to_workflow(row) if row else None

    async def save_step(self, step: WorkflowStep) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_steps
                    (id, workflow_instance_id, step_name, step_type, status, input, output,
                     error, idempotency_key, attempt_count, started_at, completed_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    output = EXCLUDED.output,
                    error = EXCLUDED.error,
                    attempt_count = EXCLUDED.attempt_count,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at
                """,
                step.id,
                step.workflow_instance_id,
                step.step_name,
                step.step_type,
                step.status,
                _serialize_json_value(step.input),
                _serialize_json_value(step.output),
                step.error,
                step.idempotency_key,
                step.attempt_count,
                step.started_at,
                step.completed_at,
                step.created_at,
            )

    async def get_step_by_idempotency_key(
        self, workflow_instance_id: UUID, idempotency_key: str
    ) -> WorkflowStep | None:
        async with self._connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM workflow_steps
                WHERE workflow_instance_id = $1 AND idempotency_key = $2
                """,
                workflow_instance_id,
                idempotency_key,
            )
            return self._row_to_step(row) if row else None

    async def get_steps(self, workflow_instance_id: UUID) -> list[WorkflowStep]:
        async with self._connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_steps
                WHERE workflow_instance_id = $1
                ORDER BY created_at
                """,
                workflow_instance_id,
            )
            return [self._row_to_step(row) for row in rows]

    async def save_event(self, event: WorkflowEvent) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_events
                    (workflow_instance_id, event_type, event_data, sequence_number, timestamp)
                VALUES ($1, $2, $3, $4, $5)
                """,
                event.workflow_instance_id,
                event.event_type,
                _serialize_json_value(event.event_data),
                event.sequence_number,
                event.timestamp,
            )

    async def get_events(
        self, workflow_instance_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[WorkflowEvent]:
        async with self._connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_events
                WHERE workflow_instance_id = $1
                ORDER BY sequence_number
                LIMIT $2 OFFSET $3
                """,
                workflow_instance_id,
                limit,
                offset,
            )
            return [self._row_to_event(row) for row in rows]

    async def get_next_sequence(self, workflow_instance_id: UUID) -> int:
        async with self._connection() as conn:
            result = await conn.fetchval(
                """
                SELECT COALESCE(MAX(sequence_number), 0) + 1
                FROM workflow_events
                WHERE workflow_instance_id = $1
                """,
                workflow_instance_id,
            )
            return result  # type: ignore[no-any-return]

    async def save_compensation(self, compensation: WorkflowCompensation) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_compensations
                    (id, workflow_instance_id, step_id, compensation_name, status,
                     input, output, error, executed_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    output = EXCLUDED.output,
                    error = EXCLUDED.error,
                    executed_at = EXCLUDED.executed_at
                """,
                compensation.id,
                compensation.workflow_instance_id,
                compensation.step_id,
                compensation.compensation_name,
                compensation.status,
                _serialize_json_value(compensation.input),
                _serialize_json_value(compensation.output),
                compensation.error,
                compensation.executed_at,
                compensation.created_at,
            )

    async def get_compensations(
        self, workflow_instance_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[WorkflowCompensation]:
        async with self._connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_compensations
                WHERE workflow_instance_id = $1
                ORDER BY created_at
                LIMIT $2 OFFSET $3
                """,
                workflow_instance_id,
                limit,
                offset,
            )
            return [self._row_to_compensation(row) for row in rows]

    async def save_checkpoint(self, checkpoint: CheckpointData) -> None:
        async with self._connection() as conn:
            await conn.execute(
                """
                INSERT INTO workflow_checkpoints
                    (id, workflow_instance_id, step_index, state, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                checkpoint.checkpoint_id,
                checkpoint.workflow_instance_id,
                checkpoint.step_index,
                _serialize_json_value(checkpoint.state),
                checkpoint.created_at,
            )

    async def get_latest_checkpoint(self, workflow_instance_id: UUID) -> CheckpointData | None:
        async with self._connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM workflow_checkpoints
                WHERE workflow_instance_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                workflow_instance_id,
            )
            return self._row_to_checkpoint(row) if row else None

    async def list_workflows(
        self, tenant_id: str, status: WorkflowStatus | None = None, limit: int = 100
    ) -> list[WorkflowInstance]:
        query = """
            SELECT * FROM workflow_instances
            WHERE tenant_id = $1
        """
        args = [tenant_id]

        if status:
            query += " AND status = $2"
            args.append(status.value)

        query += f" ORDER BY created_at DESC LIMIT ${len(args) + 1}"
        args.append(limit)

        async with self._connection() as conn:
            rows = await conn.fetch(query, *args)
            return [self._row_to_workflow(row) for row in rows]

    def _row_to_workflow(self, row: asyncpg.Record) -> WorkflowInstance:
        return WorkflowInstance(
            id=row["id"],
            workflow_type=row["workflow_type"],
            workflow_id=row["workflow_id"],
            tenant_id=row["tenant_id"],
            status=WorkflowStatus(row["status"]),
            input=_deserialize_json_value(row["input"]),
            output=_deserialize_json_value(row["output"]),
            error=row["error"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            constitutional_hash=row["constitutional_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_step(self, row: asyncpg.Record) -> WorkflowStep:
        return WorkflowStep(
            id=row["id"],
            workflow_instance_id=row["workflow_instance_id"],
            step_name=row["step_name"],
            step_type=StepType(row["step_type"]),
            status=StepStatus(row["status"]),
            input=_deserialize_json_value(row["input"]),
            output=_deserialize_json_value(row["output"]),
            error=row["error"],
            idempotency_key=row["idempotency_key"],
            attempt_count=row["attempt_count"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
        )

    def _row_to_event(self, row: asyncpg.Record) -> WorkflowEvent:
        return WorkflowEvent(
            id=row["id"],
            workflow_instance_id=row["workflow_instance_id"],
            event_type=EventType(row["event_type"]),
            event_data=_deserialize_json_value(row["event_data"]),
            sequence_number=row["sequence_number"],
            timestamp=row["timestamp"],
        )

    def _row_to_compensation(self, row: asyncpg.Record) -> WorkflowCompensation:
        return WorkflowCompensation(
            id=row["id"],
            workflow_instance_id=row["workflow_instance_id"],
            step_id=row["step_id"],
            compensation_name=row["compensation_name"],
            status=StepStatus(row["status"]),
            input=_deserialize_json_value(row["input"]),
            output=_deserialize_json_value(row["output"]),
            error=row["error"],
            executed_at=row["executed_at"],
            created_at=row["created_at"],
        )

    def _row_to_checkpoint(self, row: asyncpg.Record) -> CheckpointData:
        return CheckpointData(
            workflow_instance_id=row["workflow_instance_id"],
            checkpoint_id=row["id"],
            step_index=row["step_index"],
            state=_deserialize_json_value(row["state"]),
            created_at=row["created_at"],
        )
