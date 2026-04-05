/// Append-only audit logging to D1 with durable per-tenant chain state.

import type { AuditRecord, AuditStatus, Env } from "../types.ts";
import { chainHash } from "../util/hash.ts";

const AUDIT_STATUS_PREFIX = "audit:status:";
const GENESIS_HASH = "genesis";
const MAX_CHAIN_WRITE_ATTEMPTS = 5;
const READY_AUDIT_DATABASES = new WeakSet<object>();
const AUDIT_SCHEMA_BOOTSTRAPS = new WeakMap<object, Promise<void>>();

interface ChainStateRow {
  tenant_id: string;
  last_chain_hash: string;
  degraded: number;
  last_error: string | null;
  updated_at: string;
}

interface AuditChainRow {
  chain_hash: string;
  prev_chain_hash: string;
}

interface AuditLogHeadRow {
  chain_hash: string;
  timestamp: string;
}

export interface AuditWriteResult {
  persisted: boolean;
  fail_closed: boolean;
  tenant_id: string;
  status: AuditStatus;
  error: string | null;
}

export interface AuditCompactionResult {
  tenant_id: string;
  last_chain_hash: string | null;
  total_records: number;
  retained_records: number;
  deleted_records: number;
}

interface D1RunResult {
  success?: boolean;
  changes?: number;
  meta?: {
    changes?: number;
  };
}

function buildAuditStatusKey(tenantId: string): string {
  return `${AUDIT_STATUS_PREFIX}${tenantId}`;
}

function buildDefaultAuditStatus(tenantId: string): AuditStatus {
  return {
    tenant_id: tenantId,
    degraded: false,
    last_error: null,
    updated_at: "",
    last_chain_hash: null,
  };
}

function buildAuditEntryData(record: Omit<AuditRecord, "chain_hash">, previousChainHash: string): string {
  return JSON.stringify({
    request_id: record.request_id,
    phase: record.phase,
    valid: record.valid,
    constitutional_hash: record.constitutional_hash,
    timestamp: record.timestamp,
    tenant_id: record.tenant_id,
    endpoint: record.endpoint,
    model: record.model,
    latency_ms: record.latency_ms,
    prev_chain_hash: previousChainHash,
  });
}

