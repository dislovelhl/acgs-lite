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

from context_memory.models import (
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
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestContextType:
    def test_all_values(self):
        assert ContextType.CONSTITUTIONAL == "constitutional"
        assert ContextType.POLICY == "policy"
        assert ContextType.GOVERNANCE == "governance"
        assert ContextType.SEMANTIC == "semantic"
        assert ContextType.EPISODIC == "episodic"
        assert ContextType.WORKING == "working"
        assert ContextType.SYSTEM == "system"

    def test_is_str_enum(self):
        assert isinstance(ContextType.CONSTITUTIONAL, str)

    def test_membership(self):
        assert "constitutional" in [ct.value for ct in ContextType]
        assert len(list(ContextType)) == 7


class TestContextPriority:
    def test_all_values(self):
        assert ContextPriority.CRITICAL == 4
        assert ContextPriority.HIGH == 3
        assert ContextPriority.MEDIUM == 2
        assert ContextPriority.LOW == 1
        assert ContextPriority.BACKGROUND == 0

    def test_is_int_enum(self):
        assert isinstance(ContextPriority.CRITICAL, int)

    def test_ordering(self):
        assert ContextPriority.CRITICAL > ContextPriority.HIGH
        assert ContextPriority.HIGH > ContextPriority.MEDIUM
        assert ContextPriority.MEDIUM > ContextPriority.LOW
        assert ContextPriority.LOW > ContextPriority.BACKGROUND

    def test_membership(self):
        assert len(list(ContextPriority)) == 5


class TestMemoryOperationType:
    def test_all_values(self):
        assert MemoryOperationType.STORE == "store"
        assert MemoryOperationType.RETRIEVE == "retrieve"
        assert MemoryOperationType.UPDATE == "update"
        assert MemoryOperationType.DELETE == "delete"
        assert MemoryOperationType.CONSOLIDATE == "consolidate"
        assert MemoryOperationType.SEARCH == "search"
        assert MemoryOperationType.CACHE_HIT == "cache_hit"
        assert MemoryOperationType.CACHE_MISS == "cache_miss"

    def test_is_str_enum(self):
        assert isinstance(MemoryOperationType.STORE, str)

    def test_membership(self):
        assert len(list(MemoryOperationType)) == 8


# ---------------------------------------------------------------------------
# MambaConfig
# ---------------------------------------------------------------------------


class TestMambaConfig:
    def test_defaults(self):
        cfg = MambaConfig()
        assert cfg.d_model == 256
        assert cfg.d_state == 128
        assert cfg.num_layers == 6
        assert cfg.expand_factor == 2
        assert cfg.max_context_length == 4_000_000
        assert cfg.precision == "float32"
        assert cfg.enable_quantization is False
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = MambaConfig(
            d_model=512,
            d_state=256,
            num_layers=12,
            expand_factor=4,
            max_context_length=8_000_000,
            precision="float16",
            enable_quantization=True,
        )
        assert cfg.d_model == 512
        assert cfg.d_state == 256
        assert cfg.num_layers == 12
        assert cfg.expand_factor == 4
        assert cfg.max_context_length == 8_000_000
        assert cfg.precision == "float16"
        assert cfg.enable_quantization is True

    def test_bfloat16_precision(self):
        cfg = MambaConfig(precision="bfloat16")
        assert cfg.precision == "bfloat16"

    def test_invalid_precision(self):
        with pytest.raises(ValidationError) as exc_info:
            MambaConfig(precision="int8")
        assert "Precision must be one of" in str(exc_info.value)

    def test_invalid_constitutional_hash(self):
        with pytest.raises(ValidationError) as exc_info:
            MambaConfig(constitutional_hash="deadbeef")
        assert "Invalid constitutional hash" in str(exc_info.value)

    def test_d_model_min_boundary(self):
        cfg = MambaConfig(d_model=64)
        assert cfg.d_model == 64

    def test_d_model_max_boundary(self):
        cfg = MambaConfig(d_model=4096)
        assert cfg.d_model == 4096

    def test_d_model_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_model=63)

    def test_d_model_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_model=4097)

    def test_d_state_min_boundary(self):
        cfg = MambaConfig(d_state=32)
        assert cfg.d_state == 32

    def test_d_state_max_boundary(self):
        cfg = MambaConfig(d_state=512)
        assert cfg.d_state == 512

    def test_d_state_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_state=31)

    def test_d_state_above_max(self):
        with pytest.raises(ValidationError):
            MambaConfig(d_state=513)

    def test_num_layers_min_boundary(self):
        cfg = MambaConfig(num_layers=1)
        assert cfg.num_layers == 1

    def test_num_layers_max_boundary(self):
        cfg = MambaConfig(num_layers=24)
        assert cfg.num_layers == 24

    def test_num_layers_below_min(self):
        with pytest.raises(ValidationError):
            MambaConfig(num_layers=0)

    def test_expand_factor_min_boundary(self):
        cfg = MambaConfig(expand_factor=1)
        assert cfg.expand_factor == 1

    def test_expand_factor_max_boundary(self):
        cfg = MambaConfig(expand_factor=4)
        assert cfg.expand_factor == 4

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

    def test_from_attributes_config(self):
        # model_config includes from_attributes=True
        assert MambaConfig.model_config.get("from_attributes") is True

    def test_serialization(self):
        cfg = MambaConfig()
        data = cfg.model_dump()
        assert data["d_model"] == 256
        assert data["precision"] == "float32"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# JRTConfig
