-- ACGS-2 Multi-Tenancy Foundation Migration
-- Constitutional Hash: cdd01ef066bc6cf2
-- Phase 10, Task 1: Multi-Tenant Database Foundation
--
-- This migration adds multi-tenant support via PostgreSQL Row-Level Security (RLS).
-- All tenant-scoped tables will have automatic data isolation.

-- ============================================================================
-- 1. Create Tenants Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(63) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'suspended', 'deactivated', 'migrating')),

    -- Configuration (stored as JSONB for flexibility)
    config JSONB NOT NULL DEFAULT '{}',

    -- Resource quotas
    quota JSONB NOT NULL DEFAULT '{
        "max_agents": 100,
        "max_policies": 1000,
        "max_messages_per_minute": 10000,
        "max_batch_size": 1000,
        "max_storage_mb": 10240,
        "max_concurrent_sessions": 100
    }',

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Hierarchical tenancy
    parent_tenant_id UUID REFERENCES tenants(tenant_id) ON DELETE SET NULL,

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    suspended_at TIMESTAMPTZ,

    -- Indexes
    CONSTRAINT valid_slug CHECK (slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$')
);

-- Indexes for tenants table
CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
CREATE INDEX IF NOT EXISTS idx_tenants_parent ON tenants(parent_tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenants_created ON tenants(created_at DESC);

-- ============================================================================
-- 2. Add tenant_id to Constitutional Versions
-- ============================================================================

ALTER TABLE constitutional_versions
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(tenant_id);

-- Create index for tenant lookups
CREATE INDEX IF NOT EXISTS idx_constitutional_versions_tenant
    ON constitutional_versions(tenant_id);

-- ============================================================================
-- 3. Add tenant_id to Amendment Proposals
-- ============================================================================

ALTER TABLE amendment_proposals
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(tenant_id);

CREATE INDEX IF NOT EXISTS idx_amendment_proposals_tenant
    ON amendment_proposals(tenant_id);

-- ============================================================================
-- 4. Create Policies Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    description TEXT,

    -- Policy content
    policy_type VARCHAR(50) NOT NULL DEFAULT 'rego',
    content TEXT NOT NULL,

    -- Status and lifecycle
    status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'deprecated', 'archived')),

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ,

    -- Ownership
    created_by VARCHAR(255),
    updated_by VARCHAR(255),

    UNIQUE(tenant_id, name, version)
);

CREATE INDEX IF NOT EXISTS idx_policies_tenant ON policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_policies_name ON policies(tenant_id, name);
CREATE INDEX IF NOT EXISTS idx_policies_tags ON policies USING GIN(tags);

