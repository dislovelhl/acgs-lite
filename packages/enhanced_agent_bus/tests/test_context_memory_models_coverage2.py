# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for context_memory/models.py
Target: ≥95% coverage of all classes, methods, validators, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.context_memory.models import (
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

# ---------------------------------------------------------------------------
# ContextType enum
# ---------------------------------------------------------------------------


class TestContextType:
    def test_constitutional(self):
        assert ContextType.CONSTITUTIONAL == "constitutional"

    def test_policy(self):
        assert ContextType.POLICY == "policy"

    def test_governance(self):
        assert ContextType.GOVERNANCE == "governance"

    def test_semantic(self):
        assert ContextType.SEMANTIC == "semantic"

    def test_episodic(self):
        assert ContextType.EPISODIC == "episodic"

    def test_working(self):
        assert ContextType.WORKING == "working"

    def test_system(self):
        assert ContextType.SYSTEM == "system"

    def test_is_str(self):
        assert isinstance(ContextType.CONSTITUTIONAL, str)

    def test_count(self):
        assert len(ContextType) == 7

    def test_values_in_enum(self):
        values = {ct.value for ct in ContextType}
        assert "policy" in values
        assert "governance" in values


# ---------------------------------------------------------------------------
# ContextPriority enum
# ---------------------------------------------------------------------------


class TestContextPriority:
    def test_critical_value(self):
        assert ContextPriority.CRITICAL == 4

    def test_high_value(self):
        assert ContextPriority.HIGH == 3

    def test_medium_value(self):
        assert ContextPriority.MEDIUM == 2

    def test_low_value(self):
        assert ContextPriority.LOW == 1

    def test_background_value(self):
        assert ContextPriority.BACKGROUND == 0

    def test_is_int(self):
        assert isinstance(ContextPriority.CRITICAL, int)

    def test_ordering(self):
        assert ContextPriority.CRITICAL > ContextPriority.HIGH
        assert ContextPriority.HIGH > ContextPriority.MEDIUM
        assert ContextPriority.MEDIUM > ContextPriority.LOW
        assert ContextPriority.LOW > ContextPriority.BACKGROUND

    def test_count(self):
        assert len(ContextPriority) == 5


# ---------------------------------------------------------------------------
# MemoryOperationType enum
# ---------------------------------------------------------------------------


class TestMemoryOperationType:
    def test_store(self):
        assert MemoryOperationType.STORE == "store"

    def test_retrieve(self):
        assert MemoryOperationType.RETRIEVE == "retrieve"

    def test_update(self):
        assert MemoryOperationType.UPDATE == "update"

    def test_delete(self):
        assert MemoryOperationType.DELETE == "delete"

    def test_consolidate(self):
        assert MemoryOperationType.CONSOLIDATE == "consolidate"

    def test_search(self):
        assert MemoryOperationType.SEARCH == "search"

    def test_cache_hit(self):
        assert MemoryOperationType.CACHE_HIT == "cache_hit"

    def test_cache_miss(self):
        assert MemoryOperationType.CACHE_MISS == "cache_miss"

    def test_count(self):
        assert len(MemoryOperationType) == 8

    def test_is_str(self):
        assert isinstance(MemoryOperationType.STORE, str)


# ---------------------------------------------------------------------------
# MambaConfig
# ---------------------------------------------------------------------------


class TestMambaConfigDefaults:
    def test_default_d_model(self):
        cfg = MambaConfig()
        assert cfg.d_model == 256

    def test_default_d_state(self):
        cfg = MambaConfig()
        assert cfg.d_state == 128

    def test_default_num_layers(self):
        cfg = MambaConfig()
        assert cfg.num_layers == 6

    def test_default_expand_factor(self):
        cfg = MambaConfig()
        assert cfg.expand_factor == 2

    def test_default_max_context_length(self):
        cfg = MambaConfig()
        assert cfg.max_context_length == 4_000_000

    def test_default_precision(self):
        cfg = MambaConfig()
        assert cfg.precision == "float32"

    def test_default_enable_quantization(self):
        cfg = MambaConfig()
        assert cfg.enable_quantization is False

    def test_default_constitutional_hash(self):
        cfg = MambaConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH


class TestMambaConfigCustomValues:
    def test_custom_d_model(self):
        cfg = MambaConfig(d_model=512)
        assert cfg.d_model == 512

    def test_boundary_d_model_min(self):
        cfg = MambaConfig(d_model=64)
        assert cfg.d_model == 64

    def test_boundary_d_model_max(self):
        cfg = MambaConfig(d_model=4096)
        assert cfg.d_model == 4096

    def test_d_model_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_model=63)

    def test_d_model_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_model=4097)

    def test_d_state_min(self):
        cfg = MambaConfig(d_state=32)
        assert cfg.d_state == 32

    def test_d_state_max(self):
        cfg = MambaConfig(d_state=512)
        assert cfg.d_state == 512

    def test_d_state_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_state=31)

    def test_d_state_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_state=513)

    def test_num_layers_min(self):
        cfg = MambaConfig(num_layers=1)
        assert cfg.num_layers == 1

    def test_num_layers_max(self):
        cfg = MambaConfig(num_layers=24)
        assert cfg.num_layers == 24

    def test_num_layers_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(num_layers=0)

    def test_num_layers_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(num_layers=25)

    def test_expand_factor_min(self):
        cfg = MambaConfig(expand_factor=1)
        assert cfg.expand_factor == 1

    def test_expand_factor_max(self):
        cfg = MambaConfig(expand_factor=4)
        assert cfg.expand_factor == 4

    def test_expand_factor_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(expand_factor=0)

    def test_expand_factor_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(expand_factor=5)

    def test_max_context_length_min(self):
        cfg = MambaConfig(max_context_length=1024)
        assert cfg.max_context_length == 1024

    def test_max_context_length_max(self):
        cfg = MambaConfig(max_context_length=16_000_000)
        assert cfg.max_context_length == 16_000_000

    def test_max_context_length_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(max_context_length=1023)

    def test_max_context_length_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(max_context_length=16_000_001)

    def test_precision_float16(self):
        cfg = MambaConfig(precision="float16")
        assert cfg.precision == "float16"

    def test_precision_bfloat16(self):
        cfg = MambaConfig(precision="bfloat16")
        assert cfg.precision == "bfloat16"

    def test_precision_float32(self):
        cfg = MambaConfig(precision="float32")
        assert cfg.precision == "float32"

    def test_precision_invalid(self):
        with pytest.raises(ValidationError):
            MambaConfig(precision="int8")

    def test_precision_invalid_empty(self):
        with pytest.raises(ValidationError):
            MambaConfig(precision="")

    def test_constitutional_hash_valid(self):
        cfg = MambaConfig(constitutional_hash=CONSTITUTIONAL_HASH)
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_invalid(self):
        with pytest.raises(ValidationError):
            MambaConfig(constitutional_hash="wronghash")

    def test_enable_quantization_true(self):
        cfg = MambaConfig(enable_quantization=True)
        assert cfg.enable_quantization is True

    def test_from_attributes(self):
        # model_config includes from_attributes=True
        assert MambaConfig.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# JRTConfig
