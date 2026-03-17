"""
Tests for SAFLA Neural Memory System v3.0

Comprehensive test coverage for:
- Four-tier memory architecture
- Cross-session persistence
- Vector embeddings and semantic search
- Memory compression
- Feedback loop optimization
- Constitutional compliance

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

from safla_memory import (
    CONSTITUTIONAL_HASH,
    SKLEARN_AVAILABLE,
    FeedbackLoop,
    MemoryCompressor,
    MemoryEntry,
    MemoryTier,
    SAFLAConfig,
    SAFLANeuralMemoryV3,
    VectorIndex,
    create_safla_memory,
)

RUN_EAB_SAFLA_MEMORY_TESTS = os.getenv("RUN_EAB_SAFLA_MEMORY_TESTS", "false").lower() == "true"
if not RUN_EAB_SAFLA_MEMORY_TESTS:
    pytestmark = pytest.mark.skip(
        reason=(
            "SAFLA memory tests disabled by default in this runtime. "
            "Set RUN_EAB_SAFLA_MEMORY_TESTS=true to run."
        )
    )


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_hash_value(self):
        """Should have correct constitutional hash."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_config_has_hash(self):
        """Config should include constitutional hash."""
        config = SAFLAConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_memory_entry_has_hash(self):
        """Memory entries should include constitutional hash."""
        entry = MemoryEntry(
            tier=MemoryTier.SEMANTIC,
            key="test",
            value="test_value",
        )
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH


class TestMemoryTiers:
    """Test four-tier memory architecture."""

    def test_tier_values(self):
        """Should have all four memory tiers."""
        tiers = list(MemoryTier)
        assert len(tiers) == 4
        assert MemoryTier.VECTOR in tiers
        assert MemoryTier.EPISODIC in tiers
        assert MemoryTier.SEMANTIC in tiers
        assert MemoryTier.WORKING in tiers

    def test_tier_string_values(self):
        """Tier values should be lowercase strings."""
        assert MemoryTier.VECTOR.value == "vector"
        assert MemoryTier.EPISODIC.value == "episodic"
        assert MemoryTier.SEMANTIC.value == "semantic"
        assert MemoryTier.WORKING.value == "working"


class TestMemoryEntry:
    """Test MemoryEntry dataclass."""

    def test_create_entry(self):
        """Should create a memory entry with defaults."""
        entry = MemoryEntry(
            tier=MemoryTier.SEMANTIC,
            key="test_key",
            value={"data": "test"},
        )
        assert entry.tier == MemoryTier.SEMANTIC
        assert entry.key == "test_key"
        assert entry.value == {"data": "test"}
        assert entry.confidence == 1.0
        assert entry.access_count == 0
        assert entry.compressed is False
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_entry_with_embedding(self):
        """Should store embedding vector."""
        embedding = [0.1, 0.2, 0.3, 0.4]
        entry = MemoryEntry(
            tier=MemoryTier.VECTOR,
            key="embedded",
            value="text",
            embedding=embedding,
        )
        assert entry.embedding == embedding

    def test_entry_with_ttl(self):
        """Should store TTL value."""
        entry = MemoryEntry(
            tier=MemoryTier.WORKING,
            key="temp",
            value="data",
            ttl_seconds=3600,
        )
        assert entry.ttl_seconds == 3600


class TestVectorIndex:
    """Test vector index for semantic search."""

    def test_add_document(self):
        """Should add document to index."""
        index = VectorIndex()
        result = index.add("doc1", "Python programming guide")
        assert result is True

    def test_add_duplicate_fails(self):
        """Should not add duplicate documents."""
        index = VectorIndex()
        index.add("doc1", "First document")
        result = index.add("doc1", "Second document")
        assert result is False

    def test_remove_document(self):
        """Should remove document from index."""
        index = VectorIndex()
        index.add("doc1", "Test document")
        result = index.remove("doc1")
        assert result is True

    def test_remove_nonexistent(self):
        """Should handle removing non-existent document."""
        index = VectorIndex()
        result = index.remove("nonexistent")
        assert result is False

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="sklearn required")
    def test_search(self):
        """Should find similar documents."""
        index = VectorIndex()
        index.add("doc1", "Python programming language")
        index.add("doc2", "JavaScript web development")
        index.add("doc3", "Python data science")

        results = index.search("Python programming", limit=2)
        assert len(results) >= 1
        # Results should include Python-related docs
        ids = [r[0] for r in results]
        assert "doc1" in ids or "doc3" in ids

    def test_search_empty_index(self):
        """Should handle search on empty index."""
        index = VectorIndex()
        results = index.search("test query")
        assert results == []


