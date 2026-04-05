/** ACGS data types matching backend Pydantic/dataclass models. */

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type WorkflowAction = "block" | "warn" | "escalate";

export interface Rule {
  id: string;
  text: string;
  severity: Severity;
  keywords: string[];
  patterns: string[];
  category: string;
  subcategory: string;
  depends_on: string[];
  enabled: boolean;
  workflow_action: WorkflowAction;
  hardcoded: boolean;
  tags: string[];
  priority: number;
  condition: Record<string, unknown>;
  deprecated: boolean;
  replaced_by: string;
  valid_from: string;
  valid_until: string;
  metadata: Record<string, unknown>;
}

export interface Violation {
  rule_id: string;
  rule_text: string;
  severity: Severity;
  matched_content: string;
  category: string;
}

export interface ValidationResult {
  valid: boolean;
  constitutional_hash: string;
  violations: Violation[];
  rules_checked: number;
  latency_ms: number;
  request_id: string;
  timestamp: string;
  action: string;
  agent_id: string;
}

export interface HealthResponse {
  status: string;
  engine: string;
}

export interface StatsResponse {
  total_validations: number;
  compliance_rate: number;
  avg_latency_ms: number;
  rules_count?: number;
  constitutional_hash?: string;
  audit_mode?: string;
  audit_metrics_complete?: boolean;
  unique_agents?: number;
  recent_validations?: ValidationResult[];
  audit_entry_count: number;
  audit_chain_valid: boolean;
}

export interface GovernanceState {
  state_id: string;
  rules: Rule[];
  version: string;
  name: string;
  description: string;
  metadata: Record<string, unknown>;
}

export interface StabilityMetrics {
  spectral_radius_bound: number;
  divergence: number;
  max_weight: number;
  stability_hash: string;
  input_norm: number;
  output_norm: number;
  timestamp: string;
}

export interface AuditEntry {
  timestamp: string;
  action: string;
  agent_id: string;
  valid: boolean;
  violations_count: number;
  rules_checked: number;
  latency_ms: number;
  request_id: string;
}
