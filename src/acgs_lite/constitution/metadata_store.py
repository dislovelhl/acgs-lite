"""Governance metadata store — key-value metadata attached to governance artifacts.

Provides a lightweight, queryable metadata store for annotating governance artifacts
(rules, decisions, agents, sessions, or any string-keyed entity) with arbitrary
key-value pairs. Supports namespaced keys, bulk operations, TTL expiry, metadata
diffing, and structured export. Zero hot-path overhead — all operations are
independent of the governance engine's critical evaluation path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetadataScope(str, Enum):
    """Scope of a metadata namespace."""

    RULE = "rule"
    DECISION = "decision"
    AGENT = "agent"
    SESSION = "session"
    CUSTOM = "custom"


@dataclass
class MetadataEntry:
    """A single metadata key-value entry attached to an artifact."""

    artifact_id: str
    key: str
    value: Any
    scope: MetadataScope = MetadataScope.CUSTOM
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    expires_at: float | None = None  # monotonic timestamp; None = never expires
    author: str | None = None  # who/what set this entry

    def is_expired(self) -> bool:
        """Return True if the entry has passed its TTL."""
        if self.expires_at is None:
            return False
        return time.monotonic() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialise to plain dict (for export/logging)."""
        return {
            "artifact_id": self.artifact_id,
            "key": self.key,
            "value": self.value,
            "scope": self.scope.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "author": self.author,
        }