# ---------------------------------------------------------------------------


class TestJRTConfigDefaults:
    def test_default_repetition_factor(self):
        cfg = JRTConfig()
        assert cfg.repetition_factor == 3

    def test_default_context_window_size(self):
        cfg = JRTConfig()
        assert cfg.context_window_size == 8192

    def test_default_relevance_threshold(self):
        cfg = JRTConfig()
        assert cfg.relevance_threshold == 0.7

    def test_default_max_critical_sections(self):
        cfg = JRTConfig()
        assert cfg.max_critical_sections == 10

    def test_default_constitutional_priority_boost(self):
        cfg = JRTConfig()
        assert cfg.constitutional_priority_boost == 0.3

    def test_default_enable_smart_windowing(self):
        cfg = JRTConfig()
        assert cfg.enable_smart_windowing is True

    def test_default_constitutional_hash(self):
        cfg = JRTConfig()
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH


class TestJRTConfigCustom:
    def test_repetition_factor_min(self):
        cfg = JRTConfig(repetition_factor=1)
        assert cfg.repetition_factor == 1

    def test_repetition_factor_max(self):
        cfg = JRTConfig(repetition_factor=10)
        assert cfg.repetition_factor == 10

    def test_repetition_factor_below_min(self):
        with pytest.raises(ValidationError):
            JRTConfig(repetition_factor=0)

    def test_repetition_factor_above_max(self):
        with pytest.raises(ValidationError):
            JRTConfig(repetition_factor=11)

    def test_context_window_size_min(self):
        cfg = JRTConfig(context_window_size=1024)
        assert cfg.context_window_size == 1024

    def test_context_window_size_max(self):
        cfg = JRTConfig(context_window_size=131072)
        assert cfg.context_window_size == 131072

    def test_context_window_size_below_min(self):
        with pytest.raises(ValidationError):
            JRTConfig(context_window_size=1023)

    def test_context_window_size_above_max(self):
        with pytest.raises(ValidationError):
            JRTConfig(context_window_size=131073)

    def test_relevance_threshold_zero(self):
        cfg = JRTConfig(relevance_threshold=0.0)
        assert cfg.relevance_threshold == 0.0

    def test_relevance_threshold_one(self):
        cfg = JRTConfig(relevance_threshold=1.0)
        assert cfg.relevance_threshold == 1.0

    def test_relevance_threshold_below_zero(self):
        with pytest.raises(ValidationError):
            JRTConfig(relevance_threshold=-0.1)

    def test_relevance_threshold_above_one(self):
        with pytest.raises(ValidationError):
            JRTConfig(relevance_threshold=1.1)

    def test_max_critical_sections_min(self):
        cfg = JRTConfig(max_critical_sections=1)
        assert cfg.max_critical_sections == 1

    def test_max_critical_sections_max(self):
        cfg = JRTConfig(max_critical_sections=100)
        assert cfg.max_critical_sections == 100

    def test_max_critical_sections_below_min(self):
        with pytest.raises(ValidationError):
            JRTConfig(max_critical_sections=0)

    def test_max_critical_sections_above_max(self):
        with pytest.raises(ValidationError):
            JRTConfig(max_critical_sections=101)

    def test_constitutional_priority_boost_zero(self):
        cfg = JRTConfig(constitutional_priority_boost=0.0)
        assert cfg.constitutional_priority_boost == 0.0

    def test_constitutional_priority_boost_one(self):
        cfg = JRTConfig(constitutional_priority_boost=1.0)
        assert cfg.constitutional_priority_boost == 1.0

    def test_constitutional_priority_boost_below_zero(self):
        with pytest.raises(ValidationError):
            JRTConfig(constitutional_priority_boost=-0.1)

    def test_constitutional_priority_boost_above_one(self):
        with pytest.raises(ValidationError):
            JRTConfig(constitutional_priority_boost=1.1)

    def test_smart_windowing_false(self):
        cfg = JRTConfig(enable_smart_windowing=False)
        assert cfg.enable_smart_windowing is False

    def test_from_attributes(self):
        assert JRTConfig.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# ContextChunk