# ---------------------------------------------------------------------------


class TestJRTConfig:
    def test_defaults(self):
        cfg = JRTConfig()
        assert cfg.repetition_factor == 3
        assert cfg.context_window_size == 8192
        assert cfg.relevance_threshold == 0.7
        assert cfg.max_critical_sections == 10
        assert cfg.constitutional_priority_boost == 0.3
        assert cfg.enable_smart_windowing is True
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = JRTConfig(
            repetition_factor=5,
            context_window_size=16384,
            relevance_threshold=0.9,
            max_critical_sections=50,
            constitutional_priority_boost=0.5,
            enable_smart_windowing=False,
        )
        assert cfg.repetition_factor == 5
        assert cfg.context_window_size == 16384
        assert cfg.relevance_threshold == 0.9
        assert cfg.max_critical_sections == 50
        assert cfg.constitutional_priority_boost == 0.5
        assert cfg.enable_smart_windowing is False

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

    def test_relevance_threshold_min(self):
        cfg = JRTConfig(relevance_threshold=0.0)
        assert cfg.relevance_threshold == 0.0

    def test_relevance_threshold_max(self):
        cfg = JRTConfig(relevance_threshold=1.0)
        assert cfg.relevance_threshold == 1.0

    def test_relevance_threshold_below_min(self):
        with pytest.raises(ValidationError):
            JRTConfig(relevance_threshold=-0.1)

    def test_relevance_threshold_above_max(self):
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

    def test_constitutional_priority_boost_min(self):
        cfg = JRTConfig(constitutional_priority_boost=0.0)
        assert cfg.constitutional_priority_boost == 0.0

    def test_constitutional_priority_boost_max(self):
        cfg = JRTConfig(constitutional_priority_boost=1.0)
        assert cfg.constitutional_priority_boost == 1.0

    def test_from_attributes_config(self):
        assert JRTConfig.model_config.get("from_attributes") is True

    def test_serialization(self):
        cfg = JRTConfig()
        data = cfg.model_dump()
        assert data["repetition_factor"] == 3
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# ContextChunk
# ---------------------------------------------------------------------------


