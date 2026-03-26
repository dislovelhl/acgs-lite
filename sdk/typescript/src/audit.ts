/**
 * Audit trail API methods.
 */

import type { HttpClient } from "./client.js";
import type { AuditTrailOptions, AuditTrailResponse } from "./types.js";

export class AuditApi {
  constructor(private readonly http: HttpClient) {}

  /** Fetch the paginated audit trail with optional filters. */
  async getTrail(options: AuditTrailOptions = {}): Promise<AuditTrailResponse> {
    const query: Record<string, string | number | undefined> = {
      page: options.page,
      limit: options.limit,
      severity: options.severity,
      tenant_id: options.tenant_id,
      start_date: options.start_date,
      end_date: options.end_date,
    };

    return this.http.request<AuditTrailResponse>("/api/v1/audit/trail", {
      query,
    });
  }
}
