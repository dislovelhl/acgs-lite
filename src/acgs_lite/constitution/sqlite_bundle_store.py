"""SQLite-backed BundleStore for durable constitution lifecycle state.

Mirrors the ``SQLiteGovernanceStateBackend`` pattern from
``acgs_lite.openshell_state`` with additions required for multi-step
bundle lifecycle:

- WAL journal mode and 5-second busy timeout prevent write contention.
- Partial unique index ``WHERE status = 'ACTIVE'`` enforces one-active-
  per-tenant at the database level, defeating TOCTOU races in
  ``activate()`` / ``rollback()``.
- All multi-step writes are wrapped in a single ``BEGIN EXCLUSIVE``
  transaction so a crash mid-activate cannot leave a partially-written
  bundle visible to readers.
- ``sqlite3.OperationalError`` is caught and re-raised as
  ``LifecycleError`` so callers never see raw SQLite exceptions.
- A ``schema_migrations`` table provides a forward migration path from
  day one.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from acgs_lite.constitution.activation import ActivationRecord
from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle
from acgs_lite.constitution.bundle_store import CASVersionConflict
from acgs_lite.constitution.lifecycle_service import LifecycleError

_SCHEMA_VERSION = 1


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteBundleStore:
    """BundleStore backed by a local SQLite database.

    :param path: Filesystem path to the SQLite database file.
        The parent directory is created on first use.

    Thread safety: SQLite's WAL mode allows concurrent readers; writers
    serialize via the ``busy_timeout``.  If two processes race on
    ``activate()``, the database-level partial unique index on
    ``status = 'ACTIVE'`` guarantees only one succeeds.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._ensure_schema()

    # ── internal helpers ─────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version     INTEGER PRIMARY KEY,
                    applied_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bundles (
                    bundle_id   TEXT PRIMARY KEY,
                    tenant_id   TEXT NOT NULL,
                    status      TEXT NOT NULL,
                    payload     TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                -- Exactly one ACTIVE bundle per tenant at the DB level.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active
                    ON bundles(tenant_id)
                    WHERE status = 'active';

                CREATE TABLE IF NOT EXISTS activations (
                    tenant_id   TEXT PRIMARY KEY,
                    bundle_id   TEXT NOT NULL,
                    payload     TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tenant_versions (
                    tenant_id   TEXT PRIMARY KEY,
                    version     INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            existing = conn.execute(
                "SELECT version FROM schema_migrations WHERE version = ?",
                (_SCHEMA_VERSION,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (_SCHEMA_VERSION, _utcnow()),
                )
            conn.commit()

    def _wrap(self, exc: sqlite3.OperationalError) -> LifecycleError:
        return LifecycleError(f"SQLiteBundleStore: database error - {exc}")

    # ── BundleStore Protocol ─────────────────────────────────────────────

    def save_bundle(self, bundle: ConstitutionBundle) -> None:
        payload = json.dumps(bundle.model_dump(mode="json"))
        now = _utcnow()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO bundles (bundle_id, tenant_id, status, payload, updated_at)
                    VALUES (:bid, :tid, :status, :payload, :now)
                    ON CONFLICT(bundle_id) DO UPDATE SET
                        tenant_id  = excluded.tenant_id,
                        status     = excluded.status,
                        payload    = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    {
                        "bid": bundle.bundle_id,
                        "tid": bundle.tenant_id,
                        "status": bundle.status.value,
                        "payload": payload,
                        "now": now,
                    },
                )
                conn.commit()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc

    def get_bundle(self, bundle_id: str) -> ConstitutionBundle | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM bundles WHERE bundle_id = ?",
                    (bundle_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
        if row is None:
            return None
        return ConstitutionBundle.model_validate(json.loads(row["payload"]))

    def get_active_bundle(self, tenant_id: str) -> ConstitutionBundle | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM bundles WHERE tenant_id = ? AND status = 'active'",
                    (tenant_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
        if row is None:
            return None
        return ConstitutionBundle.model_validate(json.loads(row["payload"]))

    def list_bundles(
        self,
        tenant_id: str,
        *,
        status: BundleStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ConstitutionBundle]:
        order_clause = "ORDER BY json_extract(payload, '$.version') DESC"
        # Use -1 as SQLite sentinel for "no limit" (LIMIT -1 means unlimited in SQLite)
        limit_val: int = int(limit) if limit is not None else -1
        offset_val: int = int(offset) if offset else 0
        try:
            with self._connect() as conn:
                if status is not None:
                    rows = conn.execute(
                        f"SELECT payload FROM bundles WHERE tenant_id = ? AND status = ?"
                        f" {order_clause} LIMIT ? OFFSET ?",
                        (tenant_id, status.value, limit_val, offset_val),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"SELECT payload FROM bundles WHERE tenant_id = ?"
                        f" {order_clause} LIMIT ? OFFSET ?",
                        (tenant_id, limit_val, offset_val),
                    ).fetchall()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
        return [ConstitutionBundle.model_validate(json.loads(r["payload"])) for r in rows]

    def save_activation(self, activation: ActivationRecord) -> None:
        payload = json.dumps(activation.model_dump(mode="json"))
        now = _utcnow()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO activations (tenant_id, bundle_id, payload, updated_at)
                    VALUES (:tid, :bid, :payload, :now)
                    ON CONFLICT(tenant_id) DO UPDATE SET
                        bundle_id  = excluded.bundle_id,
                        payload    = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    {
                        "tid": activation.tenant_id,
                        "bid": activation.bundle_id,
                        "payload": payload,
                        "now": now,
                    },
                )
                conn.commit()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc

    def get_activation(self, tenant_id: str) -> ActivationRecord | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT payload FROM activations WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
        if row is None:
            return None
        return ActivationRecord.model_validate(json.loads(row["payload"]))

    def save_bundle_transactional(
        self,
        bundles: list[ConstitutionBundle],
        activation: ActivationRecord | None = None,
    ) -> None:
        """Save multiple bundles (and an optional activation) atomically.

        Used by ``activate()`` / ``rollback()`` which touch 2-4 bundle rows
        plus an activation record.  ``BEGIN EXCLUSIVE`` serializes writers so
        two concurrent ``activate()`` calls cannot both observe zero ACTIVE
        bundles and both succeed — the partial unique index is the last-resort
        guard, but the exclusive lock provides a cleaner error path.
        """
        now = _utcnow()
        try:
            with self._connect() as conn:
                conn.execute("BEGIN EXCLUSIVE")
                for bundle in bundles:
                    payload = json.dumps(bundle.model_dump(mode="json"))
                    conn.execute(
                        """
                        INSERT INTO bundles (bundle_id, tenant_id, status, payload, updated_at)
                        VALUES (:bid, :tid, :status, :payload, :now)
                        ON CONFLICT(bundle_id) DO UPDATE SET
                            tenant_id  = excluded.tenant_id,
                            status     = excluded.status,
                            payload    = excluded.payload,
                            updated_at = excluded.updated_at
                        """,
                        {
                            "bid": bundle.bundle_id,
                            "tid": bundle.tenant_id,
                            "status": bundle.status.value,
                            "payload": payload,
                            "now": now,
                        },
                    )
                if activation is not None:
                    apayload = json.dumps(activation.model_dump(mode="json"))
                    conn.execute(
                        """
                        INSERT INTO activations (tenant_id, bundle_id, payload, updated_at)
                        VALUES (:tid, :bid, :payload, :now)
                        ON CONFLICT(tenant_id) DO UPDATE SET
                            bundle_id  = excluded.bundle_id,
                            payload    = excluded.payload,
                            updated_at = excluded.updated_at
                        """,
                        {
                            "tid": activation.tenant_id,
                            "bid": activation.bundle_id,
                            "payload": apayload,
                            "now": now,
                        },
                    )
                conn.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc

    def get_tenant_version(self, tenant_id: str) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT version FROM tenant_versions WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
        return 0 if row is None else row["version"]

    def cas_tenant_version(self, tenant_id: str, expected: int) -> None:
        try:
            with self._connect() as conn:
                conn.execute("BEGIN EXCLUSIVE")
                row = conn.execute(
                    "SELECT version FROM tenant_versions WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
                current = 0 if row is None else row["version"]
                if current != expected:
                    conn.execute("ROLLBACK")
                    raise CASVersionConflict(
                        f"Tenant {tenant_id!r} version conflict: expected {expected}, current {current}"
                    )
                conn.execute(
                    """
                    INSERT INTO tenant_versions (tenant_id, version) VALUES (?, ?)
                    ON CONFLICT(tenant_id) DO UPDATE SET version = excluded.version
                    """,
                    (tenant_id, current + 1),
                )
                conn.execute("COMMIT")
        except CASVersionConflict:
            raise
        except sqlite3.OperationalError as exc:
            raise self._wrap(exc) from exc
