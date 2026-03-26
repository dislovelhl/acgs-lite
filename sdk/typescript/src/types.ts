/**
 * TypeScript types for the ACGS platform API.
 *
 * All response types use readonly properties to enforce immutability.
 */

// ---------------------------------------------------------------------------
// Client configuration
// ---------------------------------------------------------------------------

export interface ACGSClientConfig {
  /** Base URL of the ACGS API gateway (e.g. "http://localhost:8080"). */
  readonly baseUrl: string;
  /** Additional headers sent with every request (e.g. auth tokens). */
  readonly headers?: Readonly<Record<string, string>>;
  /** Request timeout in milliseconds. Defaults to 30 000. */
  readonly timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Governance
// ---------------------------------------------------------------------------

export interface GovernanceEvent {
  readonly id: string;
  readonly type: string;
  readonly severity: string;
  readonly action: string;
  readonly result: string;
  readonly tenant_id: string;
  readonly timestamp: string;
}

export interface ComplianceFramework {
  readonly framework: string;
  readonly status: string;
  readonly score: number;
  readonly items_total: number;
  readonly items_passing: number;
}

export interface GovernanceStatus {
  readonly constitutional_hash: string;
  readonly maci_strict_mode: boolean;
  readonly total_validations_24h: number;
  readonly violations_24h: number;
  readonly compliance_frameworks: readonly ComplianceFramework[];
  readonly last_updated: string;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface ServiceHealth {
  readonly service_name: string;
  readonly status: string;
  readonly port: number;
  readonly uptime_seconds: number;
  readonly last_check: string;
  readonly version: string;
}

export interface HealthDashboard {
  readonly overall_status: string;
  readonly services: readonly ServiceHealth[];
  readonly checked_at: string;
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export interface AuditEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly action: string;
  readonly actor: string;
  readonly result: string;
  readonly severity: string;
  readonly hash: string;
  readonly previous_hash: string;
  readonly metadata: Readonly<Record<string, unknown>>;
}

export interface AuditTrailResponse {
  readonly items: readonly AuditEntry[];
  readonly total: number;
  readonly page: number;
  readonly limit: number;
}

export interface AuditTrailOptions {
  readonly page?: number;
  readonly limit?: number;
  readonly severity?: string;
  readonly tenant_id?: string;
  readonly start_date?: string;
  readonly end_date?: string;
}

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------

export type PolicyStatus = "draft" | "active" | "archived";

export interface RuleModel {
  readonly id: string;
  readonly text: string;
  readonly severity: string;
  readonly keywords: readonly string[];
  readonly patterns: readonly string[];
}

export interface PolicyResponse {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly version: number;
  readonly rules: readonly RuleModel[];
  readonly source_yaml: string;
  readonly status: PolicyStatus;
  readonly created_at: string;
  readonly updated_at: string;
  readonly created_by: string;
}

export interface PolicyListResponse {
  readonly items: readonly PolicyResponse[];
  readonly total: number;
  readonly page: number;
  readonly limit: number;
}

export interface PolicyCreateInput {
  readonly name: string;
  readonly description?: string;
  readonly source_yaml: string;
  readonly created_by?: string;
}

export interface PolicyUpdateInput {
  readonly name?: string;
  readonly description?: string;
  readonly source_yaml?: string;
  readonly status?: PolicyStatus;
}

export interface PolicyListOptions {
  readonly page?: number;
  readonly limit?: number;
  readonly status?: PolicyStatus;
}

export interface PolicyVersion {
  readonly version: number;
  readonly source_yaml: string;
  readonly rules: readonly RuleModel[];
  readonly created_at: string;
  readonly created_by: string;
}

export interface CompileResult {
  readonly policy_id: string;
  readonly version: number;
  readonly rules: readonly RuleModel[];
  readonly warnings: readonly string[];
  readonly compiled_at: string;
}

// ---------------------------------------------------------------------------
// Version
// ---------------------------------------------------------------------------

export interface VersionInfo {
  readonly package: string;
  readonly current_version: string;
  readonly platform_version: string;
  readonly constitutional_hash: string;
  readonly updated_at: string;
}
