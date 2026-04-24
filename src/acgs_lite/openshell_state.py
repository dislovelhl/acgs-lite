"""State backends and versioned persistence for OpenShell governance."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, cast

from acgs_lite.constitution.quorum import GateState, QuorumManager

CURRENT_STATE_FORMAT_VERSION = 2
logger = logging.getLogger(__name__)


class GovernanceStateError(Exception):
    """Base exception for governance state persistence failures."""


class GovernanceStateChecksumError(GovernanceStateError):
    """Raised when persisted state fails checksum verification."""


class GovernanceStateMigrationError(GovernanceStateError):
    """Raised when a persisted state cannot be migrated."""


class GovernanceStateVersionError(GovernanceStateError):
    """Raised when the stored state version is unsupported."""


class GovernanceStateObservabilityHook(Protocol):
    """Observability hook for state lifecycle events."""

    def __call__(self, event: str, **fields: Any) -> None:
        """Record a state lifecycle event."""


def _default_observability_hook(event: str, **fields: Any) -> None:
    logger.info("openshell_state_%s", event, extra={"openshell_state": fields})


class GovernanceStateBackend(Protocol):
    """Backend protocol for persisting governance decisions and approval state."""

    def load_state(self) -> dict[str, Any]:
        """Load raw persisted state."""

    def save_state(self, payload: dict[str, Any]) -> None:
        """Persist raw state."""


class InMemoryGovernanceStateBackend:
    """Ephemeral governance state backend."""

    def __init__(self) -> None:
        self._payload = empty_state_payload()

    def load_state(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(json.dumps(self._payload)))

    def save_state(self, payload: dict[str, Any]) -> None:
        self._payload = cast(dict[str, Any], json.loads(json.dumps(payload)))


class JsonFileGovernanceStateBackend:
    """JSON-file governance state backend with atomic writes."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load_state(self) -> dict[str, Any]:
        if not self._path.exists():
            return empty_state_payload()
        return cast(dict[str, Any], json.loads(self._path.read_text(encoding="utf-8")))

    def save_state(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._path)