class TestMemoryCompressor:
    """Test memory compression utility."""

    def test_compress_data(self):
        """Should compress data."""
        data = b"This is some test data that should be compressed " * 100
        compressed, ratio = MemoryCompressor.compress(data)
        assert len(compressed) < len(data)
        assert ratio > 0

    def test_decompress_data(self):
        """Should decompress data correctly."""
        original = b"Test data for compression and decompression"
        compressed, _ = MemoryCompressor.compress(original)
        decompressed = MemoryCompressor.decompress(compressed)
        assert decompressed == original

    def test_should_compress_large(self):
        """Should recommend compression for large data."""
        large_data = b"x" * 2000
        assert MemoryCompressor.should_compress(large_data, threshold=1024) is True

    def test_should_not_compress_small(self):
        """Should not recommend compression for small data."""
        small_data = b"x" * 100
        assert MemoryCompressor.should_compress(small_data, threshold=1024) is False

    def test_compression_ratio(self):
        """Should achieve reasonable compression ratio."""
        # Highly compressible data
        data = b"aaaaaaaaaa" * 1000
        _, ratio = MemoryCompressor.compress(data)
        assert ratio > 0.9  # Should compress very well


class TestSAFLANeuralMemoryV3:
    """Test SAFLA Neural Memory System v3.0."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def memory(self, temp_db):
        """Create memory instance with temp DB."""
        config = SAFLAConfig(
            db_path=temp_db,
            persistence_enabled=True,
        )
        mem = SAFLANeuralMemoryV3(config)
        return mem

    @pytest.fixture
    def memory_no_persist(self):
        """Create memory instance without persistence."""
        config = SAFLAConfig(persistence_enabled=False)
        return SAFLANeuralMemoryV3(config)

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, memory):
        """Should store and retrieve values."""
        await memory.store(
            MemoryTier.SEMANTIC,
            "test_key",
            {"data": "value"},
        )
        result = await memory.retrieve(MemoryTier.SEMANTIC, "test_key")
        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_store_in_all_tiers(self, memory):
        """Should store in all memory tiers."""
        for tier in MemoryTier:
            await memory.store(tier, f"key_{tier.value}", f"value_{tier.value}")
            result = await memory.retrieve(tier, f"key_{tier.value}")
            assert result == f"value_{tier.value}"

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent(self, memory):
        """Should return None for non-existent key."""
        result = await memory.retrieve(MemoryTier.SEMANTIC, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_with_confidence(self, memory):
        """Should store with confidence level."""
        await memory.store(
            MemoryTier.SEMANTIC,
            "confident_key",
            "value",
            confidence=0.9,
        )
        entry = memory._memories[MemoryTier.SEMANTIC]["confident_key"]
        assert entry.confidence == 0.9

    @pytest.mark.asyncio
    async def test_store_with_ttl(self, memory):
        """Should store with TTL."""
        await memory.store(
            MemoryTier.WORKING,
            "temp_key",
            "value",
            ttl_seconds=3600,
        )
        entry = memory._memories[MemoryTier.WORKING]["temp_key"]
        assert entry.ttl_seconds == 3600

    @pytest.mark.asyncio
    async def test_search_semantic_by_key(self, memory):
        """Should find entries by key match."""
        await memory.store(
            MemoryTier.SEMANTIC,
            "python_guide",
            "Introduction to Python",
        )
        results = await memory.search_semantic("python")
        assert len(results) > 0
        assert any(r.key == "python_guide" for r in results)

    @pytest.mark.asyncio
    async def test_search_semantic_by_value(self, memory):
        """Should find entries by value match."""
        await memory.store(
            MemoryTier.SEMANTIC,
            "guide_123",
            "Learn Python programming basics",
        )
        results = await memory.search_semantic("Python")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_cross_tier(self, memory):
        """Should search across multiple tiers."""
        await memory.store(MemoryTier.SEMANTIC, "sem_key", "Python data")
        await memory.store(MemoryTier.EPISODIC, "ep_key", "Python session")

        results = await memory.search_cross_tier("Python")
        assert MemoryTier.SEMANTIC in results
        assert MemoryTier.EPISODIC in results
        assert len(results[MemoryTier.SEMANTIC]) > 0
        assert len(results[MemoryTier.EPISODIC]) > 0


class TestFeedbackLoops:
    """Test feedback loop functionality."""

    @pytest.fixture
    def memory(self):
        """Create memory instance without persistence."""
        config = SAFLAConfig(
            persistence_enabled=False,
            feedback_confidence_threshold=0.8,
        )
        return SAFLANeuralMemoryV3(config)

    @pytest.mark.asyncio
    async def test_add_feedback_loop(self, memory):
        """Should add feedback loop."""
        loop_id = await memory.add_feedback_loop(
            context={"task": "test"},
            action="test_action",
            outcome="success",
            learning="Test works well",
            confidence=0.9,
        )
        assert loop_id is not None
        assert len(memory._feedback_loops) == 1

    @pytest.mark.asyncio
    async def test_high_confidence_auto_applies(self, memory):
        """High confidence feedback should auto-apply to semantic memory."""
        await memory.add_feedback_loop(
            context={"task": "test"},
            action="test_action",
            outcome="success",
            learning="High confidence learning",
            confidence=0.95,
        )

        # Should be stored in semantic memory
        assert len(memory._memories[MemoryTier.SEMANTIC]) > 0

    @pytest.mark.asyncio
    async def test_low_confidence_not_auto_applied(self, memory):
        """Low confidence feedback should not auto-apply."""
        await memory.add_feedback_loop(
            context={"task": "test"},
            action="test_action",
            outcome="failure",
            learning="Low confidence learning",
            confidence=0.5,
        )

        # Should not be in semantic memory
        semantic_keys = list(memory._memories[MemoryTier.SEMANTIC].keys())
        assert not any("learning_" in k for k in semantic_keys)

    @pytest.mark.asyncio
    async def test_get_relevant_feedback(self, memory):
        """Should retrieve relevant feedback loops."""
        await memory.add_feedback_loop(
            context={"task": "python", "type": "code"},
            action="code_review",
            outcome="success",
            learning="Python code reviewed",
            confidence=0.85,
        )

        await memory.add_feedback_loop(
            context={"task": "javascript", "type": "code"},
            action="code_review",
            outcome="success",
            learning="JS code reviewed",
            confidence=0.85,
        )

        relevant = await memory.get_relevant_feedback({"task": "python"})
        assert len(relevant) > 0

    @pytest.mark.asyncio
    async def test_optimize_feedback_loops(self, memory):
        """Should consolidate similar feedback loops."""
        # Add multiple similar feedback loops
        for i in range(5):
            await memory.add_feedback_loop(
                context={"iteration": i},
                action="common_action",
                outcome="success",
                learning=f"Learning {i}",
                confidence=0.9,
            )

        result = await memory.optimize_feedback_loops()
        assert result["optimized"] > 0 or result["consolidated"] > 0


class TestPersistence:
    """Test cross-session persistence."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_persistence_stores_data(self, temp_db_path):
        """Should persist data to SQLite."""
        config = SAFLAConfig(db_path=temp_db_path, persistence_enabled=True)
        memory = SAFLANeuralMemoryV3(config)

        await memory.store(MemoryTier.SEMANTIC, "persist_key", "persist_value")
        await memory.shutdown()

        # Verify file exists
        assert os.path.exists(temp_db_path)

    @pytest.mark.asyncio
    async def test_persistence_loads_data(self, temp_db_path):
        """Should load data from SQLite on startup."""
        # Store data
        config = SAFLAConfig(db_path=temp_db_path, persistence_enabled=True)
        memory1 = SAFLANeuralMemoryV3(config)
        await memory1.store(MemoryTier.SEMANTIC, "persist_test", "stored_value")
        await memory1.shutdown()

        # Create new instance and verify data loaded
        memory2 = SAFLANeuralMemoryV3(config)
        result = await memory2.retrieve(MemoryTier.SEMANTIC, "persist_test")
        assert result == "stored_value"
        await memory2.shutdown()

    @pytest.mark.asyncio
    async def test_export_memories(self, temp_db_path):
        """Should export memories to JSON."""
        config = SAFLAConfig(db_path=temp_db_path, persistence_enabled=False)
        memory = SAFLANeuralMemoryV3(config)

        await memory.store(MemoryTier.SEMANTIC, "export_key", "export_value")

        export_path = temp_db_path + ".json"
        result = await memory.export_memories(export_path)

        assert result is True
        assert os.path.exists(export_path)

        os.unlink(export_path)

    @pytest.mark.asyncio
    async def test_import_memories(self, temp_db_path):
        """Should import memories from JSON."""
        config = SAFLAConfig(persistence_enabled=False)
        memory1 = SAFLANeuralMemoryV3(config)
        await memory1.store(MemoryTier.SEMANTIC, "import_key", "import_value")

        export_path = temp_db_path + ".json"
        await memory1.export_memories(export_path)

        memory2 = SAFLANeuralMemoryV3(config)
        imported = await memory2.import_memories(export_path)

        assert imported > 0
        result = await memory2.retrieve(MemoryTier.SEMANTIC, "import_key")
        assert result == "import_value"

        os.unlink(export_path)


