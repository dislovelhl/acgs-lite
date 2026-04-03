"""SQLite-backed AuditStore with hash chain integrity.

Constitutional Hash: 608508a9bd224290

Zero external dependencies — uses stdlib sqlite3 and hashlib.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from acgs_lite.audit import AuditEntry

from .audit_store import AuditStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_entries (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    valid INTEGER NOT NULL,
    violations TEXT NOT NULL DEFAULT '[]',
    constitutional_hash TEXT NOT NULL DEFAULT '',
    latency_ms REAL NOT NULL DEFAULT 0.0,
    timestamp TEXT NOT NULL DEFAULT '',
    chain_hash TEXT NOT NULL,
    seq INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_id ON audit_entries(agent_id);
CREATE INDEX IF NOT EXISTS idx_seq ON audit_entries(seq);
"""


def _compute_chain_hash(previous_hash: str, entry: AuditEntry) -> str:
    payload = f"{previous_hash}|{entry.id}|{entry.action}|{entry.valid}"
    return hashlib.sha256(payload.encode()).hexdigest()


class SQLiteAuditStore(AuditStore):
    """Persistent audit store using SQLite with hash chain verification."""

    def __init__(self, path: str | Path = "acgs_audit.db") -> None:
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def append(self, entry: AuditEntry) -> str:
        seq = self.count()
        previous_hash = self._last_chain_hash() if seq > 0 else "genesis"
        chain_hash = _compute_chain_hash(previous_hash, entry)

        violations_json = json.dumps(entry.violations if entry.violations else [])

        self._conn.execute(
            """INSERT INTO audit_entries
               (id, type, agent_id, action, valid, violations,
                constitutional_hash, latency_ms, timestamp, chain_hash, seq)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.type,
                entry.agent_id,
                entry.action,
                1 if entry.valid else 0,
                violations_json,
                getattr(entry, "constitutional_hash", ""),
                getattr(entry, "latency_ms", 0.0),
                getattr(entry, "timestamp", ""),
                chain_hash,
                seq,
            ),
        )
        self._conn.commit()
        return entry.id

    def get(self, entry_id: str) -> AuditEntry | None:
        row = self._conn.execute(
            "SELECT id, type, agent_id, action, valid, violations, "
            "constitutional_hash, latency_ms, timestamp FROM audit_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_entries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        agent_id: str | None = None,
    ) -> list[AuditEntry]:
        if agent_id is not None:
            rows = self._conn.execute(
                "SELECT id, type, agent_id, action, valid, violations, "
                "constitutional_hash, latency_ms, timestamp "
                "FROM audit_entries WHERE agent_id = ? ORDER BY seq LIMIT ? OFFSET ?",
                (agent_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, type, agent_id, action, valid, violations, "
                "constitutional_hash, latency_ms, timestamp "
                "FROM audit_entries ORDER BY seq LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM audit_entries").fetchone()
        return row[0] if row else 0

    def verify_chain(self) -> bool:
        rows = self._conn.execute(
            "SELECT id, action, valid, chain_hash FROM audit_entries ORDER BY seq"
        ).fetchall()
        if not rows:
            return True

        previous_hash = "genesis"
        for entry_id, action, valid, stored_hash in rows:
            payload = f"{previous_hash}|{entry_id}|{action}|{bool(valid)}"
            expected = hashlib.sha256(payload.encode()).hexdigest()
            if expected != stored_hash:
                return False
            previous_hash = stored_hash
        return True

    def _last_chain_hash(self) -> str:
        row = self._conn.execute(
            "SELECT chain_hash FROM audit_entries ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else "genesis"

    @staticmethod
    def _row_to_entry(row: tuple) -> AuditEntry:
        return AuditEntry(
            id=row[0],
            type=row[1],
            agent_id=row[2],
            action=row[3],
            valid=bool(row[4]),
            violations=json.loads(row[5]) if row[5] else [],
            constitutional_hash=row[6],
            latency_ms=row[7],
            timestamp=row[8],
        )

    def close(self) -> None:
        self._conn.close()
