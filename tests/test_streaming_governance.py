"""Tests for streaming response governance.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine.core import GovernanceEngine
from acgs_lite.engine.streaming import (
    GovernedStreamWrapper,
    StreamChunkResult,
    StreamingValidator,
    StreamStats,
    governed_stream,
)
from acgs_lite.engine.types import Violation

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

RULES_YAML = """
rules:
  - id: SAFETY-001
    text: Do not deploy models without safety review
    severity: critical
    category: safety
    keywords: [deploy, model, without, safety, review]
    patterns:
      - "\\\\bdeploy.{0,30}without.{0,30}safety\\\\b"

  - id: FAIRNESS-001
    text: Do not use age-based discrimination
    severity: high
    category: fairness
    keywords: [age-based, discrimination, bias]
    patterns:
      - "age-based|age.*discriminat"

  - id: TRANSPARENCY-001
    text: Do not hide AI involvement in decisions
    severity: critical
    category: transparency
    keywords: [hide, secret, conceal, AI, involvement]
    patterns:
      - "\\\\bhide.{0,30}AI\\\\b"
      - "\\\\bsecret\\\\b"

  - id: INFO-001
    text: Prefer clear language
    severity: low
    category: style
    keywords: [obfuscate, unclear]
"""


@pytest.fixture()
def constitution() -> Constitution:
    return Constitution.from_yaml_str(RULES_YAML)


@pytest.fixture()
def engine(
    constitution: Constitution,
) -> GovernanceEngine:
    return GovernanceEngine(constitution, strict=True)


@pytest.fixture()
def nonstrict_engine(
    constitution: Constitution,
) -> GovernanceEngine:
    return GovernanceEngine(constitution, strict=False)


# -------------------------------------------------------------------
# StreamChunkResult dataclass
# -------------------------------------------------------------------


class TestStreamChunkResult:
    def test_default_fields(self) -> None:
        r = StreamChunkResult(
            chunk="hello",
            passed=True,
            buffer_position=5,
            window_text="hello",
        )
        assert r.chunk == "hello"
        assert r.passed is True
        assert r.violations == []
        assert r.should_halt is False
        assert r.buffer_position == 5
        assert r.window_text == "hello"

    def test_fields_with_violations(self) -> None:
        v = Violation(
            rule_id="R1",
            rule_text="test",
            severity=Severity.CRITICAL,
            matched_content="bad",
            category="safety",
        )
        r = StreamChunkResult(
            chunk="x",
            passed=False,
            violations=[v],
            should_halt=True,
            buffer_position=10,
            window_text="some text",
        )
        assert len(r.violations) == 1
        assert r.should_halt is True


# -------------------------------------------------------------------
# StreamingValidator.feed -- accumulation and threshold
# -------------------------------------------------------------------


class TestFeedAccumulation:
    def test_no_validation_below_threshold(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """feed() should NOT validate below threshold."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=100,
        )
        result = sv.feed("short")
        assert result.passed is True
        assert result.window_text == ""
        assert sv.stats.validations_performed == 0

    def test_validation_at_threshold(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Validation fires when chars >= threshold."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        result = sv.feed("a" * 15)
        assert sv.stats.validations_performed == 1
        assert result.window_text != ""

    def test_multiple_feeds_accumulate(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Multiple small feeds accumulate until threshold."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=20,
        )
        sv.feed("hello")  # 5 chars
        assert sv.stats.validations_performed == 0
        sv.feed("world")  # 10 chars total
        assert sv.stats.validations_performed == 0
        r3 = sv.feed("!" * 15)  # 25 chars total
        assert sv.stats.validations_performed == 1
        assert r3.window_text != ""


# -------------------------------------------------------------------
# StreamingValidator.flush
# -------------------------------------------------------------------


class TestFlush:
    def test_flush_validates_remaining(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """flush() validates remaining text in the window."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        sv.feed("clean text here")
        assert sv.stats.validations_performed == 0
        result = sv.flush()
        assert sv.stats.validations_performed == 1
        assert result.passed is True
        assert "clean text here" in result.window_text

    def test_flush_empty_buffer(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """flush() on empty buffer returns a passing result."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        result = sv.flush()
        assert result.passed is True
        assert result.window_text == ""
        assert sv.stats.validations_performed == 0


# -------------------------------------------------------------------
# StreamingValidator.reset
# -------------------------------------------------------------------


class TestReset:
    def test_reset_clears_state(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed("a" * 15)
        assert sv.stats.chunks_processed == 1
        sv.reset()
        assert sv.stats.chunks_processed == 0
        assert sv.stats.validations_performed == 0
        assert sv.stats.total_chars == 0

    def test_reset_allows_reuse(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed("a" * 15)
        sv.reset()
        result = sv.feed("b" * 15)
        assert sv.stats.chunks_processed == 1
        assert result.buffer_position == 15


# -------------------------------------------------------------------
# Sliding window keeps only last N chunks
# -------------------------------------------------------------------


class TestSlidingWindow:
    def test_window_trims_to_size(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            window_size=3,
            flush_interval_chars=1000,
        )
        for i in range(6):
            sv.feed(f"chunk{i} ")
        result = sv.flush()
        assert "chunk3" in result.window_text
        assert "chunk4" in result.window_text
        assert "chunk5" in result.window_text
        assert "chunk0" not in result.window_text
        assert "chunk1" not in result.window_text
        assert "chunk2" not in result.window_text

    def test_window_size_one(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            window_size=1,
            flush_interval_chars=1000,
        )
        sv.feed("first ")
        sv.feed("second ")
        sv.feed("third ")
        result = sv.flush()
        assert "third" in result.window_text
        assert "first" not in result.window_text


# -------------------------------------------------------------------
# Non-blocking mode: violations logged but stream continues
# -------------------------------------------------------------------


class TestNonBlockingMode:
    def test_violations_detected_but_no_halt(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Without blocking_severities, no halt."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        result = sv.feed(
            "deploy model without safety review now",
        )
        assert result.passed is False
        assert result.should_halt is False
        assert len(result.violations) > 0

    def test_stats_track_violations(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed(
            "deploy model without safety review now",
        )
        assert sv.stats.violations_detected > 0
        assert sv.stats.halted is False


# -------------------------------------------------------------------
# Blocking mode: CRITICAL severity halts stream
# -------------------------------------------------------------------


class TestBlockingMode:
    def test_critical_severity_halts(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )
        result = sv.feed(
            "deploy model without safety review now",
        )
        assert result.should_halt is True
        assert sv.stats.halted is True

    def test_non_matching_severity_no_halt(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Only severities in blocking_severities cause halt."""
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
            blocking_severities={"low"},
        )
        result = sv.feed(
            "deploy model without safety review now",
        )
        assert result.should_halt is False


# -------------------------------------------------------------------
# GovernedStreamWrapper -- sync iterator
# -------------------------------------------------------------------


class TestGovernedStreamWrapperSync:
    def test_yields_chunks(
        self,
        engine: GovernanceEngine,
    ) -> None:
        chunks = [
            "Hello ",
            "world ",
            "this is clean text.",
        ]
        wrapper = GovernedStreamWrapper(
            iter(chunks),
            StreamingValidator(
                engine,
                flush_interval_chars=1000,
            ),
        )
        collected = list(wrapper)
        assert collected == chunks

    def test_halts_on_blocking_violation(
        self,
        engine: GovernanceEngine,
    ) -> None:
        bad = "deploy model without safety review " * 5
        chunks = [bad, "more text"]
        validator = StreamingValidator(
            engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )
        wrapper = GovernedStreamWrapper(
            iter(chunks),
            validator,
        )
        collected = list(wrapper)
        assert any("[GOVERNANCE]" in c for c in collected)
        assert "more text" not in collected

    def test_custom_halt_message(
        self,
        engine: GovernanceEngine,
    ) -> None:
        bad = "deploy model without safety review " * 5
        validator = StreamingValidator(
            engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )
        wrapper = GovernedStreamWrapper(
            iter([bad]),
            validator,
            halt_message="STOPPED",
        )
        collected = list(wrapper)
        assert "STOPPED" in collected

    def test_flush_halt_at_stream_end(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Flush at end of stream can also trigger halt."""
        bad = "deploy model without safety review"
        validator = StreamingValidator(
            engine,
            flush_interval_chars=1000,
            blocking_severities={"critical"},
        )
        wrapper = GovernedStreamWrapper(
            iter([bad]),
            validator,
        )
        collected = list(wrapper)
        assert any("[GOVERNANCE]" in c for c in collected)


# -------------------------------------------------------------------
# GovernedStreamWrapper -- async iterator
# -------------------------------------------------------------------


class TestGovernedStreamWrapperAsync:
    @pytest.mark.asyncio
    async def test_yields_chunks_async(
        self,
        engine: GovernanceEngine,
    ) -> None:
        async def gen():
            for c in ["Hello ", "world."]:
                yield c

        validator = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        wrapper = GovernedStreamWrapper(
            gen(),
            validator,
        )
        collected = []
        async for chunk in wrapper:
            collected.append(chunk)
        assert collected == ["Hello ", "world."]

    @pytest.mark.asyncio
    async def test_halts_on_blocking_async(
        self,
        engine: GovernanceEngine,
    ) -> None:
        bad = "deploy model without safety review " * 5

        async def gen():
            yield bad
            yield "more"

        validator = StreamingValidator(
            engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )
        wrapper = GovernedStreamWrapper(
            gen(),
            validator,
        )
        collected = []
        async for chunk in wrapper:
            collected.append(chunk)
        assert any("[GOVERNANCE]" in c for c in collected)
        assert "more" not in collected

    @pytest.mark.asyncio
    async def test_flush_halt_at_stream_end_async(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Async flush at end can also trigger halt."""
        bad = "deploy model without safety review"

        async def gen():
            yield bad

        validator = StreamingValidator(
            engine,
            flush_interval_chars=1000,
            blocking_severities={"critical"},
        )
        wrapper = GovernedStreamWrapper(
            gen(),
            validator,
        )
        collected = []
        async for chunk in wrapper:
            collected.append(chunk)
        assert any("[GOVERNANCE]" in c for c in collected)


# -------------------------------------------------------------------
# governed_stream() convenience function
# -------------------------------------------------------------------


class TestGovernedStream:
    def test_returns_governed_wrapper(
        self,
        engine: GovernanceEngine,
    ) -> None:
        wrapper = governed_stream(iter(["hi"]), engine)
        assert isinstance(wrapper, GovernedStreamWrapper)

    def test_passthrough_kwargs(
        self,
        engine: GovernanceEngine,
    ) -> None:
        wrapper = governed_stream(
            iter(["hi"]),
            engine,
            window_size=3,
            flush_interval_chars=100,
            blocking_severities={"critical"},
            halt_message="STOP",
        )
        collected = list(wrapper)
        assert collected == ["hi"]

    def test_governed_stream_halts(
        self,
        engine: GovernanceEngine,
    ) -> None:
        bad = "deploy model without safety review " * 5
        wrapper = governed_stream(
            iter([bad, "tail"]),
            engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )
        collected = list(wrapper)
        assert "tail" not in collected

    def test_with_audit_log(
        self,
        engine: GovernanceEngine,
    ) -> None:
        audit = AuditLog()
        wrapper = governed_stream(
            iter(["a" * 15]),
            engine,
            flush_interval_chars=10,
            audit_log=audit,
        )
        list(wrapper)
        assert len(audit) >= 1


# -------------------------------------------------------------------
# Stats tracking
# -------------------------------------------------------------------


class TestStatsTracking:
    def test_chunks_processed(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        sv.feed("a")
        sv.feed("b")
        sv.feed("c")
        assert sv.stats.chunks_processed == 3

    def test_total_chars(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        sv.feed("hello")
        sv.feed("world")
        assert sv.stats.total_chars == 10

    def test_violations_detected_count(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed(
            "deploy model without safety review " * 3,
        )
        assert sv.stats.violations_detected > 0

    def test_wrapper_stats_property(
        self,
        engine: GovernanceEngine,
    ) -> None:
        validator = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        wrapper = GovernedStreamWrapper(
            iter(["a", "b"]),
            validator,
        )
        list(wrapper)
        assert wrapper.stats.chunks_processed == 2

    def test_latency_tracked(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed("a" * 15)
        assert sv.stats.latency_ms >= 0.0


# -------------------------------------------------------------------
# Buffer position tracking
# -------------------------------------------------------------------


class TestBufferPosition:
    def test_position_increments(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        r1 = sv.feed("hello")
        assert r1.buffer_position == 5
        r2 = sv.feed("world!")
        assert r2.buffer_position == 11

    def test_position_resets_on_reset(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=1000,
        )
        sv.feed("hello")
        sv.reset()
        r = sv.feed("new")
        assert r.buffer_position == 3


# -------------------------------------------------------------------
# Audit log integration
# -------------------------------------------------------------------


class TestAuditLogIntegration:
    def test_records_to_audit_log(
        self,
        engine: GovernanceEngine,
    ) -> None:
        audit = AuditLog()
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
            audit_log=audit,
        )
        sv.feed("a" * 15)
        assert len(audit) == 1
        entry = audit.entries[0]
        assert entry.type == "streaming_validation"

    def test_no_audit_without_log(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        sv.feed("a" * 15)
        assert sv.stats.validations_performed == 1

    def test_audit_chain_integrity(
        self,
        engine: GovernanceEngine,
    ) -> None:
        audit = AuditLog()
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
            audit_log=audit,
        )
        sv.feed("a" * 15)
        sv.feed("b" * 15)
        assert audit.verify_chain()


# -------------------------------------------------------------------
# Async feed
# -------------------------------------------------------------------


class TestAsyncFeed:
    @pytest.mark.asyncio
    async def test_afeed_returns_result(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        result = await sv.afeed("a" * 15)
        assert isinstance(result, StreamChunkResult)
        assert sv.stats.validations_performed == 1

    @pytest.mark.asyncio
    async def test_afeed_below_threshold(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=100,
        )
        result = await sv.afeed("short")
        assert result.passed is True
        assert sv.stats.validations_performed == 0


# -------------------------------------------------------------------
# Edge cases
# -------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_chunk(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=10,
        )
        result = sv.feed("")
        assert result.passed is True
        assert result.buffer_position == 0

    def test_window_size_clamped_to_one(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            window_size=0,
            flush_interval_chars=10,
        )
        sv.feed("a" * 15)
        assert sv.stats.validations_performed == 1

    def test_stream_stats_defaults(self) -> None:
        s = StreamStats()
        assert s.chunks_processed == 0
        assert s.validations_performed == 0
        assert s.violations_detected == 0
        assert s.halted is False
        assert s.total_chars == 0
        assert s.latency_ms == 0.0

    def test_flush_interval_clamped_to_one(
        self,
        engine: GovernanceEngine,
    ) -> None:
        sv = StreamingValidator(
            engine,
            flush_interval_chars=0,
        )
        # Should not crash; interval clamped to 1
        result = sv.feed("a")
        assert sv.stats.validations_performed == 1


# -------------------------------------------------------------------
# Engine exception during streaming
# -------------------------------------------------------------------


class TestStreamingEngineError:
    def test_feed_fail_closed_on_engine_exception_by_default(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """Default (fail_open_on_error=False): engine exception halts the stream."""
        from unittest.mock import MagicMock

        mock_engine = MagicMock()
        mock_engine.non_strict.return_value.__enter__ = MagicMock()
        mock_engine.non_strict.return_value.__exit__ = MagicMock(return_value=False)
        mock_engine.validate.side_effect = RuntimeError(
            "unexpected engine failure",
        )

        sv = StreamingValidator(
            mock_engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
        )

        result = sv.feed("a" * 15)
        assert result.passed is False
        assert result.should_halt is True
        assert result.violations == []
        assert sv.stats.validations_performed == 1
        assert sv.stats.halted is True

    def test_feed_survives_engine_exception_when_fail_open_opt_in(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """With fail_open_on_error=True, engine exception yields passing result (legacy behavior)."""
        from unittest.mock import MagicMock

        mock_engine = MagicMock()
        mock_engine.non_strict.return_value.__enter__ = MagicMock()
        mock_engine.non_strict.return_value.__exit__ = MagicMock(return_value=False)
        mock_engine.validate.side_effect = RuntimeError(
            "unexpected engine failure",
        )

        sv = StreamingValidator(
            mock_engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
            fail_open_on_error=True,
        )

        result = sv.feed("a" * 15)
        assert result.passed is True
        assert result.should_halt is False
        assert result.violations == []
        assert sv.stats.validations_performed == 1

    def test_feed_continues_after_engine_exception_when_fail_open_opt_in(
        self,
        engine: GovernanceEngine,
    ) -> None:
        """With fail_open_on_error=True, stream can process further chunks after error."""
        from unittest.mock import MagicMock

        call_count = 0

        mock_engine = MagicMock()
        mock_engine.non_strict.return_value.__enter__ = MagicMock()
        mock_engine.non_strict.return_value.__exit__ = MagicMock(return_value=False)

        def _fail_then_succeed(text: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            result = MagicMock()
            result.violations = []
            return result

        mock_engine.validate.side_effect = _fail_then_succeed

        sv = StreamingValidator(
            mock_engine,
            flush_interval_chars=10,
            blocking_severities={"critical"},
            fail_open_on_error=True,
        )

        r1 = sv.feed("a" * 15)
        assert r1.passed is True

        r2 = sv.feed("b" * 15)
        assert r2.passed is True
        assert sv.stats.validations_performed == 2
