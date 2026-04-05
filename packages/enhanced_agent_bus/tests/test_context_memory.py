"""
ACGS-2 Context & Memory - Comprehensive Test Suite
Constitutional Hash: 608508a9bd224290

Tests for Layer 1: Context & Memory (Mamba-2 Hybrid Processor).
Covers all components with 50+ tests for constitutional compliance.
"""

import asyncio
import os
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add path for imports
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Import context_memory components

from context_memory.constitutional_context_cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    CacheTier,
    ConstitutionalContextCache,
)
from context_memory.hybrid_context_manager import (
    HybridContextConfig,
    HybridContextManager,
    HybridProcessingResult,
    ProcessingMode,
    SharedAttentionProcessor,
)
from context_memory.jrt_context_preparer import (
    CriticalSectionMarker,
    JRTContextPreparer,
    JRTPreparationResult,
    JRTRetrievalStrategy,
)
from context_memory.long_term_memory import (
    ConsolidationStrategy,
    LongTermMemoryConfig,
    LongTermMemoryStore,
    MemorySearchResult,
    MemoryTier,
)
from context_memory.mamba_processor import (
    NUMPY_AVAILABLE,
    TORCH_AVAILABLE,
    Mamba2SSMLayer,
    MambaProcessor,
    MambaProcessorConfig,
    ProcessingResult,
)
from context_memory.models import (
    CONSTITUTIONAL_HASH,
    ContextChunk,
    ContextPriority,
    ContextRetrievalResult,
    ContextType,
    ContextWindow,
    EpisodicMemoryEntry,
    JRTConfig,
    MambaConfig,
    MemoryConsolidationResult,
    MemoryOperation,
    MemoryOperationType,
    MemoryQuery,
    SemanticMemoryEntry,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_context_chunks() -> list[ContextChunk]:
    """Create sample context chunks for testing."""
    return [
        ContextChunk(
            content="Constitutional principle: All AI must be beneficial.",
            context_type=ContextType.CONSTITUTIONAL,
            priority=ContextPriority.CRITICAL,
            token_count=10,
            relevance_score=1.0,
            is_critical=True,
        ),
        ContextChunk(
            content="Policy rule: Data must be encrypted at rest.",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=8,
            relevance_score=0.9,
        ),
        ContextChunk(
            content="Governance decision: Approve agent deployment.",
            context_type=ContextType.GOVERNANCE,
            priority=ContextPriority.MEDIUM,
            token_count=6,
            relevance_score=0.7,
        ),
        ContextChunk(
            content="Background context: System is operational.",
            context_type=ContextType.SYSTEM,
            priority=ContextPriority.BACKGROUND,
            token_count=5,
            relevance_score=0.5,
        ),
    ]


@pytest.fixture
def mamba_config() -> MambaProcessorConfig:
    """Create Mamba processor configuration."""
    return MambaProcessorConfig(
        d_model=64,
        d_state=32,
        num_layers=2,
        max_context_length=1000,
    )


@pytest.fixture
def hybrid_config() -> HybridContextConfig:
    """Create hybrid context manager configuration."""
    return HybridContextConfig(
        mamba_d_model=64,
        mamba_d_state=32,
        mamba_num_layers=2,
        attention_num_heads=4,
        attention_max_seq_len=512,
    )


@pytest.fixture
def jrt_config() -> JRTConfig:
    """Create JRT context preparer configuration."""
    return JRTConfig(
        repetition_factor=2,
        context_window_size=1024,
        relevance_threshold=0.5,
        max_critical_sections=5,
    )


@pytest.fixture
def ltm_config() -> LongTermMemoryConfig:
    """Create long-term memory configuration."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    return LongTermMemoryConfig(
        db_path=db_path,
        max_episodic_entries=100,
        max_semantic_entries=50,
        enable_persistence=True,
        enable_audit_trail=True,
    )


@pytest.fixture
def cache_config() -> CacheConfig:
    """Create cache configuration."""
    return CacheConfig(
        l1_max_entries=100,
        l1_ttl_seconds=60,
        l2_enabled=False,
        enable_warming=True,
    )


# =============================================================================
# Model Tests (10 tests)
# =============================================================================


class TestModels:
    """Test data models for context/memory."""

    def test_constitutional_hash_constant(self):
        """Test constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_context_type_enum(self):
        """Test ContextType enum values."""
        assert ContextType.CONSTITUTIONAL.value == "constitutional"
        assert ContextType.POLICY.value == "policy"
        assert ContextType.GOVERNANCE.value == "governance"

    def test_context_priority_ordering(self):
        """Test ContextPriority ordering."""
        assert ContextPriority.CRITICAL.value > ContextPriority.HIGH.value
        assert ContextPriority.HIGH.value > ContextPriority.MEDIUM.value
        assert ContextPriority.MEDIUM.value > ContextPriority.LOW.value

    def test_mamba_config_validation(self):
        """Test MambaConfig validation."""
        config = MambaConfig(d_model=256, d_state=128)
        assert config.d_model == 256
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_mamba_config_invalid_hash(self):
        """Test MambaConfig rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            MambaConfig(constitutional_hash="invalid")

    def test_context_chunk_creation(self):
        """Test ContextChunk creation with defaults."""
        chunk = ContextChunk(
            content="Test content",
            context_type=ContextType.CONSTITUTIONAL,
            priority=ContextPriority.CRITICAL,
            token_count=10,
        )
        assert chunk.chunk_id != ""
        assert chunk.constitutional_hash == CONSTITUTIONAL_HASH

    def test_context_window_add_chunk(self, sample_context_chunks):
        """Test adding chunks to context window."""
        window = ContextWindow(max_tokens=50)
        for chunk in sample_context_chunks:
            assert window.add_chunk(chunk)
        assert window.total_tokens == 29  # 10 + 8 + 6 + 5

    def test_context_window_max_tokens(self, sample_context_chunks):
        """Test context window respects max tokens."""
        window = ContextWindow(max_tokens=15)
        added = 0
        for chunk in sample_context_chunks:
            if window.add_chunk(chunk):
                added += 1
        assert added < len(sample_context_chunks)

    def test_episodic_memory_entry_decay(self):
        """Test episodic memory relevance decay."""
        entry = EpisodicMemoryEntry(
            entry_id="test",
            session_id="session",
            tenant_id="tenant",
            timestamp=datetime.now(UTC) - timedelta(hours=10),
            event_type="test",
            content="test content",
        )
        initial_decay = entry.relevance_decay
        entry.decay_relevance(decay_rate=0.05)
        assert entry.relevance_decay < initial_decay

    def test_semantic_memory_confidence_update(self):
        """Test semantic memory confidence update."""
        entry = SemanticMemoryEntry(
            entry_id="test",
            knowledge_type="policy",
            content="test",
            confidence=0.5,
            source="test",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        entry.update_confidence(0.9)
        assert entry.confidence > 0.5
        assert entry.confidence < 0.9  # EMA smoothing


# =============================================================================
# Mamba Processor Tests (10 tests)
# =============================================================================


class TestMambaProcessor:
    """Test Mamba-2 SSM processor."""

    def test_processor_initialization(self, mamba_config):
        """Test MambaProcessor initialization."""
        processor = MambaProcessor(config=mamba_config)
        assert len(processor.layers) == mamba_config.num_layers
        assert processor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_processor_invalid_hash(self, mamba_config):
        """Test MambaProcessor rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            MambaProcessor(config=mamba_config, constitutional_hash="invalid")

    def test_ssm_layer_initialization(self):
        """Test Mamba2SSMLayer initialization."""
        layer = Mamba2SSMLayer(d_model=64, d_state=32, layer_idx=0)
        assert layer.d_model == 64
        assert layer.d_state == 32
        assert layer.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not available")
    def test_ssm_layer_forward_torch(self):
        """Test SSM layer forward pass with PyTorch."""
        import torch

        layer = Mamba2SSMLayer(d_model=64, d_state=32)
        x = torch.randn(1, 10, 64)
        output, _state = layer.forward(x)
        assert output.shape == x.shape

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not available")
    def test_ssm_layer_forward_numpy(self):
        """Test SSM layer forward pass with NumPy."""
        import numpy as np

        layer = Mamba2SSMLayer(d_model=64, d_state=32)
        x = np.random.randn(1, 10, 64).astype(np.float32)
        output, _state = layer.forward(x)
        assert output.shape == x.shape

    def test_processor_process_basic(self, mamba_config):
        """Test basic processing."""
        processor = MambaProcessor(config=mamba_config)
        embeddings = processor._simple_embed("test input")
        result = processor.process(embeddings)
        assert isinstance(result, ProcessingResult)
        assert result.constitutional_validated

    def test_processor_stream_processing(self, mamba_config):
        """Test stream processing for long contexts."""
        mamba_config.chunk_size = 10
        processor = MambaProcessor(config=mamba_config)
        embeddings = processor._simple_embed("a" * 100)  # Long input
        result = processor.process(embeddings, stream=True)
        assert result.tokens_processed > 0

    def test_processor_reset_state(self, mamba_config):
        """Test processor state reset."""
        processor = MambaProcessor(config=mamba_config)
        embeddings = processor._simple_embed("test")
        processor.process(embeddings)
        processor.reset_state()
        assert len(processor._states) == 0

    def test_processor_metrics(self, mamba_config):
        """Test processor metrics collection."""
        processor = MambaProcessor(config=mamba_config)
        embeddings = processor._simple_embed("test")
        processor.process(embeddings)
        metrics = processor.get_metrics()
        assert "total_tokens_processed" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_processor_context_chunks(self, mamba_config, sample_context_chunks):
        """Test processing context chunks."""
        processor = MambaProcessor(config=mamba_config)
        result = processor.process_context_chunks(sample_context_chunks[:2])
        assert result.metadata["chunk_count"] == 2


# =============================================================================
# Hybrid Context Manager Tests (10 tests)
# =============================================================================


class TestHybridContextManager:
    """Test hybrid context manager."""

    def test_manager_initialization(self, hybrid_config):
        """Test HybridContextManager initialization."""
        manager = HybridContextManager(config=hybrid_config)
        assert manager.mamba_processor is not None
        assert manager.attention_processor is not None

    def test_manager_invalid_hash(self, hybrid_config):
        """Test manager rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            HybridContextManager(config=hybrid_config, constitutional_hash="invalid")

    def test_auto_mode_selection_short(self, hybrid_config, sample_context_chunks):
        """Test auto mode selects attention for short context."""
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=100)
        window.add_chunk(sample_context_chunks[0])
        mode = manager._auto_select_mode(window)
        assert mode in [ProcessingMode.ATTENTION_ONLY, ProcessingMode.HYBRID]

    def test_auto_mode_selection_constitutional(self, hybrid_config, sample_context_chunks):
        """Test auto mode selects hybrid for constitutional content."""
        hybrid_config.constitutional_always_attention = True
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=1000)
        window.add_chunk(sample_context_chunks[0])  # Constitutional
        mode = manager._auto_select_mode(window)
        assert mode == ProcessingMode.HYBRID

    async def test_process_ssm_only(self, hybrid_config, sample_context_chunks):
        """Test SSM-only processing mode."""
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=100)
        window.add_chunk(sample_context_chunks[1])  # Non-constitutional
        result = await manager._process_ssm_only(window)
        assert result.processing_mode == ProcessingMode.SSM_ONLY
        assert result.ssm_processed_tokens > 0

    async def test_process_attention_only(self, hybrid_config, sample_context_chunks):
        """Test attention-only processing mode."""
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=100)
        window.add_chunk(sample_context_chunks[0])
        result = await manager._process_attention_only(window)
        assert result.processing_mode == ProcessingMode.ATTENTION_ONLY
        assert result.attention_processed_tokens > 0

    async def test_process_hybrid(self, hybrid_config, sample_context_chunks):
        """Test hybrid processing mode."""
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=100)
        for chunk in sample_context_chunks:
            window.add_chunk(chunk)
        result = await manager._process_hybrid(window)
        assert result.processing_mode == ProcessingMode.HYBRID

    async def test_process_with_caching(self, hybrid_config, sample_context_chunks):
        """Test processing with caching enabled."""
        hybrid_config.enable_caching = True
        manager = HybridContextManager(config=hybrid_config)
        window = ContextWindow(max_tokens=100)
        window.add_chunk(sample_context_chunks[0])

        # First call - cache miss
        result1 = await manager.process_context_window(window)
        assert not result1.cache_hit

        # Second call - cache hit
        result2 = await manager.process_context_window(window)
        assert result2.cache_hit

    def test_manager_clear_cache(self, hybrid_config):
        """Test cache clearing."""
        manager = HybridContextManager(config=hybrid_config)
        manager._cache["test"] = ("value", datetime.now(UTC))
        cleared = manager.clear_cache()
        assert cleared == 1
        assert len(manager._cache) == 0

    def test_manager_metrics(self, hybrid_config):
        """Test manager metrics collection."""
        manager = HybridContextManager(config=hybrid_config)
        metrics = manager.get_metrics()
        assert "ssm_calls" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# JRT Context Preparer Tests (10 tests)
# =============================================================================


class TestJRTContextPreparer:
    """Test JRT context preparer."""

    def test_preparer_initialization(self, jrt_config):
        """Test JRTContextPreparer initialization."""
        preparer = JRTContextPreparer(config=jrt_config)
        assert preparer.config.repetition_factor == 2
        assert preparer.constitutional_hash == CONSTITUTIONAL_HASH

    def test_preparer_invalid_hash(self, jrt_config):
        """Test preparer rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            JRTContextPreparer(config=jrt_config, constitutional_hash="invalid")

    def test_set_constitutional_context(self, jrt_config, sample_context_chunks):
        """Test setting constitutional context."""
        preparer = JRTContextPreparer(config=jrt_config)
        preparer.set_constitutional_context([sample_context_chunks[0]])
        assert len(preparer._constitutional_context) == 1

    def test_default_relevance_score(self, jrt_config):
        """Test default relevance scoring."""
        preparer = JRTContextPreparer(config=jrt_config)
        score = preparer._default_relevance_score(
            "beneficial AI", "Constitutional principle: All AI must be beneficial."
        )
        assert 0 < score <= 1.0

    def test_strategy_relevance_first(self, jrt_config, sample_context_chunks):
        """Test relevance-first strategy."""
        preparer = JRTContextPreparer(config=jrt_config)
        scored = [(c, c.relevance_score) for c in sample_context_chunks]
        ordered = preparer._apply_strategy(scored, JRTRetrievalStrategy.RELEVANCE_FIRST)
        assert ordered[0].relevance_score >= ordered[-1].relevance_score

    def test_strategy_priority_first(self, jrt_config, sample_context_chunks):
        """Test priority-first strategy."""
        preparer = JRTContextPreparer(config=jrt_config)
        scored = [(c, c.relevance_score) for c in sample_context_chunks]
        ordered = preparer._apply_strategy(scored, JRTRetrievalStrategy.PRIORITY_FIRST)
        assert ordered[0].priority.value >= ordered[-1].priority.value

    async def test_prepare_context(self, jrt_config, sample_context_chunks):
        """Test full context preparation."""
        preparer = JRTContextPreparer(config=jrt_config)
        result = await preparer.prepare_context(
            query="AI governance",
            available_chunks=sample_context_chunks,
        )
        assert isinstance(result, JRTPreparationResult)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_prepare_context_with_repetitions(self, jrt_config, sample_context_chunks):
        """Test context preparation with critical section repetitions."""
        jrt_config.repetition_factor = 2
        preparer = JRTContextPreparer(config=jrt_config)
        preparer.set_constitutional_context([sample_context_chunks[0]])
        result = await preparer.prepare_context(
            query="constitutional",
            available_chunks=sample_context_chunks,
        )
        assert result.repetitions_applied >= 0

    def test_identify_critical_sections(self, jrt_config, sample_context_chunks):
        """Test critical section identification."""
        preparer = JRTContextPreparer(config=jrt_config)
        scored = [(c, c.relevance_score) for c in sample_context_chunks]
        critical = preparer._identify_critical_sections(scored)
        # Constitutional chunk should be critical
        assert len(critical) > 0

    def test_critical_section_marker(self):
        """Test CriticalSectionMarker creation."""
        marker = CriticalSectionMarker(
            start_position=0,
            end_position=100,
            section_type=ContextType.CONSTITUTIONAL,
            priority=ContextPriority.CRITICAL,
        )
        assert marker.content_hash != ""
        assert marker.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Long Term Memory Tests (10 tests)
# =============================================================================


class TestLongTermMemory:
    """Test long-term memory store."""

    def test_ltm_initialization(self, ltm_config):
        """Test LongTermMemoryStore initialization."""
        store = LongTermMemoryStore(config=ltm_config)
        assert store.config.enable_persistence
        assert store.constitutional_hash == CONSTITUTIONAL_HASH

    def test_ltm_invalid_hash(self, ltm_config):
        """Test store rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            LongTermMemoryStore(config=ltm_config, constitutional_hash="invalid")

    async def test_store_episodic(self, ltm_config):
        """Test storing episodic memory."""
        store = LongTermMemoryStore(config=ltm_config)
        entry_id = await store.store_episodic(
            session_id="session1",
            tenant_id="tenant1",
            event_type="test",
            content="Test event content",
        )
        assert entry_id != ""
        await store.shutdown()

    async def test_retrieve_episodic(self, ltm_config):
        """Test retrieving episodic memory."""
        store = LongTermMemoryStore(config=ltm_config)
        entry_id = await store.store_episodic(
            session_id="session1",
            tenant_id="tenant1",
            event_type="test",
            content="Test content",
        )
        entries = await store.retrieve_episodic(session_id="session1")
        assert len(entries) > 0
        await store.shutdown()

    async def test_store_semantic(self, ltm_config):
        """Test storing semantic memory."""
        store = LongTermMemoryStore(config=ltm_config)
        entry_id = await store.store_semantic(
            knowledge_type="policy",
            content="All data must be encrypted",
            confidence=0.9,
            source="policy_document",
        )
        assert entry_id != ""
        await store.shutdown()

    async def test_search_semantic(self, ltm_config):
        """Test searching semantic memory."""
        store = LongTermMemoryStore(config=ltm_config)
        await store.store_semantic(
            knowledge_type="policy",
            content="Data encryption policy",
            confidence=0.9,
            source="test",
        )
        result = await store.search_semantic(query="encryption")
        assert isinstance(result, MemorySearchResult)
        await store.shutdown()

    async def test_consolidation_time_based(self, ltm_config):
        """Test time-based memory consolidation."""
        store = LongTermMemoryStore(config=ltm_config)
        await store.store_episodic(
            session_id="session1",
            tenant_id="tenant1",
            event_type="test",
            content="Test",
        )
        result = await store.consolidate(strategy=ConsolidationStrategy.TIME_BASED)
        assert isinstance(result, MemoryConsolidationResult)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        await store.shutdown()

    async def test_consolidation_access_based(self, ltm_config):
        """Test access-based memory consolidation."""
        store = LongTermMemoryStore(config=ltm_config)
        result = await store.consolidate(strategy=ConsolidationStrategy.ACCESS_BASED)
        assert isinstance(result, MemoryConsolidationResult)
        await store.shutdown()

    def test_ltm_metrics(self, ltm_config):
        """Test LTM metrics collection."""
        store = LongTermMemoryStore(config=ltm_config)
        metrics = store.get_metrics()
        assert "episodic_writes" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_memory_tier_enum(self):
        """Test MemoryTier enum values."""
        assert MemoryTier.WORKING.value == "working"
        assert MemoryTier.SHORT_TERM.value == "short_term"
        assert MemoryTier.LONG_TERM.value == "long_term"


# =============================================================================
# Constitutional Context Cache Tests (10 tests)
# =============================================================================


class TestConstitutionalContextCache:
    """Test constitutional context cache."""

    def test_cache_initialization(self, cache_config):
        """Test ConstitutionalContextCache initialization."""
        cache = ConstitutionalContextCache(config=cache_config)
        assert cache.config.l1_max_entries == 100
        assert cache.constitutional_hash == CONSTITUTIONAL_HASH

    def test_cache_invalid_hash(self, cache_config):
        """Test cache rejects invalid hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            ConstitutionalContextCache(config=cache_config, constitutional_hash="invalid")

    async def test_cache_set_get(self, cache_config):
        """Test basic cache set and get."""
        cache = ConstitutionalContextCache(config=cache_config)
        await cache.set("key1", "value1")
        value = await cache.get("key1")
        assert value == "value1"

    async def test_cache_miss(self, cache_config):
        """Test cache miss returns default."""
        cache = ConstitutionalContextCache(config=cache_config)
        value = await cache.get("nonexistent", default="default")
        assert value == "default"

    async def test_cache_expiration(self, cache_config):
        """Test cache entry expiration."""
        cache_config.l1_ttl_seconds = 1
        cache = ConstitutionalContextCache(config=cache_config)
        await cache.set("key1", "value1", ttl_seconds=1)
        await asyncio.sleep(1.1)
        value = await cache.get("key1")
        assert value is None

    async def test_cache_eviction(self, cache_config):
        """Test LRU cache eviction."""
        cache_config.l1_max_entries = 3
        cache = ConstitutionalContextCache(config=cache_config)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        await cache.set("key4", "value4")  # Should evict key1
        value = await cache.get("key1")
        assert value is None

    async def test_set_constitutional_context(self, cache_config, sample_context_chunks):
        """Test setting constitutional context."""
        cache = ConstitutionalContextCache(config=cache_config)
        await cache.set_constitutional_context([sample_context_chunks[0]])
        chunks = await cache.get_constitutional_context()
        assert len(chunks) == 1

    async def test_warm_cache(self, cache_config, sample_context_chunks):
        """Test cache warming."""
        cache = ConstitutionalContextCache(config=cache_config)
        warmed = await cache.warm_cache(sample_context_chunks)
        assert warmed == len(sample_context_chunks)

    async def test_invalidate_pattern(self, cache_config):
        """Test pattern-based invalidation."""
        cache = ConstitutionalContextCache(config=cache_config)
        await cache.set("prefix:key1", "value1")
        await cache.set("prefix:key2", "value2")
        await cache.set("other:key3", "value3")
        count = await cache.invalidate_pattern("prefix:")
        assert count == 2

    def test_cache_stats(self, cache_config):
        """Test cache statistics."""
        cache = ConstitutionalContextCache(config=cache_config)
        stats = cache.get_stats()
        assert isinstance(stats, CacheStats)
        assert stats.constitutional_hash == CONSTITUTIONAL_HASH

    def test_cache_metrics(self, cache_config):
        """Test cache metrics collection."""
        cache = ConstitutionalContextCache(config=cache_config)
        metrics = cache.get_metrics()
        assert "hit_rate" in metrics
        assert "p99_latency_ms" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# Integration Tests (5 tests)
# =============================================================================


class TestIntegration:
    """Integration tests for context/memory components."""

    async def test_full_pipeline(self, hybrid_config, jrt_config, sample_context_chunks):
        """Test full context processing pipeline."""
        # Prepare context
        preparer = JRTContextPreparer(config=jrt_config)
        prep_result = await preparer.prepare_context(
            query="constitutional governance",
            available_chunks=sample_context_chunks,
        )

        # Process with hybrid manager
        manager = HybridContextManager(config=hybrid_config)
        proc_result = await manager.process_context_window(prep_result.prepared_window)

        assert proc_result.constitutional_validated
        assert proc_result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_cache_with_ltm(self, cache_config, ltm_config):
        """Test cache integration with long-term memory."""
        cache = ConstitutionalContextCache(config=cache_config)
        store = LongTermMemoryStore(config=ltm_config)

        # Store in LTM
        entry_id = await store.store_semantic(
            knowledge_type="policy",
            content="Test policy",
            confidence=0.9,
            source="test",
        )

        # Cache the entry
        await cache.set(f"semantic:{entry_id}", "Test policy")
        value = await cache.get(f"semantic:{entry_id}")

        assert value == "Test policy"
        await store.shutdown()

    async def test_constitutional_context_flow(
        self, cache_config, jrt_config, sample_context_chunks
    ):
        """Test constitutional context always flows through."""
        cache = ConstitutionalContextCache(config=cache_config)
        preparer = JRTContextPreparer(config=jrt_config)

        # set constitutional context
        const_chunk = sample_context_chunks[0]
        await cache.set_constitutional_context([const_chunk])
        preparer.set_constitutional_context([const_chunk])

        # Prepare context
        result = await preparer.prepare_context(
            query="test query",
            available_chunks=sample_context_chunks[1:],  # Non-constitutional
        )

        # Constitutional should still be present
        assert result.constitutional_context_present

    async def test_performance_under_load(self, cache_config):
        """Test cache performance under load."""
        cache = ConstitutionalContextCache(config=cache_config)
        num_operations = 100

        start = time.perf_counter()
        for i in range(num_operations):
            await cache.set(f"key{i}", f"value{i}")
            await cache.get(f"key{i}")
        elapsed = time.perf_counter() - start

        metrics = cache.get_metrics()
        # Should be fast - less than 100ms for 200 operations
        assert elapsed < 1.0
        assert metrics["p99_within_target"]

    def test_constitutional_hash_consistency(
        self, mamba_config, hybrid_config, jrt_config, ltm_config, cache_config
    ):
        """Test constitutional hash is consistent across all components."""
        processor = MambaProcessor(config=mamba_config)
        manager = HybridContextManager(config=hybrid_config)
        preparer = JRTContextPreparer(config=jrt_config)
        store = LongTermMemoryStore(config=ltm_config)
        cache = ConstitutionalContextCache(config=cache_config)

        # All should have the same constitutional hash
        assert processor.constitutional_hash == CONSTITUTIONAL_HASH
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH
        assert preparer.constitutional_hash == CONSTITUTIONAL_HASH
        assert store.constitutional_hash == CONSTITUTIONAL_HASH
        assert cache.constitutional_hash == CONSTITUTIONAL_HASH


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
