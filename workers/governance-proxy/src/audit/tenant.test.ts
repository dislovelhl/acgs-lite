import { describe, expect, it } from "vitest";

import {
  parseAdminAuditQuery,
  resolveAuditTenantId,
  sanitizeTenantId,
} from "./tenant.ts";

describe("audit tenant helpers", () => {
  it("sanitizes valid tenant ids and rejects invalid ones", () => {
    expect(sanitizeTenantId("tenant-1")).toBe("tenant-1");
    expect(sanitizeTenantId(" user@example.com ")).toBe("user@example.com");
    expect(sanitizeTenantId("tenant with spaces")).toBeNull();
    expect(sanitizeTenantId("")).toBeNull();
  });

  it("prefers trusted header order and ignores untrusted tenant headers", async () => {
    const keyedRequest = new Request("https://example.com/v1/responses", {
      headers: {
        "x-api-key-id": "key-123",
        "x-tenant-id": "tenant-ignored",
      },
    });
    await expect(resolveAuditTenantId(keyedRequest)).resolves.toBe("key-123");

    const hashedRequest = new Request("https://example.com/v1/responses", {
      headers: {
        authorization: "Bearer super-secret-token",
        "x-tenant-id": "tenant-ignored",
      },
    });
    await expect(resolveAuditTenantId(hashedRequest)).resolves.toMatch(/^auth:[a-f0-9]{16}$/);

    const anonymousRequest = new Request("https://example.com/v1/responses");
    await expect(resolveAuditTenantId(anonymousRequest)).resolves.toBe("anonymous");
  });

  it("requires tenant scope for admin audit queries and clamps the limit", () => {
    const parsed = parseAdminAuditQuery(
      new URL("https://example.com/admin/audit?tenant_id=tenant-1&limit=999"),
    );
    expect(parsed).toEqual({ tenantId: "tenant-1", limit: 200 });

    expect(() => parseAdminAuditQuery(new URL("https://example.com/admin/audit"))).toThrow(
      "tenant_id query parameter is required",
    );
  });
});
