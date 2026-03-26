/**
 * Health check API methods.
 */

import type { HttpClient } from "./client.js";
import type { HealthDashboard } from "./types.js";

export class HealthApi {
  constructor(private readonly http: HttpClient) {}

  /** Fetch the aggregated health dashboard for all platform services. */
  async getDashboard(): Promise<HealthDashboard> {
    return this.http.request<HealthDashboard>("/api/v1/health/dashboard");
  }
}
