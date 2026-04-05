"""
Comprehensive coverage tests for enhanced_agent_bus batch 5.

Targets:
  1. guardrails/audit_log.py  (BlockchainLedger, AuditLog, AuditLogConfig)
  2. multi_tenancy/db_repository.py  (DatabaseTenantRepository)
  3. caching.py  (cached decorator, RedisCacheClient, helpers)
  4. pqc_validators.py  (enforcement gates, validators, helpers)

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from enhanced_agent_bus._compat.security.pqc import UnsupportedPQCAlgorithmError

# ---------------------------------------------------------------------------
# 2. caching
# ---------------------------------------------------------------------------
from enhanced_agent_bus.caching import (
    RedisCacheClient,
    _async_lookup_cache,
    _async_store_cache,
    _make_cache_key,
    _record_cache_miss,
    _reset_cache_state,
    _sync_lookup_cache,
    _sync_store_cache,
    cache_key,
    cached,
    clear_cache,
    get_cache_stats,
    invalidate_pattern,
    set_cache_hash_mode,
)

# ---------------------------------------------------------------------------
# 1. guardrails/audit_log
# ---------------------------------------------------------------------------
from enhanced_agent_bus.guardrails.audit_log import (
    AuditLog,
    AuditLogConfig,
    BlockchainLedger,
)
from enhanced_agent_bus.guardrails.enums import GuardrailLayer, SafetyAction
from enhanced_agent_bus.guardrails.models import GuardrailResult, Violation

# ---------------------------------------------------------------------------
# 3. pqc_validators  (heavy mocking required for src.core.shared.security.pqc)
# ---------------------------------------------------------------------------


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_caching_state():
    """Reset module-level cache state before each test."""
    _reset_cache_state()
    yield
    _reset_cache_state()


@pytest.fixture
def tmp_ledger(tmp_path):
    """Return a temp file path for blockchain ledger."""
    return str(tmp_path / "ledger.json")


# ============================================================================
# BlockchainLedger tests
# ============================================================================


class TestBlockchainLedger:
    """Tests for BlockchainLedger."""

    def test_init_creates_genesis_block(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        assert len(ledger.blocks) == 1
        genesis = ledger.blocks[0]
        assert genesis["index"] == 0
        assert genesis["data"] == {"type": "genesis"}
        assert genesis["previous_hash"] == "0" * 64
        assert "hash" in genesis

    def test_init_creates_parent_dirs(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "ledger.json")
        ledger = BlockchainLedger(storage_path=nested)
        assert len(ledger.blocks) == 1
        assert os.path.exists(nested)

    def test_init_loads_existing_valid_ledger(self, tmp_ledger):
        ledger1 = BlockchainLedger(storage_path=tmp_ledger)
        # Create a second instance that should load from disk
        ledger2 = BlockchainLedger(storage_path=tmp_ledger)
        assert len(ledger2.blocks) == 1
        assert ledger2.blocks[0]["hash"] == ledger1.blocks[0]["hash"]

    def test_init_detects_tampered_ledger(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        original_hash = ledger.blocks[0]["hash"]
        # Tamper: add a second block with wrong previous_hash
        tampered_blocks = ledger.blocks.copy()
        tampered_blocks.append(
            {
                "index": 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {"tampered": True},
                "previous_hash": "wrong_previous_hash",
                "hash": "fake_hash",
            }
        )
        with open(tmp_ledger, "w") as f:
            json.dump(tampered_blocks, f)
        # Reload - should detect integrity failure via logger
        ledger2 = BlockchainLedger(storage_path=tmp_ledger)
        # The ledger loads the tampered chain but logs an error
        # Integrity check returns False for the tampered chain
        assert ledger2._verify_chain_integrity() is False

    def test_init_handles_corrupt_json(self, tmp_ledger):
        with open(tmp_ledger, "w") as f:
            f.write("not valid json {{{")
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        assert len(ledger.blocks) == 1  # recreated genesis

    @pytest.mark.asyncio
    async def test_add_entry(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        block = await ledger.add_entry({"event": "test_audit"})
        assert block["index"] == 1
        assert block["data"] == {"event": "test_audit"}
        assert block["previous_hash"] == ledger.blocks[0]["hash"]
        assert len(ledger.blocks) == 2

    @pytest.mark.asyncio
    async def test_add_multiple_entries(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        for i in range(5):
            await ledger.add_entry({"seq": i})
        assert len(ledger.blocks) == 6  # genesis + 5

    def test_verify_chain_integrity_valid(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        assert ledger._verify_chain_integrity() is True

    def test_verify_chain_integrity_broken_hash(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        # Manually append a bad block
        bad_block = {
            "index": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {},
            "previous_hash": "wrong",
            "hash": "wrong",
        }
        ledger.blocks.append(bad_block)
        assert ledger._verify_chain_integrity() is False

    def test_get_latest_block(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        latest = ledger.get_latest_block()
        assert latest["index"] == 0

    def test_get_block_by_index_found(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        block = ledger.get_block_by_index(0)
        assert block is not None
        assert block["index"] == 0

    def test_get_block_by_index_not_found(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        assert ledger.get_block_by_index(999) is None

    def test_verify_entry_found(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        genesis_hash = ledger.blocks[0]["hash"]
        assert ledger.verify_entry(genesis_hash) is True

    def test_verify_entry_not_found(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        assert ledger.verify_entry("nonexistent") is False

    def test_calculate_block_hash_deterministic(self, tmp_ledger):
        ledger = BlockchainLedger(storage_path=tmp_ledger)
        block = {
            "index": 0,
            "timestamp": "2025-01-01T00:00:00",
            "data": {"x": 1},
            "previous_hash": "abc",
        }
        h1 = ledger._calculate_block_hash(block)
        h2 = ledger._calculate_block_hash(block)
        assert h1 == h2

    def test_persist_chain_handles_oserror(self, tmp_path):
        ledger = BlockchainLedger(storage_path=str(tmp_path / "ledger.json"))
        # Make dir read-only to force OSError
        ledger.storage_path = "/proc/nonexistent/ledger.json"
        # Should not raise, just log
        ledger._persist_chain()


# ============================================================================
# AuditLogConfig tests
# ============================================================================


class TestAuditLogConfig:
    def test_defaults(self):
        cfg = AuditLogConfig()
        assert cfg.enabled is True
        assert cfg.retention_days == 90
        assert cfg.log_to_blockchain is False
        assert cfg.log_to_siem is False
        assert cfg.siem_providers == []
        assert cfg.siem_timeout_seconds == 30.0
        assert cfg.siem_fail_silent is True

    def test_custom_config(self):
        cfg = AuditLogConfig(
            enabled=False,
            retention_days=30,
            log_to_blockchain=True,
            blockchain_storage_path="/tmp/test.json",
        )
        assert cfg.enabled is False
        assert cfg.retention_days == 30
        assert cfg.log_to_blockchain is True


# ============================================================================
# AuditLog tests
# ============================================================================


class TestAuditLog:
    def test_get_layer(self):
        audit = AuditLog()
        assert audit.get_layer() == GuardrailLayer.AUDIT_LOG

    def test_init_default_config(self):
        audit = AuditLog()
        assert audit.config.enabled is True
        assert audit._blockchain_ledger is None

    def test_init_with_blockchain(self, tmp_ledger):
        cfg = AuditLogConfig(log_to_blockchain=True, blockchain_storage_path=tmp_ledger)
        audit = AuditLog(config=cfg)
        assert audit._blockchain_ledger is not None

    @pytest.mark.asyncio
    async def test_process_creates_entry(self):
        audit = AuditLog()
        context = {"trace_id": "t1", "allowed": True, "processing_time_ms": 5.0}
        result = await audit.process("test data", context)
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        entries = audit.get_entries()
        assert len(entries) == 1
        assert entries[0]["trace_id"] == "t1"

    @pytest.mark.asyncio
    async def test_process_disabled(self):
        cfg = AuditLogConfig(enabled=False)
        audit = AuditLog(config=cfg)
        await audit.process("data", {"trace_id": "t2"})
        assert len(audit.get_entries()) == 0

    @pytest.mark.asyncio
    async def test_process_with_violations(self):
        from enhanced_agent_bus.guardrails.enums import ViolationSeverity

        audit = AuditLog()
        v = Violation(
            layer=GuardrailLayer.INPUT_SANITIZER,
            violation_type="test",
            severity=ViolationSeverity.LOW,
            message="test violation",
        )
        context = {"trace_id": "t3", "violations": [v], "allowed": False}
        await audit.process("data", context)
        entries = audit.get_entries()
        assert len(entries[0]["violations"]) == 1

    @pytest.mark.asyncio
    async def test_process_with_layer_and_action_enums(self):
        audit = AuditLog()
        context = {
            "trace_id": "t4",
            "current_layer": GuardrailLayer.AUDIT_LOG,
            "action": SafetyAction.ALLOW,
            "allowed": True,
        }
        await audit.process("data", context)
        entry = audit.get_entries()[0]
        assert entry["layer"] == "audit_log"
        assert entry["action"] == "allow"

    @pytest.mark.asyncio
    async def test_process_with_blockchain(self, tmp_ledger):
        cfg = AuditLogConfig(log_to_blockchain=True, blockchain_storage_path=tmp_ledger)
        audit = AuditLog(config=cfg)
        await audit.process("data", {"trace_id": "t5"})
        # Blockchain should have genesis + 1
        assert len(audit._blockchain_ledger.blocks) == 2

    @pytest.mark.asyncio
    async def test_log_to_blockchain_no_ledger(self):
        audit = AuditLog()
        # Should not raise, just log warning
        await audit._log_to_blockchain({"test": True})

    @pytest.mark.asyncio
    async def test_log_to_siem_no_providers(self):
        audit = AuditLog()
        # Should return immediately
        await audit._log_to_siem({"test": True})

    @pytest.mark.asyncio
    async def test_log_to_siem_success(self):
        audit = AuditLog()
        provider = AsyncMock()
        provider.send_event = AsyncMock(return_value=True)
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        await audit._log_to_siem({"test": True})
        assert audit._siem_metrics["events_sent"] == 1

    @pytest.mark.asyncio
    async def test_log_to_siem_failure_silent(self):
        audit = AuditLog()
        provider = AsyncMock()
        provider.send_event = AsyncMock(return_value=False)
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        await audit._log_to_siem({"test": True})
        assert audit._siem_metrics["events_failed"] == 1

    @pytest.mark.asyncio
    async def test_log_to_siem_exception_silent(self):
        audit = AuditLog()
        provider = AsyncMock()
        provider.send_event = AsyncMock(side_effect=RuntimeError("boom"))
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        # siem_fail_silent=True by default, should not raise
        await audit._log_to_siem({"test": True})
        assert audit._siem_metrics["events_failed"] == 1

    @pytest.mark.asyncio
    async def test_log_to_siem_exception_not_silent(self):
        cfg = AuditLogConfig(siem_fail_silent=False)
        audit = AuditLog(config=cfg)
        provider = AsyncMock()
        provider.send_event = AsyncMock(side_effect=RuntimeError("boom"))
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        with pytest.raises(RuntimeError, match="SIEM logging failed"):
            await audit._log_to_siem({"test": True})

    @pytest.mark.asyncio
    async def test_log_to_siem_send_returns_false_not_silent(self):
        cfg = AuditLogConfig(siem_fail_silent=False)
        audit = AuditLog(config=cfg)
        provider = AsyncMock()
        provider.send_event = AsyncMock(return_value=False)
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        with pytest.raises(RuntimeError, match="SIEM logging failed"):
            await audit._log_to_siem({"test": True})

    def test_get_siem_metrics(self):
        audit = AuditLog()
        metrics = audit.get_siem_metrics()
        assert metrics == {"events_sent": 0, "events_failed": 0, "providers_configured": 0}

    @pytest.mark.asyncio
    async def test_health_check_siem_empty(self):
        audit = AuditLog()
        health = await audit.health_check_siem()
        assert health == {}

    @pytest.mark.asyncio
    async def test_health_check_siem_with_health_check(self):
        audit = AuditLog()
        provider = MagicMock()
        provider.health_check = AsyncMock(return_value={"status": "healthy"})
        provider.__class__.__name__ = "TestProvider"
        audit._siem_providers = [provider]

        health = await audit.health_check_siem()
        assert "TestProvider_0" in health
        assert health["TestProvider_0"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_siem_no_health_method(self):
        audit = AuditLog()
        provider = MagicMock(spec=[])  # no attributes
        provider.__class__.__name__ = "BasicProvider"
        audit._siem_providers = [provider]

        health = await audit.health_check_siem()
        key = "BasicProvider_0"
        assert health[key]["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_health_check_siem_exception(self):
        audit = AuditLog()
        provider = MagicMock()
        provider.health_check = AsyncMock(side_effect=RuntimeError("fail"))
        provider.__class__.__name__ = "FailProvider"
        audit._siem_providers = [provider]

        health = await audit.health_check_siem()
        assert health["FailProvider_0"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_get_metrics_empty(self):
        audit = AuditLog()
        metrics = await audit.get_metrics()
        assert metrics == {"total_entries": 0}

    @pytest.mark.asyncio
    async def test_get_metrics_with_entries(self):
        audit = AuditLog()
        # Process multiple entries
        await audit.process("d", {"trace_id": "a", "allowed": True, "processing_time_ms": 10})
        await audit.process("d", {"trace_id": "b", "allowed": False, "processing_time_ms": 20})

        metrics = await audit.get_metrics()
        assert metrics["total_entries"] == 2
        assert metrics["allowed_count"] == 1
        assert metrics["blocked_count"] == 1
        assert metrics["allowed_rate"] == 0.5
        assert metrics["avg_processing_time_ms"] == 15.0

    def test_get_entries_all(self):
        audit = AuditLog()
        audit._audit_entries = [{"trace_id": "a"}, {"trace_id": "b"}]
        entries = audit.get_entries()
        assert len(entries) == 2

    def test_get_entries_by_trace_id(self):
        audit = AuditLog()
        audit._audit_entries = [{"trace_id": "a"}, {"trace_id": "b"}, {"trace_id": "a"}]
        entries = audit.get_entries(trace_id="a")
        assert len(entries) == 2

    def test_get_entries_returns_copy(self):
        audit = AuditLog()
        audit._audit_entries = [{"trace_id": "x"}]
        entries = audit.get_entries()
        entries.append({"trace_id": "y"})
        assert len(audit._audit_entries) == 1  # original unchanged

    def test_get_blockchain_entries_no_ledger(self):
        audit = AuditLog()
        assert audit.get_blockchain_entries() == []

    def test_get_blockchain_entries_with_ledger(self, tmp_ledger):
        cfg = AuditLogConfig(log_to_blockchain=True, blockchain_storage_path=tmp_ledger)
        audit = AuditLog(config=cfg)
        entries = audit.get_blockchain_entries()
        assert len(entries) == 1  # genesis

    def test_verify_blockchain_integrity_no_ledger(self):
        audit = AuditLog()
        assert audit.verify_blockchain_integrity() is True

    def test_verify_blockchain_integrity_with_ledger(self, tmp_ledger):
        cfg = AuditLogConfig(log_to_blockchain=True, blockchain_storage_path=tmp_ledger)
        audit = AuditLog(config=cfg)
        assert audit.verify_blockchain_integrity() is True

    def test_get_blockchain_stats_no_ledger(self):
        audit = AuditLog()
        stats = audit.get_blockchain_stats()
        assert stats == {"enabled": False, "block_count": 0}

    def test_get_blockchain_stats_with_ledger(self, tmp_ledger):
        cfg = AuditLogConfig(log_to_blockchain=True, blockchain_storage_path=tmp_ledger)
        audit = AuditLog(config=cfg)
        stats = audit.get_blockchain_stats()
        assert stats["enabled"] is True
        assert stats["block_count"] == 1
        assert stats["latest_block_index"] == 0
        assert "latest_block_hash" in stats

    @patch("enhanced_agent_bus.guardrails.audit_log.AuditLog._initialize_siem_providers")
    def test_init_calls_siem_init_when_enabled(self, mock_init):
        cfg = AuditLogConfig(log_to_siem=True)
        AuditLog(config=cfg)
        mock_init.assert_called_once()

    def test_initialize_siem_providers_import_error(self):
        cfg = AuditLogConfig(log_to_siem=True, siem_providers=[{"provider_type": "splunk"}])
        with patch.dict("sys.modules", {"enhanced_agent_bus.guardrails.siem_providers": None}):
            audit = AuditLog.__new__(AuditLog)
            audit.config = cfg
            audit._audit_entries = []
            audit._blockchain_ledger = None
            audit._siem_providers = []
            audit._siem_metrics = {"events_sent": 0, "events_failed": 0, "providers_configured": 0}
            # This should handle the ImportError gracefully
            audit._initialize_siem_providers()

    def test_initialize_siem_providers_missing_fields(self):
        cfg = AuditLogConfig(
            log_to_siem=True,
            siem_providers=[
                {"provider_type": "", "endpoint_url": "", "auth_token": ""},  # all empty
            ],
        )
        audit = AuditLog.__new__(AuditLog)
        audit.config = cfg
        audit._audit_entries = []
        audit._blockchain_ledger = None
        audit._siem_providers = []
        audit._siem_metrics = {"events_sent": 0, "events_failed": 0, "providers_configured": 0}
        audit._initialize_siem_providers()
        assert len(audit._siem_providers) == 0

    def test_initialize_siem_providers_disabled_provider(self):
        cfg = AuditLogConfig(
            log_to_siem=True,
            siem_providers=[
                {
                    "enabled": False,
                    "provider_type": "splunk",
                    "endpoint_url": "http://x",
                    "auth_token": "tok",
                },
            ],
        )
        audit = AuditLog.__new__(AuditLog)
        audit.config = cfg
        audit._audit_entries = []
        audit._blockchain_ledger = None
        audit._siem_providers = []
        audit._siem_metrics = {"events_sent": 0, "events_failed": 0, "providers_configured": 0}
        audit._initialize_siem_providers()
        assert len(audit._siem_providers) == 0


# ============================================================================
# Caching tests
# ============================================================================


class TestCacheKey:
    def test_cache_key_deterministic(self):
        k1 = cache_key("a", "b", x=1)
        k2 = cache_key("a", "b", x=1)
        assert k1 == k2

    def test_cache_key_different_args(self):
        k1 = cache_key("a")
        k2 = cache_key("b")
        assert k1 != k2

    def test_make_cache_key(self):
        key = _make_cache_key("func", ("a",), {"b": 1})
        assert key.startswith("func:")


class TestSetCacheHashMode:
    def test_set_valid_mode(self):
        set_cache_hash_mode("sha256")
        # Should not raise

    def test_set_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid cache hash mode"):
            set_cache_hash_mode("invalid")

    def test_set_fast_mode_fallback(self):
        # fast_hash likely not available, should log warning but not raise
        set_cache_hash_mode("fast")
        # Reset to default
        set_cache_hash_mode("sha256")


class TestSyncCache:
    def test_sync_lookup_miss(self):
        hit, val = _sync_lookup_cache("nonexistent", time.time())
        assert hit is False
        assert val is None

    def test_sync_store_and_lookup(self):
        now = time.time()
        _sync_store_cache("key1", "value1", now + 100, 10)
        hit, val = _sync_lookup_cache("key1", now)
        assert hit is True
        assert val == "value1"

    def test_sync_lookup_expired(self):
        now = time.time()
        _sync_store_cache("key2", "val", now - 1, 10)  # already expired
        hit, val = _sync_lookup_cache("key2", now)
        assert hit is False

    def test_sync_store_eviction(self):
        now = time.time()
        _sync_store_cache("a", 1, now + 100, 1)  # max_size=1
        _sync_store_cache("b", 2, now + 100, 1)  # evicts "a"
        hit_a, _ = _sync_lookup_cache("a", now)
        hit_b, val_b = _sync_lookup_cache("b", now)
        assert hit_a is False
        assert hit_b is True
        assert val_b == 2


class TestAsyncCache:
    @pytest.mark.asyncio
    async def test_async_lookup_miss(self):
        hit, val = await _async_lookup_cache("nonexistent", time.time())
        assert hit is False
        assert val is None

    @pytest.mark.asyncio
    async def test_async_store_and_lookup(self):
        now = time.time()
        await _async_store_cache("ak1", "av1", now + 100, 10)
        hit, val = await _async_lookup_cache("ak1", now)
        assert hit is True
        assert val == "av1"

    @pytest.mark.asyncio
    async def test_async_lookup_expired(self):
        now = time.time()
        await _async_store_cache("ak2", "av2", now - 1, 10)
        hit, val = await _async_lookup_cache("ak2", now)
        assert hit is False

    @pytest.mark.asyncio
    async def test_async_eviction(self):
        now = time.time()
        await _async_store_cache("x", 1, now + 100, 1)
        await _async_store_cache("y", 2, now + 100, 1)
        hit_x, _ = await _async_lookup_cache("x", now)
        hit_y, val_y = await _async_lookup_cache("y", now)
        assert hit_x is False
        assert hit_y is True


class TestRecordCacheMiss:
    def test_increments_misses(self):
        stats_before = get_cache_stats()
        _record_cache_miss()
        stats_after = get_cache_stats()
        assert stats_after["misses"] == stats_before["misses"] + 1


class TestCacheStats:
    def test_get_cache_stats(self):
        stats = get_cache_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "evictions" in stats

    def test_clear_cache(self):
        now = time.time()
        _sync_store_cache("z", 1, now + 100, 10)
        count = clear_cache()
        assert count >= 1
        hit, _ = _sync_lookup_cache("z", now)
        assert hit is False

    def test_invalidate_pattern(self):
        now = time.time()
        _sync_store_cache("prefix:a", 1, now + 100, 100)
        _sync_store_cache("prefix:b", 2, now + 100, 100)
        _sync_store_cache("other:c", 3, now + 100, 100)
        removed = invalidate_pattern("prefix:")
        assert removed == 2
        hit, _ = _sync_lookup_cache("other:c", now)
        assert hit is True


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_async_cached_function(self):
        call_count = 0

        @cached(ttl_seconds=60, max_size=100)
        async def async_fn(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        r1 = await async_fn(5)
        r2 = await async_fn(5)
        assert r1 == 10
        assert r2 == 10
        assert call_count == 1  # second call should be cached

    def test_sync_cached_function(self):
        call_count = 0

        @cached(ttl_seconds=60, max_size=100)
        def sync_fn(x):
            nonlocal call_count
            call_count += 1
            return x + 1

        r1 = sync_fn(3)
        r2 = sync_fn(3)
        assert r1 == 4
        assert r2 == 4
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_async_cached_different_args(self):
        @cached(ttl_seconds=60)
        async def fn(x):
            return x

        r1 = await fn(1)
        r2 = await fn(2)
        assert r1 == 1
        assert r2 == 2


class TestRedisCacheClient:
    @pytest.mark.asyncio
    async def test_get_success(self):
        mock_conn = AsyncMock()
        mock_conn.get = AsyncMock(return_value=b"cached_value")

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        client = RedisCacheClient(mock_pool)
        result = await client.get("key1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_returns_none_on_miss(self):
        mock_conn = AsyncMock()
        mock_conn.get = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        client = RedisCacheClient(mock_pool)
        result = await client.get("miss")
        assert result is None

    def _make_error_pool(self, error):
        """Create a mock pool whose connection() context manager raises on __aenter__."""
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=error)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(return_value=mock_ctx)
        return mock_pool

    @staticmethod
    def _redis_conn_error():
        from redis.exceptions import ConnectionError as RCE

        return RCE("down")

    @staticmethod
    def _redis_error():
        from redis.exceptions import RedisError as RE

        return RE("redis error")

    @pytest.mark.asyncio
    async def test_get_connection_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_conn_error()))
        result = await client.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_error()))
        result = await client.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_connection_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_conn_error()))
        result = await client.set("key1", "val")
        assert result is False

    @pytest.mark.asyncio
    async def test_set_redis_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_error()))
        result = await client.set("key1", "val")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_connection_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_conn_error()))
        result = await client.delete("key1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_redis_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_error()))
        result = await client.delete("key1")
        assert result is False

    @pytest.mark.asyncio
    async def test_mget_connection_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_conn_error()))
        result = await client.mget(["a", "b"])
        assert result == [None, None]

    @pytest.mark.asyncio
    async def test_mget_redis_error(self):
        client = RedisCacheClient(self._make_error_pool(self._redis_error()))
        result = await client.mget(["a", "b"])
        assert result == [None, None]

    @pytest.mark.asyncio
    async def test_set_success(self):
        mock_conn = AsyncMock()
        mock_conn.setex = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        client = RedisCacheClient(mock_pool)
        result = await client.set("key1", "val", ttl=60)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_success(self):
        mock_conn = AsyncMock()
        mock_conn.delete = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        client = RedisCacheClient(mock_pool)
        result = await client.delete("key1")
        assert result is True

    @pytest.mark.asyncio
    async def test_mget_success(self):
        mock_conn = AsyncMock()
        mock_conn.mget = AsyncMock(return_value=[b"v1", None, b"v3"])

        mock_pool = MagicMock()
        mock_pool.connection = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        client = RedisCacheClient(mock_pool)
        result = await client.mget(["a", "b", "c"])
        assert len(result) == 3


# ============================================================================
# DatabaseTenantRepository tests
# ============================================================================


class TestDatabaseTenantRepository:
    """Tests for db_repository.py with fully mocked SQLAlchemy session."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        session.add_all = MagicMock()
        session.delete = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        with patch(
            "enhanced_agent_bus.multi_tenancy.db_repository.TieredCacheManager"
        ) as MockCache:
            mock_cache = MagicMock()
            mock_cache.initialize = AsyncMock(return_value=True)
            mock_cache.close = AsyncMock()
            mock_cache.get_async = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            mock_cache.delete = AsyncMock()
            MockCache.return_value = mock_cache

            from enhanced_agent_bus.multi_tenancy.db_repository import DatabaseTenantRepository

            repo = DatabaseTenantRepository(session=mock_session, enable_caching=True)
            return repo

    @pytest.fixture
    def repo_no_cache(self, mock_session):
        from enhanced_agent_bus.multi_tenancy.db_repository import DatabaseTenantRepository

        return DatabaseTenantRepository(session=mock_session, enable_caching=False)

    def _make_mock_orm(self, **overrides):
        """Create a mock TenantORM with reasonable defaults."""
        now = datetime.now(UTC)
        orm = MagicMock()
        orm.tenant_id = overrides.get("tenant_id", "tid-1")
        orm.name = overrides.get("name", "Test Tenant")
        orm.slug = overrides.get("slug", "test-tenant")
        orm.status = overrides.get("status", "active")
        orm.config = overrides.get("config", {})
        orm.quota = overrides.get("quota", {})
        orm.metadata_ = overrides.get("metadata_", {})
        orm.parent_tenant_id = overrides.get("parent_tenant_id", None)
        orm.created_at = overrides.get("created_at", now)
        orm.updated_at = overrides.get("updated_at", now)
        orm.activated_at = overrides.get("activated_at", None)
        orm.suspended_at = overrides.get("suspended_at", None)
        return orm

    def test_generate_tenant_cache_key(self, repo):
        key = repo._generate_tenant_cache_key("tid-1")
        assert key.startswith("tenant:id:")

    def test_generate_slug_cache_key(self, repo):
        key = repo._generate_slug_cache_key("my-slug")
        assert key.startswith("tenant:slug:")

    @pytest.mark.asyncio
    async def test_initialize_with_cache(self, repo):
        result = await repo.initialize()
        assert result is True

    @pytest.mark.asyncio
    async def test_initialize_no_cache(self, repo_no_cache):
        result = await repo_no_cache.initialize()
        assert result is True

    @pytest.mark.asyncio
    async def test_close(self, repo):
        await repo.close()
        # Should not raise

    @pytest.mark.asyncio
    async def test_close_no_cache(self, repo_no_cache):
        await repo_no_cache.close()

    @pytest.mark.asyncio
    async def test_invalidate_tenant_cache(self, repo):
        await repo._invalidate_tenant_cache("tid-1", "slug-1")
        # Should call delete twice (by id and by slug)

    @pytest.mark.asyncio
    async def test_invalidate_tenant_cache_no_slug(self, repo):
        await repo._invalidate_tenant_cache("tid-1")

    @pytest.mark.asyncio
    async def test_invalidate_cache_no_cache_manager(self, repo_no_cache):
        await repo_no_cache._invalidate_tenant_cache("tid-1", "slug-1")

    def test_orm_to_pydantic(self, repo):
        orm = self._make_mock_orm()
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.tenant_id == "tid-1"
        assert tenant.name == "Test Tenant"
        assert tenant.slug == "test-tenant"

    def test_orm_to_pydantic_none_status(self, repo):
        orm = self._make_mock_orm(status=None)
        tenant = repo._orm_to_pydantic(orm)
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        assert tenant.status == TenantStatus.PENDING

    def test_pydantic_to_orm(self, repo):
        from enhanced_agent_bus.multi_tenancy.models import Tenant, TenantConfig, TenantStatus

        tenant = Tenant(
            tenant_id="tid-2",
            name="T2",
            slug="t2-slug",
            status=TenantStatus.ACTIVE,
            config=TenantConfig(),
        )
        with patch("enhanced_agent_bus.multi_tenancy.db_repository.TenantORM") as MockORM:
            MockORM.return_value = MagicMock()
            orm = repo._pydantic_to_orm(tenant)
            MockORM.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_slug(self, repo, mock_session):
        # Simulate existing slug
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # existing
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="already exists"):
            await repo.create_tenant(name="Test", slug="existing-slug")

    @pytest.mark.asyncio
    async def test_create_tenant_success(self, mock_session):
        """Test create_tenant by patching TenantORM at the module level."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.refresh = AsyncMock()

        mock_orm_instance = self._make_mock_orm(name="New", slug="new-slug")

        with (
            patch(
                "enhanced_agent_bus.multi_tenancy.db_repository.TenantORM",
                return_value=mock_orm_instance,
            ) as MockORM,
            patch("enhanced_agent_bus.multi_tenancy.db_repository.select") as mock_select,
            patch("enhanced_agent_bus.multi_tenancy.db_repository.TieredCacheManager") as MockCache,
        ):
            mock_select.return_value = MagicMock(where=MagicMock(return_value=MagicMock()))
            mock_cache = MagicMock()
            mock_cache.set = AsyncMock()
            mock_cache.get_async = AsyncMock(return_value=None)
            mock_cache.delete = AsyncMock()
            mock_cache.initialize = AsyncMock(return_value=True)
            mock_cache.close = AsyncMock()
            MockCache.return_value = mock_cache

            from enhanced_agent_bus.multi_tenancy.db_repository import DatabaseTenantRepository

            repo = DatabaseTenantRepository(session=mock_session, enable_caching=True)
            tenant = await repo.create_tenant(name="New", slug="new-slug")
            assert tenant.name == "New"

    @pytest.mark.asyncio
    async def test_get_tenant_cache_hit(self, repo):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        cached_data = {
            "tenant_id": "tid-cached",
            "name": "Cached",
            "slug": "cached-slug",
            "status": TenantStatus.ACTIVE,
            "config": {},
            "quota": {},
            "metadata": {},
            "parent_tenant_id": "",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        repo._tenant_cache.get_async = AsyncMock(return_value=cached_data)

        tenant = await repo.get_tenant("tid-cached")
        assert tenant is not None
        assert tenant.tenant_id == "tid-cached"

    @pytest.mark.asyncio
    async def test_get_tenant_cache_miss_db_hit(self, repo, mock_session):
        repo._tenant_cache.get_async = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_orm = self._make_mock_orm(tenant_id="tid-db")
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("tid-db")
        assert tenant is not None
        assert tenant.tenant_id == "tid-db"

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, repo, mock_session):
        repo._tenant_cache.get_async = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant("nonexistent")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_cache_hit(self, repo):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        cached_data = {
            "tenant_id": "tid-s",
            "name": "S",
            "slug": "s-slug",
            "status": TenantStatus.ACTIVE,
            "config": {},
            "quota": {},
            "metadata": {},
            "parent_tenant_id": "",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        repo._tenant_cache.get_async = AsyncMock(return_value=cached_data)

        tenant = await repo.get_tenant_by_slug("s-slug")
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_not_found(self, repo, mock_session):
        repo._tenant_cache.get_async = AsyncMock(return_value=None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant_by_slug("missing")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_list_tenants(self, repo, mock_session):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self._make_mock_orm()]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants()
        assert len(tenants) == 1

    @pytest.mark.asyncio
    async def test_list_tenants_with_status_filter(self, repo, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants(status=TenantStatus.ACTIVE)
        assert tenants == []

    @pytest.mark.asyncio
    async def test_list_tenants_with_offset(self, repo, mock_session):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        tenants = await repo.list_tenants(offset=10, limit=5)
        assert tenants == []

    @pytest.mark.asyncio
    async def test_activate_tenant_found(self, repo, mock_session):
        mock_orm = self._make_mock_orm(status="pending")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.activate_tenant("tid-1")
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_activate_tenant_not_found(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.activate_tenant("missing")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_suspend_tenant_found(self, repo, mock_session):
        mock_orm = self._make_mock_orm()
        mock_orm.metadata_ = {}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.suspend_tenant("tid-1", reason="policy violation")
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_suspend_tenant_not_found(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.suspend_tenant("missing")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_suspend_tenant_no_reason(self, repo, mock_session):
        mock_orm = self._make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.suspend_tenant("tid-1")
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_update_tenant_config(self, repo, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig

        mock_orm = self._make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        new_config = TenantConfig(cache_ttl_seconds=600)
        tenant = await repo.update_tenant_config("tid-1", new_config)
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_update_tenant_config_not_found(self, repo, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant_config("missing", TenantConfig())
        assert tenant is None

    @pytest.mark.asyncio
    async def test_update_tenant_quota(self, repo, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantQuota

        mock_orm = self._make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant_quota("tid-1", TenantQuota(max_agents=200))
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_update_tenant_quota_not_found(self, repo, mock_session):
        from enhanced_agent_bus.multi_tenancy.models import TenantQuota

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant_quota("missing", TenantQuota())
        assert tenant is None

    @pytest.mark.asyncio
    async def test_update_tenant_name_and_metadata(self, repo, mock_session):
        mock_orm = self._make_mock_orm()
        mock_orm.metadata_ = {"existing": "data"}
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant("tid-1", name="New Name", metadata={"new": "val"})
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant("missing", name="X")
        assert tenant is None

    @pytest.mark.asyncio
    async def test_update_tenant_no_changes(self, repo, mock_session):
        mock_orm = self._make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.update_tenant("tid-1")
        assert tenant is not None

    @pytest.mark.asyncio
    async def test_delete_tenant_found(self, repo, mock_session):
        mock_orm = self._make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        deleted = await repo.delete_tenant("tid-1")
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_tenant_not_found(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        deleted = await repo.delete_tenant("missing")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_get_tenant_count(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        count = await repo.get_tenant_count()
        assert count == 42

    @pytest.mark.asyncio
    async def test_get_tenant_count_none(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        count = await repo.get_tenant_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_active_tenant_count(self, repo, mock_session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_session.execute.return_value = mock_result

        count = await repo.get_active_tenant_count()
        assert count == 10

    @pytest.mark.asyncio
    async def test_get_children(self, repo, mock_session):
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self._make_mock_orm(tenant_id="child-1")]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        children = await repo.get_children("parent-1")
        assert len(children) == 1

    @pytest.mark.asyncio
    async def test_create_tenants_bulk(self, repo, mock_session):
        with patch("enhanced_agent_bus.multi_tenancy.db_repository.TenantORM") as MockORM:
            mock_orm = self._make_mock_orm()
            MockORM.return_value = mock_orm

            tenants_data = [
                {"name": "T1", "slug": "t1-slug"},
                {"name": "T2", "slug": "t2-slug"},
            ]
            tenants = await repo.create_tenants_bulk(tenants_data)
            assert len(tenants) == 2

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_db_hit(self, repo, mock_session):
        repo._tenant_cache.get_async = AsyncMock(return_value=None)
        mock_orm = self._make_mock_orm(tenant_id="tid-slug", slug="found-slug")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        mock_session.execute.return_value = mock_result

        tenant = await repo.get_tenant_by_slug("found-slug")
        assert tenant is not None
        assert tenant.tenant_id == "tid-slug"


# ============================================================================
# PQC Validators tests
# ============================================================================


class TestPqcValidatorsHelper:
    """Tests for the lightweight PqcValidators helper class."""

    def test_import(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v._constitutional_hash is not None

    def test_process_valid_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process("hello") == "hello"

    def test_process_none(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(None) is None

    def test_process_non_string(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators()
        assert v.process(123) is None  # type: ignore[arg-type]

    def test_custom_constitutional_hash(self):
        from enhanced_agent_bus.pqc_validators import PqcValidators

        v = PqcValidators(constitutional_hash="custom_hash")
        assert v._constitutional_hash == "custom_hash"


class TestExtractMessageContent:
    def test_extract_excludes_signature(self):
        from enhanced_agent_bus.pqc_validators import _extract_message_content

        data = {"a": 1, "b": 2, "signature": "sig"}
        content = _extract_message_content(data)
        parsed = json.loads(content.decode())
        assert "signature" not in parsed
        assert parsed["a"] == 1

    def test_extract_empty_data(self):
        from enhanced_agent_bus.pqc_validators import _extract_message_content

        content = _extract_message_content({})
        assert content == b"{}"


class TestIsSelfValidation:
    def test_self_validation_by_output_author(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-x", {"output_author": "agent-1"}) is True

    def test_no_self_validation_different_author(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-x", {"output_author": "agent-2"}) is False

    def test_self_validation_by_target_id_contains_agent(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "agent-1-output-5", {}) is True

    def test_no_self_validation(self):
        from enhanced_agent_bus.pqc_validators import _is_self_validation

        assert _is_self_validation("agent-1", "output-5", {}) is False


class TestCheckEnforcementForCreate:
    @pytest.mark.asyncio
    async def test_migration_context_returns_early(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        # Should not raise regardless of key_type
        await check_enforcement_for_create(
            key_type=None,
            key_algorithm=None,
            enforcement_config=config,
            migration_context=True,
        )

    @pytest.mark.asyncio
    async def test_non_strict_mode_returns_early(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_create(
            key_type=None,
            key_algorithm=None,
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_mode_no_key_type_raises(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")

        with pytest.raises(Exception, match="PQC key required"):
            await check_enforcement_for_create(
                key_type=None,
                key_algorithm=None,
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_mode_classical_key_raises(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")

        with pytest.raises(Exception, match="not accepted"):
            await check_enforcement_for_create(
                key_type="classical",
                key_algorithm="ed25519",
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_mode_valid_pqc_key(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")

        # ML-DSA-65 should be in the approved list
        await check_enforcement_for_create(
            key_type="pqc",
            key_algorithm="ML-DSA-65",
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_mode_unsupported_pqc_algorithm(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_create

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")

        with pytest.raises(UnsupportedPQCAlgorithmError):
            await check_enforcement_for_create(
                key_type="pqc",
                key_algorithm="UNSUPPORTED-ALGO",
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_get_mode_safe_fallback_on_error(self):
        from enhanced_agent_bus.pqc_validators import _get_mode_safe

        config = AsyncMock()
        config.get_mode = AsyncMock(side_effect=RuntimeError("config unavailable"))

        mode = await _get_mode_safe(config)
        assert mode == "strict"


class TestCheckEnforcementForUpdate:
    @pytest.mark.asyncio
    async def test_migration_context_returns_early(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
            migration_context=True,
        )

    @pytest.mark.asyncio
    async def test_non_strict_mode_returns_early(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="permissive")
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
        )

    @pytest.mark.asyncio
    async def test_strict_mode_classical_key_raises(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")

        with pytest.raises(Exception, match="must be migrated"):
            await check_enforcement_for_update(
                existing_key_type="classical",
                enforcement_config=config,
            )

    @pytest.mark.asyncio
    async def test_strict_mode_pqc_key_ok(self):
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_update

        config = AsyncMock()
        config.get_mode = AsyncMock(return_value="strict")
        await check_enforcement_for_update(
            existing_key_type="pqc",
            enforcement_config=config,
        )


class TestValidateConstitutionalHashPqc:
    @pytest.mark.asyncio
    async def test_missing_constitutional_hash(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(data={})
        assert result.valid is False
        assert any("Missing" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_hash_mismatch(self):
        from enhanced_agent_bus.pqc_validators import validate_constitutional_hash_pqc

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": "wrong_hash_value"},
            expected_hash="608508a9bd224290",
        )
        assert result.valid is False
        assert any("mismatch" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_hash_no_signature(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_constitutional_hash_pqc,
        )

        result = await validate_constitutional_hash_pqc(
            data={"constitutional_hash": CONSTITUTIONAL_HASH},
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_hash_with_signature_dict_no_inner_sig_no_pqc(self):
        """Signature dict present but no 'signature' key inside -> no classical verification."""
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_constitutional_hash_pqc,
        )

        result = await validate_constitutional_hash_pqc(
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "signature": {"version": "v1", "other": "data"},
            },
            pqc_config=None,
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_hash_with_non_dict_signature_no_pqc(self):
        from enhanced_agent_bus.pqc_validators import (
            CONSTITUTIONAL_HASH,
            validate_constitutional_hash_pqc,
        )

        result = await validate_constitutional_hash_pqc(
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "signature": "just_a_string",
            },
            pqc_config=None,
        )
        assert result.valid is True


class TestValidateMaciRecordPqc:
    @pytest.mark.asyncio
    async def test_missing_required_fields(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(record={})
        assert result.valid is False
        assert any("agent_id" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_constitutional_hash_mismatch(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "a1",
                "action": "validate",
                "timestamp": "2025-01-01",
                "constitutional_hash": "wrong",
            },
            expected_hash="608508a9bd224290",
        )
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_self_validation_detected(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2025-01-01",
                "target_output_id": "output-1",
                "output_author": "agent-1",
            },
        )
        assert result.valid is False
        assert any("Self-validation" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_valid_maci_record_no_pqc(self):
        from enhanced_agent_bus.pqc_validators import validate_maci_record_pqc

        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2025-01-01",
            },
        )
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_valid_maci_record_with_pqc_metadata(self):
        from enhanced_agent_bus.pqc_validators import PQCConfig, validate_maci_record_pqc

        config = PQCConfig(pqc_enabled=False)
        result = await validate_maci_record_pqc(
            record={
                "agent_id": "agent-1",
                "action": "validate",
                "timestamp": "2025-01-01",
            },
            pqc_config=config,
        )
        assert result.valid is True
        assert result.pqc_metadata is not None
        assert result.pqc_metadata.verification_mode == "classical_only"


class TestSupportedPqcAlgorithms:
    def test_algorithms_list_not_empty(self):
        from enhanced_agent_bus.pqc_validators import SUPPORTED_PQC_ALGORITHMS

        assert len(SUPPORTED_PQC_ALGORITHMS) > 0

    def test_known_algorithms_present(self):
        from enhanced_agent_bus.pqc_validators import SUPPORTED_PQC_ALGORITHMS

        # At minimum the fallback list should contain ML-DSA variants
        assert any("ML-DSA" in alg for alg in SUPPORTED_PQC_ALGORITHMS)
