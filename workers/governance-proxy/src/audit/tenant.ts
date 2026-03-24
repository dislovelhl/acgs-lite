/// Tenant resolution and admin audit query parsing for the governance proxy.

import { sha256 } from "../util/hash.ts";

const TENANT_ID_PATTERN = /^[A-Za-z0-9:@._-]{1,128}$/;
const TENANT_HEADER_CANDIDATES = [
  "x-api-key-id",
  "cf-access-authenticated-user-email",
] as const;

export interface AdminAuditQuery {
  tenantId: string;
  limit: number;
}

export function sanitizeTenantId(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim();
  if (!TENANT_ID_PATTERN.test(normalized)) {
    return null;
  }

  return normalized;
}

export async function resolveAuditTenantId(request: Request): Promise<string> {
  for (const headerName of TENANT_HEADER_CANDIDATES) {
    const tenantId = sanitizeTenantId(request.headers.get(headerName));
    if (tenantId) {
      return tenantId;
    }
  }

  const authorization = request.headers.get("authorization");
  if (authorization) {
    const digest = await sha256(authorization);
    return `auth:${digest.slice(0, 16)}`;
  }

  return "anonymous";
}

export function parseAdminAuditQuery(url: URL): AdminAuditQuery {
  const tenantId = sanitizeTenantId(url.searchParams.get("tenant_id"));
  if (!tenantId) {
    throw new Error("tenant_id query parameter is required");
  }

  const parsedLimit = Number.parseInt(url.searchParams.get("limit") ?? "20", 10);
  const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 200) : 20;

  return {
    tenantId,
    limit,
  };
}
