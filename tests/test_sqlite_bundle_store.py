"""Tests for SQLiteBundleStore — Phase B persistent backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.constitution.bundle import BundleStatus, ConstitutionBundle
from acgs_lite.constitution.evidence import InMemoryLifecycleAuditSink
from acgs_lite.constitution.lifecycle_service import ConstitutionLifecycle
from acgs_lite.constitution.provenance import RuleProvenanceGraph
from acgs_lite.constitution.sqlite_bundle_store import SQLiteBundleStore
from acgs_lite.evals.schema import EvalScenario


def _make_constitution() -> Constitution:
    return Constitution.from_rules(
        list(Constitution.default().rules[:2]),
        name="sqlite-test",
    )


def _make_store(tmp_path: Path) -> SQLiteBundleStore:
    return SQLiteBundleStore(tmp_path / "test.db")


def _make_lifecycle(store: SQLiteBundleStore) -> ConstitutionLifecycle:
    return ConstitutionLifecycle(
        store=store,
        sink=InMemoryLifecycleAuditSink(),
        provenance=RuleProvenanceGraph(),
    )


async def _drive_to_active(lc: ConstitutionLifecycle, tenant_id: str = "tenant-a") -> str:
    draft = await lc.create_draft(tenant_id, "proposer-1")
    await lc.submit_for_review(draft.bundle_id, "proposer-1")
    await lc.approve_review(draft.bundle_id, "reviewer-1")
    await lc.run_evaluation(
        draft.bundle_id,
        scenarios=[EvalScenario(id="s1", input_action="check status", expected_valid=True)],
    )
    await lc.approve(draft.bundle_id, "approver-1", signature="sig-ok")
    await lc.stage(draft.bundle_id, "executor-1")
    await lc.activate(draft.bundle_id, "executor-1")
    return draft.bundle_id


class TestSQLiteBundleStoreRoundTrip:
    @pytest.mark.asyncio
    async def test_save_and_get_bundle(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        draft = await lc.create_draft("tenant-a", "proposer-1")
        bundle_id = draft.bundle_id

        fetched = store.get_bundle(bundle_id)
        assert fetched is not None
        assert fetched.bundle_id == bundle_id
        assert fetched.tenant_id == "tenant-a"

    @pytest.mark.asyncio
    async def test_hash_survives_round_trip(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        draft = await lc.create_draft("tenant-a", "proposer-1")
        original_hash = draft.constitutional_hash

        fetched = store.get_bundle(draft.bundle_id)
        assert fetched is not None
        assert fetched.constitutional_hash == original_hash

    @pytest.mark.asyncio
    async def test_get_active_bundle_none_when_empty(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        active = store.get_active_bundle("tenant-x")
        assert active is None

    @pytest.mark.asyncio
    async def test_get_active_bundle_returns_active(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        bundle_id = await _drive_to_active(lc, "tenant-a")

        active = store.get_active_bundle("tenant-a")
        assert active is not None
        assert active.bundle_id == bundle_id
        assert active.status == BundleStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_list_bundles_with_status_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        draft = await lc.create_draft("tenant-a", "proposer-1")

        all_bundles = store.list_bundles("tenant-a")
        draft_bundles = store.list_bundles("tenant-a", status=BundleStatus.DRAFT)

        assert any(b.bundle_id == draft.bundle_id for b in all_bundles)
        assert any(b.bundle_id == draft.bundle_id for b in draft_bundles)

    @pytest.mark.asyncio
    async def test_only_one_active_per_tenant(self, tmp_path: Path) -> None:
        """Partial unique index enforces one-ACTIVE-per-tenant."""
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        # Activate first bundle
        await _drive_to_active(lc, "tenant-a")

        # Activate a second bundle — lifecycle supersedes the first
        await _drive_to_active(lc, "tenant-a")

        active_bundles = [
            b for b in store.list_bundles("tenant-a") if b.status == BundleStatus.ACTIVE
        ]
        assert len(active_bundles) == 1

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        id_a = await _drive_to_active(lc, "tenant-a")
        id_b = await _drive_to_active(lc, "tenant-b")

        active_a = store.get_active_bundle("tenant-a")
        active_b = store.get_active_bundle("tenant-b")

        assert active_a is not None and active_a.bundle_id == id_a
        assert active_b is not None and active_b.bundle_id == id_b
        assert id_a != id_b

    def test_database_file_created(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "bundle.db"
        SQLiteBundleStore(db_path)
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_persistence_across_store_instances(self, tmp_path: Path) -> None:
        """Data written by one store instance is readable by a new instance."""
        db_path = tmp_path / "shared.db"

        store1 = SQLiteBundleStore(db_path)
        lc1 = _make_lifecycle(store1)
        draft = await lc1.create_draft("tenant-a", "proposer-1")

        # Create a second store instance pointing at the same file
        store2 = SQLiteBundleStore(db_path)
        fetched = store2.get_bundle(draft.bundle_id)

        assert fetched is not None
        assert fetched.bundle_id == draft.bundle_id


# ── atomic_transition ────────────────────────────────────────────────────

class TestAtomicTransition:
    @pytest.mark.asyncio
    async def test_atomic_transition_saves_bundle_and_activation(
        self, tmp_path: Path
    ) -> None:
        from acgs_lite.constitution.activation import ActivationRecord
        from acgs_lite.constitution.bundle import BundleStatus

        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        # Use the lifecycle to produce a properly-formed ACTIVE bundle
        draft = await lc.create_draft("tenant-atomic", "proposer-1")
        await lc.submit_for_review(draft.bundle_id, "proposer-1")
        await lc.approve_review(draft.bundle_id, "reviewer-1")
        await lc.run_evaluation(
            draft.bundle_id,
            scenarios=[EvalScenario(id="s1", input_action="check", expected_valid=True)],
        )
        await lc.approve(draft.bundle_id, "approver-1", signature="sig-1")
        await lc.stage(draft.bundle_id, "executor-1")

        bundle = store.get_bundle(draft.bundle_id)
        assert bundle is not None
        bundle.status = BundleStatus.ACTIVE
        bundle.activated_by = "executor-1"

        activation = ActivationRecord(
            bundle_id=bundle.bundle_id,
            version=bundle.version,
            tenant_id="tenant-atomic",
            constitutional_hash=bundle.constitutional_hash,
            activated_by="executor-1",
            rollback_to_bundle_id=None,
            signature="sig-atomic",
        )

        store.save_bundle_transactional(bundles=[bundle], activation=activation)

        fetched = store.get_bundle(bundle.bundle_id)
        assert fetched is not None
        assert fetched.status == BundleStatus.ACTIVE

        fetched_activation = store.get_activation("tenant-atomic")
        assert fetched_activation is not None
        assert fetched_activation.bundle_id == bundle.bundle_id

    @pytest.mark.asyncio
    async def test_atomic_transition_saves_multiple_bundles_no_activation(
        self, tmp_path: Path
    ) -> None:
        from acgs_lite.constitution.bundle import BundleStatus

        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        b1 = await lc.create_draft("tenant-multi", "proposer-1")
        b2 = await lc.create_draft("tenant-multi", "proposer-2")

        bundle1 = store.get_bundle(b1.bundle_id)
        bundle2 = store.get_bundle(b2.bundle_id)
        assert bundle1 is not None and bundle2 is not None

        bundle1.status = BundleStatus.WITHDRAWN
        store.save_bundle_transactional(bundles=[bundle1, bundle2], activation=None)

        assert store.get_bundle(b1.bundle_id) is not None
        assert store.get_bundle(b2.bundle_id) is not None
        assert store.get_activation("tenant-multi") is None

    @pytest.mark.asyncio
    async def test_atomic_transition_overwrites_existing_bundle(self, tmp_path: Path) -> None:
        from acgs_lite.constitution.bundle import BundleStatus

        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        draft = await lc.create_draft("tenant-overwrite", "proposer-1")
        bundle = store.get_bundle(draft.bundle_id)
        assert bundle is not None
        assert bundle.status == BundleStatus.DRAFT

        bundle.status = BundleStatus.WITHDRAWN
        store.save_bundle_transactional(bundles=[bundle], activation=None)

        fetched = store.get_bundle(draft.bundle_id)
        assert fetched is not None
        assert fetched.status == BundleStatus.WITHDRAWN


# ── error wrapping ───────────────────────────────────────────────────────


class TestOperationalErrorWrapping:
    def test_wrap_converts_operational_error_to_lifecycle_error(self, tmp_path: Path) -> None:
        import sqlite3

        from acgs_lite.constitution.lifecycle_service import LifecycleError

        store = _make_store(tmp_path)
        exc = sqlite3.OperationalError("disk I/O error")
        wrapped = store._wrap(exc)

        assert isinstance(wrapped, LifecycleError)
        assert "disk I/O error" in str(wrapped)

    def test_get_bundle_returns_none_for_unknown_id(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        result = store.get_bundle("does-not-exist-xyz")
        assert result is None

    def test_get_active_bundle_returns_none_when_no_active(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        result = store.get_active_bundle("no-such-tenant")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_bundles_with_offset_skips_first_n(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        lc = _make_lifecycle(store)

        for _ in range(3):
            await lc.create_draft("tenant-offset", "proposer-1")

        all_bundles = store.list_bundles("tenant-offset", limit=10)
        assert len(all_bundles) == 3

        offset_bundles = store.list_bundles("tenant-offset", limit=10, offset=1)
        assert len(offset_bundles) == 2
        assert all_bundles[1].bundle_id == offset_bundles[0].bundle_id

    def test_save_bundle_raises_lifecycle_error_on_operational_error(
        self, tmp_path: Path
    ) -> None:
        """save_bundle's except clause converts OperationalError to LifecycleError."""
        import sqlite3
        from unittest.mock import MagicMock, patch

        from acgs_lite.constitution.lifecycle_service import LifecycleError

        store = _make_store(tmp_path)
        bundle = ConstitutionBundle(
            tenant_id="t1",
            constitution=_make_constitution(),
            proposed_by="p1",
        )

        with patch.object(store, "_connect") as mock_connect:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(
                side_effect=sqlite3.OperationalError("disk full")
            )
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_ctx

            with pytest.raises(LifecycleError, match="disk full"):
                store.save_bundle(bundle)

    def test_get_bundle_raises_lifecycle_error_on_operational_error(
        self, tmp_path: Path
    ) -> None:
        """get_bundle's except clause converts OperationalError to LifecycleError."""
        import sqlite3
        from unittest.mock import MagicMock, patch

        from acgs_lite.constitution.lifecycle_service import LifecycleError

        store = _make_store(tmp_path)

        with patch.object(store, "_connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = sqlite3.OperationalError("read error")
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_connect.return_value = mock_ctx

            with pytest.raises(LifecycleError, match="read error"):
                store.get_bundle("some-id")
