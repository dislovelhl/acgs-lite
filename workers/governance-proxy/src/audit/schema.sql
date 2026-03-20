-- D1 schema for ACGS governance audit log.
-- Constitutional Hash: cdd01ef066bc6cf2

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT NOT NULL,
  phase TEXT NOT NULL CHECK (phase IN ('request', 'response')),
  valid INTEGER NOT NULL DEFAULT 1,
  violations_json TEXT NOT NULL DEFAULT '[]',
  constitutional_hash TEXT NOT NULL,
  chain_hash TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  endpoint TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  latency_ms REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_valid ON audit_log(valid);