function formatAuditError(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

async function getChainState(
  db: D1Database,
  tenantId: string,
): Promise<ChainStateRow | null> {
  const result = await db
    .prepare(
      `SELECT tenant_id, last_chain_hash, degraded, last_error, updated_at
       FROM audit_chain_state
       WHERE tenant_id = ?`,
    )
    .bind(tenantId)
    .all<ChainStateRow>();

  return result.results[0] ?? null;
}

async function getLatestAuditLogHead(
  db: D1Database,
  tenantId: string,
): Promise<AuditLogHeadRow | null> {
  const result = await db
    .prepare(
      `SELECT chain_hash, timestamp
       FROM audit_log
       WHERE tenant_id = ?
       ORDER BY id DESC
       LIMIT 1`,
    )
    .bind(tenantId)
    .all<AuditLogHeadRow>();

  return result.results[0] ?? null;
}

async function getEffectiveChainState(
  db: D1Database,
  tenantId: string,
): Promise<ChainStateRow | null> {
  const chainState = await getChainState(db, tenantId);
  if (chainState != null) {
    return chainState;
  }

  const legacyHead = await getLatestAuditLogHead(db, tenantId);
  if (legacyHead == null) {
    return null;
  }

  return {
    tenant_id: tenantId,
    last_chain_hash: legacyHead.chain_hash,
    degraded: 0,
    last_error: null,
    updated_at: legacyHead.timestamp,
  };
}

async function getTenantAuditChainRows(
  db: D1Database,
  tenantId: string,
): Promise<AuditChainRow[]> {
  const result = await db
    .prepare(
      `SELECT chain_hash, prev_chain_hash
       FROM audit_log
       WHERE tenant_id = ?`,
    )
    .bind(tenantId)
    .all<AuditChainRow>();

  return result.results;
}

function assertWriteSucceeded(result: D1RunResult, operation: string): void {
  if (result.success === false) {
    throw new Error(`D1 ${operation} failed`);
  }
}

function getAffectedRowCount(result: D1RunResult, operation: string): number {
  const changes = result.meta?.changes ?? result.changes;
  if (typeof changes === "number") {
    return changes;
  }
  throw new Error(`D1 ${operation} did not report affected row count`);
}

function isDuplicateColumnError(error: unknown): boolean {
  return error instanceof Error && error.message.toLowerCase().includes("duplicate column");
}

async function ensureAuditSchema(db: D1Database): Promise<void> {
  const dbKey = db as object;
  if (READY_AUDIT_DATABASES.has(dbKey)) {
    return;
  }

  const existingBootstrap = AUDIT_SCHEMA_BOOTSTRAPS.get(dbKey);
  if (existingBootstrap != null) {
    await existingBootstrap;
    return;
  }

  const bootstrap = (async () => {
    await db
      .prepare(
        `CREATE TABLE IF NOT EXISTS audit_log (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           request_id TEXT NOT NULL,
           phase TEXT NOT NULL CHECK (phase IN ('request', 'response')),
           valid INTEGER NOT NULL DEFAULT 1,
           violations_json TEXT NOT NULL DEFAULT '[]',
           constitutional_hash TEXT NOT NULL,
           prev_chain_hash TEXT NOT NULL DEFAULT 'genesis',
           chain_hash TEXT NOT NULL,
           timestamp TEXT NOT NULL,
           tenant_id TEXT NOT NULL DEFAULT 'default',
           endpoint TEXT NOT NULL DEFAULT '',
           model TEXT NOT NULL DEFAULT '',
           latency_ms REAL NOT NULL DEFAULT 0
         )`,
      )
      .run();

    await db
      .prepare(
        `CREATE TABLE IF NOT EXISTS audit_chain_state (
           tenant_id TEXT PRIMARY KEY,
           last_chain_hash TEXT NOT NULL,
           degraded INTEGER NOT NULL DEFAULT 0,
           last_error TEXT DEFAULT NULL,
           updated_at TEXT NOT NULL
         )`,
      )
      .run();

    try {
      await db
        .prepare(
          `ALTER TABLE audit_log
           ADD COLUMN prev_chain_hash TEXT NOT NULL DEFAULT 'genesis'`,
        )
        .run();
    } catch (error) {
      if (!isDuplicateColumnError(error)) {
        throw error;
      }
    }

    await db
      .prepare("CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_log(request_id)")
      .run();
    await db
      .prepare("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
      .run();
    await db
      .prepare("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id)")
      .run();
    await db
      .prepare("CREATE INDEX IF NOT EXISTS idx_audit_tenant_chain_hash ON audit_log(tenant_id, chain_hash)")
      .run();
    await db
      .prepare("CREATE INDEX IF NOT EXISTS idx_audit_valid ON audit_log(valid)")
      .run();
    await db
      .prepare(
        "CREATE INDEX IF NOT EXISTS idx_audit_chain_state_updated_at ON audit_chain_state(updated_at)",
      )
      .run();

    READY_AUDIT_DATABASES.add(dbKey);
  })();

  AUDIT_SCHEMA_BOOTSTRAPS.set(dbKey, bootstrap);

  try {
    await bootstrap;
  } finally {
    if (AUDIT_SCHEMA_BOOTSTRAPS.get(dbKey) === bootstrap) {
      AUDIT_SCHEMA_BOOTSTRAPS.delete(dbKey);
    }
  }
}

async function insertAuditLogRecord(
  db: D1Database,
  record: Omit<AuditRecord, "chain_hash">,
  previousChainHash: string,
  hash: string,
): Promise<void> {
  const result = await db
    .prepare(
      `INSERT INTO audit_log
       (request_id, phase, valid, violations_json, constitutional_hash,
        prev_chain_hash, chain_hash, timestamp, tenant_id, endpoint, model, latency_ms)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      record.request_id,
      record.phase,
      record.valid ? 1 : 0,
      record.violations_json,
      record.constitutional_hash,
      previousChainHash,
      hash,
      record.timestamp,
      record.tenant_id,
      record.endpoint,
      record.model,
      record.latency_ms,
    )
    .run();

  assertWriteSucceeded(result, "audit log insert");
}

async function deleteAuditLogRecord(
  db: D1Database,
  record: Omit<AuditRecord, "chain_hash">,
  hash: string,
): Promise<void> {
  const result = await db
    .prepare(
      `DELETE FROM audit_log
       WHERE tenant_id = ?
         AND request_id = ?
         AND phase = ?
         AND timestamp = ?
         AND chain_hash = ?`,
    )
    .bind(record.tenant_id, record.request_id, record.phase, record.timestamp, hash)
    .run();

  assertWriteSucceeded(result, "audit log cleanup");
}

async function deleteAuditLogRecordByChainHash(
  db: D1Database,
  tenantId: string,
  hash: string,
): Promise<void> {
  const result = await db
    .prepare(
      `DELETE FROM audit_log
       WHERE tenant_id = ?
         AND chain_hash = ?`,
    )
    .bind(tenantId, hash)
    .run();

  assertWriteSucceeded(result, "audit chain compaction");
}

async function claimChainHead(
  db: D1Database,
  record: Omit<AuditRecord, "chain_hash">,
  previousChainHash: string,
  nextChainHash: string,
  hasExistingState: boolean,
): Promise<boolean> {
  if (!hasExistingState) {
    const result = await db
      .prepare(
        `INSERT OR IGNORE INTO audit_chain_state
         (tenant_id, last_chain_hash, degraded, last_error, updated_at)
         VALUES (?, ?, 0, NULL, ?)`,
      )
      .bind(record.tenant_id, nextChainHash, record.timestamp)
      .run();

    assertWriteSucceeded(result, "initial audit chain claim");
    return getAffectedRowCount(result, "initial audit chain claim") === 1;
  }

  const result = await db
    .prepare(
      `UPDATE audit_chain_state
       SET last_chain_hash = ?,
           degraded = 0,
           last_error = NULL,
           updated_at = ?
       WHERE tenant_id = ?
         AND last_chain_hash = ?`,
    )
    .bind(nextChainHash, record.timestamp, record.tenant_id, previousChainHash)
    .run();

  assertWriteSucceeded(result, "audit chain claim");
  return getAffectedRowCount(result, "audit chain claim") === 1;
}

async function writeAuditStatus(env: Env, status: AuditStatus): Promise<void> {
  await env.CONSTITUTIONS.put(buildAuditStatusKey(status.tenant_id), JSON.stringify(status));
}

async function writeAuditStatusBestEffort(env: Env, status: AuditStatus): Promise<void> {
  try {
    await writeAuditStatus(env, status);
  } catch (error) {
    console.warn("governance_audit_status_write_failed", {
      tenant_id: status.tenant_id,
      error: formatAuditError(error, "Audit status write failed"),
    });
  }
}

function auditFailClosed(env: Env): boolean {
  return env.AUDIT_FAIL_CLOSED?.trim().toLowerCase() === "true";
}

function emitAuditFailureTelemetry(
  record: Omit<AuditRecord, "chain_hash">,
  result: AuditWriteResult,
): void {
  console.error("governance_audit_write_failed", {
    tenant_id: record.tenant_id,
    request_id: record.request_id,
    phase: record.phase,
    endpoint: record.endpoint,
    fail_closed: result.fail_closed,
    error: result.error,
    constitutional_hash: record.constitutional_hash,
  });
}

export async function getAuditStatus(env: Env, tenantId: string): Promise<AuditStatus> {
  await ensureAuditSchema(env.AUDIT_DB);

  let kvStatus: AuditStatus | null = null;
  try {
    kvStatus = await env.CONSTITUTIONS.get<AuditStatus>(buildAuditStatusKey(tenantId), "json");
  } catch (error) {
    console.warn("governance_audit_status_read_failed", {
      tenant_id: tenantId,
      error: formatAuditError(error, "Audit status read failed"),
    });
  }

  const chainState = await getEffectiveChainState(env.AUDIT_DB, tenantId);
  const baseStatus = kvStatus ?? buildDefaultAuditStatus(tenantId);

  return {
    ...baseStatus,
    tenant_id: tenantId,
    last_chain_hash: chainState?.last_chain_hash ?? baseStatus.last_chain_hash,
    updated_at: chainState?.updated_at ?? baseStatus.updated_at,
    degraded: chainState ? Boolean(chainState.degraded) : baseStatus.degraded,
    last_error: chainState?.last_error ?? baseStatus.last_error,
  };
}

/// Write an audit record to D1 and advance the durable chain head.
export async function writeAuditRecord(
  db: D1Database,
  record: Omit<AuditRecord, "chain_hash">,
): Promise<string> {
  await ensureAuditSchema(db);

  for (let attempt = 1; attempt <= MAX_CHAIN_WRITE_ATTEMPTS; attempt += 1) {
    const persistedState = await getChainState(db, record.tenant_id);
    const effectiveState = persistedState ?? (await getEffectiveChainState(db, record.tenant_id));
    const previousChainHash = effectiveState?.last_chain_hash ?? GENESIS_HASH;
    const entryData = buildAuditEntryData(record, previousChainHash);
    const hash = await chainHash(previousChainHash, entryData);

    await insertAuditLogRecord(db, record, previousChainHash, hash);

    try {
      const claimed = await claimChainHead(
        db,
        record,
        previousChainHash,
        hash,
        persistedState != null,
      );
      if (claimed) {
        return hash;
      }
    } catch (error) {
      await deleteAuditLogRecord(db, record, hash).catch(() => undefined);
      throw error;
    }

    await deleteAuditLogRecord(db, record, hash);
  }

  throw new Error(
    `Audit chain write conflicted after ${MAX_CHAIN_WRITE_ATTEMPTS} attempts for tenant ${record.tenant_id}`,
  );
}

export async function recordAudit(
  env: Env,
  record: Omit<AuditRecord, "chain_hash">,
): Promise<AuditWriteResult> {
  try {
    const chainHashValue = await writeAuditRecord(env.AUDIT_DB, record);
    const status = {
      tenant_id: record.tenant_id,
      degraded: false,
      last_error: null,
      updated_at: record.timestamp,
      last_chain_hash: chainHashValue,
    };
    await writeAuditStatusBestEffort(env, status);
    return {
      persisted: true,
      fail_closed: auditFailClosed(env),
      tenant_id: record.tenant_id,
      status,
      error: null,
    };
  } catch (error) {
    const previousStatus = await getAuditStatus(env, record.tenant_id).catch(() =>
      buildDefaultAuditStatus(record.tenant_id),
    );
    const message = formatAuditError(error, "Audit write failed");
    const status = {
      tenant_id: record.tenant_id,
      degraded: true,
      last_error: message,
      updated_at: new Date().toISOString(),
      last_chain_hash: previousStatus.last_chain_hash,
    };
    await writeAuditStatusBestEffort(env, status);
    return {
      persisted: false,
      fail_closed: auditFailClosed(env),
      tenant_id: record.tenant_id,
      status,
      error: message,
    };
  }
}

export async function persistAuditWithPolicy(
  env: Env,
  ctx: ExecutionContext,
  record: Omit<AuditRecord, "chain_hash">,
): Promise<AuditWriteResult | null> {
  if (auditFailClosed(env)) {
    const result = await recordAudit(env, record);
    if (!result.persisted) {
      emitAuditFailureTelemetry(record, result);
    }
    return result;
  }

  ctx.waitUntil(
    recordAudit(env, record).then((result) => {
      if (!result.persisted) {
        emitAuditFailureTelemetry(record, result);
      }
    }),
  );
  return null;
}

export async function compactAuditChain(
  env: Env,
  tenantId: string,
): Promise<AuditCompactionResult> {
  await ensureAuditSchema(env.AUDIT_DB);

  const state = await getEffectiveChainState(env.AUDIT_DB, tenantId);
  const rows = await getTenantAuditChainRows(env.AUDIT_DB, tenantId);
  const totalRecords = rows.length;

  if (state == null) {
    return {
      tenant_id: tenantId,
      last_chain_hash: null,
      total_records: totalRecords,
      retained_records: 0,
      deleted_records: 0,
    };
  }

  const rowsByHash = new Map(rows.map((row) => [row.chain_hash, row]));
  if (!rowsByHash.has(state.last_chain_hash)) {
    throw new Error(
      `Audit chain head ${state.last_chain_hash} is missing from audit_log for tenant ${tenantId}`,
    );
  }

  const reachable = new Set<string>();
  let currentHash = state.last_chain_hash;
  while (currentHash !== GENESIS_HASH) {
    if (reachable.has(currentHash)) {
      throw new Error(`Audit chain cycle detected for tenant ${tenantId}`);
    }
    const currentRow = rowsByHash.get(currentHash);
    if (!currentRow) {
      throw new Error(`Audit chain is broken before ${currentHash} for tenant ${tenantId}`);
    }
    reachable.add(currentHash);
    currentHash = currentRow.prev_chain_hash;
  }

  const orphanedRows = rows.filter((row) => !reachable.has(row.chain_hash));
  for (const row of orphanedRows) {
    await deleteAuditLogRecordByChainHash(env.AUDIT_DB, tenantId, row.chain_hash);
  }

  return {
    tenant_id: tenantId,
    last_chain_hash: state.last_chain_hash,
    total_records: totalRecords,
    retained_records: reachable.size,
    deleted_records: orphanedRows.length,
  };
}

export async function listAuditRecords(
  env: Env,
  tenantId: string,
  limit: number,
): Promise<{ status: AuditStatus; records: unknown[] }> {
  await ensureAuditSchema(env.AUDIT_DB);

  const result = await env.AUDIT_DB
    .prepare(
      `SELECT * FROM audit_log
       WHERE tenant_id = ?
       ORDER BY id DESC
       LIMIT ?`,
    )
    .bind(tenantId, limit)
    .all();

  const status = await getAuditStatus(env, tenantId);

  return {
    status,
    records: result.results,
  };
}
