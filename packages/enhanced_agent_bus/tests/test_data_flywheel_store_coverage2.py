"""
# Constitutional Hash: cdd01ef066bc6cf2
Additional test coverage for src/core/enhanced_agent_bus/data_flywheel/store.py

Targets paths NOT covered by test_data_flywheel_store_coverage.py:
- SQLiteBackend.count_logs with BOTH workload_type AND tenant_id filters
- SQLiteBackend._row_to_log with NULL impact_vector / policies_evaluated / policy_traces
- FlywheelDataStore.store_logs warning branch (some invalid hashes filtered)
- FlywheelDataStore.create_dataset with empty records after quality filter (dates = [])
- FlywheelDataStore.create_dataset description parameter
- FlywheelDataStore.get_workload_distribution with tenant_id filter
- FlywheelDataStore.create_sqlite_store with explicit config
- FlywheelDataStore with custom backend passed in constructor
- _stratified_split with single-record workload groups
- _random_split with very small record counts (< eval_size)
- InMemoryBackend with all combined filters active at once
- Concrete FlywheelDataStoreBackend subclass fulfilling all abstract methods
- FlywheelDataset and DatasetSplit Pydantic from_attributes model config
- SQLiteBackend._init_db index creation paths
- FlywheelDataStore.transaction with no exception (normal path already covered; verify value)
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
    impact_vector: dict | None = None,
    policies_evaluated: list | None = None,
    policy_traces: list | None = None,
) -> GovernanceDecisionLog:
    return GovernanceDecisionLog(
        message_id="msg-002",
        tenant_id=tenant_id,
        workload_type=workload_type,
        workload_id="wl-002",
        decision=decision,
        impact_score=0.4,
        impact_vector=impact_vector if impact_vector is not None else {},
        scoring_method=ImpactScoringMethod.HEURISTIC,
        scoring_confidence=0.88,
        quality_score=quality_score,
        is_high_quality=is_high_quality,
        constitutional_hash=constitutional_hash,
        created_at=created_at or datetime.now(UTC),
        hitl_required=hitl_required,
        hitl_decision=hitl_decision,
        hitl_feedback=hitl_feedback,
        required_deliberation=required_deliberation,
        deliberation_outcome=deliberation_outcome,
        policies_evaluated=policies_evaluated if policies_evaluated is not None else [],
        policy_traces=policy_traces if policy_traces is not None else [],
    )


def _make_logs(n: int, **kwargs) -> list[GovernanceDecisionLog]:
    return [_make_log(**kwargs) for _ in range(n)]


def _make_sqlite_backend() -> tuple[SQLiteBackend, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(db_path=path)
    return backend, path


def _make_store_config(
    *,
    min_total_records: int = 10,
    eval_size: int = 10,
    val_ratio: float = 0.1,
    limit: int = 1000,
    seed: int | None = 42,
) -> FlywheelConfig:
    return FlywheelConfig(
        data_split=DataSplitConfig(
            min_total_records=min_total_records,
            eval_size=eval_size,
            val_ratio=val_ratio,
            limit=limit,
            random_seed=seed,
        )
    )


# ---------------------------------------------------------------------------
# SQLiteBackend — combined filters in count_logs
# ---------------------------------------------------------------------------


class TestSQLiteBackendCountLogsBothFilters:
    async def test_count_logs_both_workload_and_tenant(self):
        """count_logs with workload_type AND tenant_id together."""
        backend, path = _make_sqlite_backend()
        try:
            await backend.store_logs(
                _make_logs(3, workload_type=WorkloadType.AUDIT_LOG, tenant_id="t1")
            )
            await backend.store_logs(
                _make_logs(2, workload_type=WorkloadType.AUDIT_LOG, tenant_id="t2")
            )
            await backend.store_logs(
                _make_logs(4, workload_type=WorkloadType.GOVERNANCE_REQUEST, tenant_id="t1")
            )
            count = await backend.count_logs(workload_type=WorkloadType.AUDIT_LOG, tenant_id="t1")
            assert count == 3
        finally:
            await backend.close()
            os.unlink(path)

    async def test_count_logs_both_filters_no_match(self):
        """count_logs returns 0 when both filters match nothing."""
        backend, path = _make_sqlite_backend()
        try:
            await backend.store_logs(
                _make_logs(5, workload_type=WorkloadType.AUDIT_LOG, tenant_id="t1")
            )
            count = await backend.count_logs(
                workload_type=WorkloadType.GOVERNANCE_REQUEST, tenant_id="t1"
            )
            assert count == 0
        finally:
            await backend.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# SQLiteBackend._row_to_log — NULL optional columns in raw DB rows
# ---------------------------------------------------------------------------


class TestSQLiteRowToLogNullFields:
    async def test_row_to_log_null_impact_vector(self):
        """_row_to_log must handle NULL impact_vector column → empty dict."""
        backend, path = _make_sqlite_backend()
        try:
            log = _make_log(impact_vector={})
            await backend.store_logs([log])

            # Manually set impact_vector to NULL in the DB
            conn = backend._conn
            assert conn is not None
            conn.execute(
                "UPDATE governance_logs SET impact_vector = NULL WHERE log_id = ?",
                (log.log_id,),
            )
            conn.commit()

            results = await backend.query_logs()
            assert len(results) == 1
            assert results[0].impact_vector == {}
        finally:
            await backend.close()
            os.unlink(path)

    async def test_row_to_log_null_policies_evaluated(self):
        """_row_to_log must handle NULL policies_evaluated → empty list."""
        backend, path = _make_sqlite_backend()
        try:
            log = _make_log(policies_evaluated=["pol-1"])
            await backend.store_logs([log])

            conn = backend._conn
            assert conn is not None
            conn.execute(
                "UPDATE governance_logs SET policies_evaluated = NULL WHERE log_id = ?",
                (log.log_id,),
            )
            conn.commit()

            results = await backend.query_logs()
            assert len(results) == 1
            assert results[0].policies_evaluated == []
        finally:
            await backend.close()
            os.unlink(path)

    async def test_row_to_log_null_policy_traces(self):
        """_row_to_log must handle NULL policy_traces → empty list."""
        backend, path = _make_sqlite_backend()
        try:
            log = _make_log(policy_traces=[{"pol": "x"}])
            await backend.store_logs([log])

            conn = backend._conn
            assert conn is not None
            conn.execute(
                "UPDATE governance_logs SET policy_traces = NULL WHERE log_id = ?",
                (log.log_id,),
            )
            conn.commit()

            results = await backend.query_logs()
            assert len(results) == 1
            assert results[0].policy_traces == []
        finally:
            await backend.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# FlywheelDataStore.store_logs — warning branch when hashes are filtered
# ---------------------------------------------------------------------------


class TestFlywheelStoreLogsWarningBranch:
    async def test_warning_logged_when_invalid_hashes_filtered(self, caplog):
        """store_logs should emit a warning when some logs are filtered out."""
        import logging

        store = FlywheelDataStore()
        valid_log = _make_log(constitutional_hash=CONSTITUTIONAL_HASH)
        invalid_log = _make_log(constitutional_hash="badhash000000000")

        with caplog.at_level(
            logging.WARNING, logger="packages.enhanced_agent_bus.data_flywheel.store"
        ):
            count = await store.store_logs([valid_log, invalid_log])

        assert count == 1
        assert any("Filtered" in record.message for record in caplog.records)

    async def test_no_warning_when_all_valid(self, caplog):
        """No warning emitted when all logs have valid constitutional hash."""
        import logging

        store = FlywheelDataStore()
        logs = _make_logs(3)

        with caplog.at_level(
            logging.WARNING, logger="packages.enhanced_agent_bus.data_flywheel.store"
        ):
            count = await store.store_logs(logs)

        assert count == 3
        assert not any("Filtered" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# FlywheelDataStore.create_dataset — edge cases
# ---------------------------------------------------------------------------


class TestFlywheelCreateDatasetEdgeCases:
    async def test_create_dataset_with_description(self):
        """description parameter is stored in dataset."""
        store = FlywheelDataStore(config=_make_store_config())
        await store.store_logs(_make_logs(50))
        dataset = await store.create_dataset(
            dataset_id="ds-desc",
            name="Described Dataset",
            description="A helpful description",
        )
        assert dataset.description == "A helpful description"

    async def test_create_dataset_empty_records_after_quality_filter_date_range(self):
        """When quality filtering leaves zero records, date_range is (None, None)."""
        store = FlywheelDataStore(config=_make_store_config(min_total_records=10))
        # Store 50 records to pass total count check but all with low quality
        # The total count check uses count_logs (no quality filter) — passes
        # query_logs with min_quality_score filters them all out → records = []
        await store.store_logs(_make_logs(50, quality_score=0.1))

        dataset = await store.create_dataset(
            dataset_id="ds-empty-after-filter",
            name="Empty After Filter",
            min_quality_score=0.9,  # filters all out
            stratify_by_workload=False,
        )
        # No records; date_range should be (None, None)
        assert dataset.date_range == (None, None)
        assert dataset.total_records == 0

    async def test_create_dataset_average_quality_with_records(self):
        """average_quality_score is computed correctly."""
        store = FlywheelDataStore(config=_make_store_config())
        logs = _make_logs(20, quality_score=0.8) + _make_logs(20, quality_score=0.6)
        await store.store_logs(logs)

        dataset = await store.create_dataset(
            dataset_id="ds-avg-quality",
            name="Avg Quality",
        )
        # (20*0.8 + 20*0.6) / 40 = 0.7
        assert abs(dataset.average_quality_score - 0.7) < 0.01

    async def test_create_dataset_hitl_feedback_none_not_counted(self):
        """hitl_feedback_count only counts records with non-None hitl_feedback."""
        store = FlywheelDataStore(config=_make_store_config())
        logs_with = _make_logs(10, hitl_feedback="great")
        logs_without = _make_logs(30, hitl_feedback=None)
        await store.store_logs(logs_with + logs_without)

        dataset = await store.create_dataset(
            dataset_id="ds-hitl-none",
            name="HITL None Test",
        )
        assert dataset.hitl_feedback_count == 10

    async def test_create_dataset_workload_types_populated(self):
        """workload_types list is populated from records."""
        store = FlywheelDataStore(config=_make_store_config())
        await store.store_logs(_make_logs(20, workload_type=WorkloadType.GOVERNANCE_REQUEST))
        await store.store_logs(_make_logs(20, workload_type=WorkloadType.IMPACT_SCORING))

        dataset = await store.create_dataset(
            dataset_id="ds-wt-list",
            name="Workload Types",
        )
        assert WorkloadType.GOVERNANCE_REQUEST.value in dataset.workload_types
        assert WorkloadType.IMPACT_SCORING.value in dataset.workload_types

    async def test_create_dataset_no_hitl_feedback_at_all(self):
        """hitl_feedback_count is 0 when no logs have feedback."""
        store = FlywheelDataStore(config=_make_store_config())
        await store.store_logs(_make_logs(40))
        dataset = await store.create_dataset(
            dataset_id="ds-no-hitl",
            name="No HITL",
        )
        assert dataset.hitl_feedback_count == 0

    async def test_create_dataset_overrides_existing(self):
        """Calling create_dataset twice with the same id overwrites the dataset."""
        store = FlywheelDataStore(config=_make_store_config())
        await store.store_logs(_make_logs(40))

        ds1 = await store.create_dataset(dataset_id="ds-overwrite", name="First")
        ds2 = await store.create_dataset(dataset_id="ds-overwrite", name="Second")

        assert store.get_dataset("ds-overwrite") is ds2
        assert store.get_dataset("ds-overwrite") is not ds1


# ---------------------------------------------------------------------------
# FlywheelDataStore.get_workload_distribution — tenant filter
# ---------------------------------------------------------------------------


class TestFlywheelGetWorkloadDistributionTenant:
    async def test_tenant_filter_isolates_distribution(self):
        store = FlywheelDataStore()
        await store.store_logs(
            _make_logs(5, tenant_id="ta", workload_type=WorkloadType.GOVERNANCE_REQUEST)
        )
        await store.store_logs(_make_logs(3, tenant_id="tb", workload_type=WorkloadType.AUDIT_LOG))
        dist = await store.get_workload_distribution(tenant_id="ta")
        assert dist.get(WorkloadType.GOVERNANCE_REQUEST.value, 0) == 5
        assert WorkloadType.AUDIT_LOG.value not in dist

    async def test_no_tenant_filter_returns_all(self):
        store = FlywheelDataStore()
        await store.store_logs(
            _make_logs(2, tenant_id="ta", workload_type=WorkloadType.GOVERNANCE_REQUEST)
        )
        await store.store_logs(
            _make_logs(3, tenant_id="tb", workload_type=WorkloadType.POLICY_EVALUATION)
        )
        dist = await store.get_workload_distribution()
        assert dist[WorkloadType.GOVERNANCE_REQUEST.value] == 2
        assert dist[WorkloadType.POLICY_EVALUATION.value] == 3


# ---------------------------------------------------------------------------
# FlywheelDataStore.create_sqlite_store — with explicit config
# ---------------------------------------------------------------------------


class TestFlywheelCreateSQLiteStoreWithConfig:
    async def test_create_sqlite_store_with_config_applied(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            config = _make_store_config(min_total_records=20)
            store = FlywheelDataStore.create_sqlite_store(db_path=path, config=config)
            assert isinstance(store.backend, SQLiteBackend)
            assert store.config.data_split.min_total_records == 20
            await store.close()
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# FlywheelDataStore — custom backend passed in constructor
# ---------------------------------------------------------------------------


class TestFlywheelDataStoreCustomBackend:
    async def test_custom_backend_used(self):
        custom_backend = InMemoryBackend()
        store = FlywheelDataStore(backend=custom_backend)
        assert store.backend is custom_backend

    async def test_custom_backend_receives_store_calls(self):
        custom_backend = InMemoryBackend()
        store = FlywheelDataStore(backend=custom_backend)
        logs = _make_logs(3)
        await store.store_logs(logs)
        count = await store.count_logs()
        assert count == 3

    async def test_custom_config_and_backend(self):
        config = _make_store_config(min_total_records=10)
        backend = InMemoryBackend()
        store = FlywheelDataStore(config=config, backend=backend)
        assert store.config.data_split.min_total_records == 10
        assert store.backend is backend


# ---------------------------------------------------------------------------
# _stratified_split — single-record workload groups
# ---------------------------------------------------------------------------


class TestStratifiedSplitEdgeCases:
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

    def test_single_record_per_workload_type(self):
        """When each workload type has only 1 record, all splits still have >= 1 total."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.1,
                random_seed=0,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        # Each workload type gets 1 record — very small groups
        records = self._make_records(1, "governance_request") + self._make_records(1, "audit_log")
        train, val, eval_ = store._stratified_split(records)
        total = len(train.records) + len(val.records) + len(eval_.records)
        assert total == 2

    def test_large_eval_size_relative_to_group(self):
        """eval_size fraction larger than group size still produces a valid split."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=80,  # 80% of total
                val_ratio=0.1,
                random_seed=1,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(10, "governance_request") + self._make_records(10, "audit_log")
        train, val, eval_ = store._stratified_split(records)
        total = len(train.records) + len(val.records) + len(eval_.records)
        assert total == 20

    def test_stratified_distribution_keys_match_workload_types(self):
        """workload_distribution keys in each split correspond to actual workload types."""
        store = FlywheelDataStore(config=_make_store_config())
        records = (
            self._make_records(15, "governance_request")
            + self._make_records(15, "audit_log")
            + self._make_records(15, "deliberation")
        )
        train, val, eval_ = store._stratified_split(records)
        for split in (train, val, eval_):
            for key in split.workload_distribution:
                assert key in {"governance_request", "audit_log", "deliberation"}


# ---------------------------------------------------------------------------
# _random_split — small record counts
# ---------------------------------------------------------------------------


class TestRandomSplitSmallCounts:
    def _make_records(self, n: int, workload_type: str = "governance_request") -> list[dict]:
        return [
            {
                "id": f"s-{i}",
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

    def test_three_records_does_not_crash(self):
        """_random_split with only 3 records runs without error."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=100,  # will be capped to len//3 = 1
                val_ratio=0.1,
                random_seed=42,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(3)
        train, val, eval_ = store._random_split(records)
        total = len(train.records) + len(val.records) + len(eval_.records)
        assert total == 3

    def test_zero_eval_size_when_records_less_than_three(self):
        """When len(shuffled)//3 == 0, eval_records is empty."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=100,
                val_ratio=0.5,
                random_seed=42,
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        # 2 records: len//3 == 0, so eval_size = min(100, 0) = 0
        records = self._make_records(2)
        train, val, eval_ = store._random_split(records)
        assert len(eval_.records) == 0
        assert len(train.records) + len(val.records) == 2

    def test_random_split_preserves_all_records(self):
        """No records are lost during random splitting."""
        config = FlywheelConfig(
            data_split=DataSplitConfig(
                min_total_records=10,
                eval_size=10,
                val_ratio=0.2,
                random_seed=None,  # no seed
                limit=1000,
            )
        )
        store = FlywheelDataStore(config=config)
        records = self._make_records(25)
        train, val, eval_ = store._random_split(records)
        assert len(train.records) + len(val.records) + len(eval_.records) == 25


# ---------------------------------------------------------------------------
# InMemoryBackend — all filters combined in single query
# ---------------------------------------------------------------------------


class TestInMemoryBackendCombinedFilters:
    async def test_all_filters_combined(self):
        """Query with workload_type + tenant_id + start_time + end_time + min_quality_score."""
        backend = InMemoryBackend()

        now = datetime.now(UTC)
        # Matches all filters
        match = _make_log(
            workload_type=WorkloadType.AUDIT_LOG,
            tenant_id="tx",
            quality_score=0.9,
            created_at=now,
        )
        # Wrong workload type
        wrong_wt = _make_log(
            workload_type=WorkloadType.GOVERNANCE_REQUEST,
            tenant_id="tx",
            quality_score=0.9,
            created_at=now,
        )
        # Wrong tenant
        wrong_tenant = _make_log(
            workload_type=WorkloadType.AUDIT_LOG,
            tenant_id="ty",
            quality_score=0.9,
            created_at=now,
        )
        # Outside time range
        old = _make_log(
            workload_type=WorkloadType.AUDIT_LOG,
            tenant_id="tx",
            quality_score=0.9,
            created_at=now - timedelta(days=5),
        )
        # Below quality threshold
        low_quality = _make_log(
            workload_type=WorkloadType.AUDIT_LOG,
            tenant_id="tx",
            quality_score=0.2,
            created_at=now,
        )
        await backend.store_logs([match, wrong_wt, wrong_tenant, old, low_quality])

        results = await backend.query_logs(
            workload_type=WorkloadType.AUDIT_LOG,
            tenant_id="tx",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            min_quality_score=0.5,
        )
        assert len(results) == 1
        assert results[0].tenant_id == "tx"
        assert results[0].workload_type == WorkloadType.AUDIT_LOG

    async def test_count_with_both_workload_and_tenant_filters(self):
        """InMemoryBackend.count_logs with workload_type + tenant_id together."""
        backend = InMemoryBackend()
        await backend.store_logs(
            _make_logs(4, workload_type=WorkloadType.DELIBERATION, tenant_id="t1")
        )
        await backend.store_logs(
            _make_logs(2, workload_type=WorkloadType.DELIBERATION, tenant_id="t2")
        )
        await backend.store_logs(
            _make_logs(3, workload_type=WorkloadType.AUDIT_LOG, tenant_id="t1")
        )
        count = await backend.count_logs(workload_type=WorkloadType.DELIBERATION, tenant_id="t1")
        assert count == 4


# ---------------------------------------------------------------------------
# Concrete FlywheelDataStoreBackend subclass — fulfils all abstract methods
# ---------------------------------------------------------------------------


class _FullConcreteBackend(FlywheelDataStoreBackend):
    """A minimal but complete implementation used purely for interface testing."""

    def __init__(self) -> None:
        self._data: list = []

    async def store_logs(self, logs):
        self._data.extend(logs)
        return len(logs)

    async def query_logs(
        self,
        workload_type=None,
        tenant_id=None,
        start_time=None,
        end_time=None,
        min_quality_score=0.0,
        limit=1000,
        offset=0,
    ):
        return self._data[offset : offset + limit]

    async def count_logs(self, workload_type=None, tenant_id=None):
        return len(self._data)

    async def get_workload_distribution(self, tenant_id=None):
        dist: dict[str, int] = {}
        for log in self._data:
            k = log.workload_type.value
            dist[k] = dist.get(k, 0) + 1
        return dist

    async def delete_old_logs(self, retention_days):
        return 0

    async def close(self):
        self._data.clear()


class TestConcreteBackendSubclass:
    async def test_can_instantiate_concrete_backend(self):
        backend = _FullConcreteBackend()
        assert isinstance(backend, FlywheelDataStoreBackend)

    async def test_store_and_count(self):
        backend = _FullConcreteBackend()
        logs = _make_logs(5)
        count = await backend.store_logs(logs)
        assert count == 5
        assert await backend.count_logs() == 5

    async def test_query_returns_stored(self):
        backend = _FullConcreteBackend()
        logs = _make_logs(3)
        await backend.store_logs(logs)
        result = await backend.query_logs()
        assert len(result) == 3

    async def test_close_clears(self):
        backend = _FullConcreteBackend()
        await backend.store_logs(_make_logs(2))
        await backend.close()
        assert await backend.count_logs() == 0

    async def test_delete_old_logs_returns_zero(self):
        backend = _FullConcreteBackend()
        deleted = await backend.delete_old_logs(30)
        assert deleted == 0

    async def test_get_workload_distribution(self):
        backend = _FullConcreteBackend()
        await backend.store_logs(_make_logs(3, workload_type=WorkloadType.AUDIT_LOG))
        dist = await backend.get_workload_distribution()
        assert dist[WorkloadType.AUDIT_LOG.value] == 3

    async def test_store_used_in_flywheel_store(self):
        """FlywheelDataStore works correctly with the concrete backend."""
        backend = _FullConcreteBackend()
        store = FlywheelDataStore(backend=backend)
        count = await store.store_logs(_make_logs(4))
        assert count == 4
        assert await store.count_logs() == 4


# ---------------------------------------------------------------------------
# DatasetSplit and FlywheelDataset — model_config from_attributes
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_dataset_split_from_attributes_model_config(self):
        """model_config 'from_attributes' is set; verify ORM init path."""
        split = DatasetSplit.model_validate(
            {"name": "train", "records": [], "workload_distribution": {}},
            from_attributes=False,
        )
        assert split.name == "train"

    def test_flywheel_dataset_from_attributes_model_config(self):
        """FlywheelDataset model_config 'from_attributes' allows dict validation."""
        ds = FlywheelDataset.model_validate(
            {"dataset_id": "d-1", "name": "My DS"},
            from_attributes=False,
        )
        assert ds.dataset_id == "d-1"
        assert ds.constitutional_hash == CONSTITUTIONAL_HASH

    def test_dataset_split_constitutional_hash_default(self):
        split = DatasetSplit(name="eval")
        assert split.constitutional_hash == CONSTITUTIONAL_HASH

    def test_flywheel_dataset_date_range_none_by_default(self):
        ds = FlywheelDataset(dataset_id="d-2", name="N")
        assert ds.date_range == (None, None)

    def test_flywheel_dataset_workload_types_list(self):
        ds = FlywheelDataset(
            dataset_id="d-3",
            name="N",
            workload_types=["governance_request", "audit_log"],
        )
        assert len(ds.workload_types) == 2


# ---------------------------------------------------------------------------
# SQLiteBackend — query with all filters combined
# ---------------------------------------------------------------------------


class TestSQLiteBackendAllFiltersCombined:
    async def test_query_all_filters(self):
        backend, path = _make_sqlite_backend()
        try:
            now = datetime.now(UTC)
            match = _make_log(
                workload_type=WorkloadType.IMPACT_SCORING,
                tenant_id="t-combined",
                quality_score=0.95,
                created_at=now,
            )
            old = _make_log(
                workload_type=WorkloadType.IMPACT_SCORING,
                tenant_id="t-combined",
                quality_score=0.95,
                created_at=now - timedelta(days=10),
            )
            low_q = _make_log(
                workload_type=WorkloadType.IMPACT_SCORING,
                tenant_id="t-combined",
                quality_score=0.1,
                created_at=now,
            )
            await backend.store_logs([match, old, low_q])

            results = await backend.query_logs(
                workload_type=WorkloadType.IMPACT_SCORING,
                tenant_id="t-combined",
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                min_quality_score=0.5,
            )
            assert len(results) == 1
            assert results[0].quality_score > 0.5
        finally:
            await backend.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# FlywheelDataStore — query_logs full delegation
# ---------------------------------------------------------------------------


class TestFlywheelQueryLogsDelegation:
    async def test_query_logs_all_params(self):
        """query_logs passes all params through to backend."""
        store = FlywheelDataStore()
        now = datetime.now(UTC)
        await store.store_logs(
            _make_logs(5, workload_type=WorkloadType.MACI_ENFORCEMENT, tenant_id="qd-t")
        )
        await store.store_logs(
            _make_logs(3, workload_type=WorkloadType.GOVERNANCE_REQUEST, tenant_id="other")
        )
        results = await store.query_logs(
            workload_type=WorkloadType.MACI_ENFORCEMENT,
            tenant_id="qd-t",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
            min_quality_score=0.5,
            limit=10,
            offset=0,
        )
        assert len(results) == 5


# ---------------------------------------------------------------------------
# SQLiteBackend._init_db — verify index creation does not fail on re-init
# ---------------------------------------------------------------------------


class TestSQLiteInitDB:
    def test_reinit_db_is_idempotent(self):
        """Calling _init_db twice (indices use IF NOT EXISTS) should not fail."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            backend = SQLiteBackend(db_path=path)
            # Call _init_db again — should be idempotent
            backend._init_db()
            assert backend._conn is not None
        finally:
            if backend._conn:
                backend._conn.close()
            os.unlink(path)

    def test_table_and_indices_created(self):
        """Verify governance_logs table and all four indices exist."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            backend = SQLiteBackend(db_path=path)
            conn = backend._conn
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='governance_logs'"
            )
            assert cursor.fetchone() is not None

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='governance_logs'"
            )
            index_names = {row[0] for row in cursor.fetchall()}
            assert "idx_workload_type" in index_names
            assert "idx_tenant_id" in index_names
            assert "idx_created_at" in index_names
            assert "idx_quality_score" in index_names
        finally:
            if backend._conn:
                backend._conn.close()
            os.unlink(path)


# ---------------------------------------------------------------------------
# FlywheelDataStore.cleanup_old_logs — delegates to backend
# ---------------------------------------------------------------------------


class TestFlywheelCleanupOldLogs:
    async def test_cleanup_delegates_retention_days(self):
        """cleanup_old_logs uses the config's log_retention_days."""
        store = FlywheelDataStore(config=FlywheelConfig(log_retention_days=7))
        old = _make_log(created_at=datetime.now(UTC) - timedelta(days=10))
        fresh = _make_log(created_at=datetime.now(UTC))
        await store.store_logs([old, fresh])
        deleted = await store.cleanup_old_logs()
        assert deleted == 1

    async def test_cleanup_no_old_logs(self):
        store = FlywheelDataStore(config=FlywheelConfig(log_retention_days=7))
        fresh = _make_log(created_at=datetime.now(UTC))
        await store.store_logs([fresh])
        deleted = await store.cleanup_old_logs()
        assert deleted == 0


# ---------------------------------------------------------------------------
# FlywheelDataStore.transaction — exception types at boundary
# ---------------------------------------------------------------------------


class TestTransactionContextManagerEdgeCases:
    async def test_transaction_does_not_swallow_key_error(self):
        """KeyError is NOT in the caught set — it propagates unchanged."""
        store = FlywheelDataStore()
        # The transaction catches (RuntimeError, ValueError, TypeError, OSError) and re-raises.
        # KeyError is not in that list, so it propagates as an unhandled exception too.
        with pytest.raises(KeyError):
            async with store.transaction():
                raise KeyError("unexpected key")

    async def test_transaction_yields_same_store_object_on_success(self):
        """On a successful block the yielded object is the store itself."""
        store = FlywheelDataStore()
        captured: list[FlywheelDataStore] = []
        async with store.transaction() as s:
            captured.append(s)
        assert captured[0] is store