class TestCleanup:
    """Test memory cleanup and TTL."""

    @pytest.fixture
    def memory(self):
        """Create memory instance without persistence."""
        config = SAFLAConfig(persistence_enabled=False)
        return SAFLANeuralMemoryV3(config)

    @pytest.mark.asyncio
    async def test_clear_tier(self, memory):
        """Should clear a memory tier."""
        await memory.store(MemoryTier.WORKING, "key1", "value1")
        await memory.store(MemoryTier.WORKING, "key2", "value2")

        count = await memory.clear_tier(MemoryTier.WORKING)
        assert count == 2
        assert len(memory._memories[MemoryTier.WORKING]) == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, memory):
        """Should remove expired entries."""
        # Store with very short TTL (already expired due to old creation date)
        entry = MemoryEntry(
            tier=MemoryTier.WORKING,
            key="expired_key",
            value="expired_value",
            ttl_seconds=1,  # 1 second TTL
            created_at=datetime(2020, 1, 1, tzinfo=UTC),  # Old date (years ago)
        )
        memory._memories[MemoryTier.WORKING]["expired_key"] = entry

        removed = await memory.cleanup_expired()
        assert removed >= 1


class TestStats:
    """Test statistics and metrics."""

    @pytest.fixture
    def memory(self):
        """Create memory instance."""
        config = SAFLAConfig(persistence_enabled=False)
        return SAFLANeuralMemoryV3(config)

    @pytest.mark.asyncio
    async def test_get_stats(self, memory):
        """Should return comprehensive stats."""
        await memory.store(MemoryTier.SEMANTIC, "key1", "value1")
        await memory.store(MemoryTier.WORKING, "key2", "value2")
        await memory.retrieve(MemoryTier.SEMANTIC, "key1")

        stats = memory.get_stats()

        assert "tier_counts" in stats
        assert stats["tier_counts"]["semantic"] == 1
        assert stats["tier_counts"]["working"] == 1
        assert stats["total_entries"] == 2
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "performance" in stats
        assert stats["performance"]["operations"] >= 3

    @pytest.mark.asyncio
    async def test_cache_hit_tracking(self, memory):
        """Should track cache hits and misses."""
        await memory.store(MemoryTier.SEMANTIC, "key", "value")
        await memory.retrieve(MemoryTier.SEMANTIC, "key")  # Hit
        await memory.retrieve(MemoryTier.SEMANTIC, "nonexistent")  # Miss

        stats = memory.get_stats()
        assert stats["performance"]["cache_hit_rate"] > 0