class TestContextChunk:
    def _make_chunk(self, **kwargs) -> ContextChunk:
        defaults = dict(
            content="hello world",
            context_type=ContextType.WORKING,
            priority=ContextPriority.LOW,
            token_count=10,
        )
        defaults.update(kwargs)
        return ContextChunk(**defaults)

    def test_basic_creation(self):
        chunk = self._make_chunk()
        assert chunk.content == "hello world"
        assert chunk.context_type == ContextType.WORKING
        assert chunk.priority == ContextPriority.LOW
        assert chunk.token_count == 10

    def test_defaults(self):
        chunk = self._make_chunk()
        assert chunk.relevance_score == 1.0
        assert chunk.is_critical is False
        assert chunk.source_id is None
        assert chunk.embedding is None
        assert chunk.metadata == {}
        assert chunk.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(chunk.created_at, datetime)

    def test_chunk_id_auto_generated(self):
        chunk = self._make_chunk()
        assert chunk.chunk_id != ""
        # Validate it looks like a UUID
        uuid.UUID(chunk.chunk_id)

    def test_chunk_id_provided(self):
        chunk = self._make_chunk(chunk_id="custom-id-123")
        assert chunk.chunk_id == "custom-id-123"

    def test_chunk_id_not_overwritten_when_provided(self):
        provided = str(uuid.uuid4())
        chunk = self._make_chunk(chunk_id=provided)
        assert chunk.chunk_id == provided

    def test_two_chunks_have_different_ids(self):
        c1 = self._make_chunk()
        c2 = self._make_chunk()
        assert c1.chunk_id != c2.chunk_id

    def test_embedding_can_be_set(self):
        chunk = self._make_chunk(embedding=[0.1, 0.2, 0.3])
        assert chunk.embedding == [0.1, 0.2, 0.3]

    def test_source_id_can_be_set(self):
        chunk = self._make_chunk(source_id="src-001")
        assert chunk.source_id == "src-001"

    def test_metadata_can_be_set(self):
        chunk = self._make_chunk(metadata={"key": "value"})
        assert chunk.metadata == {"key": "value"}

    def test_is_critical_flag(self):
        chunk = self._make_chunk(is_critical=True)
        assert chunk.is_critical is True

    def test_all_context_types(self):
        for ct in ContextType:
            chunk = self._make_chunk(context_type=ct)
            assert chunk.context_type == ct

    def test_all_priorities(self):
        for p in ContextPriority:
            chunk = self._make_chunk(priority=p)
            assert chunk.priority == p

    def test_created_at_is_utc(self):
        chunk = self._make_chunk()
        assert chunk.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# ContextWindow
# ---------------------------------------------------------------------------


