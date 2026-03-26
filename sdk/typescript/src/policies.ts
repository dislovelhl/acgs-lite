/**
 * Policy CRUD and compilation API methods.
 */

import type { HttpClient } from "./client.js";
import type {
  CompileResult,
  PolicyCreateInput,
  PolicyListOptions,
  PolicyListResponse,
  PolicyResponse,
  PolicyUpdateInput,
  PolicyVersion,
} from "./types.js";

export class PoliciesApi {
  constructor(private readonly http: HttpClient) {}

  /** Create a new policy from YAML source. */
  async create(data: PolicyCreateInput): Promise<PolicyResponse> {
    return this.http.request<PolicyResponse>("/api/v1/policies", {
      method: "POST",
      body: data,
    });
  }

  /** List policies with pagination and optional status filter. */
  async list(options: PolicyListOptions = {}): Promise<PolicyListResponse> {
    const query: Record<string, string | number | undefined> = {
      page: options.page,
      limit: options.limit,
      status: options.status,
    };

    return this.http.request<PolicyListResponse>("/api/v1/policies", {
      query,
    });
  }

  /** Get a single policy by ID. */
  async get(id: string): Promise<PolicyResponse> {
    return this.http.request<PolicyResponse>(`/api/v1/policies/${encodeURIComponent(id)}`);
  }

  /** Update a policy. If source_yaml changes, a new version is created. */
  async update(id: string, data: PolicyUpdateInput): Promise<PolicyResponse> {
    return this.http.request<PolicyResponse>(
      `/api/v1/policies/${encodeURIComponent(id)}`,
      { method: "PUT", body: data },
    );
  }

  /** Delete a policy by ID. */
  async delete(id: string): Promise<void> {
    await this.http.request<void>(
      `/api/v1/policies/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  /** Get version history for a policy. */
  async getVersions(id: string): Promise<readonly PolicyVersion[]> {
    return this.http.request<PolicyVersion[]>(
      `/api/v1/policies/${encodeURIComponent(id)}/versions`,
    );
  }

  /** Re-compile a policy's YAML source into rules. */
  async compile(id: string): Promise<CompileResult> {
    return this.http.request<CompileResult>(
      `/api/v1/policies/${encodeURIComponent(id)}/compile`,
      { method: "POST" },
    );
  }
}