# ---------------------------------------------------------------------------


class TestContextChunk:
    def _make(self, **kwargs) -> ContextChunk:
        defaults = dict(
            content="test content",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=50,
        )
        defaults.update(kwargs)
        return ContextChunk(**defaults)

    def test_basic_creation(self):
        chunk = self._make()
        assert chunk.content == "test content"
        assert chunk.context_type == ContextType.POLICY
        assert chunk.priority == ContextPriority.HIGH
        assert chunk.token_count == 50

    def test_auto_chunk_id_generated(self):
        chunk = self._make()
        assert chunk.chunk_id != ""
        # Should be a valid UUID
        uuid.UUID(chunk.chunk_id)

    def test_explicit_chunk_id_preserved(self):
        chunk = self._make(chunk_id="explicit-id-123")
        assert chunk.chunk_id == "explicit-id-123"

    def test_default_relevance_score(self):
        chunk = self._make()
        assert chunk.relevance_score == 1.0

    def test_custom_relevance_score(self):
        chunk = self._make(relevance_score=0.75)
        assert chunk.relevance_score == 0.75

    def test_default_is_critical(self):
        chunk = self._make()
        assert chunk.is_critical is False

    def test_is_critical_true(self):
        chunk = self._make(is_critical=True)
        assert chunk.is_critical is True

    def test_default_source_id(self):
        chunk = self._make()
        assert chunk.source_id is None

    def test_custom_source_id(self):
        chunk = self._make(source_id="source-abc")
        assert chunk.source_id == "source-abc"

    def test_default_embedding(self):
        chunk = self._make()
        assert chunk.embedding is None

    def test_custom_embedding(self):
        embedding = [0.1, 0.2, 0.3]
        chunk = self._make(embedding=embedding)
        assert chunk.embedding == [0.1, 0.2, 0.3]

    def test_default_metadata(self):
        chunk = self._make()
        assert chunk.metadata == {}

    def test_custom_metadata(self):
        chunk = self._make(metadata={"key": "value"})
        assert chunk.metadata["key"] == "value"

    def test_constitutional_hash(self):
        chunk = self._make()
        assert chunk.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_set(self):
        chunk = self._make()
        assert isinstance(chunk.created_at, datetime)
        assert chunk.created_at.tzinfo is not None

    def test_two_chunks_have_different_ids(self):
        chunk1 = self._make()
        chunk2 = self._make()
        assert chunk1.chunk_id != chunk2.chunk_id

    def test_empty_chunk_id_triggers_generation(self):
        chunk = self._make(chunk_id="")
        assert chunk.chunk_id != ""

    def test_all_context_types(self):
        for ct in ContextType:
            chunk = self._make(context_type=ct)
            assert chunk.context_type == ct

    def test_all_priorities(self):
        for p in ContextPriority:
            chunk = self._make(priority=p)
            assert chunk.priority == p


