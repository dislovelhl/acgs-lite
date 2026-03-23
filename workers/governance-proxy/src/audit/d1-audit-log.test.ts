import { describe, expect, it, vi } from "vitest";

import type { AuditStatus, Env } from "../types.ts";
import {
  compactAuditChain,
  getAuditStatus,
  listAuditRecords,
  persistAuditWithPolicy,
  recordAudit,
  writeAuditRecord,
} from "./d1-audit-log.ts";

interface StoredAuditLogRecord {
  request_id: string;
  phase: "request" | "response";
  valid: number;
  violations_json: string;
  constitutional_hash: string;
  prev_chain_hash: string;
  chain_hash: string;
  timestamp: string;
  tenant_id: string;
  endpoint: string;
  model: string;
  latency_ms: number;
}

class MockKVNamespace {
  private readonly store = new Map<string, string>();
  failGets = false;
  failPuts = false;

  async put(key: string, value: string): Promise<void> {
    if (this.failPuts) {
      throw new Error("KV put unavailable");
    }
    this.store.set(key, value);
  }

  async get<T>(key: string, type?: "json"): Promise<T | string | null> {
    if (this.failGets) {
      throw new Error("KV get unavailable");
    }
    const value = this.store.get(key);
    if (value == null) {
      return null;
    }
    if (type === "json") {
      return JSON.parse(value) as T;
    }
    return value;
  }

  async getWithMetadata<T>(
    key: string,
    type?: "json",
  ): Promise<{ value: T | string | null; metadata: null }> {
    return {
      value: await this.get<T>(key, type),
      metadata: null,
    };
  }

  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }

  async list(): Promise<{ keys: Array<{ name: string }>; list_complete: true; cursor: "" }> {
    return {
      keys: Array.from(this.store.keys()).map((name) => ({ name })),
      list_complete: true,
      cursor: "",
    };
  }
}

class MockStatement {
  private boundArgs: unknown[] = [];

  constructor(
    private readonly db: MockD1Database,
    private readonly sql: string,
  ) {}

  bind(...args: unknown[]): this {
    this.boundArgs = args;
    return this;
  }

  async all<T>(): Promise<{ results: T[] }> {
    return this.db.executeAll<T>(this.sql, this.boundArgs);
  }

  async run(): Promise<{ success: boolean; meta: { changes: number } }> {
    return this.db.executeRun(this.sql, this.boundArgs);
  }
}

class MockD1Database {
  readonly logs: StoredAuditLogRecord[] = [];
  readonly chainState = new Map<
    string,
    {
      last_chain_hash: string;
      degraded: number;
      last_error: string | null;
      updated_at: string;
    }
  >();

  shouldFailWrites = false;
  forceNextChainClaimConflict = false;
  hasAuditLogTable = true;
  hasAuditChainStateTable = true;
  hasPrevChainHashColumn = true;

  prepare(sql: string): MockStatement {
    return new MockStatement(this, sql);
  }

  async batch(statements: MockStatement[]): Promise<unknown[]> {
    if (this.shouldFailWrites) {
      throw new Error("D1 unavailable");
    }
    const results: unknown[] = [];
    for (const statement of statements) {
      results.push(await statement.run());
    }
    return results;
  }

  async executeAll<T>(sql: string, args: unknown[]): Promise<{ results: T[] }> {
    if (sql.includes("FROM audit_chain_state")) {
      if (!this.hasAuditChainStateTable) {
        throw new Error("no such table: audit_chain_state");
      }
      const tenantId = String(args[0]);
      const row = this.chainState.get(tenantId);
      return { results: row ? ([{ tenant_id: tenantId, ...row }] as T[]) : [] };
    }

    if (sql.includes("FROM audit_log")) {
      if (!this.hasAuditLogTable) {
        throw new Error("no such table: audit_log");
      }
      if (sql.includes("prev_chain_hash") && !this.hasPrevChainHashColumn) {
        throw new Error("no such column: prev_chain_hash");
      }
      const tenantId = String(args[0]);
      if (sql.includes("ORDER BY id DESC") && sql.includes("LIMIT 1")) {
        const latest = this.logs
          .filter((record) => record.tenant_id === tenantId)
          .slice(-1)
          .map((record) => ({
            chain_hash: record.chain_hash,
            timestamp: record.timestamp,
          })) as T[];
        return { results: latest };
      }
      if (sql.includes("LIMIT ?")) {
        const limit = Number(args[1]);
        return {
          results: this.logs
            .filter((record) => record.tenant_id === tenantId)
            .slice()
            .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
            .slice(0, limit) as T[],
        };
      }
      return {
        results: this.logs
          .filter((record) => record.tenant_id === tenantId)
          .slice()
          .sort((left, right) => right.timestamp.localeCompare(left.timestamp)) as T[],
      };
    }

    throw new Error(`Unexpected SELECT: ${sql}`);
  }