@dataclass
class MetadataDiff:
    """Result of comparing metadata between two artifacts or two snapshots."""

    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # key -> (old, new)
    unchanged: dict[str, Any] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Return True if there are any differences."""
        return bool(self.added or self.removed or self.changed)

    def summary(self) -> str:
        """Return a human-readable diff summary."""
        parts: list[str] = []
        if self.added:
            parts.append(f"+{len(self.added)} added")
        if self.removed:
            parts.append(f"-{len(self.removed)} removed")
        if self.changed:
            parts.append(f"~{len(self.changed)} changed")
        if self.unchanged:
            parts.append(f"={len(self.unchanged)} unchanged")
        return ", ".join(parts) if parts else "no changes"


class GovernanceMetadataStore:
    """Key-value metadata store for governance artifacts.

    Stores arbitrary metadata attached to any string-keyed artifact ID.
    Supports namespaced keys (``scope:key`` convention), TTL-based expiry,
    bulk set/get, search by value, snapshot/diff, and structured export.

    All methods are synchronous and in-memory — suitable for per-process
    governance enrichment without external dependencies.

    Example usage::

        store = GovernanceMetadataStore()

        # Annotate a rule
        store.set("rule:pii-block", "owner", "security-team", scope=MetadataScope.RULE)
        store.set("rule:pii-block", "review_cycle_days", 90, scope=MetadataScope.RULE)

        # Annotate a decision
        store.set("decision:abc123", "reviewer", "agent-7", scope=MetadataScope.DECISION)

        # Retrieve
        owner = store.get("rule:pii-block", "owner")  # "security-team"

        # Bulk get all metadata for an artifact
        all_meta = store.get_all("rule:pii-block")

        # Diff two artifacts' metadata
        diff = store.diff("rule:pii-block", "rule:gdpr-block")
    """

    def __init__(self) -> None:
        # _store[artifact_id][key] = MetadataEntry
        self._store: dict[str, dict[str, MetadataEntry]] = {}
        self._change_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Core set / get / delete
    # ------------------------------------------------------------------

    def set(
        self,
        artifact_id: str,
        key: str,
        value: Any,
        *,
        scope: MetadataScope = MetadataScope.CUSTOM,
        ttl_seconds: float | None = None,
        author: str | None = None,
    ) -> MetadataEntry:
        """Set a metadata key on an artifact.

        Args:
            artifact_id: Unique identifier for the governance artifact.
            key: Metadata key (e.g. ``"owner"``, ``"review_cycle_days"``).
            value: Arbitrary JSON-serialisable value.
            scope: Semantic scope tag for the artifact type.
            ttl_seconds: Optional time-to-live in seconds (monotonic clock).
            author: Optional identifier of the agent/user setting this value.

        Returns:
            The created or updated :class:`MetadataEntry`.
        """
        now = time.monotonic()
        expires_at = now + ttl_seconds if ttl_seconds is not None else None

        bucket = self._store.setdefault(artifact_id, {})
        existing = bucket.get(key)

        if existing is not None:
            old_value = existing.value
            existing.value = value
            existing.updated_at = now
            existing.expires_at = expires_at
            existing.author = author
            entry = existing
            self._log(
                "update", artifact_id, key, old_value=old_value, new_value=value, author=author
            )
        else:
            entry = MetadataEntry(
                artifact_id=artifact_id,
                key=key,
                value=value,
                scope=scope,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
                author=author,
            )
            bucket[key] = entry
            self._log("set", artifact_id, key, new_value=value, author=author)

        return entry

    def get(self, artifact_id: str, key: str, default: Any = None) -> Any:
        """Get a metadata value, returning ``default`` if missing or expired."""
        entry = self._store.get(artifact_id, {}).get(key)
        if entry is None or entry.is_expired():
            return default
        return entry.value

    def get_entry(self, artifact_id: str, key: str) -> MetadataEntry | None:
        """Return the full :class:`MetadataEntry` or ``None`` if absent/expired."""
        entry = self._store.get(artifact_id, {}).get(key)
        if entry is None or entry.is_expired():
            return None
        return entry

    def delete(self, artifact_id: str, key: str) -> bool:
        """Delete a metadata key. Returns True if the key existed."""
        bucket = self._store.get(artifact_id, {})
        if key in bucket:
            old = bucket.pop(key)
            self._log("delete", artifact_id, key, old_value=old.value)
            if not bucket:
                del self._store[artifact_id]
            return True
        return False

    def delete_artifact(self, artifact_id: str) -> int:
        """Delete all metadata for an artifact. Returns number of keys removed."""
        bucket = self._store.pop(artifact_id, {})
        count = len(bucket)
        if count:
            self._log("delete_artifact", artifact_id, "*", count=count)
        return count

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def set_many(
        self,
        artifact_id: str,
        mapping: dict[str, Any],
        *,
        scope: MetadataScope = MetadataScope.CUSTOM,
        ttl_seconds: float | None = None,
        author: str | None = None,
    ) -> list[MetadataEntry]:
        """Set multiple keys on one artifact at once."""
        return [
            self.set(artifact_id, k, v, scope=scope, ttl_seconds=ttl_seconds, author=author)
            for k, v in mapping.items()
        ]

    def get_all(self, artifact_id: str, *, include_expired: bool = False) -> dict[str, Any]:
        """Return all metadata for an artifact as a plain ``{key: value}`` dict."""
        bucket = self._store.get(artifact_id, {})
        result: dict[str, Any] = {}
        for key, entry in bucket.items():
            if include_expired or not entry.is_expired():
                result[key] = entry.value
        return result

    def get_all_entries(
        self, artifact_id: str, *, include_expired: bool = False
    ) -> dict[str, MetadataEntry]:
        """Return all :class:`MetadataEntry` objects for an artifact."""
        bucket = self._store.get(artifact_id, {})
        return {k: e for k, e in bucket.items() if include_expired or not e.is_expired()}

    def copy_metadata(
        self,
        source_id: str,
        dest_id: str,
        *,
        keys: list[str] | None = None,
        overwrite: bool = True,
        author: str | None = None,
    ) -> int:
        """Copy metadata from one artifact to another.

        Args:
            source_id: Source artifact identifier.
            dest_id: Destination artifact identifier.
            keys: If given, only copy these specific keys.
            overwrite: If False, skip keys that already exist on dest.
            author: Optional author tag for copied entries.

        Returns:
            Number of keys copied.
        """
        source_entries = self.get_all_entries(source_id)
        copied = 0
        dest_bucket = self._store.setdefault(dest_id, {})

        for key, entry in source_entries.items():
            if keys is not None and key not in keys:
                continue
            if not overwrite and key in dest_bucket and not dest_bucket[key].is_expired():
                continue
            self.set(dest_id, key, entry.value, scope=entry.scope, author=author or entry.author)
            copied += 1

        return copied

    # ------------------------------------------------------------------
    # Search / query
    # ------------------------------------------------------------------

    def find_by_value(
        self, value: Any, *, scope: MetadataScope | None = None
    ) -> list[tuple[str, str]]:
        """Find all (artifact_id, key) pairs where value matches.

        Args:
            value: Value to search for (equality check).
            scope: If given, restrict to entries with this scope.

        Returns:
            List of ``(artifact_id, key)`` tuples.
        """
        results: list[tuple[str, str]] = []
        for artifact_id, bucket in self._store.items():
            for key, entry in bucket.items():
                if entry.is_expired():
                    continue
                if scope is not None and entry.scope != scope:
                    continue
                if entry.value == value:
                    results.append((artifact_id, key))
        return results

    def find_by_key(self, key: str, *, scope: MetadataScope | None = None) -> dict[str, Any]:
        """Return ``{artifact_id: value}`` for all artifacts that have *key*.

        Args:
            key: Metadata key to search for.
            scope: If given, restrict to entries with this scope.

        Returns:
            Mapping of artifact_id → value for matching entries.
        """
        results: dict[str, Any] = {}
        for artifact_id, bucket in self._store.items():
            entry = bucket.get(key)
            if entry is None or entry.is_expired():
                continue
            if scope is not None and entry.scope != scope:
                continue
            results[artifact_id] = entry.value
        return results

    def artifacts_with_scope(self, scope: MetadataScope) -> list[str]:
        """Return all artifact IDs that have at least one entry with *scope*."""
        result: list[str] = []
        for artifact_id, bucket in self._store.items():
            for entry in bucket.values():
                if not entry.is_expired() and entry.scope == scope:
                    result.append(artifact_id)
                    break
        return result

    def has_key(self, artifact_id: str, key: str) -> bool:
        """Return True if the artifact has the given key and it is not expired."""
        entry = self._store.get(artifact_id, {}).get(key)
        return entry is not None and not entry.is_expired()

    # ------------------------------------------------------------------
    # TTL / expiry management
    # ------------------------------------------------------------------

    def purge_expired(self) -> int:
        """Remove all expired entries from the store.

        Returns:
            Number of entries purged.
        """
        purged = 0
        empty_artifacts: list[str] = []
        for artifact_id, bucket in self._store.items():
            expired_keys = [k for k, e in bucket.items() if e.is_expired()]
            for k in expired_keys:
                del bucket[k]
                purged += 1
            if not bucket:
                empty_artifacts.append(artifact_id)
        for artifact_id in empty_artifacts:
            del self._store[artifact_id]
        return purged

    def refresh_ttl(self, artifact_id: str, key: str, ttl_seconds: float) -> bool:
        """Reset the TTL for a specific entry.

        Returns:
            True if the entry existed and was updated, False otherwise.
        """
        entry = self._store.get(artifact_id, {}).get(key)
        if entry is None or entry.is_expired():
            return False
        entry.expires_at = time.monotonic() + ttl_seconds
        entry.updated_at = time.monotonic()
        return True

    # ------------------------------------------------------------------
    # Diff / snapshot
    # ------------------------------------------------------------------

    def snapshot(self, artifact_id: str) -> dict[str, Any]:
        """Return a point-in-time snapshot of all non-expired metadata values."""
        return self.get_all(artifact_id)

    def diff(self, artifact_id_a: str, artifact_id_b: str) -> MetadataDiff:
        """Compare metadata between two artifacts.

        Args:
            artifact_id_a: First artifact (treated as "before").
            artifact_id_b: Second artifact (treated as "after").

        Returns:
            :class:`MetadataDiff` describing added/removed/changed/unchanged keys.
        """
        a = self.get_all(artifact_id_a)
        b = self.get_all(artifact_id_b)
        return self._compute_diff(a, b)

    def diff_snapshots(self, before: dict[str, Any], after: dict[str, Any]) -> MetadataDiff:
        """Compare two plain snapshot dicts (e.g. from :meth:`snapshot`)."""
        return self._compute_diff(before, after)

    @staticmethod
    def _compute_diff(a: dict[str, Any], b: dict[str, Any]) -> MetadataDiff:
        all_keys = set(a) | set(b)
        result = MetadataDiff()
        for key in all_keys:
            if key in a and key not in b:
                result.removed[key] = a[key]
            elif key in b and key not in a:
                result.added[key] = b[key]
            elif a[key] != b[key]:
                result.changed[key] = (a[key], b[key])
            else:
                result.unchanged[key] = a[key]
        return result

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_artifact(self, artifact_id: str) -> list[dict[str, Any]]:
        """Export all entries for one artifact as a list of dicts."""
        return [
            e.to_dict() for e in self._store.get(artifact_id, {}).values() if not e.is_expired()
        ]

    def export_all(self, *, scope: MetadataScope | None = None) -> dict[str, list[dict[str, Any]]]:
        """Export the full store (or a scope-filtered subset) as a plain dict.

        Returns:
            ``{artifact_id: [entry_dict, ...]}`` mapping.
        """
        result: dict[str, list[dict[str, Any]]] = {}
        for artifact_id, bucket in self._store.items():
            entries = [
                e.to_dict()
                for e in bucket.values()
                if not e.is_expired() and (scope is None or e.scope == scope)
            ]
            if entries:
                result[artifact_id] = entries
        return result

    # ------------------------------------------------------------------
    # Summary / statistics
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return aggregate statistics about the store."""
        total_artifacts = 0
        total_entries = 0
        expired_entries = 0
        scope_counts: dict[str, int] = {}

        for bucket in self._store.values():
            if bucket:
                total_artifacts += 1
            for entry in bucket.values():
                total_entries += 1
                if entry.is_expired():
                    expired_entries += 1
                else:
                    scope_key = entry.scope.value
                    scope_counts[scope_key] = scope_counts.get(scope_key, 0) + 1

        return {
            "total_artifacts": total_artifacts,
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "scope_counts": scope_counts,
            "change_log_length": len(self._change_log),
        }

    def change_log(
        self, *, artifact_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return the change log, optionally filtered by artifact_id."""
        log = self._change_log
        if artifact_id is not None:
            log = [e for e in log if e.get("artifact_id") == artifact_id]
        if limit is not None:
            log = log[-limit:]
        return log

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, action: str, artifact_id: str, key: str, **kwargs: Any) -> None:
        self._change_log.append(
            {
                "action": action,
                "artifact_id": artifact_id,
                "key": key,
                "timestamp": time.monotonic(),
                **kwargs,
            }
        )