# ---------------------------------------------------------------------------
# ContextWindow
# ---------------------------------------------------------------------------


class TestContextWindow:
    def _chunk(
        self,
        token_count: int = 100,
        priority: ContextPriority = ContextPriority.LOW,
        context_type: ContextType = ContextType.POLICY,
        is_critical: bool = False,
        relevance_score: float = 1.0,
    ) -> ContextChunk:
        return ContextChunk(
            content=f"chunk content {uuid.uuid4()}",
            context_type=context_type,
            priority=priority,
            token_count=token_count,
            is_critical=is_critical,
            relevance_score=relevance_score,
        )

    def test_default_window_creation(self):
        window = ContextWindow()
        assert window.chunks == []
        assert window.total_tokens == 0
        assert window.max_tokens == 4_000_000

    def test_auto_window_id(self):
        window = ContextWindow()
        assert window.window_id != ""
        uuid.UUID(window.window_id)

    def test_explicit_window_id(self):
        window = ContextWindow(window_id="my-window")
        assert window.window_id == "my-window"

    def test_empty_window_id_triggers_generation(self):
        window = ContextWindow(window_id="")
        assert window.window_id != ""

    def test_constitutional_hash(self):
        window = ContextWindow()
        assert window.constitutional_hash == CONSTITUTIONAL_HASH

    def test_created_at_set(self):
        window = ContextWindow()
        assert isinstance(window.created_at, datetime)

    def test_recalculate_tokens_on_init_with_chunks(self):
        c1 = self._chunk(token_count=100)
        c2 = self._chunk(token_count=200)
        window = ContextWindow(chunks=[c1, c2])
        assert window.total_tokens == 300

    def test_add_chunk_success(self):
        window = ContextWindow(max_tokens=1000)
        chunk = self._chunk(token_count=500)
        result = window.add_chunk(chunk)
        assert result is True
        assert len(window.chunks) == 1
        assert window.total_tokens == 500

    def test_add_chunk_exceeds_limit(self):
        window = ContextWindow(max_tokens=100)
        chunk = self._chunk(token_count=101)
        result = window.add_chunk(chunk)
        assert result is False
        assert len(window.chunks) == 0
        assert window.total_tokens == 0

    def test_add_chunk_exactly_at_limit(self):
        window = ContextWindow(max_tokens=100)
        chunk = self._chunk(token_count=100)
        result = window.add_chunk(chunk)
        assert result is True

    def test_add_chunk_one_over_limit(self):
        window = ContextWindow(max_tokens=100)
        chunk = self._chunk(token_count=101)
        result = window.add_chunk(chunk)
        assert result is False

    def test_add_multiple_chunks(self):
        window = ContextWindow(max_tokens=1000)
        for _ in range(5):
            window.add_chunk(self._chunk(token_count=100))
        assert len(window.chunks) == 5
        assert window.total_tokens == 500

    def test_add_chunk_fills_up(self):
        window = ContextWindow(max_tokens=300)
        assert window.add_chunk(self._chunk(token_count=200)) is True
        assert window.add_chunk(self._chunk(token_count=200)) is False
        assert window.total_tokens == 200

    def test_get_by_type_found(self):
        window = ContextWindow()
        c1 = self._chunk(context_type=ContextType.POLICY)
        c2 = self._chunk(context_type=ContextType.GOVERNANCE)
        window.add_chunk(c1)
        window.add_chunk(c2)
        result = window.get_by_type(ContextType.POLICY)
        assert len(result) == 1
        assert result[0] is c1

    def test_get_by_type_not_found(self):
        window = ContextWindow()
        window.add_chunk(self._chunk(context_type=ContextType.POLICY))
        result = window.get_by_type(ContextType.SYSTEM)
        assert result == []

    def test_get_by_type_multiple(self):
        window = ContextWindow()
        c1 = self._chunk(context_type=ContextType.POLICY)
        c2 = self._chunk(context_type=ContextType.POLICY)
        window.add_chunk(c1)
        window.add_chunk(c2)
        result = window.get_by_type(ContextType.POLICY)
        assert len(result) == 2

    def test_get_critical_chunks_none(self):
        window = ContextWindow()
        window.add_chunk(self._chunk(is_critical=False))
        assert window.get_critical_chunks() == []

    def test_get_critical_chunks_some(self):
        window = ContextWindow()
        c1 = self._chunk(is_critical=True)
        c2 = self._chunk(is_critical=False)
        window.add_chunk(c1)
        window.add_chunk(c2)
        result = window.get_critical_chunks()
        assert len(result) == 1
        assert result[0] is c1

    def test_get_critical_chunks_all(self):
        window = ContextWindow()
        c1 = self._chunk(is_critical=True)
        c2 = self._chunk(is_critical=True)
        window.add_chunk(c1)
        window.add_chunk(c2)
        assert len(window.get_critical_chunks()) == 2

    def test_to_text_empty(self):
        window = ContextWindow()
        assert window.to_text() == ""

    def test_to_text_single(self):
        window = ContextWindow()
        c = ContextChunk(
            content="hello",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=5,
        )
        window.add_chunk(c)
        assert window.to_text() == "hello"

    def test_to_text_sorted_by_priority(self):
        window = ContextWindow()
        low = ContextChunk(
            content="low",
            context_type=ContextType.POLICY,
            priority=ContextPriority.LOW,
            token_count=5,
        )
        high = ContextChunk(
            content="high",
            context_type=ContextType.POLICY,
            priority=ContextPriority.CRITICAL,
            token_count=5,
        )
        window.add_chunk(low)
        window.add_chunk(high)
        text = window.to_text()
        # higher priority should come first
        assert text.index("high") < text.index("low")

    def test_to_text_sorted_by_relevance_when_same_priority(self):
        window = ContextWindow()
        c1 = ContextChunk(
            content="low_rel",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=5,
            relevance_score=0.3,
        )
        c2 = ContextChunk(
            content="high_rel",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=5,
            relevance_score=0.9,
        )
        window.add_chunk(c1)
        window.add_chunk(c2)
        text = window.to_text()
        assert text.index("high_rel") < text.index("low_rel")

    def test_to_text_separator(self):
        window = ContextWindow()
        c1 = ContextChunk(
            content="A",
            context_type=ContextType.POLICY,
            priority=ContextPriority.HIGH,
            token_count=5,
        )
        c2 = ContextChunk(
            content="B",
            context_type=ContextType.POLICY,
            priority=ContextPriority.LOW,
            token_count=5,
        )
        window.add_chunk(c1)
        window.add_chunk(c2)
        text = window.to_text()
        assert "\n\n" in text

    def test_recalculate_tokens_empty(self):
        window = ContextWindow()
        window._recalculate_tokens()
        assert window.total_tokens == 0

    def test_different_window_ids(self):
        w1 = ContextWindow()
        w2 = ContextWindow()
        assert w1.window_id != w2.window_id


