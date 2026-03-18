/**
 * Unit tests for @acgs/client using the Node.js built-in test runner.
 *
 * All HTTP requests are intercepted via a minimal fetch mock so no real
 * server is required.
 */

import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { ACGSClient, ACGSError } from "../src/index.js";

// ---------------------------------------------------------------------------
// Fetch mock infrastructure
// ---------------------------------------------------------------------------

type FetchFn = typeof globalThis.fetch;

interface MockRoute {
  method: string;
  pathPrefix: string;
  status: number;
  body: unknown;
  headers?: Record<string, string>;
}

let routes: MockRoute[] = [];
let originalFetch: FetchFn;

function mockFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const url = typeof input === "string" ? input : input.toString();
  const method = (init?.method ?? "GET").toUpperCase();
  const pathname = new URL(url).pathname;

  const route = routes.find(
    (r) =>
      r.method === method &&
      pathname.startsWith(r.pathPrefix),
  );

  if (!route) {
    return Promise.resolve(
      new Response("Not Found", { status: 404 }),
    );
  }

  const responseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...route.headers,
  };

  const body =
    route.status === 204 ? null : JSON.stringify(route.body);

  return Promise.resolve(
    new Response(body, {
      status: route.status,
      headers: responseHeaders,
    }),
  );
}

function addRoute(route: MockRoute): void {
  routes = [...routes, route];
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  originalFetch = globalThis.fetch;
  (globalThis as Record<string, unknown>)["fetch"] = mockFetch;
  routes = [];
});

afterEach(() => {
  (globalThis as Record<string, unknown>)["fetch"] = originalFetch;
  routes = [];
});

// ---------------------------------------------------------------------------
// Client construction
// ---------------------------------------------------------------------------

describe("ACGSClient", () => {
  it("exposes governance, audit, health, and policies sub-APIs", () => {
    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    assert.ok(client.governance);
    assert.ok(client.audit);
    assert.ok(client.health);
    assert.ok(client.policies);
  });

  it("strips trailing slash from baseUrl", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/version/platform",
      status: 200,
      body: {
        package: "acgs",
        current_version: "3.0.0",
        platform_version: "3.0.0",
        constitutional_hash: "cdd01ef066bc6cf2",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    const client = new ACGSClient({
      baseUrl: "http://localhost:8080/",
    });
    const version = await client.getVersion();
    assert.equal(version.current_version, "3.0.0");
  });
});

// ---------------------------------------------------------------------------
// Version
// ---------------------------------------------------------------------------

describe("getVersion", () => {
  it("returns platform version info", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/version/platform",
      status: 200,
      body: {
        package: "acgs",
        current_version: "3.0.0",
        platform_version: "3.0.0",
        constitutional_hash: "cdd01ef066bc6cf2",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const version = await client.getVersion();

    assert.equal(version.package, "acgs");
    assert.equal(version.constitutional_hash, "cdd01ef066bc6cf2");
  });
});

// ---------------------------------------------------------------------------
// Governance
// ---------------------------------------------------------------------------

describe("governance.getStatus", () => {
  it("returns governance status", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/governance/status",
      status: 200,
      body: {
        constitutional_hash: "cdd01ef066bc6cf2",
        maci_strict_mode: true,
        total_validations_24h: 15423,
        violations_24h: 37,
        compliance_frameworks: [
          {
            framework: "EU AI Act",
            status: "compliant",
            score: 0.92,
            items_total: 125,
            items_passing: 115,
          },
        ],
        last_updated: "2026-01-01T00:00:00Z",
      },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const status = await client.governance.getStatus();

    assert.equal(status.maci_strict_mode, true);
    assert.equal(status.total_validations_24h, 15423);
    assert.equal(status.compliance_frameworks.length, 1);
    assert.equal(status.compliance_frameworks[0]?.framework, "EU AI Act");
  });
});

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

describe("health.getDashboard", () => {
  it("returns the health dashboard", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/health/dashboard",
      status: 200,
      body: {
        overall_status: "healthy",
        services: [
          {
            service_name: "api-gateway",
            status: "healthy",
            port: 8080,
            uptime_seconds: 1234.5,
            last_check: "2026-01-01T00:00:00Z",
            version: "3.0.0",
          },
        ],
        checked_at: "2026-01-01T00:00:00Z",
      },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const dashboard = await client.health.getDashboard();

    assert.equal(dashboard.overall_status, "healthy");
    assert.equal(dashboard.services.length, 1);
    assert.equal(dashboard.services[0]?.service_name, "api-gateway");
  });
});

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

