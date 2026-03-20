/// Type definitions for the ACGS governance proxy.
///
/// Constitutional Hash: cdd01ef066bc6cf2

export interface Env {
  CONSTITUTIONS: KVNamespace;
  AUDIT_DB: D1Database;
  CONSTITUTIONAL_HASH: string;
  UPSTREAM_API_KEY?: string;
}

export interface GovernanceContext {
  tenantId: string;
  endpoint: "chat.completions" | "responses" | "embeddings";
  model: string;
  env: string;
  apiKeyId: string;
  systemPrompt?: string;
  actionDescription?: string;
  actionDetail?: string;
}

export interface GovernanceViolation {
  rule_id: string;
  rule_text: string;
  severity: "critical" | "high" | "medium" | "low";
  matched_content: string;
  category: string;
}

export interface GovernanceResult {
  decision: number;
  valid: boolean;
  violations: GovernanceViolation[];
  blocking: boolean;
  constitutional_hash: string;
  rules_checked: number;
}

export interface AuditRecord {
  request_id: string;
  phase: "request" | "response";
  valid: boolean;
  violations_json: string;
  constitutional_hash: string;
  chain_hash: string;
  timestamp: string;
  tenant_id: string;
  endpoint: string;
  model: string;
  latency_ms: number;
}

export interface GovernanceProof {
  version: "v1";
  requestId: string;
  phase: "request" | "response";
  constitutionalHash: string;
  result: "allow" | "deny";
  rulesChecked: number;
}