-- ============================================================================
-- 5. Create Agents Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS agents (
    agent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    description TEXT,

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'suspended', 'decommissioned')),

    -- MACI role
    maci_role VARCHAR(50),
    capabilities TEXT[] DEFAULT '{}',

    -- Configuration
    config JSONB NOT NULL DEFAULT '{}',

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ,

    UNIQUE(tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_agents_maci_role ON agents(tenant_id, maci_role);

-- ============================================================================
-- 6. Create Agent Messages Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    from_agent_id UUID REFERENCES agents(agent_id),
    to_agent_id UUID REFERENCES agents(agent_id),

    message_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'NORMAL'
        CHECK (priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'expired')),

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',
    validation_result JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_tenant ON agent_messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON agent_messages(tenant_id, from_agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(tenant_id, to_agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON agent_messages(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_messages_created ON agent_messages(tenant_id, created_at DESC);

-- ============================================================================
-- 7. Create Audit Logs Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    event_type VARCHAR(100) NOT NULL,
    event_source VARCHAR(255) NOT NULL,

    -- Actor information
    actor_id VARCHAR(255),
    actor_type VARCHAR(50),

    -- Event details
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    action VARCHAR(100) NOT NULL,

    -- Content
    old_value JSONB,
    new_value JSONB,
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Request context
    request_id VARCHAR(255),
    source_ip INET,
    user_agent TEXT,

    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partitioning for audit logs (by month)
-- Note: In production, consider partitioning by tenant_id + time

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event ON audit_logs(tenant_id, event_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(tenant_id, actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(tenant_id, resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(tenant_id, created_at DESC);

-- ============================================================================
-- 8. Create Decision Logs Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS decision_logs (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    decision_type VARCHAR(100) NOT NULL,

    -- Request
    request_content JSONB NOT NULL,
    request_context JSONB NOT NULL DEFAULT '{}',

    -- Decision
    decision VARCHAR(50) NOT NULL
        CHECK (decision IN ('allowed', 'denied', 'escalated', 'pending')),
    decision_reason TEXT,

    -- Impact assessment
    impact_score DECIMAL(5, 4),
    risk_level VARCHAR(20),

    -- Policy evaluation
    policies_evaluated TEXT[] DEFAULT '{}',
    policy_results JSONB,

    -- Deliberation (if applicable)
    deliberation_required BOOLEAN NOT NULL DEFAULT FALSE,
    deliberation_id UUID,

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',
    constitutional_compliant BOOLEAN NOT NULL DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,

    -- Blockchain anchoring
    blockchain_tx_hash VARCHAR(128),
    anchored_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_decision_logs_tenant ON decision_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_decision_logs_type ON decision_logs(tenant_id, decision_type);
CREATE INDEX IF NOT EXISTS idx_decision_logs_decision ON decision_logs(tenant_id, decision);
CREATE INDEX IF NOT EXISTS idx_decision_logs_created ON decision_logs(tenant_id, created_at DESC);

-- ============================================================================
-- 9. Create Governance Sessions Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS governance_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    session_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'expired', 'cancelled')),

    -- Session context
    initiator_id VARCHAR(255),
    config JSONB NOT NULL DEFAULT '{}',

    -- Metrics
    request_count INTEGER NOT NULL DEFAULT 0,
    violation_count INTEGER NOT NULL DEFAULT 0,
    escalation_count INTEGER NOT NULL DEFAULT 0,

    -- Risk tracking
    current_risk_level VARCHAR(20) NOT NULL DEFAULT 'LOW',

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_governance_sessions_tenant ON governance_sessions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_governance_sessions_status ON governance_sessions(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_governance_sessions_initiator ON governance_sessions(tenant_id, initiator_id);

-- ============================================================================
-- 10. Create MACI Records Table with Multi-Tenancy
-- ============================================================================

CREATE TABLE IF NOT EXISTS maci_records (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),

    agent_id UUID NOT NULL REFERENCES agents(agent_id),
    role VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,

    -- Target output (for cross-validation)
    target_output_id UUID,
    target_agent_id UUID REFERENCES agents(agent_id),

    -- Validation result
    allowed BOOLEAN NOT NULL,
    denied_reason TEXT,

    -- Constitutional compliance
    constitutional_hash VARCHAR(64) NOT NULL DEFAULT 'cdd01ef066bc6cf2',

    -- Metadata
    metadata JSONB NOT NULL DEFAULT '{}',

    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maci_records_tenant ON maci_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_maci_records_agent ON maci_records(tenant_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_maci_records_role ON maci_records(tenant_id, role);
CREATE INDEX IF NOT EXISTS idx_maci_records_created ON maci_records(tenant_id, created_at DESC);

-- ============================================================================
-- 11. Enable Row-Level Security
-- ============================================================================

-- Enable RLS on all tenant-scoped tables
ALTER TABLE constitutional_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE constitutional_versions FORCE ROW LEVEL SECURITY;

ALTER TABLE amendment_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE amendment_proposals FORCE ROW LEVEL SECURITY;

ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies FORCE ROW LEVEL SECURITY;

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents FORCE ROW LEVEL SECURITY;

ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

ALTER TABLE decision_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_logs FORCE ROW LEVEL SECURITY;

ALTER TABLE governance_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE governance_sessions FORCE ROW LEVEL SECURITY;

ALTER TABLE maci_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE maci_records FORCE ROW LEVEL SECURITY;

-- ============================================================================
-- 12. Create RLS Policies for Tenant Isolation
-- ============================================================================

-- Tenant isolation policies (using PostgreSQL session variables)
-- These ensure each tenant can only access their own data

-- Constitutional Versions
CREATE POLICY constitutional_versions_tenant_isolation ON constitutional_versions
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true
           OR tenant_id IS NULL);  -- Allow global versions

-- Amendment Proposals
CREATE POLICY amendment_proposals_tenant_isolation ON amendment_proposals
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true
           OR tenant_id IS NULL);

-- Policies
CREATE POLICY policies_tenant_isolation ON policies
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- Agents
CREATE POLICY agents_tenant_isolation ON agents
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- Agent Messages
CREATE POLICY agent_messages_tenant_isolation ON agent_messages
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- Audit Logs
CREATE POLICY audit_logs_tenant_isolation ON audit_logs
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- Decision Logs
CREATE POLICY decision_logs_tenant_isolation ON decision_logs
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- Governance Sessions
CREATE POLICY governance_sessions_tenant_isolation ON governance_sessions
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- MACI Records
CREATE POLICY maci_records_tenant_isolation ON maci_records
    FOR ALL
    TO PUBLIC
    USING (tenant_id::text = current_setting('app.current_tenant_id', true)
           OR current_setting('app.is_admin', true)::boolean = true);

-- ============================================================================
-- 13. Create Helper Functions
-- ============================================================================

-- Function to set tenant context
CREATE OR REPLACE FUNCTION set_tenant_context(p_tenant_id TEXT, p_is_admin BOOLEAN DEFAULT FALSE)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', p_tenant_id, FALSE);
    PERFORM set_config('app.is_admin', p_is_admin::TEXT, FALSE);
    PERFORM set_config('app.constitutional_hash', 'cdd01ef066bc6cf2', FALSE);
END;
$$ LANGUAGE plpgsql;

-- Function to clear tenant context
CREATE OR REPLACE FUNCTION clear_tenant_context()
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', '', FALSE);
    PERFORM set_config('app.is_admin', 'false', FALSE);
END;
$$ LANGUAGE plpgsql;

-- Function to get current tenant
CREATE OR REPLACE FUNCTION get_current_tenant_id()
RETURNS TEXT AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', TRUE);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 14. Create Updated_At Trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_policies_updated_at
    BEFORE UPDATE ON policies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agents_updated_at
    BEFORE UPDATE ON agents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_governance_sessions_updated_at
    BEFORE UPDATE ON governance_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 15. Insert Default System Tenant
-- ============================================================================

INSERT INTO tenants (
    tenant_id,
    name,
    slug,
    status,
    config,
    constitutional_hash
) VALUES (
    '00000000-0000-0000-0000-000000000000',
    'ACGS-2 System',
    'system',
    'active',
    '{"is_system_tenant": true}',
    'cdd01ef066bc6cf2'
) ON CONFLICT (slug) DO NOTHING;

-- ============================================================================
-- Migration Complete
-- Constitutional Hash: cdd01ef066bc6cf2
-- ============================================================================
