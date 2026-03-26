"""
PostgreSQL Saga Repository Schema Definitions
Constitutional Hash: 608508a9bd224290

Contains database schema SQL and configuration constants for the
PostgreSQL saga state repository.
"""

from enhanced_agent_bus.saga_persistence.models import SagaState

# Default configuration constants
DEFAULT_POOL_MIN_SIZE = 5
DEFAULT_POOL_MAX_SIZE = 20
DEFAULT_LOCK_TIMEOUT_SECONDS = 30
DEFAULT_TTL_DAYS = 7

# Valid state transitions
VALID_STATE_TRANSITIONS: dict[SagaState, set[SagaState]] = {
    SagaState.INITIALIZED: {SagaState.RUNNING, SagaState.FAILED},
    SagaState.RUNNING: {SagaState.COMPLETED, SagaState.COMPENSATING, SagaState.FAILED},
    SagaState.COMPENSATING: {SagaState.COMPENSATED, SagaState.FAILED},
    SagaState.COMPLETED: set(),  # Terminal state
    SagaState.COMPENSATED: set(),  # Terminal state
    SagaState.FAILED: set(),  # Terminal state
}

# Database schema for self-initialization
SCHEMA_SQL = """
-- Saga States Table
CREATE TABLE IF NOT EXISTS saga_states (
    saga_id UUID PRIMARY KEY,
    saga_name VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    correlation_id UUID NOT NULL,
    state VARCHAR(50) NOT NULL DEFAULT 'INITIALIZED',
    compensation_strategy VARCHAR(50) NOT NULL DEFAULT 'LIFO',
    current_step_index INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    compensation_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    compensated_at TIMESTAMPTZ,
    total_duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    failure_reason TEXT,
    timeout_ms INTEGER NOT NULL DEFAULT 300000,
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT CONSTITUTIONAL_HASH,  -- pragma: allowlist secret
    CONSTRAINT valid_state CHECK (state IN (
        'INITIALIZED', 'RUNNING', 'COMPENSATING',
        'COMPLETED', 'COMPENSATED', 'FAILED'
    )),
    CONSTRAINT valid_compensation_strategy CHECK (compensation_strategy IN (
        'LIFO', 'PARALLEL', 'SELECTIVE'
    )),
    CONSTRAINT valid_constitutional_hash CHECK (constitutional_hash = CONSTITUTIONAL_HASH)  -- pragma: allowlist secret
);

-- Indexes for saga_states
CREATE INDEX IF NOT EXISTS idx_saga_states_tenant_id ON saga_states(tenant_id);
CREATE INDEX IF NOT EXISTS idx_saga_states_state ON saga_states(state);
CREATE INDEX IF NOT EXISTS idx_saga_states_created_at ON saga_states(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_saga_states_tenant_state ON saga_states(tenant_id, state);
CREATE INDEX IF NOT EXISTS idx_saga_states_correlation ON saga_states(correlation_id);

-- Saga Checkpoints Table
CREATE TABLE IF NOT EXISTS saga_checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    saga_id UUID NOT NULL REFERENCES saga_states(saga_id) ON DELETE CASCADE,
    checkpoint_name VARCHAR(255) NOT NULL,
    state_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    completed_step_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending_step_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_constitutional BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT CONSTITUTIONAL_HASH,  -- pragma: allowlist secret
    CONSTRAINT valid_checkpoint_hash CHECK (constitutional_hash = CONSTITUTIONAL_HASH)  -- pragma: allowlist secret
);

-- Indexes for saga_checkpoints
CREATE INDEX IF NOT EXISTS idx_saga_checkpoints_saga_id ON saga_checkpoints(saga_id);
CREATE INDEX IF NOT EXISTS idx_saga_checkpoints_created_at ON saga_checkpoints(saga_id, created_at DESC);

-- Saga Locks Table (for distributed locking)
CREATE TABLE IF NOT EXISTS saga_locks (
    saga_id UUID PRIMARY KEY,
    lock_holder VARCHAR(255) NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT CONSTITUTIONAL_HASH,  -- pragma: allowlist secret
    CONSTRAINT valid_lock_hash CHECK (constitutional_hash = CONSTITUTIONAL_HASH)  -- pragma: allowlist secret
);

-- Index for lock expiration cleanup
CREATE INDEX IF NOT EXISTS idx_saga_locks_expires_at ON saga_locks(expires_at);
"""


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_POOL_MAX_SIZE",
    "DEFAULT_POOL_MIN_SIZE",
    "DEFAULT_TTL_DAYS",
    "SCHEMA_SQL",
    "VALID_STATE_TRANSITIONS",
]