class TestContextWindow:
    def _make_chunk(self, token_count: int = 10, **kwargs) -> ContextChunk:
        return ContextChunk(
            content="content",
            context_type=ContextType.WORKING,
            priority=ContextPriority.LOW,
            token_count=token_count,
            **kwargs,
        )

    def test_default_creation(self):
        window = ContextWindow()
        assert window.chunks == []
        assert window.total_tokens == 0
        assert window.max_tokens == 4_000_000
        assert window.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(window.created_at, datetime)

    def test_window_id_auto_generated(self):
        window = ContextWindow()
        assert window.window_id != ""
        uuid.UUID(window.window_id)

    def test_window_id_provided(self):
        window = ContextWindow(window_id="win-abc")
        assert window.window_id == "win-abc"

    def test_two_windows_have_different_ids(self):
        w1 = ContextWindow()
        w2 = ContextWindow()
        assert w1.window_id != w2.window_id

    def test_recalculate_tokens_on_init_empty(self):
        window = ContextWindow()
        assert window.total_tokens == 0

    def test_recalculate_tokens_on_init_with_chunks(self):
        chunks = [self._make_chunk(10), self._make_chunk(20)]
        window = ContextWindow(chunks=chunks)
        assert window.total_tokens == 30

    def test_add_chunk_success(self):
        window = ContextWindow(max_tokens=100)
        chunk = self._make_chunk(token_count=50)
        result = window.add_chunk(chunk)
        assert result is True
        assert len(window.chunks) == 1
        assert window.total_tokens == 50

    def test_add_chunk_exceeds_max(self):
        window = ContextWindow(max_tokens=10)
        chunk = self._make_chunk(token_count=20)
        result = window.add_chunk(chunk)
        assert result is False
        assert len(window.chunks) == 0
        assert window.total_tokens == 0

    def test_add_chunk_exactly_at_limit(self):
        window = ContextWindow(max_tokens=10)
        chunk = self._make_chunk(token_count=10)
        # 0 + 10 > 10 is False, so it should pass
        # Actually condition is: total_tokens + chunk.token_count > max_tokens
        # 0 + 10 > 10 → False, so it fits
        result = window.add_chunk(chunk)
        assert result is True

    def test_add_chunk_one_over_limit(self):
        window = ContextWindow(max_tokens=10)
        chunk = self._make_chunk(token_count=11)
        result = window.add_chunk(chunk)
        assert result is False

    def test_get_by_type(self):
        window = ContextWindow()
        constitutional_chunk = ContextChunk(
            content="c",
            context_type=ContextType.CONSTITUTIONAL,
            priority=ContextPriority.LOW,
            token_count=5,
        )
        policy_chunk = ContextChunk(
            content="p",
            context_type=ContextType.POLICY,
            priority=ContextPriority.LOW,
            token_count=5,
        )
        window.add_chunk(constitutional_chunk)
        window.add_chunk(policy_chunk)

        result = window.get_by_type(ContextType.CONSTITUTIONAL)
        assert len(result) == 1
        assert result[0].context_type == ContextType.CONSTITUTIONAL

    def test_get_by_type_none_found(self):
        window = ContextWindow()
        result = window.get_by_type(ContextType.GOVERNANCE)
        assert result == []

    def test_get_by_type_multiple(self):
        window = ContextWindow()
        for _ in range(3):
            window.add_chunk(
                ContextChunk(
                    content="p",
                    context_type=ContextType.POLICY,
                    priority=ContextPriority.LOW,
                    token_count=1,
                )
            )
        window.add_chunk(
            ContextChunk(
                content="w",
                context_type=ContextType.WORKING,
                priority=ContextPriority.LOW,
                token_count=1,
            )
        )

        result = window.get_by_type(ContextType.POLICY)
        assert len(result) == 3

    def test_get_critical_chunks(self):
        window = ContextWindow()
        critical = self._make_chunk(is_critical=True, token_count=5)
        non_critical = self._make_chunk(is_critical=False, token_count=5)
        window.add_chunk(critical)
        window.add_chunk(non_critical)

        result = window.get_critical_chunks()
        assert len(result) == 1
        assert result[0].is_critical is True

    def test_get_critical_chunks_none(self):
        window = ContextWindow()
        result = window.get_critical_chunks()
        assert result == []

    def test_to_text_empty(self):
        window = ContextWindow()
        assert window.to_text() == ""

    def test_to_text_single_chunk(self):
        window = ContextWindow()
        chunk = self._make_chunk(token_count=5)
        chunk.content = "hello"
        window.add_chunk(chunk)
        assert window.to_text() == "hello"

    def test_to_text_multiple_chunks_joined(self):
        window = ContextWindow()
        c1 = ContextChunk(
            content="low",
            context_type=ContextType.WORKING,
            priority=ContextPriority.LOW,
            token_count=5,
            relevance_score=0.5,
        )
        c2 = ContextChunk(
            content="critical",
            context_type=ContextType.WORKING,
            priority=ContextPriority.CRITICAL,
            token_count=5,
            relevance_score=1.0,
        )
        window.add_chunk(c1)
        window.add_chunk(c2)
        text = window.to_text()
        # Critical/higher priority should come first
        assert text.startswith("critical")
        assert "\n\n" in text

    def test_to_text_sorted_by_priority_then_relevance(self):
        window = ContextWindow()
        c_high = ContextChunk(
            content="high",
            context_type=ContextType.WORKING,
            priority=ContextPriority.HIGH,
            token_count=5,
            relevance_score=0.5,
        )
        c_low = ContextChunk(
            content="low",
            context_type=ContextType.WORKING,
            priority=ContextPriority.LOW,
            token_count=5,
            relevance_score=1.0,
        )
        window.add_chunk(c_high)
        window.add_chunk(c_low)
        text = window.to_text()
        assert text.startswith("high")

    def test_constitutional_hash_default(self):
        window = ContextWindow()
        assert window.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# ContextRetrievalResult
