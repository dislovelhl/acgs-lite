/**
 * @acgs/client -- TypeScript SDK for the ACGS platform API gateway.
 *
 * Usage:
 *
 * ```ts
 * import { ACGSClient } from "@acgs/client";
 *
 * const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
 *
 * const status = await client.governance.getStatus();
 * const trail  = await client.audit.getTrail({ severity: "CRITICAL" });
 * const health = await client.health.getDashboard();
 * const policy = await client.policies.create({ name: "Safety", source_yaml: "..." });
 * const ver    = await client.getVersion();
 * ```
 */

import { HttpClient } from "./client.js";
import { AuditApi } from "./audit.js";
import { GovernanceApi } from "./governance.js";
import { HealthApi } from "./health.js";
import { PoliciesApi } from "./policies.js";
import type { ACGSClientConfig, VersionInfo } from "./types.js";

export class ACGSClient {
  private readonly http: HttpClient;

  /** Governance status and live event subscriptions. */
  readonly governance: GovernanceApi;
  /** Paginated, hash-chained audit trail. */
  readonly audit: AuditApi;
  /** Aggregated platform health dashboard. */
  readonly health: HealthApi;
  /** Policy CRUD, versioning, and compilation. */
  readonly policies: PoliciesApi;

  constructor(config: ACGSClientConfig) {
    this.http = new HttpClient(config);
    this.governance = new GovernanceApi(this.http);
    this.audit = new AuditApi(this.http);
    this.health = new HealthApi(this.http);
    this.policies = new PoliciesApi(this.http);
  }

  /** Get current platform version information. */
  async getVersion(): Promise<VersionInfo> {
    return this.http.request<VersionInfo>("/api/v1/version/platform");
  }
}

// Re-export everything consumers might need.
export { ACGSError, ACGSNetworkError, ACGSTimeoutError } from "./errors.js";
export type {
  ACGSClientConfig,
  AuditEntry,
  AuditTrailOptions,
  AuditTrailResponse,
  CompileResult,
  ComplianceFramework,
  GovernanceEvent,
  GovernanceStatus,
  HealthDashboard,
  PolicyCreateInput,
  PolicyListOptions,
  PolicyListResponse,
  PolicyResponse,
  PolicyStatus,
  PolicyUpdateInput,
  PolicyVersion,
  RuleModel,
  ServiceHealth,
  VersionInfo,
} from "./types.js";
export type { GovernanceEventCallback, Unsubscribe } from "./governance.js";