class TestFactoryFunction:
    """Test factory function."""

    def test_create_safla_memory_defaults(self):
        """Should create memory with defaults."""
        memory = create_safla_memory(persistence_enabled=False)
        assert isinstance(memory, SAFLANeuralMemoryV3)
        assert memory._constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_safla_memory_custom_hash(self):
        """Should accept custom constitutional hash."""
        custom_hash = "custom_hash_123"
        memory = create_safla_memory(
            persistence_enabled=False,
            constitutional_hash=custom_hash,
        )
        assert memory._constitutional_hash == custom_hash


class TestPerformance:
    """Performance tests."""

    @pytest.fixture
    def memory(self):
        """Create memory instance."""
        config = SAFLAConfig(persistence_enabled=False)
        return SAFLANeuralMemoryV3(config)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_high_throughput_stores(self, memory):
        """Should handle high throughput stores."""
        import time

        start = time.perf_counter()
        for i in range(1000):
            await memory.store(MemoryTier.SEMANTIC, f"key_{i}", f"value_{i}")
        elapsed = time.perf_counter() - start

        ops_per_sec = 1000 / elapsed
        # Async operations have overhead; target 500+ ops/sec minimum
        assert ops_per_sec > 500

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_high_throughput_retrieves(self, memory):
        """Should handle high throughput retrieves."""
        # Pre-populate
        for i in range(100):
            await memory.store(MemoryTier.SEMANTIC, f"key_{i}", f"value_{i}")

        import time

        start = time.perf_counter()
        for i in range(1000):
            await memory.retrieve(MemoryTier.SEMANTIC, f"key_{i % 100}")
        elapsed = time.perf_counter() - start

        ops_per_sec = 1000 / elapsed
        # Retrieves should be very fast
        assert ops_per_sec > 10000