describe("audit.getTrail", () => {
  it("returns paginated audit entries", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/audit/trail",
      status: 200,
      body: {
        items: [
          {
            id: "audit-0001",
            timestamp: "2026-01-01T00:00:00Z",
            action: "validate_action",
            actor: "agent-1",
            result: "ALLOWED",
            severity: "LOW",
            hash: "abc123",
            previous_hash: "genesis",
            metadata: {},
          },
        ],
        total: 1,
        page: 1,
        limit: 20,
      },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const trail = await client.audit.getTrail({ page: 1, limit: 20, severity: "LOW" });

    assert.equal(trail.total, 1);
    assert.equal(trail.items.length, 1);
    assert.equal(trail.items[0]?.action, "validate_action");
  });
});

// ---------------------------------------------------------------------------
// Policies
// ---------------------------------------------------------------------------

describe("policies", () => {
  const policyBody = {
    id: "pol-1",
    name: "Safety",
    description: "Test policy",
    version: 1,
    rules: [],
    source_yaml: "rules: []",
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by: "system",
  };

  it("create returns a policy", async () => {
    addRoute({
      method: "POST",
      pathPrefix: "/api/v1/policies",
      status: 201,
      body: policyBody,
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const policy = await client.policies.create({
      name: "Safety",
      source_yaml: "rules: []",
    });

    assert.equal(policy.name, "Safety");
    assert.equal(policy.status, "draft");
  });

  it("list returns paginated policies", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/policies",
      status: 200,
      body: { items: [policyBody], total: 1, page: 1, limit: 20 },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const list = await client.policies.list();

    assert.equal(list.total, 1);
    assert.equal(list.items[0]?.name, "Safety");
  });

  it("get returns a single policy", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/policies/pol-1",
      status: 200,
      body: policyBody,
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const policy = await client.policies.get("pol-1");

    assert.equal(policy.id, "pol-1");
  });

  it("update returns the updated policy", async () => {
    addRoute({
      method: "PUT",
      pathPrefix: "/api/v1/policies/pol-1",
      status: 200,
      body: { ...policyBody, name: "Updated" },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const policy = await client.policies.update("pol-1", { name: "Updated" });

    assert.equal(policy.name, "Updated");
  });

  it("delete resolves without error on 204", async () => {
    addRoute({
      method: "DELETE",
      pathPrefix: "/api/v1/policies/pol-1",
      status: 204,
      body: null,
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    await client.policies.delete("pol-1");
  });

  it("getVersions returns version history", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/policies/pol-1/versions",
      status: 200,
      body: [
        {
          version: 1,
          source_yaml: "rules: []",
          rules: [],
          created_at: "2026-01-01T00:00:00Z",
          created_by: "system",
        },
      ],
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const versions = await client.policies.getVersions("pol-1");

    assert.equal(versions.length, 1);
    assert.equal(versions[0]?.version, 1);
  });

  it("compile returns the compile result", async () => {
    addRoute({
      method: "POST",
      pathPrefix: "/api/v1/policies/pol-1/compile",
      status: 200,
      body: {
        policy_id: "pol-1",
        version: 1,
        rules: [],
        warnings: [],
        compiled_at: "2026-01-01T00:00:00Z",
      },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });
    const result = await client.policies.compile("pol-1");

    assert.equal(result.policy_id, "pol-1");
    assert.equal(result.warnings.length, 0);
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe("error handling", () => {
  it("throws ACGSError on non-OK responses", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/governance/status",
      status: 500,
      body: { detail: "Internal Server Error" },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });

    await assert.rejects(
      () => client.governance.getStatus(),
      (err: unknown) => {
        assert.ok(err instanceof ACGSError);
        assert.equal(err.status, 500);
        assert.ok(err.body.includes("Internal Server Error"));
        return true;
      },
    );
  });

  it("throws ACGSError with 404 for not-found policies", async () => {
    addRoute({
      method: "GET",
      pathPrefix: "/api/v1/policies/nonexistent",
      status: 404,
      body: { detail: "Policy not found" },
    });

    const client = new ACGSClient({ baseUrl: "http://localhost:8080" });

    await assert.rejects(
      () => client.policies.get("nonexistent"),
      (err: unknown) => {
        assert.ok(err instanceof ACGSError);
        assert.equal(err.status, 404);
        return true;
      },
    );
  });
});