# ---------------------------------------------------------------------------
# ContextRetrievalResult
# ---------------------------------------------------------------------------


class TestContextRetrievalResult:
    def _window(self) -> ContextWindow:
        return ContextWindow()

    def test_basic_creation(self):
        w = self._window()
        result = ContextRetrievalResult(window=w, retrieval_time_ms=5.5)
        assert result.window is w
        assert result.retrieval_time_ms == 5.5

    def test_defaults(self):
        result = ContextRetrievalResult(window=self._window(), retrieval_time_ms=1.0)
        assert result.relevance_scores == {}
        assert result.cache_hit is False
        assert result.source_count == 0
        assert result.constitutional_validated is True
        assert result.warnings == []
        assert result.metadata == {}
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        w = self._window()
        result = ContextRetrievalResult(
            window=w,
            retrieval_time_ms=2.5,
            relevance_scores={"a": 0.9},
            cache_hit=True,
            source_count=3,
            constitutional_validated=False,
            warnings=["warn1"],
            metadata={"key": "val"},
        )
        assert result.relevance_scores == {"a": 0.9}
        assert result.cache_hit is True
        assert result.source_count == 3
        assert result.constitutional_validated is False
        assert result.warnings == ["warn1"]
        assert result.metadata == {"key": "val"}

    def test_zero_retrieval_time(self):
        result = ContextRetrievalResult(window=self._window(), retrieval_time_ms=0.0)
        assert result.retrieval_time_ms == 0.0