  async executeRun(
    sql: string,
    args: unknown[],
  ): Promise<{ success: boolean; meta: { changes: number } }> {
    if (this.shouldFailWrites) {
      throw new Error("D1 unavailable");
    }

    if (sql.includes("CREATE TABLE IF NOT EXISTS audit_log")) {
      this.hasAuditLogTable = true;
      return { success: true, meta: { changes: 0 } };
    }

    if (sql.includes("CREATE TABLE IF NOT EXISTS audit_chain_state")) {
      this.hasAuditChainStateTable = true;
      return { success: true, meta: { changes: 0 } };
    }

    if (sql.includes("ALTER TABLE audit_log") && sql.includes("ADD COLUMN prev_chain_hash")) {
      if (!this.hasAuditLogTable) {
        throw new Error("no such table: audit_log");
      }
      if (this.hasPrevChainHashColumn) {
        throw new Error("duplicate column name: prev_chain_hash");
      }
      this.hasPrevChainHashColumn = true;
      return { success: true, meta: { changes: 0 } };
    }

    if (sql.includes("CREATE INDEX IF NOT EXISTS")) {
      return { success: true, meta: { changes: 0 } };
    }

    if (sql.includes("INSERT INTO audit_log")) {
      if (!this.hasAuditLogTable) {
        throw new Error("no such table: audit_log");
      }
      if (!this.hasPrevChainHashColumn) {
        throw new Error("table audit_log has no column named prev_chain_hash");
      }
      this.logs.push({
        request_id: String(args[0]),
        phase: args[1] as "request" | "response",
        valid: Number(args[2]),
        violations_json: String(args[3]),
        constitutional_hash: String(args[4]),
        prev_chain_hash: String(args[5]),
        chain_hash: String(args[6]),
        timestamp: String(args[7]),
        tenant_id: String(args[8]),
        endpoint: String(args[9]),
        model: String(args[10]),
        latency_ms: Number(args[11]),
      });
      return { success: true, meta: { changes: 1 } };
    }

    if (sql.includes("DELETE FROM audit_log")) {
      if (!this.hasAuditLogTable) {
        throw new Error("no such table: audit_log");
      }
      if (sql.includes("AND request_id = ?")) {
        const initialLength = this.logs.length;
        this.logs.splice(
          0,
          this.logs.length,
          ...this.logs.filter(
            (record) =>
              !(
                record.tenant_id === String(args[0]) &&
                record.request_id === String(args[1]) &&
                record.phase === args[2] &&
                record.timestamp === String(args[3]) &&
                record.chain_hash === String(args[4])
              ),
          ),
        );
        return {
          success: true,
          meta: { changes: initialLength - this.logs.length },
        };
      }

      const initialLength = this.logs.length;
      this.logs.splice(
        0,
        this.logs.length,
        ...this.logs.filter(
          (record) =>
            !(record.tenant_id === String(args[0]) && record.chain_hash === String(args[1])),
        ),
      );
      return {
        success: true,
        meta: { changes: initialLength - this.logs.length },
      };
    }

    if (sql.includes("INSERT OR IGNORE INTO audit_chain_state")) {
      if (!this.hasAuditChainStateTable) {
        throw new Error("no such table: audit_chain_state");
      }
      const tenantId = String(args[0]);
      if (this.chainState.has(tenantId)) {
        return { success: true, meta: { changes: 0 } };
      }
      this.chainState.set(tenantId, {
        last_chain_hash: String(args[1]),
        degraded: 0,
        last_error: null,
        updated_at: String(args[2]),
      });
      return { success: true, meta: { changes: 1 } };
    }

    if (sql.includes("UPDATE audit_chain_state")) {
      if (!this.hasAuditChainStateTable) {
        throw new Error("no such table: audit_chain_state");
      }
      const nextChainHash = String(args[0]);
      const updatedAt = String(args[1]);
      const tenantId = String(args[2]);
      const previousChainHash = String(args[3]);
      const currentState = this.chainState.get(tenantId);

      if (this.forceNextChainClaimConflict) {
        this.forceNextChainClaimConflict = false;
        this.logs.push({
          request_id: "competing-request",
          phase: "request",
          valid: 1,
          violations_json: "[]",
          constitutional_hash: "cdd01ef066bc6cf2",
          prev_chain_hash: previousChainHash,
          chain_hash: "competing-hash",
          timestamp: "2026-03-21T00:00:01.500Z",
          tenant_id: tenantId,
          endpoint: "responses",
          model: "gpt-5.4",
          latency_ms: 8,
        });
        this.chainState.set(tenantId, {
          last_chain_hash: "competing-hash",
          degraded: 0,
          last_error: null,
          updated_at: "2026-03-21T00:00:01.500Z",
        });
        return { success: true, meta: { changes: 0 } };
      }

      if (currentState == null || currentState.last_chain_hash !== previousChainHash) {
        return { success: true, meta: { changes: 0 } };
      }

      this.chainState.set(tenantId, {
        last_chain_hash: nextChainHash,
        degraded: 0,
        last_error: null,
        updated_at: updatedAt,
      });
      return { success: true, meta: { changes: 1 } };
    }

    throw new Error(`Unexpected RUN: ${sql}`);
  }
}