# ---------------------------------------------------------------------------


class TestContextRetrievalResult:
    def _make_window(self) -> ContextWindow:
        return ContextWindow()

    def test_basic_creation(self):
        window = self._make_window()
        result = ContextRetrievalResult(window=window, retrieval_time_ms=12.5)
        assert result.window is window
        assert result.retrieval_time_ms == 12.5

    def test_defaults(self):
        window = self._make_window()
        result = ContextRetrievalResult(window=window, retrieval_time_ms=0.0)
        assert result.relevance_scores == {}
        assert result.cache_hit is False
        assert result.source_count == 0
        assert result.constitutional_validated is True
        assert result.warnings == []
        assert result.metadata == {}
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        window = self._make_window()
        result = ContextRetrievalResult(
            window=window,
            retrieval_time_ms=3.14,
            relevance_scores={"a": 0.9, "b": 0.7},
            cache_hit=True,
            source_count=5,
            constitutional_validated=False,
            warnings=["warn1"],
            metadata={"meta": "data"},
        )
        assert result.relevance_scores == {"a": 0.9, "b": 0.7}
        assert result.cache_hit is True
        assert result.source_count == 5
        assert result.constitutional_validated is False
        assert result.warnings == ["warn1"]
        assert result.metadata == {"meta": "data"}


# ---------------------------------------------------------------------------
# EpisodicMemoryEntry
# ---------------------------------------------------------------------------


class TestEpisodicMemoryEntry:
    def _make_entry(self, **kwargs) -> EpisodicMemoryEntry:
        defaults = dict(
            entry_id="entry-001",
            session_id="session-001",
            tenant_id="tenant-001",
            timestamp=datetime.now(UTC),
            event_type="interaction",
            content="some content",
        )
        defaults.update(kwargs)
        return EpisodicMemoryEntry(**defaults)

    def test_basic_creation(self):
        entry = self._make_entry()
        assert entry.entry_id == "entry-001"
        assert entry.session_id == "session-001"
        assert entry.tenant_id == "tenant-001"
        assert entry.event_type == "interaction"
        assert entry.content == "some content"

    def test_defaults(self):
        entry = self._make_entry()
        assert entry.outcome is None
        assert entry.context == {}
        assert entry.relevance_decay == 1.0
        assert entry.access_count == 0
        assert entry.last_accessed is None
        assert entry.embedding is None
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        entry = self._make_entry(
            outcome="approved",
            context={"key": "val"},
            relevance_decay=0.8,
            access_count=3,
            embedding=[0.1, 0.2],
        )
        assert entry.outcome == "approved"
        assert entry.context == {"key": "val"}
        assert entry.relevance_decay == 0.8
        assert entry.access_count == 3
        assert entry.embedding == [0.1, 0.2]

    def test_decay_relevance_recent_entry(self):
        entry = self._make_entry(timestamp=datetime.now(UTC))
        initial = entry.relevance_decay
        entry.decay_relevance(decay_rate=0.01)
        # Very recent entry, minimal decay
        assert entry.relevance_decay <= initial
        assert entry.relevance_decay >= 0.1

    def test_decay_relevance_old_entry(self):
        # Entry from long ago should decay to 0.1 minimum
        from datetime import timedelta

        old_ts = datetime.now(UTC) - timedelta(hours=1000)
        entry = self._make_entry(timestamp=old_ts)
        entry.decay_relevance(decay_rate=0.01)
        assert entry.relevance_decay == 0.1

    def test_decay_relevance_respects_minimum(self):
        from datetime import timedelta

        very_old = datetime.now(UTC) - timedelta(hours=10000)
        entry = self._make_entry(timestamp=very_old)
        entry.decay_relevance(decay_rate=1.0)
        assert entry.relevance_decay == 0.1

    def test_decay_relevance_default_rate(self):
        entry = self._make_entry(timestamp=datetime.now(UTC))
        entry.decay_relevance()
        assert entry.relevance_decay >= 0.1

    def test_record_access_increments_count(self):
        entry = self._make_entry()
        assert entry.access_count == 0
        entry.record_access()
        assert entry.access_count == 1
        entry.record_access()
        assert entry.access_count == 2

    def test_record_access_sets_last_accessed(self):
        entry = self._make_entry()
        assert entry.last_accessed is None
        before = datetime.now(UTC)
        entry.record_access()
        after = datetime.now(UTC)
        assert entry.last_accessed is not None
        assert before <= entry.last_accessed <= after

    def test_record_access_updates_last_accessed(self):
        entry = self._make_entry()
        entry.record_access()
        first = entry.last_accessed
        entry.record_access()
        second = entry.last_accessed
        assert second >= first  # type: ignore[operator]