class SQLiteGovernanceStateBackend:
    """SQLite-backed governance state backend using stdlib sqlite3."""

    def __init__(self, path: str | Path, *, key: str = "openshell_governance") -> None:
        self._path = Path(path)
        self._key = key
        self._ensure_schema()

    def load_state(self) -> dict[str, Any]:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT payload FROM governance_state WHERE state_key = ?",
                (self._key,),
            ).fetchone()
        if row is None:
            return empty_state_payload()
        return cast(dict[str, Any], json.loads(str(row[0])))

    def save_state(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO governance_state (state_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (self._key, json.dumps(payload, sort_keys=True), utcnow().isoformat()),
            )
            conn.commit()

    def _ensure_schema(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS governance_state (
                    state_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()


class RedisGovernanceStateBackend:
    """Redis-backed governance state backend using an injected client."""

    def __init__(self, client: Any, *, key: str = "openshell_governance") -> None:
        self._client = client
        self._key = key

    def load_state(self) -> dict[str, Any]:
        raw = self._client.get(self._key)
        if raw in (None, b"", ""):
            return empty_state_payload()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cast(dict[str, Any], json.loads(str(raw)))

    def save_state(self, payload: dict[str, Any]) -> None:
        self._client.set(self._key, json.dumps(payload, sort_keys=True))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_state_checksum(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def empty_state_payload() -> dict[str, Any]:
    base = {
        "format_version": CURRENT_STATE_FORMAT_VERSION,
        "backend": "memory",
        "updated_at": "",
        "decisions": {},
        "gates": {},
    }
    return with_checksum(base)


def with_checksum(payload: dict[str, Any]) -> dict[str, Any]:
    unsigned = {k: v for k, v in payload.items() if k != "checksum"}
    return {**unsigned, "checksum": compute_state_checksum(unsigned)}


def verify_state_checksum(payload: dict[str, Any]) -> None:
    stored_checksum = payload.get("checksum")
    if not isinstance(stored_checksum, str) or not stored_checksum:
        raise GovernanceStateChecksumError("Governance state checksum missing")
    unsigned = {k: v for k, v in payload.items() if k != "checksum"}
    expected_checksum = compute_state_checksum(unsigned)
    if stored_checksum != expected_checksum:
        raise GovernanceStateChecksumError("Governance state checksum mismatch")


def serialize_state(
    *,
    decision_store: dict[str, Any],
    quorum: QuorumManager,
    backend_name: str,
) -> dict[str, Any]:
    serialized_gates: dict[str, dict[str, Any]] = {}
    for gate_id, gate in quorum._gates.items():
        serialized_gates[gate_id] = {
            "action": gate.action,
            "required_approvals": gate.required_approvals,
            "eligible_voters": sorted(gate.eligible_voters) if gate.eligible_voters else None,
            "deadline": gate.deadline.isoformat() if gate.deadline else "",
            "state": gate.state.value,
            "metadata": gate.metadata,
            "votes": [
                {
                    "voter_id": vote.voter_id,
                    "approve": vote.approve,
                    "timestamp": vote.timestamp,
                    "note": vote.note,
                }
                for vote in gate.votes
            ],
        }

    payload = {
        "format_version": CURRENT_STATE_FORMAT_VERSION,
        "backend": backend_name,
        "updated_at": utcnow().isoformat(),
        "decisions": {
            decision_id: decision.model_dump(mode="json")
            for decision_id, decision in decision_store.items()
        },
        "gates": serialized_gates,
    }
    return with_checksum(payload)


def apply_state_migration(version: int, payload: dict[str, Any]) -> dict[str, Any]:
    if version == 1:
        migrated = {
            "format_version": 2,
            "backend": payload.get("backend", "json-file"),
            "updated_at": payload.get("updated_at", ""),
            "decisions": payload.get("decisions", {}),
            "gates": payload.get("gates", {}),
        }
        return with_checksum(migrated)
    raise GovernanceStateMigrationError(
        f"No migration path from governance state format_version={version}"
    )


def migrate_state(raw_state: dict[str, Any]) -> dict[str, Any]:
    if not raw_state:
        return empty_state_payload()

    version = raw_state.get("format_version")
    if version is None:
        version = 1
        raw_state = {
            "format_version": 1,
            "backend": "legacy-json",
            "updated_at": "",
            "decisions": raw_state.get("decisions", {}),
            "gates": raw_state.get("gates", {}),
        }

    if int(version) > CURRENT_STATE_FORMAT_VERSION:
        raise GovernanceStateVersionError(
            f"Unsupported governance state format_version={version}; "
            f"current={CURRENT_STATE_FORMAT_VERSION}"
        )

    migrated = raw_state
    while int(migrated["format_version"]) < CURRENT_STATE_FORMAT_VERSION:
        migrated = apply_state_migration(int(migrated["format_version"]), migrated)

    verify_state_checksum(migrated)
    return migrated


class PersistentGovernanceState:
    """Versioned governance state manager backed by a pluggable backend."""

    def __init__(
        self,
        backend: GovernanceStateBackend | None = None,
        *,
        observability_hook: GovernanceStateObservabilityHook | None = None,
    ) -> None:
        self._backend = backend if backend is not None else InMemoryGovernanceStateBackend()
        self._observability_hook = observability_hook or _default_observability_hook
        raw_state = self._backend.load_state()
        initial_version = raw_state.get("format_version", 1 if raw_state else 0)
        try:
            self._state = migrate_state(raw_state)
        except GovernanceStateChecksumError as exc:
            self._observability_hook(
                "checksum_failure",
                backend_type=self._backend.__class__.__name__,
                error=str(exc),
            )
            raise
        except GovernanceStateError as exc:
            self._observability_hook(
                "load_failure",
                backend_type=self._backend.__class__.__name__,
                error=str(exc),
            )
            raise

        self._observability_hook(
            "loaded",
            backend_type=self._backend.__class__.__name__,
            format_version=self._state["format_version"],
        )
        if initial_version != self._state["format_version"]:
            self._observability_hook(
                "migrated",
                backend_type=self._backend.__class__.__name__,
                from_version=initial_version,
                to_version=self._state["format_version"],
            )

    def load_decisions(self, model_cls: Any) -> dict[str, Any]:
        raw_decisions = self._state.get("decisions", {})
        return {
            decision_id: model_cls.model_validate(payload)
            for decision_id, payload in raw_decisions.items()
        }

    def load_quorum(self, quorum: QuorumManager) -> None:
        raw_gates = self._state.get("gates", {})
        for gate_id, payload in raw_gates.items():
            quorum.open(
                action=str(payload["action"]),
                required_approvals=int(payload["required_approvals"]),
                eligible_voters=set(payload["eligible_voters"])
                if payload.get("eligible_voters") is not None
                else None,
                gate_id=gate_id,
                metadata=dict(payload.get("metadata", {})),
            )
            gate = quorum._gates[gate_id]
            deadline = payload.get("deadline")
            gate.deadline = datetime.fromisoformat(deadline) if deadline else None
            for vote in payload.get("votes", []):
                quorum.vote(
                    gate_id,
                    voter_id=str(vote["voter_id"]),
                    approve=bool(vote["approve"]),
                    note=str(vote.get("note", "")),
                    _now=datetime.fromisoformat(str(vote["timestamp"])),
                )
            gate.state = GateState(str(payload.get("state", GateState.OPEN.value)))

    def save(self, *, decision_store: dict[str, Any], quorum: QuorumManager) -> None:
        payload = serialize_state(
            decision_store=decision_store,
            quorum=quorum,
            backend_name=self._backend.__class__.__name__,
        )
        self._backend.save_state(payload)
        self._state = payload
        self._observability_hook(
            "saved",
            backend_type=self._backend.__class__.__name__,
            format_version=payload["format_version"],
            decision_count=len(payload["decisions"]),
            gate_count=len(payload["gates"]),
        )


__all__ = [
    "CURRENT_STATE_FORMAT_VERSION",
    "GovernanceStateChecksumError",
    "GovernanceStateBackend",
    "GovernanceStateError",
    "GovernanceStateMigrationError",
    "GovernanceStateObservabilityHook",
    "GovernanceStateVersionError",
    "InMemoryGovernanceStateBackend",
    "JsonFileGovernanceStateBackend",
    "PersistentGovernanceState",
    "RedisGovernanceStateBackend",
    "SQLiteGovernanceStateBackend",
    "apply_state_migration",
    "compute_state_checksum",
    "empty_state_payload",
    "migrate_state",
    "serialize_state",
    "utcnow",
    "verify_state_checksum",
    "with_checksum",
]