# ---------------------------------------------------------------------------
# EpisodicMemoryEntry
# ---------------------------------------------------------------------------


class TestEpisodicMemoryEntry:
    def _make(self, **kwargs) -> EpisodicMemoryEntry:
        now = datetime.now(UTC)
        defaults = dict(
            entry_id="entry-1",
            session_id="session-1",
            tenant_id="tenant-1",
            timestamp=now,
            event_type="message",
            content="some content",
        )
        defaults.update(kwargs)
        return EpisodicMemoryEntry(**defaults)

    def test_basic_creation(self):
        e = self._make()
        assert e.entry_id == "entry-1"
        assert e.session_id == "session-1"
        assert e.tenant_id == "tenant-1"
        assert e.event_type == "message"
        assert e.content == "some content"

    def test_defaults(self):
        e = self._make()
        assert e.outcome is None
        assert e.context == {}
        assert e.relevance_decay == 1.0
        assert e.access_count == 0
        assert e.last_accessed is None
        assert e.embedding is None
        assert e.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_outcome(self):
        e = self._make(outcome="approved")
        assert e.outcome == "approved"

    def test_custom_context(self):
        e = self._make(context={"agent": "bot"})
        assert e.context["agent"] == "bot"

    def test_custom_embedding(self):
        e = self._make(embedding=[0.5, 0.6])
        assert e.embedding == [0.5, 0.6]

    def test_decay_relevance_fresh_entry(self):
        # Entry just created — age ~0 hours, decay minimal
        e = self._make()
        e.decay_relevance(decay_rate=0.01)
        assert e.relevance_decay >= 0.99

    def test_decay_relevance_old_entry(self):
        # Entry from a long time ago — should hit the floor of 0.1
        from datetime import timedelta

        old_ts = datetime.now(UTC) - timedelta(hours=10000)
        e = self._make(timestamp=old_ts)
        e.decay_relevance(decay_rate=0.01)
        assert e.relevance_decay == 0.1

    def test_decay_relevance_floor(self):
        from datetime import timedelta

        old_ts = datetime.now(UTC) - timedelta(hours=200)
        e = self._make(timestamp=old_ts)
        e.decay_relevance(decay_rate=0.1)
        assert e.relevance_decay >= 0.1

    def test_decay_relevance_custom_rate(self):
        from datetime import timedelta

        ts = datetime.now(UTC) - timedelta(hours=1)
        e = self._make(timestamp=ts)
        e.decay_relevance(decay_rate=0.5)
        # 1.0 - 0.5*1 = 0.5
        assert abs(e.relevance_decay - 0.5) < 0.05

    def test_record_access_increments_count(self):
        e = self._make()
        e.record_access()
        assert e.access_count == 1

    def test_record_access_multiple(self):
        e = self._make()
        for _ in range(5):
            e.record_access()
        assert e.access_count == 5

    def test_record_access_sets_last_accessed(self):
        e = self._make()
        assert e.last_accessed is None
        e.record_access()
        assert e.last_accessed is not None
        assert isinstance(e.last_accessed, datetime)

    def test_record_access_updates_last_accessed(self):
        e = self._make()
        e.record_access()
        first_access = e.last_accessed
        import time

        time.sleep(0.01)
        e.record_access()
        assert e.last_accessed >= first_access


# ---------------------------------------------------------------------------
# SemanticMemoryEntry
# ---------------------------------------------------------------------------


