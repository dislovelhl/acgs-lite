"""Tests for constitution.metadata_store module.

Covers MetadataEntry, MetadataDiff, GovernanceMetadataStore with full CRUD,
bulk ops, search, TTL, diff/snapshot, export, and summary.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from acgs_lite.constitution.metadata_store import (
    GovernanceMetadataStore,
    MetadataDiff,
    MetadataEntry,
    MetadataScope,
)

# ---------------------------------------------------------------------------
# MetadataEntry
# ---------------------------------------------------------------------------


class TestMetadataEntry:
    def test_not_expired_by_default(self):
        e = MetadataEntry(artifact_id="a", key="k", value="v")
        assert e.is_expired() is False

    def test_expired_when_past(self):
        e = MetadataEntry(
            artifact_id="a",
            key="k",
            value="v",
            expires_at=time.monotonic() - 10,
        )
        assert e.is_expired() is True

    def test_to_dict(self):
        e = MetadataEntry(artifact_id="a", key="k", value=42, scope=MetadataScope.RULE)
        d = e.to_dict()
        assert d["artifact_id"] == "a"
        assert d["key"] == "k"
        assert d["value"] == 42
        assert d["scope"] == "rule"


# ---------------------------------------------------------------------------
# MetadataDiff
# ---------------------------------------------------------------------------


class TestMetadataDiff:
    def test_no_changes(self):
        d = MetadataDiff()
        assert d.has_changes is False
        assert d.summary() == "no changes"

    def test_has_changes_added(self):
        d = MetadataDiff(added={"x": 1})
        assert d.has_changes is True
        assert "+1 added" in d.summary()

    def test_has_changes_removed(self):
        d = MetadataDiff(removed={"x": 1})
        assert d.has_changes is True
        assert "-1 removed" in d.summary()

    def test_has_changes_changed(self):
        d = MetadataDiff(changed={"x": (1, 2)})
        assert d.has_changes is True
        assert "~1 changed" in d.summary()

    def test_summary_with_unchanged(self):
        d = MetadataDiff(unchanged={"x": 1})
        assert "=1 unchanged" in d.summary()


# ---------------------------------------------------------------------------
# GovernanceMetadataStore - Core CRUD
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreCRUD:
    def test_set_and_get(self):
        store = GovernanceMetadataStore()
        store.set("art1", "owner", "alice")
        assert store.get("art1", "owner") == "alice"

    def test_get_missing_returns_default(self):
        store = GovernanceMetadataStore()
        assert store.get("nope", "key") is None
        assert store.get("nope", "key", "fallback") == "fallback"

    def test_set_updates_existing(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v1")
        store.set("a", "k", "v2")
        assert store.get("a", "k") == "v2"

    def test_get_entry(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", scope=MetadataScope.RULE)
        entry = store.get_entry("a", "k")
        assert entry is not None
        assert entry.value == "v"
        assert entry.scope == MetadataScope.RULE

    def test_get_entry_missing(self):
        store = GovernanceMetadataStore()
        assert store.get_entry("a", "k") is None

    def test_delete(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v")
        assert store.delete("a", "k") is True
        assert store.get("a", "k") is None

    def test_delete_nonexistent(self):
        store = GovernanceMetadataStore()
        assert store.delete("a", "k") is False

    def test_delete_removes_empty_bucket(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v")
        store.delete("a", "k")
        assert "a" not in store._store

    def test_delete_artifact(self):
        store = GovernanceMetadataStore()
        store.set("a", "k1", "v1")
        store.set("a", "k2", "v2")
        count = store.delete_artifact("a")
        assert count == 2
        assert store.get("a", "k1") is None

    def test_delete_artifact_nonexistent(self):
        store = GovernanceMetadataStore()
        assert store.delete_artifact("nope") == 0

    def test_has_key(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v")
        assert store.has_key("a", "k") is True
        assert store.has_key("a", "missing") is False

    def test_set_with_author(self):
        store = GovernanceMetadataStore()
        entry = store.set("a", "k", "v", author="bot")
        assert entry.author == "bot"


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreBulk:
    def test_set_many(self):
        store = GovernanceMetadataStore()
        entries = store.set_many("a", {"k1": "v1", "k2": "v2"})
        assert len(entries) == 2
        assert store.get("a", "k1") == "v1"
        assert store.get("a", "k2") == "v2"

    def test_get_all(self):
        store = GovernanceMetadataStore()
        store.set_many("a", {"k1": 1, "k2": 2})
        result = store.get_all("a")
        assert result == {"k1": 1, "k2": 2}

    def test_get_all_empty(self):
        store = GovernanceMetadataStore()
        assert store.get_all("nope") == {}

    def test_get_all_entries(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v")
        entries = store.get_all_entries("a")
        assert "k" in entries
        assert isinstance(entries["k"], MetadataEntry)

    def test_copy_metadata(self):
        store = GovernanceMetadataStore()
        store.set("src", "k1", "v1")
        store.set("src", "k2", "v2")
        copied = store.copy_metadata("src", "dst")
        assert copied == 2
        assert store.get("dst", "k1") == "v1"

    def test_copy_metadata_selective_keys(self):
        store = GovernanceMetadataStore()
        store.set("src", "k1", "v1")
        store.set("src", "k2", "v2")
        copied = store.copy_metadata("src", "dst", keys=["k1"])
        assert copied == 1
        assert store.get("dst", "k1") == "v1"
        assert store.get("dst", "k2") is None

    def test_copy_metadata_no_overwrite(self):
        store = GovernanceMetadataStore()
        store.set("src", "k", "new")
        store.set("dst", "k", "existing")
        copied = store.copy_metadata("src", "dst", overwrite=False)
        assert copied == 0
        assert store.get("dst", "k") == "existing"


# ---------------------------------------------------------------------------
# Search / query
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreSearch:
    def test_find_by_value(self):
        store = GovernanceMetadataStore()
        store.set("a", "owner", "alice")
        store.set("b", "owner", "alice")
        store.set("c", "owner", "bob")
        results = store.find_by_value("alice")
        assert len(results) == 2
        assert ("a", "owner") in results

    def test_find_by_value_with_scope(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "x", scope=MetadataScope.RULE)
        store.set("b", "k", "x", scope=MetadataScope.AGENT)
        results = store.find_by_value("x", scope=MetadataScope.RULE)
        assert len(results) == 1

    def test_find_by_key(self):
        store = GovernanceMetadataStore()
        store.set("a", "owner", "alice")
        store.set("b", "owner", "bob")
        results = store.find_by_key("owner")
        assert results == {"a": "alice", "b": "bob"}

    def test_find_by_key_with_scope(self):
        store = GovernanceMetadataStore()
        store.set("a", "owner", "alice", scope=MetadataScope.RULE)
        store.set("b", "owner", "bob", scope=MetadataScope.AGENT)
        results = store.find_by_key("owner", scope=MetadataScope.RULE)
        assert results == {"a": "alice"}

    def test_artifacts_with_scope(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", scope=MetadataScope.RULE)
        store.set("b", "k", "v", scope=MetadataScope.AGENT)
        result = store.artifacts_with_scope(MetadataScope.RULE)
        assert result == ["a"]


# ---------------------------------------------------------------------------
# TTL / expiry
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreTTL:
    def test_expired_entry_not_returned(self):
        store = GovernanceMetadataStore()
        # Set with a TTL of 0 effectively makes it expire immediately
        store.set("a", "k", "v", ttl_seconds=0.0)
        # Force expiry by patching monotonic to return future
        original_monotonic = time.monotonic
        with patch("time.monotonic", return_value=original_monotonic() + 1):
            assert store.get("a", "k") is None

    def test_purge_expired(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", ttl_seconds=0.0)
        original_monotonic = time.monotonic
        with patch("time.monotonic", return_value=original_monotonic() + 1):
            purged = store.purge_expired()
            assert purged == 1
            assert "a" not in store._store

    def test_refresh_ttl(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", ttl_seconds=100.0)
        result = store.refresh_ttl("a", "k", 200.0)
        assert result is True

    def test_refresh_ttl_missing_entry(self):
        store = GovernanceMetadataStore()
        assert store.refresh_ttl("a", "k", 100.0) is False

    def test_get_all_include_expired(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", ttl_seconds=0.0)
        original_monotonic = time.monotonic
        with patch("time.monotonic", return_value=original_monotonic() + 1):
            # Without include_expired
            assert store.get_all("a") == {}
            # With include_expired
            result = store.get_all("a", include_expired=True)
            assert result == {"k": "v"}


# ---------------------------------------------------------------------------
# Diff / snapshot
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreDiff:
    def test_snapshot(self):
        store = GovernanceMetadataStore()
        store.set_many("a", {"k1": 1, "k2": 2})
        snap = store.snapshot("a")
        assert snap == {"k1": 1, "k2": 2}

    def test_diff_between_artifacts(self):
        store = GovernanceMetadataStore()
        store.set_many("a", {"x": 1, "y": 2})
        store.set_many("b", {"y": 3, "z": 4})
        diff = store.diff("a", "b")
        assert diff.has_changes is True
        assert "x" in diff.removed
        assert "z" in diff.added
        assert "y" in diff.changed

    def test_diff_identical(self):
        store = GovernanceMetadataStore()
        store.set_many("a", {"x": 1})
        store.set_many("b", {"x": 1})
        diff = store.diff("a", "b")
        assert diff.has_changes is False
        assert "x" in diff.unchanged

    def test_diff_snapshots(self):
        store = GovernanceMetadataStore()
        before = {"k": 1}
        after = {"k": 2}
        diff = store.diff_snapshots(before, after)
        assert "k" in diff.changed


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreExport:
    def test_export_artifact(self):
        store = GovernanceMetadataStore()
        store.set("a", "k1", "v1", scope=MetadataScope.RULE)
        exported = store.export_artifact("a")
        assert len(exported) == 1
        assert exported[0]["key"] == "k1"

    def test_export_all(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", scope=MetadataScope.RULE)
        store.set("b", "k", "v", scope=MetadataScope.AGENT)
        result = store.export_all()
        assert "a" in result
        assert "b" in result

    def test_export_all_with_scope_filter(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v", scope=MetadataScope.RULE)
        store.set("b", "k", "v", scope=MetadataScope.AGENT)
        result = store.export_all(scope=MetadataScope.RULE)
        assert "a" in result
        assert "b" not in result


# ---------------------------------------------------------------------------
# Summary / statistics
# ---------------------------------------------------------------------------


class TestGovernanceMetadataStoreSummary:
    def test_summary_empty(self):
        store = GovernanceMetadataStore()
        s = store.summary()
        assert s["total_artifacts"] == 0
        assert s["total_entries"] == 0

    def test_summary_with_data(self):
        store = GovernanceMetadataStore()
        store.set("a", "k1", "v1", scope=MetadataScope.RULE)
        store.set("a", "k2", "v2", scope=MetadataScope.RULE)
        store.set("b", "k1", "v1", scope=MetadataScope.AGENT)
        s = store.summary()
        assert s["total_artifacts"] == 2
        assert s["total_entries"] == 3
        assert s["scope_counts"]["rule"] == 2
        assert s["scope_counts"]["agent"] == 1

    def test_change_log(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v1")
        store.set("a", "k", "v2")
        log = store.change_log()
        assert len(log) == 2

    def test_change_log_filtered(self):
        store = GovernanceMetadataStore()
        store.set("a", "k", "v")
        store.set("b", "k", "v")
        log = store.change_log(artifact_id="a")
        assert len(log) == 1

    def test_change_log_limited(self):
        store = GovernanceMetadataStore()
        for i in range(10):
            store.set("a", f"k{i}", f"v{i}")
        log = store.change_log(limit=3)
        assert len(log) == 3
