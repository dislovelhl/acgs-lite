"""Tests for enhanced_agent_bus.cognitive.context_inference module."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Import directly from the module file to avoid pulling in graph_rag via __init__.py
_module_path = Path(__file__).resolve().parents[1] / "cognitive" / "context_inference.py"
_spec = importlib.util.spec_from_file_location(
    "enhanced_agent_bus.cognitive.context_inference", _module_path
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def teardown_module() -> None:
    """Remove injected module from sys.modules to avoid polluting other tests."""
    sys.modules.pop(_spec.name, None)


ChunkPriority = _mod.ChunkPriority
ChunkType = _mod.ChunkType
ContextChunk = _mod.ContextChunk
ContextDelta = _mod.ContextDelta
ContextWindow = _mod.ContextWindow
IncrementalContextUpdater = _mod.IncrementalContextUpdater
LongContextManager = _mod.LongContextManager
MultiTurnReasoner = _mod.MultiTurnReasoner
ReasoningChain = _mod.ReasoningChain
ReasoningStep = _mod.ReasoningStep
SimpleTokenCounter = _mod.SimpleTokenCounter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chunk_factory():
    """Return a helper that creates ContextChunk instances with sensible defaults."""
    _counter = 0

    def _make(
        *,
        chunk_type: ChunkType = ChunkType.CONTEXT,
        content: str = "test content",
        token_count: int = 10,
        priority: ChunkPriority = ChunkPriority.MEDIUM,
        metadata: dict | None = None,
    ) -> ContextChunk:
        nonlocal _counter
        _counter += 1
        return ContextChunk(
            chunk_id=f"chunk-{_counter}",
            chunk_type=chunk_type,
            content=content,
            token_count=token_count,
            priority=priority,
            metadata=metadata or {},
        )

    return _make


@pytest.fixture()
def window():
    return ContextWindow(window_id="win-1", max_tokens=100)


@pytest.fixture()
def manager():
    return LongContextManager(max_tokens=200, eviction_threshold=0.9)


@pytest.fixture()
def updater(manager):
    return IncrementalContextUpdater(context_manager=manager)


@pytest.fixture()
def reasoner(manager):
    return MultiTurnReasoner(context_manager=manager)


# ===========================================================================
# ChunkType / ChunkPriority enums
# ===========================================================================


class TestEnums:
    def test_chunk_type_values(self):
        assert ChunkType.SYSTEM.value == "system"
        assert ChunkType.TOOL_RESULT.value == "tool_result"

    def test_chunk_priority_ordering(self):
        assert ChunkPriority.CRITICAL.value < ChunkPriority.HIGH.value
        assert ChunkPriority.HIGH.value < ChunkPriority.MEDIUM.value
        assert ChunkPriority.LOW.value < ChunkPriority.EVICTABLE.value


# ===========================================================================
# ContextChunk
# ===========================================================================


class TestContextChunk:
    def test_to_dict_contains_required_keys(self, chunk_factory):
        chunk = chunk_factory(content="hello world", token_count=5)
        d = chunk.to_dict()

        assert d["chunk_id"] == chunk.chunk_id
        assert d["chunk_type"] == "context"
        assert d["content"] == "hello world"
        assert d["token_count"] == 5
        assert d["priority"] == ChunkPriority.MEDIUM.value
        assert "created_at" in d
        assert "constitutional_hash" in d

    def test_to_dict_excludes_embedding(self, chunk_factory):
        chunk = chunk_factory()
        d = chunk.to_dict()
        assert "embedding" not in d

    def test_touch_updates_access(self, chunk_factory):
        chunk = chunk_factory()
        assert chunk.access_count == 0
        before = chunk.last_accessed

        chunk.touch()

        assert chunk.access_count == 1
        assert chunk.last_accessed >= before

    def test_touch_increments_repeatedly(self, chunk_factory):
        chunk = chunk_factory()
        chunk.touch()
        chunk.touch()
        chunk.touch()
        assert chunk.access_count == 3

    def test_default_embedding_is_none(self, chunk_factory):
        chunk = chunk_factory()
        assert chunk.embedding is None


# ===========================================================================
# ContextWindow
# ===========================================================================


class TestContextWindow:
    def test_add_chunk_success(self, window, chunk_factory):
        chunk = chunk_factory(token_count=50)
        assert window.add_chunk(chunk) is True
        assert window.total_tokens == 50
        assert len(window.chunks) == 1

    def test_add_chunk_exceeds_max_tokens(self, window, chunk_factory):
        chunk = chunk_factory(token_count=101)
        assert window.add_chunk(chunk) is False
        assert window.total_tokens == 0

    def test_add_chunk_exactly_at_limit(self, window, chunk_factory):
        chunk = chunk_factory(token_count=100)
        assert window.add_chunk(chunk) is True
        assert window.total_tokens == 100

    def test_remove_chunk_existing(self, window, chunk_factory):
        chunk = chunk_factory(token_count=30)
        window.add_chunk(chunk)

        assert window.remove_chunk(chunk.chunk_id) is True
        assert window.total_tokens == 0
        assert len(window.chunks) == 0

    def test_remove_chunk_nonexistent(self, window):
        assert window.remove_chunk("nonexistent") is False

    def test_get_chunk_existing_touches(self, window, chunk_factory):
        chunk = chunk_factory(token_count=10)
        window.add_chunk(chunk)

        result = window.get_chunk(chunk.chunk_id)
        assert result is chunk
        assert result.access_count == 1

    def test_get_chunk_nonexistent(self, window):
        assert window.get_chunk("nope") is None

    def test_available_tokens(self, window, chunk_factory):
        assert window.available_tokens() == 100
        window.add_chunk(chunk_factory(token_count=40))
        assert window.available_tokens() == 60

    def test_to_text_joins_contents(self, window, chunk_factory):
        window.add_chunk(chunk_factory(content="alpha", token_count=5))
        window.add_chunk(chunk_factory(content="beta", token_count=5))
        assert window.to_text() == "alpha\n\nbeta"

    def test_to_text_empty(self, window):
        assert window.to_text() == ""

    def test_get_chunks_by_type(self, window, chunk_factory):
        window.add_chunk(chunk_factory(chunk_type=ChunkType.HISTORY, token_count=5))
        window.add_chunk(chunk_factory(chunk_type=ChunkType.POLICY, token_count=5))
        window.add_chunk(chunk_factory(chunk_type=ChunkType.HISTORY, token_count=5))

        history = window.get_chunks_by_type(ChunkType.HISTORY)
        assert len(history) == 2

    def test_get_chunks_by_type_empty(self, window):
        assert window.get_chunks_by_type(ChunkType.SYSTEM) == []


# ===========================================================================
# SimpleTokenCounter
# ===========================================================================


class TestSimpleTokenCounter:
    def test_count_basic(self):
        counter = SimpleTokenCounter()
        result = counter.count("one two three")
        assert result == int(3 * 1.3)

    def test_count_empty_string(self):
        counter = SimpleTokenCounter()
        assert counter.count("") == 0

    def test_count_single_word(self):
        counter = SimpleTokenCounter()
        assert counter.count("hello") == int(1 * 1.3)


# ===========================================================================
# LongContextManager
# ===========================================================================


class TestLongContextManager:
    def test_create_window_with_id(self, manager):
        w = manager.create_window("my-win")
        assert w.window_id == "my-win"
        assert w.max_tokens == 200

    def test_create_window_generates_id(self, manager):
        w = manager.create_window()
        assert len(w.window_id) == 16

    def test_get_window_existing(self, manager):
        w = manager.create_window("w1")
        assert manager.get_window("w1") is w

    def test_get_window_nonexistent(self, manager):
        assert manager.get_window("nope") is None

    def test_add_to_window_success(self, manager):
        manager.create_window("w1")
        chunk = manager.add_to_window("w1", "hello world", ChunkType.USER_INPUT)
        assert chunk is not None
        assert chunk.chunk_type == ChunkType.USER_INPUT
        assert chunk.content == "hello world"

    def test_add_to_window_nonexistent_window(self, manager):
        assert manager.add_to_window("nope", "data", ChunkType.CONTEXT) is None

    def test_add_to_window_with_metadata(self, manager):
        manager.create_window("w1")
        chunk = manager.add_to_window(
            "w1",
            "text",
            ChunkType.POLICY,
            metadata={"key": "value"},
        )
        assert chunk is not None
        assert chunk.metadata == {"key": "value"}

    def test_add_to_window_with_priority(self, manager):
        manager.create_window("w1")
        chunk = manager.add_to_window(
            "w1", "data", ChunkType.CONTEXT, priority=ChunkPriority.CRITICAL
        )
        assert chunk is not None
        assert chunk.priority == ChunkPriority.CRITICAL

    def test_eviction_triggered_when_threshold_exceeded(self):
        # SimpleTokenCounter: int(len(text.split()) * 1.3)
        # Eviction logic: triggers when total + new > max * threshold,
        # then evicts LOW/EVICTABLE chunks until available_tokens >= needed_tokens.
        #
        # Strategy: fill the window near capacity with a CRITICAL chunk, then add
        # a LOW chunk, then try to add more -- the LOW chunk gets evicted to make room.
        mgr = LongContextManager(max_tokens=50, eviction_threshold=0.5)
        mgr.create_window("w1")

        # Fill most of the window with CRITICAL (not evictable)
        # 30 words => int(30*1.3) = 39 tokens
        big_critical = " ".join(["word"] * 30)
        mgr.add_to_window("w1", big_critical, ChunkType.SYSTEM, ChunkPriority.CRITICAL)

        window = mgr.get_window("w1")
        assert window.total_tokens == 39  # 39 used, 11 available

        # Add a small LOW chunk: "a b" => int(2*1.3) = 2 tokens => total 41, avail 9
        mgr.add_to_window("w1", "a b", ChunkType.HISTORY, ChunkPriority.LOW)
        assert window.total_tokens == 41

        # Now add another chunk: "x y z" => int(3*1.3) = 3 tokens
        # Check: 41 + 3 = 44 > 50 * 0.5 = 25 => eviction triggered
        # _evict_chunks needs 3 available tokens; currently 9 available >= 3 => NO eviction
        # Actually we need the window to be so full that available < needed.
        # Let's add a bigger chunk instead: 8 words => int(8*1.3) = 10 tokens
        # 41 + 10 = 51 > 25 triggers eviction; available = 9 < 10 => must evict
        new_text = " ".join(["data"] * 8)
        mgr.add_to_window("w1", new_text, ChunkType.USER_INPUT, ChunkPriority.MEDIUM)

        # The LOW chunk (2 tokens) should have been evicted to free space
        low_chunks = [c for c in window.chunks if c.priority == ChunkPriority.LOW]
        assert len(low_chunks) == 0

    def test_eviction_does_not_evict_critical(self):
        mgr = LongContextManager(max_tokens=50, eviction_threshold=0.5)
        mgr.create_window("w1")

        # Add a CRITICAL chunk
        mgr.add_to_window("w1", "critical", ChunkType.SYSTEM, ChunkPriority.CRITICAL)

        window = mgr.get_window("w1")
        critical_before = len([c for c in window.chunks if c.priority == ChunkPriority.CRITICAL])

        # Try adding more -- eviction should not touch CRITICAL
        mgr.add_to_window("w1", "more data", ChunkType.CONTEXT, ChunkPriority.MEDIUM)

        critical_after = len([c for c in window.chunks if c.priority == ChunkPriority.CRITICAL])
        assert critical_after >= critical_before

    def test_compact_window_nonexistent(self, manager):
        assert manager.compact_window("nope") == 0

    def test_compact_window_few_history_chunks(self, manager):
        manager.create_window("w1")
        for i in range(3):
            manager.add_to_window("w1", f"hist {i}", ChunkType.HISTORY)
        assert manager.compact_window("w1") == 0

    def test_compact_window_summarizes_old_history(self, manager):
        manager.create_window("w1")
        for i in range(8):
            manager.add_to_window("w1", f"history entry {i}", ChunkType.HISTORY)

        window = manager.get_window("w1")
        before_count = len(window.get_chunks_by_type(ChunkType.HISTORY))

        removed = manager.compact_window("w1")
        assert removed > 0

        after_count = len(window.get_chunks_by_type(ChunkType.HISTORY))
        # Should have fewer chunks after compaction (kept last 3 + 1 summary)
        assert after_count < before_count

    def test_summarize_chunks_truncates_long_content(self, manager):
        long_content = "x" * 300
        chunk = ContextChunk(
            chunk_id="c1",
            chunk_type=ChunkType.HISTORY,
            content=long_content,
            token_count=100,
            priority=ChunkPriority.MEDIUM,
        )
        result = manager._summarize_chunks([chunk])
        assert "..." in result
        assert result.startswith("Summary of previous context:")


# ===========================================================================
# ContextDelta dataclass
# ===========================================================================


class TestContextDelta:
    def test_default_fields(self):
        delta = ContextDelta(
            delta_id="d1",
            operation="add",
            chunk_id=None,
            content="some content",
        )
        assert delta.delta_id == "d1"
        assert isinstance(delta.metadata, dict)
        assert isinstance(delta.timestamp, datetime)


# ===========================================================================
# IncrementalContextUpdater
# ===========================================================================


class TestIncrementalContextUpdater:
    def test_apply_delta_add(self, updater, manager):
        manager.create_window("w1")
        delta = updater.apply_delta("w1", "add", content="new data")
        assert delta.operation == "add"
        assert delta.chunk_id is not None

        window = manager.get_window("w1")
        assert len(window.chunks) == 1

    def test_apply_delta_add_no_content(self, updater, manager):
        manager.create_window("w1")
        delta = updater.apply_delta("w1", "add", content=None)
        # No chunk should be added when content is None
        window = manager.get_window("w1")
        assert len(window.chunks) == 0
        assert delta.chunk_id is None

    def test_apply_delta_remove(self, updater, manager):
        manager.create_window("w1")
        add_delta = updater.apply_delta("w1", "add", content="to remove")
        cid = add_delta.chunk_id

        remove_delta = updater.apply_delta("w1", "remove", chunk_id=cid)
        assert remove_delta.operation == "remove"

        window = manager.get_window("w1")
        assert len(window.chunks) == 0

    def test_apply_delta_remove_nonexistent_window(self, updater):
        delta = updater.apply_delta("nope", "remove", chunk_id="c1")
        assert delta.operation == "remove"

    def test_apply_delta_update(self, updater, manager):
        manager.create_window("w1")
        add_delta = updater.apply_delta("w1", "add", content="original")
        old_cid = add_delta.chunk_id

        update_delta = updater.apply_delta(
            "w1", "update", content="updated content", chunk_id=old_cid
        )
        assert update_delta.operation == "update"
        # New chunk_id should differ from old one
        assert update_delta.chunk_id is not None
        assert update_delta.chunk_id != old_cid

        window = manager.get_window("w1")
        assert len(window.chunks) == 1
        assert window.chunks[0].content == "updated content"

    def test_apply_delta_update_nonexistent_chunk(self, updater, manager):
        manager.create_window("w1")
        delta = updater.apply_delta("w1", "update", content="new", chunk_id="bogus")
        # get_chunk returns None for "bogus", so no update happens
        assert delta.operation == "update"

    def test_apply_delta_update_nonexistent_window(self, updater):
        delta = updater.apply_delta("nope", "update", content="x", chunk_id="c1")
        assert delta.operation == "update"

    def test_apply_delta_unknown_operation(self, updater, manager):
        manager.create_window("w1")
        delta = updater.apply_delta("w1", "unknown_op", content="x")
        assert delta.operation == "unknown_op"
        # Should still record the delta
        deltas = updater.get_deltas("w1")
        assert len(deltas) == 1

    def test_get_deltas_empty(self, updater):
        assert updater.get_deltas("w1") == []

    def test_get_deltas_since_filter(self, updater, manager):
        manager.create_window("w1")
        updater.apply_delta("w1", "add", content="first")

        cutoff = datetime.now(UTC)

        updater.apply_delta("w1", "add", content="second")

        all_deltas = updater.get_deltas("w1")
        assert len(all_deltas) == 2

        recent = updater.get_deltas("w1", since=cutoff)
        assert len(recent) == 1

    def test_replay_deltas(self, updater, manager):
        manager.create_window("w1")
        manager.create_window("w2")

        updater.apply_delta("w1", "add", content="data A")
        updater.apply_delta("w1", "add", content="data B")

        deltas = updater.get_deltas("w1")
        results = updater.replay_deltas("w2", deltas)
        assert len(results) == 2

        window2 = manager.get_window("w2")
        assert len(window2.chunks) == 2


# ===========================================================================
# ReasoningStep / ReasoningChain
# ===========================================================================


class TestReasoningChain:
    def test_add_step_accumulates_tokens(self):
        chain = ReasoningChain(chain_id="rc-1", window_id="w1")
        step = ReasoningStep(
            step_id="s1",
            step_type="inference",
            input_context="ctx",
            output="result",
            confidence=0.9,
            token_usage=50,
        )
        chain.add_step(step)
        assert chain.total_tokens == 50
        assert len(chain.steps) == 1

    def test_add_multiple_steps(self):
        chain = ReasoningChain(chain_id="rc-1", window_id="w1")
        for i in range(3):
            chain.add_step(
                ReasoningStep(
                    step_id=f"s{i}",
                    step_type="inference",
                    input_context="",
                    output="",
                    confidence=0.8,
                    token_usage=10,
                )
            )
        assert chain.total_tokens == 30
        assert len(chain.steps) == 3


# ===========================================================================
# MultiTurnReasoner
# ===========================================================================


class TestMultiTurnReasoner:
    def test_start_chain(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        assert chain.window_id == "w1"
        assert len(chain.chain_id) == 16

    def test_reason_step_without_provider(self, reasoner, manager):
        manager.create_window("w1")
        manager.add_to_window("w1", "some context", ChunkType.CONTEXT)

        chain = reasoner.start_chain("w1")
        step = reasoner.reason_step(chain.chain_id, "What is this about?")

        assert step is not None
        assert "[Mock inference for:" in step.output
        assert step.step_type == "inference"
        assert chain.total_tokens == step.token_usage

    def test_reason_step_with_provider(self, manager):
        class FakeProvider:
            def infer(self, context: str, prompt: str) -> tuple[str, int]:
                return ("provider answer", 42)

        reasoner = MultiTurnReasoner(
            context_manager=manager,
            inference_provider=FakeProvider(),
        )
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        step = reasoner.reason_step(chain.chain_id, "test prompt")

        assert step is not None
        assert step.output == "provider answer"
        assert step.token_usage == 42

    def test_reason_step_nonexistent_chain(self, reasoner):
        assert reasoner.reason_step("no-chain", "prompt") is None

    def test_reason_step_nonexistent_window(self, reasoner, manager):
        # Start chain with a window, then remove the window reference
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        # Directly remove the window to simulate missing window
        del manager._windows["w1"]

        assert reasoner.reason_step(chain.chain_id, "prompt") is None

    def test_reason_step_truncates_long_context(self, manager):
        # Use a large max_tokens so the content actually fits in the window
        big_manager = LongContextManager(max_tokens=500_000)
        big_manager.create_window("w1")
        # 200 repetitions of a 10-char word => 2000+ chars, well over 500
        long_text = " ".join(["longword01"] * 200)
        big_manager.add_to_window("w1", long_text, ChunkType.CONTEXT)

        reasoner = MultiTurnReasoner(context_manager=big_manager)
        chain = reasoner.start_chain("w1")
        step = reasoner.reason_step(chain.chain_id, "analyze")
        assert step is not None
        assert step.input_context.endswith("...")
        assert len(step.input_context) <= 504  # 500 + "..."

    def test_finalize_chain(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        reasoner.reason_step(chain.chain_id, "do something")

        result = reasoner.finalize_chain(chain.chain_id)
        assert result is not None
        assert result.final_output is not None

    def test_finalize_chain_nonexistent(self, reasoner):
        assert reasoner.finalize_chain("nope") is None

    def test_finalize_chain_no_steps(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        assert reasoner.finalize_chain(chain.chain_id) is None

    def test_get_chain(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        assert reasoner.get_chain(chain.chain_id) is chain

    def test_get_chain_nonexistent(self, reasoner):
        assert reasoner.get_chain("nope") is None

    def test_deliberate_basic(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")

        result = reasoner.deliberate(chain.chain_id, "Should we proceed?", max_steps=3)
        assert result is not None
        assert result.final_output is not None
        assert len(result.steps) >= 1

    def test_deliberate_nonexistent_chain(self, reasoner):
        assert reasoner.deliberate("nope", "question") is None

    def test_deliberate_respects_max_steps(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")

        result = reasoner.deliberate(
            chain.chain_id,
            "complex question",
            max_steps=2,
            confidence_threshold=1.0,  # Never met, forces all steps
        )
        assert result is not None
        # With default mock: confidence=0.85 < 1.0, so it should run multiple steps
        # max_steps=2: 1 initial + 1 iteration (critique+refine counted as reason_step calls)
        assert len(result.steps) >= 2

    def test_deliberate_stops_early_on_high_confidence(self, manager):
        """With a provider that returns high confidence, deliberation stops early."""

        class HighConfProvider:
            def infer(self, context: str, prompt: str) -> tuple[str, int]:
                return ("confident answer", 10)

        reasoner = MultiTurnReasoner(
            context_manager=manager,
            inference_provider=HighConfProvider(),
        )
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")

        # confidence_threshold=0.8, default step confidence=0.85
        # The initial step already has 0.85 >= 0.8, so loop should break immediately
        result = reasoner.deliberate(
            chain.chain_id,
            "question",
            max_steps=5,
            confidence_threshold=0.8,
        )
        assert result is not None
        # Should have only the initial analyze step
        assert len(result.steps) == 1

    def test_reason_step_adds_to_window(self, reasoner, manager):
        manager.create_window("w1")
        chain = reasoner.start_chain("w1")
        reasoner.reason_step(chain.chain_id, "test")

        window = manager.get_window("w1")
        agent_outputs = window.get_chunks_by_type(ChunkType.AGENT_OUTPUT)
        assert len(agent_outputs) == 1