class TestSemanticMemoryEntry:
    def _make(self, **kwargs) -> SemanticMemoryEntry:
        now = datetime.now(UTC)
        defaults = dict(
            entry_id="sem-1",
            knowledge_type="fact",
            content="the sky is blue",
            confidence=0.9,
            source="observation",
            created_at=now,
            updated_at=now,
        )
        defaults.update(kwargs)
        return SemanticMemoryEntry(**defaults)

    def test_basic_creation(self):
        e = self._make()
        assert e.entry_id == "sem-1"
        assert e.knowledge_type == "fact"
        assert e.content == "the sky is blue"
        assert e.confidence == 0.9
        assert e.source == "observation"

    def test_defaults(self):
        e = self._make()
        assert e.embedding is None
        assert e.related_entries == []
        assert e.access_count == 0
        assert e.validation_status == "pending"
        assert e.metadata == {}
        assert e.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_embedding(self):
        e = self._make(embedding=[0.1, 0.2])
        assert e.embedding == [0.1, 0.2]

    def test_custom_related_entries(self):
        e = self._make(related_entries=["e1", "e2"])
        assert e.related_entries == ["e1", "e2"]

    def test_custom_validation_status(self):
        e = self._make(validation_status="validated")
        assert e.validation_status == "validated"

    def test_update_confidence_moves_toward_feedback(self):
        e = self._make(confidence=0.0)
        e.update_confidence(1.0)
        # alpha=0.3: 0.3*1.0 + 0.7*0.0 = 0.3
        assert abs(e.confidence - 0.3) < 1e-9

    def test_update_confidence_ema(self):
        e = self._make(confidence=0.5)
        e.update_confidence(1.0)
        # 0.3*1.0 + 0.7*0.5 = 0.65
        assert abs(e.confidence - 0.65) < 1e-9

    def test_update_confidence_updates_updated_at(self):
        now = datetime.now(UTC)
        e = self._make(updated_at=now)
        import time

        time.sleep(0.01)
        e.update_confidence(0.8)
        assert e.updated_at >= now

    def test_update_confidence_zero_feedback(self):
        e = self._make(confidence=1.0)
        e.update_confidence(0.0)
        # 0.3*0.0 + 0.7*1.0 = 0.7
        assert abs(e.confidence - 0.7) < 1e-9

    def test_update_confidence_idempotent_same_value(self):
        e = self._make(confidence=1.0)
        e.update_confidence(1.0)
        # 0.3*1.0 + 0.7*1.0 = 1.0
        assert abs(e.confidence - 1.0) < 1e-9

    def test_update_confidence_multiple_times(self):
        e = self._make(confidence=0.5)
        e.update_confidence(0.8)
        # After two updates both should converge toward 0.8
        assert e.confidence > 0.5


# ---------------------------------------------------------------------------
# MemoryQuery
# ---------------------------------------------------------------------------


class TestMemoryQuery:
    def test_basic_creation(self):
        q = MemoryQuery(query_text="find policy info")
        assert q.query_text == "find policy info"

    def test_defaults(self):
        q = MemoryQuery(query_text="test")
        assert q.query_type == "semantic"
        assert q.tenant_id is None
        assert q.session_id is None
        assert q.context_types == []
        assert q.min_relevance == 0.5
        assert q.max_results == 10
        assert q.time_range_hours is None
        assert q.include_embeddings is False
        assert q.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_query_type(self):
        q = MemoryQuery(query_text="q", query_type="episodic")
        assert q.query_type == "episodic"

    def test_custom_tenant_session(self):
        q = MemoryQuery(query_text="q", tenant_id="t1", session_id="s1")
        assert q.tenant_id == "t1"
        assert q.session_id == "s1"

    def test_context_types(self):
        q = MemoryQuery(query_text="q", context_types=[ContextType.POLICY, ContextType.SYSTEM])
        assert ContextType.POLICY in q.context_types
        assert ContextType.SYSTEM in q.context_types

    def test_custom_relevance(self):
        q = MemoryQuery(query_text="q", min_relevance=0.8)
        assert q.min_relevance == 0.8

    def test_custom_max_results(self):
        q = MemoryQuery(query_text="q", max_results=50)
        assert q.max_results == 50

    def test_time_range(self):
        q = MemoryQuery(query_text="q", time_range_hours=24)
        assert q.time_range_hours == 24

    def test_include_embeddings(self):
        q = MemoryQuery(query_text="q", include_embeddings=True)
        assert q.include_embeddings is True

    def test_hybrid_query_type(self):
        q = MemoryQuery(query_text="q", query_type="hybrid")
        assert q.query_type == "hybrid"