function createEnv(db: MockD1Database): {
  env: Env;
  kv: MockKVNamespace;
} {
  const kv = new MockKVNamespace();
  return {
    env: {
      CONSTITUTIONS: kv as unknown as KVNamespace,
      AUDIT_DB: db as unknown as D1Database,
      CONSTITUTIONAL_HASH: "cdd01ef066bc6cf2",
    },
    kv,
  };
}

function buildRecord(
  tenantId: string,
  requestId: string,
  timestamp: string,
): Parameters<typeof writeAuditRecord>[1] {
  return {
    request_id: requestId,
    phase: "request",
    valid: true,
    violations_json: "[]",
    constitutional_hash: "cdd01ef066bc6cf2",
    timestamp,
    tenant_id: tenantId,
    endpoint: "responses",
    model: "gpt-5.4",
    latency_ms: 12,
  };
}

describe("d1 audit log", () => {
  it("persists per-tenant chain state and records previous hash", async () => {
    const db = new MockD1Database();

    const firstHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-1", "2026-03-21T00:00:00.000Z"),
    );
    const secondHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-2", "2026-03-21T00:00:01.000Z"),
    );

    expect(db.logs).toHaveLength(2);
    expect(db.logs[0].prev_chain_hash).toBe("genesis");
    expect(db.logs[0].chain_hash).toBe(firstHash);
    expect(db.logs[1].prev_chain_hash).toBe(firstHash);
    expect(db.logs[1].chain_hash).toBe(secondHash);
    expect(db.chainState.get("tenant-a")?.last_chain_hash).toBe(secondHash);
  });

  it("backfills the durable head from legacy audit rows before appending", async () => {
    const db = new MockD1Database();
    db.logs.push({
      request_id: "legacy-req",
      phase: "request",
      valid: 1,
      violations_json: "[]",
      constitutional_hash: "cdd01ef066bc6cf2",
      prev_chain_hash: "genesis",
      chain_hash: "legacy-hash",
      timestamp: "2026-03-20T23:59:59.000Z",
      tenant_id: "tenant-legacy",
      endpoint: "responses",
      model: "gpt-5.4",
      latency_ms: 7,
    });

    const nextHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-legacy", "req-2", "2026-03-21T00:00:00.000Z"),
    );

    expect(db.logs).toHaveLength(2);
    expect(db.logs[1].prev_chain_hash).toBe("legacy-hash");
    expect(db.logs[1].chain_hash).toBe(nextHash);
    expect(db.chainState.get("tenant-legacy")?.last_chain_hash).toBe(nextHash);
  });

  it("bootstraps the audit schema before appending on upgraded D1 databases", async () => {
    const db = new MockD1Database();
    db.hasAuditChainStateTable = false;
    db.hasPrevChainHashColumn = false;

    const hash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-upgrade", "req-1", "2026-03-21T00:00:00.000Z"),
    );

    expect(hash).toBeTruthy();
    expect(db.hasAuditChainStateTable).toBe(true);
    expect(db.hasPrevChainHashColumn).toBe(true);
    expect(db.logs).toHaveLength(1);
    expect(db.logs[0].prev_chain_hash).toBe("genesis");
    expect(db.chainState.get("tenant-upgrade")?.last_chain_hash).toBe(hash);
  });

  it("retries chain head claims on concurrent update conflicts and cleans stale candidates", async () => {
    const db = new MockD1Database();

    const firstHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-1", "2026-03-21T00:00:00.000Z"),
    );

    db.forceNextChainClaimConflict = true;

    const secondHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-2", "2026-03-21T00:00:02.000Z"),
    );

    const requestTwoRecords = db.logs.filter((record) => record.request_id === "req-2");

    expect(requestTwoRecords).toHaveLength(1);
    expect(requestTwoRecords[0].prev_chain_hash).toBe("competing-hash");
    expect(requestTwoRecords[0].chain_hash).toBe(secondHash);
    expect(db.logs.find((record) => record.request_id === "competing-request")?.prev_chain_hash).toBe(
      firstHash,
    );
    expect(db.chainState.get("tenant-a")?.last_chain_hash).toBe(secondHash);
  });

  it("compacts unreachable audit candidates while preserving the authoritative chain", async () => {
    const db = new MockD1Database();
    const { env } = createEnv(db);

    const firstHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-1", "2026-03-21T00:00:00.000Z"),
    );
    const secondHash = await writeAuditRecord(
      db as unknown as D1Database,
      buildRecord("tenant-a", "req-2", "2026-03-21T00:00:01.000Z"),
    );

    db.logs.push({
      request_id: "orphaned-request",
      phase: "request",
      valid: 1,
      violations_json: "[]",
      constitutional_hash: "cdd01ef066bc6cf2",
      prev_chain_hash: firstHash,
      chain_hash: "orphaned-hash",
      timestamp: "2026-03-21T00:00:01.500Z",
      tenant_id: "tenant-a",
      endpoint: "responses",
      model: "gpt-5.4",
      latency_ms: 9,
    });

    const result = await compactAuditChain(env, "tenant-a");

    expect(result).toEqual({
      tenant_id: "tenant-a",
      last_chain_hash: secondHash,
      total_records: 3,
      retained_records: 2,
      deleted_records: 1,
    });
    expect(db.logs.map((record) => record.chain_hash)).toEqual([firstHash, secondHash]);
    expect(db.chainState.get("tenant-a")?.last_chain_hash).toBe(secondHash);
  });

  it("preserves legacy audit history during compaction before durable state is seeded", async () => {
    const db = new MockD1Database();
    const { env } = createEnv(db);
    db.logs.push({
      request_id: "legacy-req-1",
      phase: "request",
      valid: 1,
      violations_json: "[]",
      constitutional_hash: "cdd01ef066bc6cf2",
      prev_chain_hash: "genesis",
      chain_hash: "legacy-hash-1",
      timestamp: "2026-03-20T23:59:58.000Z",
      tenant_id: "tenant-legacy",
      endpoint: "responses",
      model: "gpt-5.4",
      latency_ms: 7,
    });
    db.logs.push({
      request_id: "legacy-req-2",
      phase: "request",
      valid: 1,
      violations_json: "[]",
      constitutional_hash: "cdd01ef066bc6cf2",
      prev_chain_hash: "legacy-hash-1",
      chain_hash: "legacy-hash-2",
      timestamp: "2026-03-20T23:59:59.000Z",
      tenant_id: "tenant-legacy",
      endpoint: "responses",
      model: "gpt-5.4",
      latency_ms: 8,
    });

    const result = await compactAuditChain(env, "tenant-legacy");

    expect(result).toEqual({
      tenant_id: "tenant-legacy",
      last_chain_hash: "legacy-hash-2",
      total_records: 2,
      retained_records: 2,
      deleted_records: 0,
    });
    expect(db.logs).toHaveLength(2);
  });

  it("refuses compaction when the durable head is missing from audit_log", async () => {
    const db = new MockD1Database();
    const { env } = createEnv(db);

    db.chainState.set("tenant-a", {
      last_chain_hash: "missing-head",
      degraded: 0,
      last_error: null,
      updated_at: "2026-03-21T00:00:02.000Z",
    });

    await expect(compactAuditChain(env, "tenant-a")).rejects.toThrow(
      "Audit chain head missing-head is missing from audit_log for tenant tenant-a",
    );
  });

  it("records degraded audit status when writes fail", async () => {
    const db = new MockD1Database();
    const { env, kv } = createEnv(db);

    await recordAudit(env, buildRecord("tenant-b", "req-1", "2026-03-21T00:00:01.000Z"));
    const previousStatus = await getAuditStatus(env, "tenant-b");

    db.shouldFailWrites = true;

    const result = await recordAudit(env, buildRecord("tenant-b", "req-3", "2026-03-21T00:00:02.000Z"));

    const status = (await kv.get(
      "audit:status:tenant-b",
      "json",
    )) as AuditStatus | null;
    expect(result.persisted).toBe(false);
    expect(status?.degraded).toBe(true);
    expect(status?.last_error).toContain("D1 unavailable");
    expect(status?.last_chain_hash).toBe(previousStatus.last_chain_hash);
  });

  it("continues writing to D1 when reading mirrored audit status from KV fails", async () => {
    const db = new MockD1Database();
    const { env, kv } = createEnv(db);
    kv.failGets = true;

    const result = await recordAudit(env, buildRecord("tenant-kv-read", "req-1", "2026-03-21T00:00:01.000Z"));

    expect(result.persisted).toBe(true);
    expect(db.logs).toHaveLength(1);
    expect(result.status.last_chain_hash).toBeTruthy();
  });

  it("treats mirrored audit status writes as best effort after a successful D1 append", async () => {
    const db = new MockD1Database();
    const { env, kv } = createEnv(db);
    kv.failPuts = true;

    const result = await recordAudit(env, buildRecord("tenant-kv-write", "req-1", "2026-03-21T00:00:01.000Z"));

    expect(result.persisted).toBe(true);
    expect(db.logs).toHaveLength(1);
    expect(result.status.last_chain_hash).toBeTruthy();
  });

  it("fails closed synchronously when configured and emits telemetry", async () => {
    const db = new MockD1Database();
    db.shouldFailWrites = true;
    const { env } = createEnv(db);
    env.AUDIT_FAIL_CLOSED = "true";
    const waitUntil = vi.fn();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await persistAuditWithPolicy(
      env,
      { waitUntil } as unknown as ExecutionContext,
      buildRecord("tenant-c", "req-1", "2026-03-21T00:00:03.000Z"),
    );

    expect(waitUntil).not.toHaveBeenCalled();
    expect(result?.persisted).toBe(false);
    expect(result?.fail_closed).toBe(true);
    expect(errorSpy).toHaveBeenCalledWith(
      "governance_audit_write_failed",
      expect.objectContaining({
        tenant_id: "tenant-c",
        request_id: "req-1",
        fail_closed: true,
      }),
    );

    errorSpy.mockRestore();
  });

  it("queues background writes by default and logs async failures", async () => {
    const db = new MockD1Database();
    db.shouldFailWrites = true;
    const { env } = createEnv(db);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let pending: Promise<unknown> | null = null;

    const result = await persistAuditWithPolicy(
      env,
      {
        waitUntil(promise: Promise<unknown>) {
          pending = promise;
        },
      } as unknown as ExecutionContext,
      buildRecord("tenant-d", "req-1", "2026-03-21T00:00:04.000Z"),
    );

    expect(result).toBeNull();
    expect(pending).not.toBeNull();
    await pending;
    expect(errorSpy).toHaveBeenCalledWith(
      "governance_audit_write_failed",
      expect.objectContaining({
        tenant_id: "tenant-d",
        request_id: "req-1",
        fail_closed: false,
      }),
    );

    errorSpy.mockRestore();
  });

  it("lists scoped records and returns tenant status", async () => {
    const db = new MockD1Database();
    const { env } = createEnv(db);

    await recordAudit(env, buildRecord("tenant-a", "req-1", "2026-03-21T00:00:00.000Z"));
    await recordAudit(env, buildRecord("tenant-b", "req-2", "2026-03-21T00:00:01.000Z"));

    const result = await listAuditRecords(env, "tenant-a", 10);
    expect(result.records).toHaveLength(1);
    expect((result.records[0] as StoredAuditLogRecord).tenant_id).toBe("tenant-a");
    expect(result.status.degraded).toBe(false);
    expect(result.status.last_chain_hash).toBeTruthy();

    const status = await getAuditStatus(env, "tenant-a");
    expect(status.degraded).toBe(false);
    expect(status.last_chain_hash).toBe(result.status.last_chain_hash);
  });
});
