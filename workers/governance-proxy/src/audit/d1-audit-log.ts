/// Append-only audit logging to D1 with chain hashing.

import type { AuditRecord } from "../types.ts";
import { chainHash } from "../util/hash.ts";

/// Last known chain hash for this isolate.
let lastChainHash = "genesis";

/// Write an audit record to D1.
/// Uses waitUntil() — caller is responsible for passing the execution context.
export async function writeAuditRecord(
  db: D1Database,
  record: Omit<AuditRecord, "chain_hash">,
): Promise<string> {
  const entryData = JSON.stringify({
    request_id: record.request_id,
    phase: record.phase,
    valid: record.valid,
    constitutional_hash: record.constitutional_hash,
    timestamp: record.timestamp,
  });

  const hash = await chainHash(lastChainHash, entryData);
  lastChainHash = hash;

  try {
    await db
      .prepare(
        `INSERT INTO audit_log
         (request_id, phase, valid, violations_json, constitutional_hash,
          chain_hash, timestamp, tenant_id, endpoint, model, latency_ms)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        record.request_id,
        record.phase,
        record.valid ? 1 : 0,
        record.violations_json,
        record.constitutional_hash,
        hash,
        record.timestamp,
        record.tenant_id,
        record.endpoint,
        record.model,
        record.latency_ms,
      )
      .run();
  } catch {
    // Audit write failures must not block the response.
    // In production, increment a metrics counter here.
  }

  return hash;
}
