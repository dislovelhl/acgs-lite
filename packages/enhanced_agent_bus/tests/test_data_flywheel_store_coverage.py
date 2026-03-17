"""
Test coverage for src/core/enhanced_agent_bus/data_flywheel/store.py
Constitutional Hash: cdd01ef066bc6cf2

Covers: CRUD ops, filtering edge cases, error paths, empty-state handling,
        SQLite backend, InMemoryBackend, FlywheelDataStore orchestration,
        stratified/random splits, dataset lifecycle, and context manager.
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.enhanced_agent_bus.data_flywheel.config import DataSplitConfig, FlywheelConfig
from packages.enhanced_agent_bus.data_flywheel.logger import (
    GovernanceDecision,
    GovernanceDecisionLog,
    ImpactScoringMethod,
    WorkloadType,
)
from packages.enhanced_agent_bus.data_flywheel.store import (
    DatasetSplit,
    FlywheelDataset,
    FlywheelDataStore,
    FlywheelDataStoreBackend,
    InMemoryBackend,
    SQLiteBackend,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.unit, pytest.mark.governance]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_log(
    *,
    workload_type: WorkloadType = WorkloadType.GOVERNANCE_REQUEST,
    tenant_id: str = "tenant-1",
    quality_score: float = 0.9,
    is_high_quality: bool = True,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
    created_at: datetime | None = None,
    hitl_required: bool = False,
    hitl_decision: GovernanceDecision | None = None,
    hitl_feedback: str | None = None,
    required_deliberation: bool = False,
    deliberation_outcome: dict | None = None,
    decision: GovernanceDecision = GovernanceDecision.APPROVED,
) -> GovernanceDecisionLog:
    return GovernanceDecisionLog(
        message_id="msg-001",
        tenant_id=tenant_id,
        workload_type=workload_type,
        workload_id="wl-001",
        decision=decision,
        impact_score=0.3,
        scoring_method=ImpactScoringMethod.SEMANTIC,
        scoring_confidence=0.95,
        quality_score=quality_score,
        is_high_quality=is_high_quality,
        constitutional_hash=constitutional_hash,
        created_at=created_at or datetime.now(UTC),
        hitl_required=hitl_required,
        hitl_decision=hitl_decision,
        hitl_feedback=hitl_feedback,
        required_deliberation=required_deliberation,
        deliberation_outcome=deliberation_outcome,
    )


def _make_logs(n: int, **kwargs) -> list[GovernanceDecisionLog]:
    return [_make_log(**kwargs) for _ in range(n)]


# ---------------------------------------------------------------------------
# DatasetSplit model
# ---------------------------------------------------------------------------


class TestDatasetSplit:
    def test_defaults(self):
        split = DatasetSplit(name="train")
        assert split.name == "train"
        assert split.records == []
        assert split.workload_distribution == {}
        assert split.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(split.created_at, datetime)

    def test_with_records(self):
        records = [{"id": "1", "label": "approved"}]
        split = DatasetSplit(name="eval", records=records, workload_distribution={"gov": 1})
        assert len(split.records) == 1
        assert split.workload_distribution["gov"] == 1


# ---------------------------------------------------------------------------
# FlywheelDataset model
# ---------------------------------------------------------------------------


class TestFlywheelDataset:
    def test_defaults(self):
        ds = FlywheelDataset(dataset_id="ds-1", name="My Dataset")
        assert ds.dataset_id == "ds-1"
        assert ds.name == "My Dataset"
        assert ds.description == ""
        assert ds.train_split is None
        assert ds.val_split is None
        assert ds.eval_split is None
        assert ds.total_records == 0
        assert ds.average_quality_score == 0.0
        assert ds.hitl_feedback_count == 0
        assert ds.constitutional_hash == CONSTITUTIONAL_HASH
        assert ds.date_range == (None, None)

    def test_with_splits(self):
        train = DatasetSplit(name="train", records=[{"id": "a"}])
        ds = FlywheelDataset(
            dataset_id="ds-2",
            name="Full Dataset",
            description="Test desc",
            train_split=train,
            total_records=100,
            workload_types=["governance_request"],
            average_quality_score=0.85,
            hitl_feedback_count=5,
        )
        assert ds.train_split is not None
        assert ds.total_records == 100
        assert ds.hitl_feedback_count == 5


# ---------------------------------------------------------------------------
# InMemoryBackend
# ---------------------------------------------------------------------------


class TestInMemoryBackend:
    @pytest.mark.asyncio
    async def test_store_logs_returns_count(self):
        backend = InMemoryBackend()
        logs = _make_logs(3)
        count = await backend.store_logs(logs)
        assert count == 3

    @pytest.mark.asyncio
    async def test_store_empty_list(self):
        backend = InMemoryBackend()
        count = await backend.store_logs([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_query_logs_no_filter(self):
        backend = InMemoryBackend()
        logs = _make_logs(5)
        await backend.store_logs(logs)
        result = await backend.query_logs()
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_query_logs_filter_workload_type(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(3, workload_type=WorkloadType.GOVERNANCE_REQUEST))
        await backend.store_logs(_make_logs(2, workload_type=WorkloadType.AUDIT_LOG))
        result = await backend.query_logs(workload_type=WorkloadType.AUDIT_LOG)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_logs_filter_tenant_id(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(3, tenant_id="tenant-A"))
        await backend.store_logs(_make_logs(2, tenant_id="tenant-B"))
        result = await backend.query_logs(tenant_id="tenant-B")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_logs_filter_start_time(self):
        backend = InMemoryBackend()
        old = _make_log(created_at=datetime.now(UTC) - timedelta(days=10))
        fresh = _make_log(created_at=datetime.now(UTC))
        await backend.store_logs([old, fresh])
        cutoff = datetime.now(UTC) - timedelta(days=1)
        result = await backend.query_logs(start_time=cutoff)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_query_logs_filter_end_time(self):
        backend = InMemoryBackend()
        old = _make_log(created_at=datetime.now(UTC) - timedelta(days=10))
        fresh = _make_log(created_at=datetime.now(UTC))
        await backend.store_logs([old, fresh])
        cutoff = datetime.now(UTC) - timedelta(days=1)
        result = await backend.query_logs(end_time=cutoff)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_query_logs_filter_min_quality_score(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(3, quality_score=0.3))
        await backend.store_logs(_make_logs(2, quality_score=0.8))
        result = await backend.query_logs(min_quality_score=0.7)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_logs_pagination_offset(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(10))
        page1 = await backend.query_logs(limit=5, offset=0)
        page2 = await backend.query_logs(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5

    @pytest.mark.asyncio
    async def test_query_logs_sorted_descending(self):
        backend = InMemoryBackend()
        t1 = _make_log(created_at=datetime.now(UTC) - timedelta(hours=2))
        t2 = _make_log(created_at=datetime.now(UTC) - timedelta(hours=1))
        t3 = _make_log(created_at=datetime.now(UTC))
        await backend.store_logs([t1, t2, t3])
        result = await backend.query_logs()
        assert result[0].created_at >= result[1].created_at >= result[2].created_at

    @pytest.mark.asyncio
    async def test_query_logs_empty_store(self):
        backend = InMemoryBackend()
        result = await backend.query_logs()
        assert result == []

    @pytest.mark.asyncio
    async def test_count_logs_no_filter(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(7))
        count = await backend.count_logs()
        assert count == 7

    @pytest.mark.asyncio
    async def test_count_logs_filter_workload_type(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(4, workload_type=WorkloadType.DELIBERATION))
        await backend.store_logs(_make_logs(3, workload_type=WorkloadType.POLICY_EVALUATION))
        count = await backend.count_logs(workload_type=WorkloadType.DELIBERATION)
        assert count == 4

    @pytest.mark.asyncio
    async def test_count_logs_filter_tenant_id(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(2, tenant_id="tenant-X"))
        await backend.store_logs(_make_logs(5, tenant_id="tenant-Y"))
        count = await backend.count_logs(tenant_id="tenant-X")
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_logs_both_filters(self):
        backend = InMemoryBackend()
        await backend.store_logs(
            _make_logs(2, tenant_id="t1", workload_type=WorkloadType.AUDIT_LOG)
        )
        await backend.store_logs(
            _make_logs(3, tenant_id="t1", workload_type=WorkloadType.GOVERNANCE_REQUEST)
        )
        await backend.store_logs(
            _make_logs(1, tenant_id="t2", workload_type=WorkloadType.AUDIT_LOG)
        )
        count = await backend.count_logs(tenant_id="t1", workload_type=WorkloadType.AUDIT_LOG)
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_empty_store(self):
        backend = InMemoryBackend()
        assert await backend.count_logs() == 0

    @pytest.mark.asyncio
    async def test_get_workload_distribution_no_filter(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(3, workload_type=WorkloadType.GOVERNANCE_REQUEST))
        await backend.store_logs(_make_logs(2, workload_type=WorkloadType.AUDIT_LOG))
        dist = await backend.get_workload_distribution()
        assert dist[WorkloadType.GOVERNANCE_REQUEST.value] == 3
        assert dist[WorkloadType.AUDIT_LOG.value] == 2

    @pytest.mark.asyncio
    async def test_get_workload_distribution_filter_tenant(self):
        backend = InMemoryBackend()
        await backend.store_logs(
            _make_logs(3, tenant_id="t1", workload_type=WorkloadType.GOVERNANCE_REQUEST)
        )
        await backend.store_logs(
            _make_logs(2, tenant_id="t2", workload_type=WorkloadType.AUDIT_LOG)
        )
        dist = await backend.get_workload_distribution(tenant_id="t1")
        assert WorkloadType.GOVERNANCE_REQUEST.value in dist
        assert WorkloadType.AUDIT_LOG.value not in dist

    @pytest.mark.asyncio
    async def test_get_workload_distribution_empty(self):
        backend = InMemoryBackend()
        dist = await backend.get_workload_distribution()
        assert dist == {}

    @pytest.mark.asyncio
    async def test_delete_old_logs_removes_stale(self):
        backend = InMemoryBackend()
        old = _make_log(created_at=datetime.now(UTC) - timedelta(days=100))
        fresh = _make_log(created_at=datetime.now(UTC))
        await backend.store_logs([old, fresh])
        deleted = await backend.delete_old_logs(retention_days=30)
        assert deleted == 1
        remaining = await backend.query_logs()
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_delete_old_logs_nothing_to_delete(self):
        backend = InMemoryBackend()
        fresh = _make_log(created_at=datetime.now(UTC))
        await backend.store_logs([fresh])
        deleted = await backend.delete_old_logs(retention_days=30)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_delete_old_logs_empty_store(self):
        backend = InMemoryBackend()
        deleted = await backend.delete_old_logs(retention_days=7)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_close_clears_logs(self):
        backend = InMemoryBackend()
        await backend.store_logs(_make_logs(5))
        await backend.close()
        result = await backend.query_logs()
        assert result == []


# ---------------------------------------------------------------------------
# SQLiteBackend
# ---------------------------------------------------------------------------


class TestSQLiteBackend:
    def _make_sqlite_backend(self) -> tuple[SQLiteBackend, str]:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        backend = SQLiteBackend(db_path=path)
        return backend, path

    @pytest.mark.asyncio
    async def test_store_and_query_basic(self):
        backend, path = self._make_sqlite_backend()
        try:
            log = _make_log()
            count = await backend.store_logs([log])
            assert count == 1
            results = await backend.query_logs()
            assert len(results) == 1
            assert results[0].tenant_id == "tenant-1"
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_store_empty_list(self):
        backend, path = self._make_sqlite_backend()
        try:
            count = await backend.store_logs([])
            assert count == 0
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_filter_workload_type(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(2, workload_type=WorkloadType.GOVERNANCE_REQUEST))
            await backend.store_logs(_make_logs(3, workload_type=WorkloadType.AUDIT_LOG))
            result = await backend.query_logs(workload_type=WorkloadType.AUDIT_LOG)
            assert len(result) == 3
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_filter_tenant_id(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(4, tenant_id="t-alpha"))
            await backend.store_logs(_make_logs(1, tenant_id="t-beta"))
            result = await backend.query_logs(tenant_id="t-beta")
            assert len(result) == 1
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_filter_start_time(self):
        backend, path = self._make_sqlite_backend()
        try:
            old = _make_log(created_at=datetime.now(UTC) - timedelta(days=15))
            fresh = _make_log(created_at=datetime.now(UTC))
            await backend.store_logs([old, fresh])
            cutoff = datetime.now(UTC) - timedelta(days=1)
            result = await backend.query_logs(start_time=cutoff)
            assert len(result) == 1
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_filter_end_time(self):
        backend, path = self._make_sqlite_backend()
        try:
            old = _make_log(created_at=datetime.now(UTC) - timedelta(days=15))
            fresh = _make_log(created_at=datetime.now(UTC))
            await backend.store_logs([old, fresh])
            cutoff = datetime.now(UTC) - timedelta(days=1)
            result = await backend.query_logs(end_time=cutoff)
            assert len(result) == 1
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_filter_min_quality(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(2, quality_score=0.4))
            await backend.store_logs(_make_logs(3, quality_score=0.9))
            result = await backend.query_logs(min_quality_score=0.7)
            assert len(result) == 3
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_query_pagination(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(10))
            page1 = await backend.query_logs(limit=4, offset=0)
            page2 = await backend.query_logs(limit=4, offset=4)
            page3 = await backend.query_logs(limit=4, offset=8)
            assert len(page1) == 4
            assert len(page2) == 4
            assert len(page3) == 2
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_count_logs_no_filter(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(6))
            count = await backend.count_logs()
            assert count == 6
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_count_logs_filter_workload(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(3, workload_type=WorkloadType.IMPACT_SCORING))
            await backend.store_logs(_make_logs(5, workload_type=WorkloadType.DELIBERATION))
            count = await backend.count_logs(workload_type=WorkloadType.IMPACT_SCORING)
            assert count == 3
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_count_logs_filter_tenant(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(2, tenant_id="tenant-X"))
            await backend.store_logs(_make_logs(4, tenant_id="tenant-Y"))
            count = await backend.count_logs(tenant_id="tenant-Y")
            assert count == 4
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_get_workload_distribution(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(_make_logs(3, workload_type=WorkloadType.GOVERNANCE_REQUEST))
            await backend.store_logs(_make_logs(2, workload_type=WorkloadType.AUDIT_LOG))
            dist = await backend.get_workload_distribution()
            assert dist[WorkloadType.GOVERNANCE_REQUEST.value] == 3
            assert dist[WorkloadType.AUDIT_LOG.value] == 2
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_get_workload_distribution_with_tenant_filter(self):
        backend, path = self._make_sqlite_backend()
        try:
            await backend.store_logs(
                _make_logs(2, tenant_id="ta", workload_type=WorkloadType.GOVERNANCE_REQUEST)
            )
            await backend.store_logs(
                _make_logs(3, tenant_id="tb", workload_type=WorkloadType.AUDIT_LOG)
            )
            dist = await backend.get_workload_distribution(tenant_id="ta")
            assert WorkloadType.GOVERNANCE_REQUEST.value in dist
            assert WorkloadType.AUDIT_LOG.value not in dist
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_delete_old_logs(self):
        backend, path = self._make_sqlite_backend()
        try:
            old = _make_log(created_at=datetime.now(UTC) - timedelta(days=200))
            fresh = _make_log(created_at=datetime.now(UTC))
            await backend.store_logs([old, fresh])
            deleted = await backend.delete_old_logs(retention_days=30)
            assert deleted == 1
            remaining = await backend.query_logs()
            assert len(remaining) == 1
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_delete_old_logs_none_to_delete(self):
        backend, path = self._make_sqlite_backend()
        try:
            fresh = _make_log(created_at=datetime.now(UTC))
            await backend.store_logs([fresh])
            deleted = await backend.delete_old_logs(retention_days=30)
            assert deleted == 0
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_close_sets_conn_to_none(self):
        backend, path = self._make_sqlite_backend()
        assert backend._conn is not None
        await backend.close()
        assert backend._conn is None
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_store_logs_when_conn_is_none(self):
        backend, path = self._make_sqlite_backend()
        await backend.close()
        os.unlink(path)
        count = await backend.store_logs(_make_logs(2))
        assert count == 0

    @pytest.mark.asyncio
    async def test_query_logs_when_conn_is_none(self):
        backend, path = self._make_sqlite_backend()
        await backend.close()
        os.unlink(path)
        result = await backend.query_logs()
        assert result == []

    @pytest.mark.asyncio
    async def test_count_logs_when_conn_is_none(self):
        backend, path = self._make_sqlite_backend()
        await backend.close()
        os.unlink(path)
        count = await backend.count_logs()
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_workload_distribution_when_conn_is_none(self):
        backend, path = self._make_sqlite_backend()
        await backend.close()
        os.unlink(path)
        dist = await backend.get_workload_distribution()
        assert dist == {}

    @pytest.mark.asyncio
    async def test_delete_old_logs_when_conn_is_none(self):
        backend, path = self._make_sqlite_backend()
        await backend.close()
        os.unlink(path)
        deleted = await backend.delete_old_logs(retention_days=30)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_row_to_log_with_optional_fields(self):
        """Ensure _row_to_log round-trips logs with HITL and deliberation fields."""
        backend, path = self._make_sqlite_backend()
        try:
            log = _make_log(
                hitl_required=True,
                hitl_decision=GovernanceDecision.APPROVED,
                hitl_feedback="looks good",
                required_deliberation=True,
                deliberation_outcome={"consensus": True, "votes": 3},
            )
            await backend.store_logs([log])
            results = await backend.query_logs()
            assert len(results) == 1
            r = results[0]
            assert r.hitl_required is True
            assert r.hitl_decision == GovernanceDecision.APPROVED
            assert r.hitl_feedback == "looks good"
            assert r.required_deliberation is True
            assert r.deliberation_outcome is not None
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_row_to_log_null_optional_fields(self):
        """_row_to_log handles NULL optional columns correctly."""
        backend, path = self._make_sqlite_backend()
        try:
            log = _make_log(
                hitl_required=False,
                hitl_decision=None,
                hitl_feedback=None,
                required_deliberation=False,
                deliberation_outcome=None,
            )
            await backend.store_logs([log])
            results = await backend.query_logs()
            r = results[0]
            assert r.hitl_decision is None
            assert r.hitl_feedback is None
            assert r.deliberation_outcome is None
        finally:
            await backend.close()
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_insert_or_replace_deduplicates(self):
        """INSERT OR REPLACE should update existing row with same log_id."""
        backend, path = self._make_sqlite_backend()
        try:
            log = _make_log(quality_score=0.5)
            await backend.store_logs([log])
            # Same log_id, changed quality score
            updated_log = log.model_copy(update={"quality_score": 0.99})
            await backend.store_logs([updated_log])
            # Should still be 1 row
            count = await backend.count_logs()
            assert count == 1
            results = await backend.query_logs()
            assert results[0].quality_score == pytest.approx(0.99)
        finally:
            await backend.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# FlywheelDataStore (orchestration layer)
# ---------------------------------------------------------------------------


class TestFlywheelDataStore:
    @pytest.mark.asyncio
    async def test_create_memory_store_class_method(self):
        store = FlywheelDataStore.create_memory_store()
        assert isinstance(store.backend, InMemoryBackend)

    @pytest.mark.asyncio
    async def test_create_sqlite_store_class_method(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = FlywheelDataStore.create_sqlite_store(db_path=path)
            assert isinstance(store.backend, SQLiteBackend)
            await store.close()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_default_backend_is_in_memory(self):
        store = FlywheelDataStore()
        assert isinstance(store.backend, InMemoryBackend)

    @pytest.mark.asyncio
    async def test_store_logs_validates_constitutional_hash(self):
        store = FlywheelDataStore()
        valid_log = _make_log(constitutional_hash=CONSTITUTIONAL_HASH)
        invalid_log = _make_log(constitutional_hash="deadbeef00000000")
        count = await store.store_logs([valid_log, invalid_log])
        # Only valid log stored
        assert count == 1
        total = await store.count_logs()
        assert total == 1

    @pytest.mark.asyncio
    async def test_store_logs_all_invalid_hashes(self):
        store = FlywheelDataStore()
        logs = _make_logs(3, constitutional_hash="badhash1234567890")
        count = await store.store_logs(logs)
        assert count == 0
        assert await store.count_logs() == 0

    @pytest.mark.asyncio
    async def test_store_logs_all_valid_hashes(self):
        store = FlywheelDataStore()
        logs = _make_logs(4)
        count = await store.store_logs(logs)
        assert count == 4

    @pytest.mark.asyncio
    async def test_query_logs_delegates_to_backend(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(5))
        results = await store.query_logs()
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_query_logs_with_filters(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(3, workload_type=WorkloadType.AUDIT_LOG))
        await store.store_logs(_make_logs(2, workload_type=WorkloadType.DELIBERATION))
        results = await store.query_logs(workload_type=WorkloadType.AUDIT_LOG)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_count_logs_delegates_to_backend(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(7))
        count = await store.count_logs()
        assert count == 7

    @pytest.mark.asyncio
    async def test_count_logs_with_filters(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(4, tenant_id="t-abc"))
        await store.store_logs(_make_logs(2, tenant_id="t-xyz"))
        count = await store.count_logs(tenant_id="t-abc")
        assert count == 4

    @pytest.mark.asyncio
    async def test_get_workload_distribution(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(2, workload_type=WorkloadType.GOVERNANCE_REQUEST))
        await store.store_logs(_make_logs(3, workload_type=WorkloadType.AUDIT_LOG))
        dist = await store.get_workload_distribution()
        assert dist[WorkloadType.GOVERNANCE_REQUEST.value] == 2
        assert dist[WorkloadType.AUDIT_LOG.value] == 3

    @pytest.mark.asyncio
    async def test_cleanup_old_logs(self):
        store = FlywheelDataStore()
        old = _make_log(created_at=datetime.now(UTC) - timedelta(days=200))
        fresh = _make_log(created_at=datetime.now(UTC))
        await store.store_logs([old, fresh])
        deleted = await store.cleanup_old_logs()
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_close_delegates_to_backend(self):
        store = FlywheelDataStore()
        await store.store_logs(_make_logs(3))
        await store.close()
        result = await store.query_logs()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_dataset_nonexistent(self):
        store = FlywheelDataStore()
        assert store.get_dataset("no-such-id") is None

    @pytest.mark.asyncio
    async def test_list_datasets_empty(self):
        store = FlywheelDataStore()
        assert store.list_datasets() == []

    @pytest.mark.asyncio
    async def test_list_datasets_after_creation(self):
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.1, limit=1000
            )
        )
        store.config = config
        await store.store_logs(_make_logs(50))
        dataset = await store.create_dataset(
            dataset_id="ds-001",
            name="Test Dataset",
        )
        assert "ds-001" in store.list_datasets()
        assert store.get_dataset("ds-001") is dataset

    @pytest.mark.asyncio
    async def test_create_dataset_raises_for_insufficient_records(self):
        store = FlywheelDataStore()
        # Default min_total_records is 50
        await store.store_logs(_make_logs(5))
        with pytest.raises(ValueError, match="Insufficient records"):
            await store.create_dataset(
                dataset_id="ds-fail",
                name="Should Fail",
            )

    @pytest.mark.asyncio
    async def test_create_dataset_stratified_split(self):
        """create_dataset with stratify_by_workload=True uses stratified split."""
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.2, limit=1000, random_seed=42
            )
        )
        store.config = config
        logs_g = _make_logs(30, workload_type=WorkloadType.GOVERNANCE_REQUEST)
        logs_a = _make_logs(30, workload_type=WorkloadType.AUDIT_LOG)
        await store.store_logs(logs_g + logs_a)

        dataset = await store.create_dataset(
            dataset_id="ds-strat",
            name="Stratified",
            stratify_by_workload=True,
        )
        assert dataset.total_records == 60
        assert dataset.train_split is not None
        assert dataset.val_split is not None
        assert dataset.eval_split is not None
        # Both workload types should appear in splits
        all_wt = set(dataset.train_split.workload_distribution.keys())
        assert WorkloadType.GOVERNANCE_REQUEST.value in all_wt
        assert WorkloadType.AUDIT_LOG.value in all_wt

    @pytest.mark.asyncio
    async def test_create_dataset_random_split(self):
        """create_dataset with stratify_by_workload=False uses random split."""
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.2, limit=1000, random_seed=7
            )
        )
        store.config = config
        await store.store_logs(_make_logs(60))

        dataset = await store.create_dataset(
            dataset_id="ds-rand",
            name="Random",
            stratify_by_workload=False,
        )
        assert dataset.total_records == 60
        assert dataset.train_split is not None
        assert dataset.val_split is not None
        assert dataset.eval_split is not None

    @pytest.mark.asyncio
    async def test_create_dataset_with_tenant_filter(self):
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.1, limit=1000
            )
        )
        store.config = config
        await store.store_logs(_make_logs(40, tenant_id="tenant-A"))
        await store.store_logs(_make_logs(40, tenant_id="tenant-B"))

        dataset = await store.create_dataset(
            dataset_id="ds-tenant",
            name="Tenant Dataset",
            tenant_id="tenant-A",
        )
        # Dataset only has tenant-A records
        assert dataset.total_records == 40

    @pytest.mark.asyncio
    async def test_create_dataset_with_min_quality_score_filter(self):
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.1, limit=1000
            )
        )
        store.config = config
        # Store enough total records to pass minimum count
        await store.store_logs(_make_logs(30, quality_score=0.3))
        await store.store_logs(_make_logs(30, quality_score=0.9))

        # Dataset count check uses count_logs (no quality filter),
        # then queries with min_quality_score applied
        dataset = await store.create_dataset(
            dataset_id="ds-quality",
            name="Quality Filtered",
            min_quality_score=0.8,
        )
        # Only high-quality logs make it into training records
        assert dataset.total_records == 30

    @pytest.mark.asyncio
    async def test_create_dataset_computes_date_range(self):
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.1, limit=1000
            )
        )
        store.config = config
        t_old = datetime.now(UTC) - timedelta(days=30)
        t_new = datetime.now(UTC)
        logs = [_make_log(created_at=t_old), _make_log(created_at=t_new)]
        # Need minimum records so pad
        logs += _make_logs(30)
        await store.store_logs(logs)

        dataset = await store.create_dataset(
            dataset_id="ds-dates",
            name="Date Range",
        )
        assert dataset.date_range[0] is not None
        assert dataset.date_range[1] is not None

    @pytest.mark.asyncio
    async def test_create_dataset_hitl_feedback_count(self):
        store = FlywheelDataStore()
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10, eval_size=10, val_ratio=0.1, limit=1000
            )
        )
        store.config = config
        logs_with_feedback = _make_logs(20, hitl_feedback="good decision")
        logs_without = _make_logs(20)
        await store.store_logs(logs_with_feedback + logs_without)

        dataset = await store.create_dataset(
            dataset_id="ds-hitl",
            name="HITL Count",
        )
        assert dataset.hitl_feedback_count == 20

    @pytest.mark.asyncio
    async def test_transaction_context_manager_yields_self(self):
        store = FlywheelDataStore()
        async with store.transaction() as s:
            assert s is store

    @pytest.mark.asyncio
    async def test_transaction_context_manager_reraises_value_error(self):
        store = FlywheelDataStore()
        with pytest.raises(ValueError):
            async with store.transaction():
                raise ValueError("test error")

    @pytest.mark.asyncio
    async def test_transaction_context_manager_reraises_runtime_error(self):
        store = FlywheelDataStore()
        with pytest.raises(RuntimeError):
            async with store.transaction():
                raise RuntimeError("runtime error")

    @pytest.mark.asyncio
    async def test_transaction_context_manager_reraises_os_error(self):
        store = FlywheelDataStore()
        with pytest.raises(OSError):
            async with store.transaction():
                raise OSError("os error")

    @pytest.mark.asyncio
    async def test_transaction_context_manager_reraises_type_error(self):
        store = FlywheelDataStore()
        with pytest.raises(TypeError):
            async with store.transaction():
                raise TypeError("type error")


# ---------------------------------------------------------------------------
# FlywheelDataStore._stratified_split edge cases
# ---------------------------------------------------------------------------


class TestStratifiedSplit:
    def _make_store_with_config(self, seed: int | None = 42) -> FlywheelDataStore:
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.1,
                random_seed=seed,
                limit=1000,
            )
        )
        return FlywheelDataStore(config=config)

    def _make_records(self, n: int, workload_type: str = "governance_request") -> list[dict]:
        return [
            {
                "id": f"rec-{i}",
                "workload_id": "wl-001",
                "features": {"workload_type": workload_type},
                "label": "approved",
                "quality_score": 0.9,
                "is_high_quality": True,
                "hitl_feedback": None,
                "timestamp": datetime.now(UTC).isoformat(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            for i in range(n)
        ]

    def test_single_workload_type(self):
        store = self._make_store_with_config()
        records = self._make_records(30, "governance_request")
        train, val, eval_ = store._stratified_split(records)
        assert len(train.records) + len(val.records) + len(eval_.records) == 30

    def test_multiple_workload_types(self):
        store = self._make_store_with_config()
        records = self._make_records(20, "governance_request") + self._make_records(20, "audit_log")
        train, val, eval_ = store._stratified_split(records)
        total = len(train.records) + len(val.records) + len(eval_.records)
        assert total == 40
        assert "governance_request" in train.workload_distribution
        assert "audit_log" in train.workload_distribution

    def test_no_random_seed(self):
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.1,
                random_seed=None,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(30)
        train, val, eval_ = store._stratified_split(records)
        assert len(train.records) + len(val.records) + len(eval_.records) == 30

    def test_split_names(self):
        store = self._make_store_with_config()
        records = self._make_records(20)
        train, val, eval_ = store._stratified_split(records)
        assert train.name == "train"
        assert val.name == "val"
        assert eval_.name == "eval"


# ---------------------------------------------------------------------------
# FlywheelDataStore._random_split edge cases
# ---------------------------------------------------------------------------


class TestRandomSplit:
    def _make_store(self, seed: int | None = 42) -> FlywheelDataStore:
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.2,
                random_seed=seed,
                limit=1000,
            )
        )
        return FlywheelDataStore(config=config)

    def _make_records(self, n: int, workload_type: str = "governance_request") -> list[dict]:
        return [
            {
                "id": f"r-{i}",
                "workload_id": "wl-001",
                "features": {"workload_type": workload_type},
                "label": "approved",
                "quality_score": 0.9,
                "is_high_quality": True,
                "hitl_feedback": None,
                "timestamp": datetime.now(UTC).isoformat(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
            for i in range(n)
        ]

    def test_basic_split(self):
        store = self._make_store()
        records = self._make_records(50)
        train, val, eval_ = store._random_split(records)
        total = len(train.records) + len(val.records) + len(eval_.records)
        assert total == 50

    def test_split_names(self):
        store = self._make_store()
        records = self._make_records(30)
        train, val, eval_ = store._random_split(records)
        assert train.name == "train"
        assert val.name == "val"
        assert eval_.name == "eval"

    def test_eval_size_capped_at_third(self):
        """If eval_size > len/3, it is capped."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=100,  # Larger than total/3
                val_ratio=0.1,
                random_seed=1,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(15)
        _train, _val, eval_ = store._random_split(records)
        assert len(eval_.records) <= len(records) // 3 + 1

    def test_no_seed(self):
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.1,
                random_seed=None,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(30)
        train, val, eval_ = store._random_split(records)
        assert len(train.records) + len(val.records) + len(eval_.records) == 30

    def test_workload_distribution_computed(self):
        store = self._make_store()
        records = self._make_records(20, "governance_request") + self._make_records(20, "audit_log")
        train, _val, _eval_2 = store._random_split(records)
        # Distribution should be populated (may have one or both types)
        assert isinstance(train.workload_distribution, dict)


# ---------------------------------------------------------------------------
# FlywheelDataStoreBackend abstract interface
# ---------------------------------------------------------------------------


class TestFlywheelDataStoreBackendABC:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            FlywheelDataStoreBackend()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        """A partial implementation raises TypeError on instantiation."""

        class PartialBackend(FlywheelDataStoreBackend):
            async def store_logs(self, logs):
                return 0

            # Missing all other abstract methods

        with pytest.raises(TypeError):
            PartialBackend()  # type: ignore[abstract]