# ---------------------------------------------------------------------------
# SemanticMemoryEntry
# ---------------------------------------------------------------------------


class TestSemanticMemoryEntry:
    def _make_entry(self, **kwargs) -> SemanticMemoryEntry:
        now = datetime.now(UTC)
        defaults = dict(
            entry_id="sem-001",
            knowledge_type="fact",
            content="The sky is blue",
            confidence=0.95,
            source="observation",
            created_at=now,
            updated_at=now,
        )
        defaults.update(kwargs)
        return SemanticMemoryEntry(**defaults)

    def test_basic_creation(self):
        entry = self._make_entry()
        assert entry.entry_id == "sem-001"
        assert entry.knowledge_type == "fact"
        assert entry.content == "The sky is blue"
        assert entry.confidence == 0.95
        assert entry.source == "observation"

    def test_defaults(self):
        entry = self._make_entry()
        assert entry.embedding is None
        assert entry.related_entries == []
        assert entry.access_count == 0
        assert entry.validation_status == "pending"
        assert entry.metadata == {}
        assert entry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        entry = self._make_entry(
            embedding=[0.5, 0.6],
            related_entries=["sem-002"],
            access_count=5,
            validation_status="validated",
            metadata={"tags": ["blue"]},
        )
        assert entry.embedding == [0.5, 0.6]
        assert entry.related_entries == ["sem-002"]
        assert entry.access_count == 5
        assert entry.validation_status == "validated"

    def test_update_confidence_basic(self):
        entry = self._make_entry(confidence=0.5)
        entry.update_confidence(feedback=1.0)
        # EMA: alpha=0.3, new = 0.3*1.0 + 0.7*0.5 = 0.3 + 0.35 = 0.65
        assert abs(entry.confidence - 0.65) < 1e-9

    def test_update_confidence_low_feedback(self):
        entry = self._make_entry(confidence=0.8)
        entry.update_confidence(feedback=0.0)
        # EMA: 0.3*0.0 + 0.7*0.8 = 0.56
        assert abs(entry.confidence - 0.56) < 1e-9

    def test_update_confidence_updates_timestamp(self):
        entry = self._make_entry()
        old_ts = entry.updated_at
        entry.update_confidence(feedback=0.9)
        assert entry.updated_at >= old_ts

    def test_update_confidence_multiple_times(self):
        entry = self._make_entry(confidence=0.5)
        for _ in range(5):
            entry.update_confidence(feedback=1.0)
        # After many iterations, confidence should converge toward 1.0
        assert entry.confidence > 0.5


# ---------------------------------------------------------------------------
# MemoryQuery
# ---------------------------------------------------------------------------


