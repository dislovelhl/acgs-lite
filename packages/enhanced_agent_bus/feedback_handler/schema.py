"""
ACGS-2 Feedback Handler - Schema Module
Constitutional Hash: 608508a9bd224290

Database schema definitions for feedback events.
"""

# Database Schema

FEEDBACK_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id VARCHAR(255) NOT NULL,
    feedback_type VARCHAR(50) NOT NULL,
    outcome VARCHAR(50) NOT NULL DEFAULT 'unknown',
    user_id VARCHAR(255),
    tenant_id VARCHAR(255),
    comment TEXT,
    correction_data JSONB,
    features JSONB,
    actual_impact FLOAT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    published_to_kafka BOOLEAN DEFAULT FALSE,

    -- Indexes for common queries
    CONSTRAINT valid_feedback_type CHECK (feedback_type IN ('positive', 'negative', 'neutral', 'correction')),
    CONSTRAINT valid_outcome CHECK (outcome IN ('success', 'failure', 'partial', 'unknown')),
    CONSTRAINT valid_actual_impact CHECK (actual_impact IS NULL OR (actual_impact >= 0.0 AND actual_impact <= 1.0))
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_feedback_decision_id ON feedback_events(decision_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback_events(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_feedback_tenant_id ON feedback_events(tenant_id) WHERE tenant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback_events(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_processed ON feedback_events(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_events(feedback_type);
"""


__all__ = [
    "FEEDBACK_TABLE_SCHEMA",
]
