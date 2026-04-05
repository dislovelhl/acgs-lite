"""
Batch 12 coverage tests for enhanced_agent_bus modules.

Targets:
- enhanced_agent_bus.constitutional.storage_infra.persistence (PersistenceManager)
- enhanced_agent_bus.llm_adapters.openclaw_adapter (OpenClawAdapter)
- enhanced_agent_bus.observability.capacity_metrics.registry (metrics registry)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module 1: persistence
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
from enhanced_agent_bus.constitutional.storage_infra.persistence import PersistenceManager

# ---------------------------------------------------------------------------
# Module 2: openclaw_adapter
# ---------------------------------------------------------------------------
from enhanced_agent_bus.llm_adapters.base import (
    AdapterStatus,
    CostEstimate,
    HealthCheckResult,
    LLMMessage,
    LLMResponse,
    StreamingMode,
)
from enhanced_agent_bus.llm_adapters.config import OpenClawAdapterConfig
from enhanced_agent_bus.llm_adapters.openclaw_adapter import OpenClawAdapter

# ---------------------------------------------------------------------------
# Module 3: capacity_metrics.registry
# ---------------------------------------------------------------------------
from enhanced_agent_bus.observability.capacity_metrics.registry import (
    CacheLayer,
    CacheMissReason,
    PerformanceMetricsRegistry,
    ValidationResult,
    adaptive_threshold_timer,
    batch_overhead_timer,
    deliberation_layer_timer,
    get_performance_metrics,
    maci_enforcement_timer,
    opa_policy_timer,
    record_adaptive_threshold_decision,
    record_batch_processing_overhead,
    record_cache_miss,
    record_constitutional_validation,
    record_deliberation_layer_duration,
    record_maci_enforcement_latency,
    record_opa_policy_evaluation,
    record_z3_solver_latency,
    reset_performance_metrics,
    z3_solver_timer,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_version():
    """Build a minimal ConstitutionalVersion for testing."""
    from enhanced_agent_bus.constitutional.version_model import (
        ConstitutionalStatus,
        ConstitutionalVersion,
    )

    return ConstitutionalVersion(
        version_id="v-test-001",
        version="1.0.0",
        constitutional_hash="608508a9bd224290",
        content={"rules": ["be safe"]},
        status=ConstitutionalStatus.ACTIVE,
        metadata={"author": "test"},
        created_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
    )


def _make_amendment():
    """Build a minimal AmendmentProposal for testing."""
    from enhanced_agent_bus.constitutional.amendment_model import (
        AmendmentProposal,
        AmendmentStatus,
    )

    return AmendmentProposal(
        proposal_id="a-test-001",
        proposed_changes={"rule_add": "no harm"},
        justification="Improve safety substantially",
        proposer_agent_id="agent-42",
        target_version="1.0.0",
        new_version="1.1.0",
        status=AmendmentStatus.PROPOSED,
        impact_score=0.5,
        impact_factors={"semantic": 0.4},
        impact_recommendation="approve",
        requires_deliberation=True,
        governance_metrics_before={"compliance": 0.9},
        governance_metrics_after={"compliance": 0.95},
        approval_chain=[],
        rejection_reason=None,
        rollback_reason=None,
        metadata={"constitutional_hash": "608508a9bd224290"},
        created_at=datetime.now(UTC),
        reviewed_at=None,
        activated_at=None,
        rolled_back_at=None,
    )


def _fake_db_version():
    """Return a mock that looks like ConstitutionalVersionDB."""
    obj = MagicMock()
    obj.version_id = "v-test-001"
    obj.version = "1.0.0"
    obj.constitutional_hash = "608508a9bd224290"
    obj.content = {"rules": ["be safe"]}
    obj.predecessor_version = None
    obj.status = "active"
    obj.extra_metadata = {"author": "test"}
    obj.created_at = datetime.now(UTC)
    obj.activated_at = datetime.now(UTC)
    obj.deactivated_at = None
    return obj


def _fake_db_amendment():
    """Return a mock that looks like AmendmentProposalDB."""
    obj = MagicMock()
    obj.proposal_id = "a-test-001"
    obj.proposed_changes = {"rule_add": "no harm"}
    obj.justification = "Improve safety substantially"
    obj.proposer_agent_id = "agent-42"
    obj.target_version = "1.0.0"
    obj.new_version = "1.1.0"
    obj.status = "proposed"
    obj.impact_score = "0.5"
    obj.impact_factors = {"semantic": 0.4}
    obj.impact_recommendation = "approve"
    obj.requires_deliberation = "true"
    obj.governance_metrics_before = {"compliance": 0.9}
    obj.governance_metrics_after = {"compliance": 0.95}
    obj.approval_chain = []
    obj.rejection_reason = None
    obj.rollback_reason = None
    obj.extra_metadata = {"constitutional_hash": "608508a9bd224290"}
    obj.created_at = datetime.now(UTC)
    obj.reviewed_at = None
    obj.activated_at = None
    obj.rolled_back_at = None
    return obj


def _openclaw_config() -> OpenClawAdapterConfig:
    """Build an OpenClawAdapterConfig without hitting env vars."""
    return OpenClawAdapterConfig(
        model="anthropic/claude-opus-4-6",
        api_base="http://127.0.0.1:18790",
        gateway_url="ws://127.0.0.1:18789",
    )


# ===========================================================================
# 1. PersistenceManager tests
# ===========================================================================


class TestPersistenceManagerInit:
    def test_init_stores_config(self):
        cfg = StorageConfig(database_url="postgresql+asyncpg://localhost/test")
        pm = PersistenceManager(cfg)
        assert pm.config is cfg
        assert pm.engine is None


class TestPersistenceManagerNoEngine:
    """All methods should gracefully return defaults when engine is None."""

    @pytest.fixture()
    def pm(self):
        return PersistenceManager(StorageConfig())

    @pytest.mark.asyncio
    async def test_save_version_returns_false(self, pm):
        result = await pm.save_version(_make_version(), "tenant-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_version_returns_none(self, pm):
        result = await pm.get_version("v-1", "tenant-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_version_returns_false(self, pm):
        result = await pm.update_version(_make_version(), "tenant-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_save_amendment_returns_false(self, pm):
        result = await pm.save_amendment(_make_amendment(), "tenant-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_amendment_returns_none(self, pm):
        result = await pm.get_amendment("a-1", "tenant-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_versions_returns_empty(self, pm):
        result = await pm.list_versions("tenant-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_amendments_returns_empty(self, pm):
        amendments, total = await pm.list_amendments("tenant-1")
        assert amendments == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_active_version_returns_none(self, pm):
        result = await pm.get_active_version("tenant-1")
        assert result is None


class TestPersistenceManagerConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        pm = PersistenceManager(StorageConfig())
        mock_conn = AsyncMock()
        mock_conn.run_sync = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.create_async_engine",
            return_value=mock_engine,
        ):
            result = await pm.connect()

        assert result is True
        assert pm.engine is mock_engine

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        pm = PersistenceManager(StorageConfig())

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.create_async_engine",
            side_effect=ValueError("bad url"),
        ):
            result = await pm.connect()

        assert result is False
        assert pm.engine is None


class TestPersistenceManagerDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_with_engine(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = AsyncMock()

        await pm.disconnect()

        assert pm.engine is None

    @pytest.mark.asyncio
    async def test_disconnect_without_engine(self):
        pm = PersistenceManager(StorageConfig())
        await pm.disconnect()
        assert pm.engine is None


class TestPersistenceManagerSaveVersion:
    @pytest.mark.asyncio
    async def test_save_version_success(self):
        pm = PersistenceManager(StorageConfig())
        mock_engine = MagicMock()
        pm.engine = mock_engine

        mock_session = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()

            result = await pm.save_version(_make_version(), "tenant-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_save_version_error(self):
        pm = PersistenceManager(StorageConfig())
        mock_engine = MagicMock()
        pm.engine = mock_engine

        mock_session = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.add = MagicMock(side_effect=RuntimeError("db error"))

            result = await pm.save_version(_make_version(), "tenant-1")

        assert result is False


class TestPersistenceManagerGetVersion:
    @pytest.mark.asyncio
    async def test_get_version_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _fake_db_version()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_version("v-test-001", "tenant-1")

        assert result is not None
        assert result.version_id == "v-test-001"

    @pytest.mark.asyncio
    async def test_get_version_not_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_version("v-missing", "tenant-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_version_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("db down"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_version("v-test-001", "tenant-1")

        assert result is None


class TestPersistenceManagerUpdateVersion:
    @pytest.mark.asyncio
    async def test_update_version_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        db_v = _fake_db_version()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = db_v
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.update_version(_make_version(), "tenant-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_update_version_not_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.update_version(_make_version(), "tenant-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_update_version_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=TypeError("oops"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.update_version(_make_version(), "tenant-1")

        assert result is False


class TestPersistenceManagerSaveAmendment:
    @pytest.mark.asyncio
    async def test_save_amendment_success(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.add = MagicMock()
            mock_session.commit = AsyncMock()

            result = await pm.save_amendment(_make_amendment(), "tenant-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_save_amendment_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.add = MagicMock(side_effect=OSError("disk full"))

            result = await pm.save_amendment(_make_amendment(), "tenant-1")

        assert result is False


class TestPersistenceManagerGetAmendment:
    @pytest.mark.asyncio
    async def test_get_amendment_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _fake_db_amendment()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_amendment("a-test-001", "tenant-1")

        assert result is not None
        assert result.proposal_id == "a-test-001"

    @pytest.mark.asyncio
    async def test_get_amendment_not_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_amendment("a-missing", "tenant-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_amendment_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=ValueError("bad"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_amendment("a-test-001", "tenant-1")

        assert result is None


class TestPersistenceManagerListVersions:
    @pytest.mark.asyncio
    async def test_list_versions_success(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        db_v = _fake_db_version()
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [db_v]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.list_versions("tenant-1")

        assert len(result) == 1
        assert result[0].version_id == "v-test-001"

    @pytest.mark.asyncio
    async def test_list_versions_with_status_filter(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.list_versions("tenant-1", status="active")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_versions_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=OSError("timeout"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.list_versions("tenant-1")

        assert result == []


class TestPersistenceManagerListAmendments:
    @pytest.mark.asyncio
    async def test_list_amendments_success(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        db_a = _fake_db_amendment()
        mock_session = AsyncMock()

        # First execute returns count, second returns rows
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_rows_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [db_a]
        mock_rows_result.scalars.return_value = mock_scalars

        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_rows_result])

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            amendments, total = await pm.list_amendments("tenant-1")

        assert total == 1
        assert len(amendments) == 1

    @pytest.mark.asyncio
    async def test_list_amendments_with_status_and_proposer(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_rows_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_rows_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(side_effect=[mock_count_result, mock_rows_result])

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            amendments, total = await pm.list_amendments(
                "tenant-1", status="proposed", proposer_id="agent-42"
            )

        assert total == 0
        assert amendments == []

    @pytest.mark.asyncio
    async def test_list_amendments_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("oops"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            amendments, total = await pm.list_amendments("tenant-1")

        assert amendments == []
        assert total == 0


class TestPersistenceManagerGetActiveVersion:
    @pytest.mark.asyncio
    async def test_get_active_version_found(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _fake_db_version()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_active_version("tenant-1")

        assert result is not None
        assert result.version_id == "v-test-001"

    @pytest.mark.asyncio
    async def test_get_active_version_none(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_active_version("tenant-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_version_error(self):
        pm = PersistenceManager(StorageConfig())
        pm.engine = MagicMock()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=TypeError("bad"))

        with patch(
            "enhanced_agent_bus.constitutional.storage_infra.persistence.AsyncSession",
            return_value=mock_session,
        ):
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)

            result = await pm.get_active_version("tenant-1")

        assert result is None


class TestPersistenceManagerConverters:
    """Test the private _db_to_pydantic_* converters."""

    def test_db_to_pydantic_version(self):
        pm = PersistenceManager(StorageConfig())
        db_v = _fake_db_version()
        result = pm._db_to_pydantic_version(db_v)
        assert result.version_id == "v-test-001"
        assert result.version == "1.0.0"
        assert result.constitutional_hash == "608508a9bd224290"

    def test_db_to_pydantic_version_no_metadata(self):
        pm = PersistenceManager(StorageConfig())
        db_v = _fake_db_version()
        db_v.extra_metadata = None
        result = pm._db_to_pydantic_version(db_v)
        assert result.metadata == {}

    def test_db_to_pydantic_amendment(self):
        pm = PersistenceManager(StorageConfig())
        db_a = _fake_db_amendment()
        result = pm._db_to_pydantic_amendment(db_a)
        assert result.proposal_id == "a-test-001"
        assert result.impact_score == 0.5
        assert result.requires_deliberation is True

    def test_db_to_pydantic_amendment_no_impact_score(self):
        pm = PersistenceManager(StorageConfig())
        db_a = _fake_db_amendment()
        db_a.impact_score = None
        result = pm._db_to_pydantic_amendment(db_a)
        assert result.impact_score is None

    def test_db_to_pydantic_amendment_deliberation_false(self):
        pm = PersistenceManager(StorageConfig())
        db_a = _fake_db_amendment()
        db_a.requires_deliberation = "false"
        result = pm._db_to_pydantic_amendment(db_a)
        assert result.requires_deliberation is False


# ===========================================================================
# 2. OpenClawAdapter tests
# ===========================================================================


class TestOpenClawAdapterInit:
    def test_default_init(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        assert adapter.model == "anthropic/claude-opus-4-6"
        assert adapter.provider_name == "openclaw"
        assert adapter.streaming_mode == StreamingMode.SUPPORTED
        assert adapter.supports_function_calling is True

    def test_init_without_config_uses_default_model(self):
        with patch.object(
            OpenClawAdapterConfig,
            "from_environment",
            return_value=_openclaw_config(),
        ):
            adapter = OpenClawAdapter()
            assert adapter.model == "anthropic/claude-opus-4-6"

    def test_init_with_custom_model(self):
        with patch.object(
            OpenClawAdapterConfig,
            "from_environment",
            return_value=OpenClawAdapterConfig(
                model="openai/gpt-5.2",
                api_base="http://127.0.0.1:18790",
            ),
        ):
            adapter = OpenClawAdapter(model="openai/gpt-5.2")
            assert adapter.model == "openai/gpt-5.2"


class TestOpenClawAdapterPrepareMessages:
    def test_prepare_basic_messages(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
        ]
        result = adapter._prepare_messages(messages)
        assert len(result) == 2
        assert result[0] == {"role": "system", "content": "You are helpful"}
        assert result[1] == {"role": "user", "content": "Hello"}

    def test_prepare_messages_with_name(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        messages = [
            LLMMessage(role="user", content="Hi", name="alice"),
        ]
        result = adapter._prepare_messages(messages)
        assert result[0]["name"] == "alice"


class TestOpenClawAdapterGetClient:
    def test_get_client_creates_sync_client(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_openai_mod = MagicMock()
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            client = adapter._get_client()
            assert client is not None

    def test_get_client_reuses_cached(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        sentinel = MagicMock()
        adapter._client = sentinel
        assert adapter._get_client() is sentinel

    def test_get_client_uses_api_key_if_set(self):
        cfg = _openclaw_config()
        adapter = OpenClawAdapter(config=cfg, api_key="test-key-123")
        mock_openai_mod = MagicMock()
        mock_openai_mod.OpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            adapter._get_client()
            call_kwargs = mock_openai_mod.OpenAI.call_args
            assert call_kwargs[1]["api_key"] == "test-key-123"

    def test_get_client_fallback_key(self):
        cfg = _openclaw_config()
        adapter = OpenClawAdapter(config=cfg)
        mock_openai_mod = MagicMock()
        mock_openai_mod.OpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            adapter._get_client()
            call_kwargs = mock_openai_mod.OpenAI.call_args
            assert call_kwargs[1]["api_key"] == "openclaw-local"


class TestOpenClawAdapterGetAsyncClient:
    @pytest.mark.asyncio
    async def test_get_async_client_creates(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_openai_mod = MagicMock()
        mock_async_client = MagicMock()
        mock_openai_mod.AsyncOpenAI.return_value = mock_async_client

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            client = await adapter._get_async_client()
            assert client is not None

    @pytest.mark.asyncio
    async def test_get_async_client_reuses_cached(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        sentinel = MagicMock()
        adapter._async_client = sentinel
        result = await adapter._get_async_client()
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_get_async_client_uses_api_key(self):
        cfg = _openclaw_config()
        adapter = OpenClawAdapter(config=cfg, api_key="my-key")
        mock_openai_mod = MagicMock()
        mock_openai_mod.AsyncOpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            await adapter._get_async_client()
            call_kwargs = mock_openai_mod.AsyncOpenAI.call_args
            assert call_kwargs[1]["api_key"] == "my-key"

    @pytest.mark.asyncio
    async def test_get_async_client_fallback_key(self):
        cfg = _openclaw_config()
        adapter = OpenClawAdapter(config=cfg)
        mock_openai_mod = MagicMock()
        mock_openai_mod.AsyncOpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai_mod}):
            await adapter._get_async_client()
            call_kwargs = mock_openai_mod.AsyncOpenAI.call_args
            assert call_kwargs[1]["api_key"] == "openclaw-local"


class TestOpenClawAdapterComplete:
    def _mock_from_openai(self):
        """Return a fake LLMResponse for ResponseConverter mock."""
        from enhanced_agent_bus.llm_adapters.base import CompletionMetadata

        return LLMResponse(
            content="Hello back!",
            metadata=CompletionMetadata(model="test", provider="openclaw"),
        )

    def test_complete_success(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"raw": True}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        with patch(
            "enhanced_agent_bus.llm_adapters.openclaw_adapter.ResponseConverter.from_openai_response",
            return_value=self._mock_from_openai(),
        ):
            result = adapter.complete(messages)

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello back!"

    def test_complete_with_max_tokens_and_stop(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"raw": True}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        with patch(
            "enhanced_agent_bus.llm_adapters.openclaw_adapter.ResponseConverter.from_openai_response",
            return_value=self._mock_from_openai(),
        ):
            result = adapter.complete(messages, max_tokens=10, stop=["END"])

        assert result.content == "Hello back!"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 10
        assert call_kwargs["stop"] == ["END"]

    def test_complete_raises_on_error(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("gateway down")
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="test")]
        with pytest.raises(RuntimeError, match="gateway down"):
            adapter.complete(messages)


class TestOpenClawAdapterAcomplete:
    def _mock_from_openai(self, content="Async hello!"):
        from enhanced_agent_bus.llm_adapters.base import CompletionMetadata

        return LLMResponse(
            content=content,
            metadata=CompletionMetadata(model="test", provider="openclaw"),
        )

    @pytest.mark.asyncio
    async def test_acomplete_success(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"raw": True}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="Hello async")]
        with patch(
            "enhanced_agent_bus.llm_adapters.openclaw_adapter.ResponseConverter.from_openai_response",
            return_value=self._mock_from_openai(),
        ):
            result = await adapter.acomplete(messages)

        assert result.content == "Async hello!"

    @pytest.mark.asyncio
    async def test_acomplete_with_options(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"raw": True}

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="short")]
        with patch(
            "enhanced_agent_bus.llm_adapters.openclaw_adapter.ResponseConverter.from_openai_response",
            return_value=self._mock_from_openai("ok"),
        ):
            result = await adapter.acomplete(messages, max_tokens=5, stop=["DONE"], temperature=0.1)

        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_acomplete_raises_on_error(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=ConnectionError("refused"))
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="test")]
        with pytest.raises(ConnectionError):
            await adapter.acomplete(messages)


class TestOpenClawAdapterStream:
    def test_stream_yields_chunks(self):
        adapter = OpenClawAdapter(config=_openclaw_config())

        chunk1 = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="He"))])
        chunk2 = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="llo"))])
        chunk3 = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        chunks = list(adapter.stream(messages))

        assert chunks == ["He", "llo"]

    def test_stream_with_max_tokens_and_stop(self):
        adapter = OpenClawAdapter(config=_openclaw_config())

        chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk])
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        chunks = list(adapter.stream(messages, max_tokens=5, stop=["END"]))

        assert chunks == ["ok"]
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 5
        assert call_kwargs["stop"] == ["END"]
        assert call_kwargs["stream"] is True

    def test_stream_empty_choices(self):
        adapter = OpenClawAdapter(config=_openclaw_config())

        chunk = SimpleNamespace(choices=[])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk])
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hi")]
        chunks = list(adapter.stream(messages))
        assert chunks == []


class TestOpenClawAdapterAstream:
    @pytest.mark.asyncio
    async def test_astream_yields_chunks(self):
        adapter = OpenClawAdapter(config=_openclaw_config())

        chunk1 = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="A"))])
        chunk2 = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="B"))])

        async def mock_aiter():
            for c in [chunk1, chunk2]:
                yield c

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_aiter())
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="go")]
        chunks = []
        async for chunk in adapter.astream(messages):
            chunks.append(chunk)

        assert chunks == ["A", "B"]

    @pytest.mark.asyncio
    async def test_astream_with_options(self):
        adapter = OpenClawAdapter(config=_openclaw_config())

        chunk = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="x"))])

        async def mock_aiter():
            yield chunk

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_aiter())
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="go")]
        chunks = []
        async for c in adapter.astream(messages, max_tokens=3, stop=["."]):
            chunks.append(c)

        assert chunks == ["x"]


class TestOpenClawAdapterCountTokens:
    def test_count_tokens_with_tiktoken(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        messages = [
            LLMMessage(role="user", content="Hello world"),
        ]
        # tiktoken should be available; result should be positive
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_fallback_without_tiktoken(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        messages = [
            LLMMessage(role="user", content="Hello world test message"),
        ]
        with patch.dict("sys.modules", {"tiktoken": None}):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *args, **kwargs: (
                    (_ for _ in ()).throw(ImportError("no tiktoken"))
                    if name == "tiktoken"
                    else __builtins__.__import__(name, *args, **kwargs)  # type: ignore[attr-defined]
                ),
            ):
                count = adapter.count_tokens(messages)
                # Fallback: len(content) // 4
                assert count == len("Hello world test message") // 4


class TestOpenClawAdapterEstimateCost:
    def test_estimate_cost_known_model(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        cost = adapter.estimate_cost(prompt_tokens=1000, completion_tokens=500)
        assert isinstance(cost, CostEstimate)
        assert cost.total_cost_usd > 0
        assert cost.currency == "USD"
        assert "openclaw" in cost.pricing_model

    def test_estimate_cost_unknown_model(self):
        cfg = OpenClawAdapterConfig(
            model="unknown/model-x",
            api_base="http://127.0.0.1:18790",
        )
        adapter = OpenClawAdapter(config=cfg)
        cost = adapter.estimate_cost(prompt_tokens=1000, completion_tokens=500)
        assert cost.total_cost_usd == 0.0

    def test_estimate_cost_zero_tokens(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        cost = adapter.estimate_cost(prompt_tokens=0, completion_tokens=0)
        assert cost.total_cost_usd == 0.0


class TestOpenClawAdapterHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=[])
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert isinstance(result, HealthCheckResult)
        assert result.status == AdapterStatus.HEALTHY
        assert "reachable" in result.message

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        adapter = OpenClawAdapter(config=_openclaw_config())
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=ConnectionError("refused"))
        adapter._async_client = mock_client

        result = await adapter.health_check()
        assert result.status == AdapterStatus.UNHEALTHY
        assert "unreachable" in result.message


# ===========================================================================
# 3. Capacity Metrics Registry tests
# ===========================================================================


class TestRegistryReset:
    def test_reset_clears_all(self):
        reset_performance_metrics()
        # After reset, getting registry should create a fresh one
        reg = get_performance_metrics()
        assert isinstance(reg, PerformanceMetricsRegistry)


class TestZ3SolverMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_z3_solver_latency(self):
        record_z3_solver_latency(42.0, operation="solve")

    def test_record_z3_solver_latency_check_operation(self):
        record_z3_solver_latency(10.0, operation="check")

    def test_z3_solver_timer(self):
        with z3_solver_timer("optimize"):
            time.sleep(0.001)


class TestAdaptiveThresholdMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_adaptive_threshold_decision(self):
        record_adaptive_threshold_decision(5.0, decision_type="calibration")

    def test_adaptive_threshold_timer(self):
        with adaptive_threshold_timer("adjustment"):
            time.sleep(0.001)


class TestCacheMissMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_cache_miss_with_enum(self):
        record_cache_miss(CacheLayer.L1, CacheMissReason.EXPIRED)

    def test_record_cache_miss_with_string(self):
        record_cache_miss("L2", "not_found")

    def test_record_cache_miss_l3_evicted(self):
        record_cache_miss(CacheLayer.L3, CacheMissReason.EVICTED)


class TestBatchProcessingMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_batch_size_bucket_1_10(self):
        record_batch_processing_overhead(100.0, batch_size=5)

    def test_batch_size_bucket_11_50(self):
        record_batch_processing_overhead(200.0, batch_size=25)

    def test_batch_size_bucket_51_100(self):
        record_batch_processing_overhead(300.0, batch_size=75)

    def test_batch_size_bucket_101_500(self):
        record_batch_processing_overhead(400.0, batch_size=200)

    def test_batch_size_bucket_500_plus(self):
        record_batch_processing_overhead(500.0, batch_size=600)

    def test_batch_overhead_timer(self):
        with batch_overhead_timer(10):
            time.sleep(0.001)


class TestMACIEnforcementMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_maci_latency_few_samples(self):
        # Fewer than 10 samples: no P99 computed
        for i in range(5):
            record_maci_enforcement_latency(float(i), maci_role="EXECUTIVE")

    def test_record_maci_latency_enough_samples(self):
        # 10+ samples triggers P99 calculation
        for i in range(15):
            record_maci_enforcement_latency(float(i), maci_role="JUDICIAL")

    def test_maci_enforcement_timer(self):
        with maci_enforcement_timer("LEGISLATIVE"):
            time.sleep(0.001)


class TestConstitutionalValidationMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_validation_success_enum(self):
        record_constitutional_validation(ValidationResult.SUCCESS)

    def test_record_validation_failure_enum(self):
        record_constitutional_validation(ValidationResult.FAILURE, "strict")

    def test_record_validation_string(self):
        record_constitutional_validation("error", "lenient")

    def test_record_validation_hash_mismatch(self):
        record_constitutional_validation(ValidationResult.HASH_MISMATCH)

    def test_record_validation_timeout(self):
        record_constitutional_validation(ValidationResult.TIMEOUT)


class TestOPAPolicyMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_opa_evaluation(self):
        record_opa_policy_evaluation(15.0, policy_name="authz", decision="deny")

    def test_opa_policy_timer_default_decision(self):
        with opa_policy_timer("authz") as ctx:
            time.sleep(0.001)
        assert ctx["decision"] == "allow"

    def test_opa_policy_timer_custom_decision(self):
        with opa_policy_timer("rate_limit") as ctx:
            ctx["decision"] = "deny"
        assert ctx["decision"] == "deny"


class TestDeliberationMetrics:
    def setup_method(self):
        reset_performance_metrics()

    def test_record_deliberation_none_impact(self):
        record_deliberation_layer_duration(50.0, layer_type="hitl", impact_score=None)

    def test_record_deliberation_low_impact(self):
        record_deliberation_layer_duration(30.0, impact_score=0.1)

    def test_record_deliberation_medium_impact(self):
        record_deliberation_layer_duration(40.0, impact_score=0.4)

    def test_record_deliberation_high_impact(self):
        record_deliberation_layer_duration(60.0, impact_score=0.7)

    def test_record_deliberation_critical_impact(self):
        record_deliberation_layer_duration(100.0, impact_score=0.9)

    def test_deliberation_layer_timer(self):
        with deliberation_layer_timer("impact_scoring", impact_score=0.5):
            time.sleep(0.001)


class TestPerformanceMetricsRegistry:
    def setup_method(self):
        reset_performance_metrics()

    def test_singleton(self):
        r1 = get_performance_metrics()
        r2 = get_performance_metrics()
        assert r1 is r2

    def test_record_z3_latency(self):
        reg = get_performance_metrics()
        reg.record_z3_latency(10.0, "solve")

    def test_record_adaptive_threshold(self):
        reg = get_performance_metrics()
        reg.record_adaptive_threshold(5.0, "calibration")

    def test_record_cache_miss_via_registry(self):
        reg = get_performance_metrics()
        reg.record_cache_miss(CacheLayer.L1, CacheMissReason.NOT_FOUND)

    def test_record_batch_overhead_via_registry(self):
        reg = get_performance_metrics()
        reg.record_batch_overhead(1000.0, 50)

    def test_record_maci_latency_via_registry(self):
        reg = get_performance_metrics()
        reg.record_maci_latency(3.0, "EXECUTIVE")

    def test_record_validation_via_registry(self):
        reg = get_performance_metrics()
        reg.record_validation(ValidationResult.SUCCESS, "standard")

    def test_record_opa_evaluation_via_registry(self):
        reg = get_performance_metrics()
        reg.record_opa_evaluation(8.0, "access", "allow")

    def test_record_deliberation_via_registry(self):
        reg = get_performance_metrics()
        reg.record_deliberation(20.0, "consensus", 0.6)

    def test_constitutional_hash_default(self):
        reg = get_performance_metrics()
        assert isinstance(reg.constitutional_hash, str)
        assert len(reg.constitutional_hash) > 0


class TestEnumValues:
    """Verify enum members exist and have expected values."""

    def test_cache_layer_values(self):
        assert CacheLayer.L1.value == "L1"
        assert CacheLayer.L2.value == "L2"
        assert CacheLayer.L3.value == "L3"

    def test_cache_miss_reason_values(self):
        assert CacheMissReason.EXPIRED.value == "expired"
        assert CacheMissReason.EVICTED.value == "evicted"
        assert CacheMissReason.NOT_FOUND.value == "not_found"

    def test_validation_result_values(self):
        assert ValidationResult.SUCCESS.value == "success"
        assert ValidationResult.FAILURE.value == "failure"
        assert ValidationResult.ERROR.value == "error"
        assert ValidationResult.HASH_MISMATCH.value == "hash_mismatch"
        assert ValidationResult.TIMEOUT.value == "timeout"