class TestMemoryQuery:
    def test_basic_creation(self):
        q = MemoryQuery(query_text="find policy about X")
        assert q.query_text == "find policy about X"

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

    def test_custom_values(self):
        q = MemoryQuery(
            query_text="episodic query",
            query_type="episodic",
            tenant_id="t1",
            session_id="s1",
            context_types=[ContextType.CONSTITUTIONAL, ContextType.POLICY],
            min_relevance=0.8,
            max_results=20,
            time_range_hours=24,
            include_embeddings=True,
        )
        assert q.query_type == "episodic"
        assert q.tenant_id == "t1"
        assert q.session_id == "s1"
        assert q.context_types == [ContextType.CONSTITUTIONAL, ContextType.POLICY]
        assert q.min_relevance == 0.8
        assert q.max_results == 20
        assert q.time_range_hours == 24
        assert q.include_embeddings is True

    def test_hybrid_query_type(self):
        q = MemoryQuery(query_text="hybrid", query_type="hybrid")
        assert q.query_type == "hybrid"

    def test_context_types_all_types(self):
        all_types = list(ContextType)
        q = MemoryQuery(query_text="all", context_types=all_types)
        assert q.context_types == all_types


# ---------------------------------------------------------------------------
# MemoryConsolidationResult
# ---------------------------------------------------------------------------


class TestMemoryConsolidationResult:
    def _make_result(self, **kwargs) -> MemoryConsolidationResult:
        defaults = dict(
            entries_processed=100,
            entries_consolidated=80,
            entries_archived=10,
            entries_deleted=5,
            consolidation_time_ms=250.0,
            memory_freed_bytes=1024,
            new_semantic_entries=15,
        )
        defaults.update(kwargs)
        return MemoryConsolidationResult(**defaults)

    def test_basic_creation(self):
        result = self._make_result()
        assert result.entries_processed == 100
        assert result.entries_consolidated == 80
        assert result.entries_archived == 10
        assert result.entries_deleted == 5
        assert result.consolidation_time_ms == 250.0
        assert result.memory_freed_bytes == 1024
        assert result.new_semantic_entries == 15

    def test_defaults(self):
        result = self._make_result()
        assert result.errors == []
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_errors(self):
        result = self._make_result(errors=["error1", "error2"])
        assert result.errors == ["error1", "error2"]

    def test_zero_values(self):
        result = self._make_result(
            entries_processed=0,
            entries_consolidated=0,
            entries_archived=0,
            entries_deleted=0,
            new_semantic_entries=0,
        )
        assert result.entries_processed == 0


# ---------------------------------------------------------------------------
# MemoryOperation
# ---------------------------------------------------------------------------


class TestMemoryOperation:
    def _make_operation(self, **kwargs) -> MemoryOperation:
        defaults = dict(
            operation_id="op-001",
            operation_type=MemoryOperationType.STORE,
            timestamp=datetime.now(UTC),
            tenant_id="tenant-001",
            session_id="session-001",
            entry_id="entry-001",
            success=True,
            latency_ms=5.0,
        )
        defaults.update(kwargs)
        return MemoryOperation(**defaults)

    def test_basic_creation(self):
        op = self._make_operation()
        assert op.operation_id == "op-001"
        assert op.operation_type == MemoryOperationType.STORE
        assert op.tenant_id == "tenant-001"
        assert op.success is True
        assert op.latency_ms == 5.0

    def test_defaults(self):
        op = self._make_operation()
        assert op.details == {}
        assert op.constitutional_hash == CONSTITUTIONAL_HASH

    def test_optional_fields_none(self):
        op = self._make_operation(session_id=None, entry_id=None)
        assert op.session_id is None
        assert op.entry_id is None

    def test_all_operation_types(self):
        for op_type in MemoryOperationType:
            op = self._make_operation(operation_type=op_type)
            assert op.operation_type == op_type

    def test_failed_operation(self):
        op = self._make_operation(success=False)
        assert op.success is False

    def test_details_can_be_set(self):
        op = self._make_operation(details={"key": "value", "count": 42})
        assert op.details == {"key": "value", "count": 42}

    def test_constitutional_hash(self):
        op = self._make_operation()
        assert op.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        import context_memory.models as m

        for name in m.__all__:
            assert hasattr(m, name), f"Missing export: {name}"

    def test_constitutional_hash_exported(self):
        import context_memory.models as m

        assert m.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_all_classes_importable(self):
        from context_memory.models import (
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

        for cls in [
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
        ]:
            assert cls is not None
