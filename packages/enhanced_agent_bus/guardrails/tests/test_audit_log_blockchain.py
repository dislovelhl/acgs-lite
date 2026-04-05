"""
Tests for audit_log.py with blockchain logging functionality.

Constitutional Hash: 608508a9bd224290
"""

import json
import os
import tempfile
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.guardrails.audit_log import (
    AuditLog,
    AuditLogConfig,
    BlockchainLedger,
)
from enhanced_agent_bus.guardrails.enums import GuardrailLayer, SafetyAction


@pytest.fixture
def temp_storage():
    """Provide temporary storage path for blockchain ledger."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def blockchain_ledger(temp_storage):
    """Provide initialized BlockchainLedger."""
    return BlockchainLedger(storage_path=temp_storage)


@pytest.fixture
def audit_log_config(temp_storage):
    """Provide AuditLogConfig with blockchain enabled."""
    return AuditLogConfig(
        enabled=True,
        log_to_blockchain=True,
        blockchain_storage_path=temp_storage,
    )


@pytest.fixture
def audit_log(audit_log_config):
    """Provide AuditLog with blockchain enabled."""
    return AuditLog(config=audit_log_config)


@pytest.fixture
def sample_audit_entry():
    """Provide sample audit entry data."""
    return {
        "trace_id": "test-trace-123",
        "timestamp": datetime.now(UTC).isoformat(),
        "layer": "INPUT_SANITIZER",
        "action": "ALLOW",
        "allowed": True,
        "violations": [],
        "processing_time_ms": 5.2,
        "metadata": {"test": True},
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }


class TestBlockchainLedger:
    """Test suite for BlockchainLedger class."""

    def test_genesis_block_creation(self, blockchain_ledger):
        """Ledger should initialize with genesis block."""
        assert len(blockchain_ledger.blocks) == 1
        genesis = blockchain_ledger.blocks[0]
        assert genesis["index"] == 0
        assert genesis["data"]["type"] == "genesis"
        assert genesis["previous_hash"] == "0" * 64
        assert genesis["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(genesis["hash"]) == 64

    async def test_add_entry_creates_new_block(self, blockchain_ledger, sample_audit_entry):
        """Adding entry should create new block with proper linkage."""
        genesis = blockchain_ledger.get_latest_block()

        block = await blockchain_ledger.add_entry(sample_audit_entry)

        assert block["index"] == 1
        assert block["data"] == sample_audit_entry
        assert block["previous_hash"] == genesis["hash"]
        assert block["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert len(block["hash"]) == 64
        assert len(blockchain_ledger.blocks) == 2

    async def test_chain_integrity_verification(self, blockchain_ledger, sample_audit_entry):
        """Chain should maintain cryptographic integrity."""
        await blockchain_ledger.add_entry(sample_audit_entry)
        await blockchain_ledger.add_entry({"test": "entry2"})

        assert blockchain_ledger._verify_chain_integrity() is True

    async def test_chain_integrity_failure_detection(self, blockchain_ledger, sample_audit_entry):
        """Chain should detect tampering."""
        await blockchain_ledger.add_entry(sample_audit_entry)
        await blockchain_ledger.add_entry({"test": "entry2"})

        block_1 = blockchain_ledger.blocks[1]
        original_hash = block_1["hash"]
        block_1["data"]["tampered"] = True
        block_1["hash"] = "tampered_hash"

        assert blockchain_ledger._verify_chain_integrity() is False

    async def test_persistence_to_disk(self, blockchain_ledger, sample_audit_entry):
        """Blocks should be persisted to disk."""
        await blockchain_ledger.add_entry(sample_audit_entry)

        ledger2 = BlockchainLedger(storage_path=blockchain_ledger.storage_path)

        assert len(ledger2.blocks) == 2
        assert ledger2.blocks[1]["data"] == sample_audit_entry

    async def test_get_block_by_index(self, blockchain_ledger, sample_audit_entry):
        """Should retrieve block by index."""
        await blockchain_ledger.add_entry(sample_audit_entry)

        block = blockchain_ledger.get_block_by_index(1)

        assert block is not None
        assert block["data"] == sample_audit_entry

    def test_get_block_by_index_nonexistent(self, blockchain_ledger):
        """Should return None for nonexistent index."""
        block = blockchain_ledger.get_block_by_index(999)
        assert block is None

    async def test_verify_entry_by_hash(self, blockchain_ledger, sample_audit_entry):
        """Should verify entry existence by hash."""
        block = await blockchain_ledger.add_entry(sample_audit_entry)

        assert blockchain_ledger.verify_entry(block["hash"]) is True
        assert blockchain_ledger.verify_entry("nonexistent_hash") is False

    def test_calculate_hash_consistency(self, blockchain_ledger):
        """Hash calculation should be deterministic."""
        block = {
            "index": 1,
            "timestamp": "2024-01-01T00:00:00",
            "data": {"test": "data"},
            "previous_hash": "0" * 64,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        hash1 = blockchain_ledger._calculate_block_hash(block)
        hash2 = blockchain_ledger._calculate_block_hash(block)

        assert hash1 == hash2
        assert len(hash1) == 64


class TestAuditLogWithBlockchain:
    """Test suite for AuditLog with blockchain integration."""

    async def test_process_creates_blockchain_entry(self, audit_log):
        """Processing audit entry should create blockchain block."""
        context = {
            "trace_id": "test-123",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 5.0,
            "metadata": {},
        }

        result = await audit_log.process(data="test", context=context)

        assert result.allowed is True

        blockchain_entries = audit_log.get_blockchain_entries()
        assert len(blockchain_entries) == 2
        assert blockchain_entries[1]["data"]["trace_id"] == "test-123"

    async def test_multiple_entries_chain_correctly(self, audit_log):
        """Multiple entries should form valid chain."""
        for i in range(3):
            context = {
                "trace_id": f"trace-{i}",
                "current_layer": GuardrailLayer.INPUT_SANITIZER,
                "action": SafetyAction.ALLOW,
                "allowed": True,
                "violations": [],
                "processing_time_ms": 1.0,
                "metadata": {},
            }
            await audit_log.process(data=f"test{i}", context=context)

        blockchain_entries = audit_log.get_blockchain_entries()
        assert len(blockchain_entries) == 4

        for i in range(1, len(blockchain_entries)):
            curr = blockchain_entries[i]
            prev = blockchain_entries[i - 1]
            assert curr["previous_hash"] == prev["hash"]

    async def test_blockchain_integrity_verification(self, audit_log):
        """Blockchain should maintain integrity across operations."""
        context = {
            "trace_id": "test",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 1.0,
            "metadata": {},
        }
        await audit_log.process(data="test", context=context)

        assert audit_log.verify_blockchain_integrity() is True

    async def test_get_blockchain_stats(self, audit_log):
        """Should return accurate blockchain statistics."""
        context = {
            "trace_id": "test",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 1.0,
            "metadata": {},
        }
        await audit_log.process(data="test", context=context)

        stats = audit_log.get_blockchain_stats()

        assert stats["enabled"] is True
        assert stats["block_count"] == 2
        assert stats["latest_block_index"] == 1
        assert "latest_block_hash" in stats
        assert "storage_path" in stats

    def test_get_blockchain_entries_returns_empty_when_disabled(self):
        """Should return empty list when blockchain disabled."""
        config = AuditLogConfig(enabled=True, log_to_blockchain=False)
        audit_log = AuditLog(config=config)

        entries = audit_log.get_blockchain_entries()
        assert entries == []

    def test_get_blockchain_stats_when_disabled(self):
        """Should indicate blockchain is disabled."""
        config = AuditLogConfig(enabled=True, log_to_blockchain=False)
        audit_log = AuditLog(config=config)

        stats = audit_log.get_blockchain_stats()

        assert stats["enabled"] is False
        assert stats["block_count"] == 0

    def test_constitutional_hash_in_blocks(self, audit_log):
        """All blocks should include constitutional hash."""
        entries = audit_log.get_blockchain_entries()
        assert len(entries) == 1

        genesis = entries[0]
        assert genesis["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAuditLogBlockchainEdgeCases:
    """Test edge cases and error handling."""

    async def test_process_without_blockchain_does_not_fail(self):
        """Processing should work without blockchain enabled."""
        config = AuditLogConfig(enabled=True, log_to_blockchain=False)
        audit_log = AuditLog(config=config)

        context = {
            "trace_id": "test",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 1.0,
            "metadata": {},
        }

        result = await audit_log.process(data="test", context=context)

        assert result.allowed is True
        assert len(audit_log.get_entries()) == 1

    async def test_audit_entry_still_logged_without_blockchain(self):
        """Regular audit logging should work without blockchain."""
        config = AuditLogConfig(enabled=True, log_to_blockchain=False)
        audit_log = AuditLog(config=config)

        context = {
            "trace_id": "test-123",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 5.0,
            "metadata": {"key": "value"},
        }

        await audit_log.process(data="test", context=context)

        entries = audit_log.get_entries()
        assert len(entries) == 1
        assert entries[0]["trace_id"] == "test-123"
        assert entries[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_custom_storage_path(self, temp_storage):
        """Should use custom storage path for blockchain ledger."""
        config = AuditLogConfig(
            enabled=True,
            log_to_blockchain=True,
            blockchain_storage_path=temp_storage,
        )
        audit_log = AuditLog(config=config)

        stats = audit_log.get_blockchain_stats()
        assert stats["storage_path"] == temp_storage


@pytest.mark.constitutional
def test_constitutional_hash_consistency():
    """Verify constitutional hash is correctly referenced."""
    from enhanced_agent_bus.guardrails.audit_log import CONSTITUTIONAL_HASH as ModuleHash

    assert ModuleHash == CONSTITUTIONAL_HASH


@pytest.mark.constitutional
class TestBlockchainConstitutionalCompliance:
    """Tests verifying constitutional compliance of blockchain logging."""

    def test_genesis_block_includes_constitutional_hash(self, blockchain_ledger):
        """Genesis block must include constitutional hash."""
        genesis = blockchain_ledger.blocks[0]
        assert genesis["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_all_blocks_include_constitutional_hash(self, blockchain_ledger):
        """All blocks must include constitutional hash."""
        await blockchain_ledger.add_entry({"test": "entry1"})
        await blockchain_ledger.add_entry({"test": "entry2"})

        for block in blockchain_ledger.blocks:
            assert block["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_audit_entries_include_constitutional_hash(self, audit_log):
        """Audit entries must include constitutional hash."""
        context = {
            "trace_id": "const-test",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 1.0,
            "metadata": {},
        }
        await audit_log.process(data="test", context=context)

        entries = audit_log.get_entries()
        assert entries[0]["constitutional_hash"] == CONSTITUTIONAL_HASH

        blockchain_entries = audit_log.get_blockchain_entries()
        assert blockchain_entries[1]["data"]["constitutional_hash"] == CONSTITUTIONAL_HASH