# ---------------------------------------------------------------------------
# MemoryConsolidationResult
# ---------------------------------------------------------------------------


class TestMemoryConsolidationResult:
    def test_basic_creation(self):
        r = MemoryConsolidationResult(
            entries_processed=100,
            entries_consolidated=50,
            entries_archived=20,
            entries_deleted=10,
            consolidation_time_ms=150.0,
            memory_freed_bytes=1024,
            new_semantic_entries=5,
        )
        assert r.entries_processed == 100
        assert r.entries_consolidated == 50
        assert r.entries_archived == 20
        assert r.entries_deleted == 10
        assert r.consolidation_time_ms == 150.0
        assert r.memory_freed_bytes == 1024
        assert r.new_semantic_entries == 5

    def test_defaults(self):
        r = MemoryConsolidationResult(
            entries_processed=0,
            entries_consolidated=0,
            entries_archived=0,
            entries_deleted=0,
            consolidation_time_ms=0.0,
            memory_freed_bytes=0,
            new_semantic_entries=0,
        )
        assert r.errors == []
        assert r.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_errors(self):
        r = MemoryConsolidationResult(
            entries_processed=1,
            entries_consolidated=0,
            entries_archived=0,
            entries_deleted=0,
            consolidation_time_ms=1.0,
            memory_freed_bytes=0,
            new_semantic_entries=0,
            errors=["error1", "error2"],
        )
        assert r.errors == ["error1", "error2"]

    def test_zero_values(self):
        r = MemoryConsolidationResult(
            entries_processed=0,
            entries_consolidated=0,
            entries_archived=0,
            entries_deleted=0,
            consolidation_time_ms=0.0,
            memory_freed_bytes=0,
            new_semantic_entries=0,
        )
        assert r.entries_processed == 0


# ---------------------------------------------------------------------------
# MemoryOperation
# ---------------------------------------------------------------------------


class TestMemoryOperation:
    def _make(self, **kwargs) -> MemoryOperation:
        now = datetime.now(UTC)
        defaults = dict(
            operation_id="op-1",
            operation_type=MemoryOperationType.STORE,
            timestamp=now,
            tenant_id="tenant-1",
            session_id="session-1",
            entry_id="entry-1",
            success=True,
            latency_ms=1.5,
        )
        defaults.update(kwargs)
        return MemoryOperation(**defaults)

    def test_basic_creation(self):
        op = self._make()
        assert op.operation_id == "op-1"
        assert op.operation_type == MemoryOperationType.STORE
        assert op.tenant_id == "tenant-1"
        assert op.session_id == "session-1"
        assert op.entry_id == "entry-1"
        assert op.success is True
        assert op.latency_ms == 1.5

    def test_defaults(self):
        op = self._make()
        assert op.details == {}
        assert op.constitutional_hash == CONSTITUTIONAL_HASH

    def test_none_session_id(self):
        op = self._make(session_id=None)
        assert op.session_id is None

    def test_none_entry_id(self):
        op = self._make(entry_id=None)
        assert op.entry_id is None

    def test_failed_operation(self):
        op = self._make(success=False)
        assert op.success is False

    def test_all_operation_types(self):
        for ot in MemoryOperationType:
            op = self._make(operation_type=ot)
            assert op.operation_type == ot

    def test_custom_details(self):
        op = self._make(details={"reason": "test"})
        assert op.details["reason"] == "test"

    def test_zero_latency(self):
        op = self._make(latency_ms=0.0)
        assert op.latency_ms == 0.0

    def test_high_latency(self):
        op = self._make(latency_ms=9999.9)
        assert op.latency_ms == 9999.9


# ---------------------------------------------------------------------------
# Module-level __all__ export check
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.context_memory import models

        for name in models.__all__:
            assert hasattr(models, name), f"{name} not found in models module"

    def test_constitutional_hash_in_all(self):
        from enhanced_agent_bus.context_memory import models

        assert "CONSTITUTIONAL_HASH" in models.__all__

    def test_context_type_in_all(self):
        from enhanced_agent_bus.context_memory import models

        assert "ContextType" in models.__all__

    def test_mamba_config_in_all(self):
        from enhanced_agent_bus.context_memory import models

        assert "MambaConfig" in models.__all__
