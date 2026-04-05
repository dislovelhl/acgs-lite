# Constitutional Hash: 608508a9bd224290
"""
Tests for ContextCoordinator to boost coverage to ≥90%.

Covers:
- __init__ with/without Mamba available
- is_mamba_available()
- process_with_context: cache hit, memory pressure, mamba path, mamba error fallback, plain fallback
- _process_with_mamba: normal, mamba_context is None guard
- _process_with_fallback: no truncation, truncation needed, no keywords
- _build_context: with/without context_window
- _detect_critical_keywords
- _calculate_fallback_compliance edge cases
- _generate_cache_key variations
- get_context_stats: with/without mamba, mamba stats error
- clear_cache
- ContextProcessingResult dataclass
- ContextCoordinatorProtocol isinstance check
"""

from __future__ import annotations

import hashlib
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to import the module under test cleanly
# ---------------------------------------------------------------------------

MODULE_PATH = "enhanced_agent_bus.coordinators.context_coordinator"


def _import_coordinator():
    """Import the module, stripping cached copy for clean reimports."""
    if MODULE_PATH in sys.modules:
        del sys.modules[MODULE_PATH]
    import importlib

    return importlib.import_module(MODULE_PATH)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def coordinator_no_mamba():
    """ContextCoordinator with Mamba unavailable (module-level flag patched)."""
    mod = _import_coordinator()
    with patch.dict(
        mod.__dict__, {"MAMBA_AVAILABLE": False, "create_constitutional_context_manager": None}
    ):
        coord = mod.ContextCoordinator()
    return coord, mod


@pytest.fixture()
def coordinator_with_mamba():
    """ContextCoordinator with a mock Mamba context manager."""
    mod = _import_coordinator()
    mock_ccm = AsyncMock()
    mock_ccm.process_with_context = AsyncMock(return_value={"compliance_score": 0.95})
    mock_ccm.get_context_stats = MagicMock(return_value={"tokens": 42})
    factory = MagicMock(return_value=mock_ccm)
    with patch.dict(
        mod.__dict__,
        {"MAMBA_AVAILABLE": True, "create_constitutional_context_manager": factory},
    ):
        coord = mod.ContextCoordinator()
    return coord, mod, mock_ccm


# ---------------------------------------------------------------------------
# ContextProcessingResult dataclass
# ---------------------------------------------------------------------------


class TestContextProcessingResult:
    def test_fields_and_defaults(self):
        mod = _import_coordinator()
        result = mod.ContextProcessingResult(
            input_text="hello",
            context_length=5,
            compliance_score=0.8,
            constitutional_hash="abc",
            critical_keywords_detected=["kw"],
            mamba_processed=True,
        )
        assert result.input_text == "hello"
        assert result.context_length == 5
        assert result.compliance_score == 0.8
        assert result.constitutional_hash == "abc"
        assert result.critical_keywords_detected == ["kw"]
        assert result.mamba_processed is True
        assert result.cache_hit is False  # default

    def test_cache_hit_explicit(self):
        mod = _import_coordinator()
        result = mod.ContextProcessingResult(
            input_text="x",
            context_length=1,
            compliance_score=0.5,
            constitutional_hash="h",
            critical_keywords_detected=[],
            mamba_processed=False,
            cache_hit=True,
        )
        assert result.cache_hit is True


# ---------------------------------------------------------------------------
# ContextCoordinatorProtocol
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_coordinator_satisfies_protocol(self, coordinator_no_mamba):
        coord, mod = coordinator_no_mamba
        assert isinstance(coord, mod.ContextCoordinatorProtocol)

    def test_non_conforming_object_fails(self):
        mod = _import_coordinator()
        assert not isinstance(object(), mod.ContextCoordinatorProtocol)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_defaults_no_mamba(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        assert coord._context_size == 100_000
        assert coord._enable_caching is True
        assert coord._memory_threshold == 0.85
        assert coord._cache == {}
        assert coord._total_processed == 0
        assert coord._cache_hits == 0
        assert coord._degradations == 0
        assert coord._mamba_context is None

    def test_custom_params_no_mamba(self):
        mod = _import_coordinator()
        with patch.dict(
            mod.__dict__,
            {"MAMBA_AVAILABLE": False, "create_constitutional_context_manager": None},
        ):
            coord = mod.ContextCoordinator(
                context_size=500, enable_caching=False, memory_threshold=0.9
            )
        assert coord._context_size == 500
        assert coord._enable_caching is False
        assert coord._memory_threshold == 0.9

    def test_init_with_mamba_success(self, coordinator_with_mamba):
        coord, _mod, mock_ccm = coordinator_with_mamba
        assert coord._mamba_context is mock_ccm

    def test_init_with_mamba_factory_raises(self):
        mod = _import_coordinator()
        bad_factory = MagicMock(side_effect=RuntimeError("boom"))
        with patch.dict(
            mod.__dict__,
            {"MAMBA_AVAILABLE": True, "create_constitutional_context_manager": bad_factory},
        ):
            coord = mod.ContextCoordinator()
        assert coord._mamba_context is None

    def test_init_with_mamba_factory_raises_value_error(self):
        mod = _import_coordinator()
        bad_factory = MagicMock(side_effect=ValueError("nope"))
        with patch.dict(
            mod.__dict__,
            {"MAMBA_AVAILABLE": True, "create_constitutional_context_manager": bad_factory},
        ):
            coord = mod.ContextCoordinator()
        assert coord._mamba_context is None

    def test_init_with_mamba_factory_raises_type_error(self):
        mod = _import_coordinator()
        bad_factory = MagicMock(side_effect=TypeError("type"))
        with patch.dict(
            mod.__dict__,
            {"MAMBA_AVAILABLE": True, "create_constitutional_context_manager": bad_factory},
        ):
            coord = mod.ContextCoordinator()
        assert coord._mamba_context is None

    def test_init_with_mamba_factory_raises_import_error(self):
        mod = _import_coordinator()
        bad_factory = MagicMock(side_effect=ImportError("missing"))
        with patch.dict(
            mod.__dict__,
            {"MAMBA_AVAILABLE": True, "create_constitutional_context_manager": bad_factory},
        ):
            coord = mod.ContextCoordinator()
        assert coord._mamba_context is None

    def test_constitutional_hash_class_attribute(self):
        mod = _import_coordinator()
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        assert mod.ContextCoordinator.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# is_mamba_available
# ---------------------------------------------------------------------------


class TestIsMambaAvailable:
    def test_false_when_no_mamba(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        assert coord.is_mamba_available() is False

    def test_true_when_mamba(self, coordinator_with_mamba):
        coord, _, _ = coordinator_with_mamba
        assert coord.is_mamba_available() is True


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------


class TestBuildContext:
    def test_no_context_window_returns_input(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        assert coord._build_context("hello", None) == "hello"

    def test_empty_context_window_returns_input(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        assert coord._build_context("hello", []) == "hello"

    def test_with_context_window(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        result = coord._build_context("input", ["a", "b", "c"])
        assert result == "a b c input"

    def test_context_window_last_5_only(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        window = ["1", "2", "3", "4", "5", "6", "7"]
        result = coord._build_context("end", window)
        # Should use last 5: 3, 4, 5, 6, 7
        assert result == "3 4 5 6 7 end"


# ---------------------------------------------------------------------------
# _detect_critical_keywords
# ---------------------------------------------------------------------------


class TestDetectCriticalKeywords:
    def test_empty_keywords(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        assert coord._detect_critical_keywords("some text", []) == []

    def test_keyword_present_case_insensitive(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        result = coord._detect_critical_keywords("Hello World", ["hello", "WORLD", "missing"])
        assert "hello" in result
        assert "WORLD" in result
        assert "missing" not in result

    def test_no_keywords_present(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        result = coord._detect_critical_keywords("completely different", ["alpha", "beta"])
        assert result == []

    def test_all_keywords_present(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        result = coord._detect_critical_keywords("alpha beta gamma", ["alpha", "beta", "gamma"])
        assert result == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# _calculate_fallback_compliance
# ---------------------------------------------------------------------------


class TestCalculateFallbackCompliance:
    def test_base_score_no_keywords_short_text(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        score = coord._calculate_fallback_compliance("short", [])
        # base=0.7, keyword_boost=0, length_factor small
        assert 0.7 <= score <= 0.71

    def test_keyword_boost_caps_at_0_2(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        keywords = ["a", "b", "c", "d", "e", "f", "g", "h", "i"]  # 9 keywords * 0.05 > 0.2
        score = coord._calculate_fallback_compliance("x " * 100, keywords)
        # base=0.7 + max_keyword=0.2 + some length
        assert score <= 1.0
        assert score >= 0.9

    def test_long_text_length_factor_caps_at_0_1(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        long_text = "word " * 5000  # > 10000 chars
        score = coord._calculate_fallback_compliance(long_text, [])
        assert score <= 1.0
        # base 0.7 + 0 keyword + 0.1 length = 0.8
        assert abs(score - 0.8) < 0.01

    def test_score_clipped_to_1(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        long_text = "word " * 5000
        many_keywords = ["kw"] * 20  # big boost
        score = coord._calculate_fallback_compliance(long_text, many_keywords)
        assert score >= 0.99  # floating-point min/max may produce 0.999...9

    def test_score_never_below_0(self, coordinator_no_mamba):
        """Ensure min clamping doesn't break anything (base is always 0.7, so this is defensive)."""
        coord, _ = coordinator_no_mamba
        score = coord._calculate_fallback_compliance("", [])
        assert score >= 0.0


# ---------------------------------------------------------------------------
# _generate_cache_key
# ---------------------------------------------------------------------------


class TestGenerateCacheKey:
    def test_invalid_cache_hash_mode_raises(self):
        mod = _import_coordinator()
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            mod.ContextCoordinator(cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_deterministic(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        k1 = coord._generate_cache_key("text", ["a"], ["kw"])
        k2 = coord._generate_cache_key("text", ["a"], ["kw"])
        assert k1 == k2

    def test_different_inputs_different_keys(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        k1 = coord._generate_cache_key("text1", None, None)
        k2 = coord._generate_cache_key("text2", None, None)
        assert k1 != k2

    def test_none_context_and_keywords(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        key = coord._generate_cache_key("hello", None, None)
        expected = hashlib.sha256(b"hello").hexdigest()[:32]
        assert key == expected

    def test_keywords_sorted(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        k1 = coord._generate_cache_key("t", None, ["b", "a"])
        k2 = coord._generate_cache_key("t", None, ["a", "b"])
        assert k1 == k2

    def test_length_is_32(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        key = coord._generate_cache_key("anything", ["ctx"], ["kw"])
        assert len(key) == 32

    def test_fast_mode_uses_kernel(self):
        mod = _import_coordinator()
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xABCD

        with patch.dict(mod.__dict__, {"FAST_HASH_AVAILABLE": True, "fast_hash": _fake_fast_hash}):
            coord = mod.ContextCoordinator(cache_hash_mode="fast")
            key = coord._generate_cache_key("x", None, None)
            assert called["value"] is True
            assert key == "000000000000abcd"

    def test_fast_mode_falls_back_to_sha256(self):
        mod = _import_coordinator()
        with patch.dict(mod.__dict__, {"FAST_HASH_AVAILABLE": False}):
            coord = mod.ContextCoordinator(cache_hash_mode="fast")
            key = coord._generate_cache_key("hello", None, None)
            expected = hashlib.sha256(b"hello").hexdigest()[:32]
            assert key == expected


# ---------------------------------------------------------------------------
# process_with_context — cache hit
# ---------------------------------------------------------------------------


class TestProcessWithContextCacheHit:
    async def test_cache_hit_returns_cached_result(self, coordinator_no_mamba):
        coord, mod = coordinator_no_mamba
        cached_result = mod.ContextProcessingResult(
            input_text="cached",
            context_length=6,
            compliance_score=0.99,
            constitutional_hash="h",
            critical_keywords_detected=[],
            mamba_processed=False,
            cache_hit=False,
        )
        cache_key = coord._generate_cache_key("cached", None, None)
        coord._cache[cache_key] = cached_result

        result = await coord.process_with_context("cached")
        assert result is cached_result
        assert result.cache_hit is True
        assert coord._cache_hits == 1

    async def test_cache_disabled_no_hit(self, coordinator_no_mamba):
        """With caching disabled, cache is never populated or checked."""
        coord, _mod = coordinator_no_mamba
        coord._enable_caching = False
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("text")
        assert coord._cache_hits == 0
        assert coord._cache == {}
        assert result.mamba_processed is False


# ---------------------------------------------------------------------------
# process_with_context — memory pressure path
# ---------------------------------------------------------------------------


class TestProcessWithContextMemoryPressure:
    async def test_high_memory_triggers_fallback(self, coordinator_with_mamba):
        coord, _mod, _mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 92.0  # above 85% threshold
            result = await coord.process_with_context("text")
        assert result.mamba_processed is False
        assert coord._degradations == 1

    async def test_high_memory_caches_fallback_result(self, coordinator_with_mamba):
        coord, _mod, _mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 92.0
            result1 = await coord.process_with_context("text2")
            result2 = await coord.process_with_context("text2")
        # Second call should be cache hit
        assert result2.cache_hit is True
        assert coord._cache_hits == 1


# ---------------------------------------------------------------------------
# process_with_context — mamba path
# ---------------------------------------------------------------------------


class TestProcessWithContextMambaPath:
    async def test_mamba_path_success(self, coordinator_with_mamba):
        coord, _mod, _mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("hello", critical_keywords=["hello"])
        assert result.mamba_processed is True
        assert result.compliance_score == 0.95
        assert coord._total_processed == 1

    async def test_mamba_path_caches_result(self, coordinator_with_mamba):
        coord, _mod, _mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            await coord.process_with_context("cached_mamba")
            result2 = await coord.process_with_context("cached_mamba")
        assert result2.cache_hit is True

    async def test_mamba_path_uses_context_window(self, coordinator_with_mamba):
        coord, _mod, mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("end", context_window=["prev1", "prev2"])
        assert result.mamba_processed is True
        # mamba_context.process_with_context called with combined context
        call_kwargs = mock_ccm.process_with_context.call_args
        assert "prev1" in call_kwargs.kwargs["input_text"] or (
            call_kwargs.args and "prev1" in call_kwargs.args[0]
        )


# ---------------------------------------------------------------------------
# process_with_context — mamba error fallback
# ---------------------------------------------------------------------------


class TestProcessWithContextMambaError:
    @pytest.mark.parametrize(
        "exc_type",
        [AttributeError, OSError, RuntimeError, TimeoutError, TypeError, ValueError],
    )
    async def test_mamba_error_falls_back(self, exc_type, coordinator_with_mamba):
        coord, _mod, mock_ccm = coordinator_with_mamba
        mock_ccm.process_with_context.side_effect = exc_type("simulated error")
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("input_text")
        assert result.mamba_processed is False
        assert coord._total_processed == 1


# ---------------------------------------------------------------------------
# process_with_context — plain fallback (no mamba)
# ---------------------------------------------------------------------------


class TestProcessWithContextFallback:
    async def test_plain_fallback(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("hello world")
        assert result.mamba_processed is False
        assert result.input_text == "hello world"
        assert coord._total_processed == 1

    async def test_caches_fallback_result(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            await coord.process_with_context("cache_me")
            result2 = await coord.process_with_context("cache_me")
        assert result2.cache_hit is True

    async def test_fallback_with_keywords(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 10.0
            result = await coord.process_with_context("hello world", critical_keywords=["hello"])
        assert "hello" in result.critical_keywords_detected


# ---------------------------------------------------------------------------
# _process_with_fallback — truncation
# ---------------------------------------------------------------------------


class TestProcessWithFallbackTruncation:
    async def test_no_truncation_when_within_limit(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        coord._context_size = 1000
        result = await coord._process_with_fallback("short text", None, None)
        assert "..." not in result.input_text  # input_text is original, not truncated

    async def test_truncation_when_exceeds_context_size(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        coord._context_size = 10  # tiny limit
        # Create a text with > 10 words
        long_text = " ".join(f"word{i}" for i in range(50))
        result = await coord._process_with_fallback(long_text, None, None)
        # context_length should be from truncated text, which has "..."
        assert result.mamba_processed is False

    async def test_truncated_text_has_ellipsis_in_context(self, coordinator_no_mamba):
        """Indirectly verify truncation by checking context_length < original."""
        coord, _mod = coordinator_no_mamba
        coord._context_size = 10
        long_input = " ".join(["word"] * 100)
        result = await coord._process_with_fallback(long_input, None, None)
        # The truncated context will be shorter than the original 100-word string
        assert result.context_length < len(long_input)


# ---------------------------------------------------------------------------
# _process_with_mamba — guard: mamba_context is None
# ---------------------------------------------------------------------------


class TestProcessWithMambaGuard:
    async def test_raises_when_mamba_context_none(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        assert coord._mamba_context is None
        with pytest.raises(RuntimeError, match="Mamba context not available"):
            await coord._process_with_mamba("text", None, None)


# ---------------------------------------------------------------------------
# get_context_stats
# ---------------------------------------------------------------------------


class TestGetContextStats:
    def test_stats_no_mamba(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 55.0
            stats = coord.get_context_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["mamba_available"] is False
        assert stats["context_size"] == 100_000
        assert stats["cache_enabled"] is True
        assert stats["cache_size"] == 0
        assert stats["total_processed"] == 0
        assert stats["cache_hits"] == 0
        assert stats["memory_threshold"] == 0.85
        assert stats["current_memory_usage_percent"] == 55.0
        assert stats["degradations_due_to_memory"] == 0
        assert "mamba_stats" not in stats

    def test_stats_with_mamba_and_get_context_stats(self, coordinator_with_mamba):
        coord, _mod, _mock_ccm = coordinator_with_mamba
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 30.0
            stats = coord.get_context_stats()
        assert stats["mamba_available"] is True
        assert stats["mamba_stats"] == {"tokens": 42}

    def test_stats_with_mamba_no_get_context_stats_attr(self, coordinator_with_mamba):
        coord, _mod, mock_ccm = coordinator_with_mamba
        del mock_ccm.get_context_stats  # remove the attribute
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 30.0
            stats = coord.get_context_stats()
        assert "mamba_stats" not in stats

    @pytest.mark.parametrize(
        "exc_type",
        [AttributeError, OSError, RuntimeError, TimeoutError, TypeError, ValueError],
    )
    def test_stats_mamba_get_stats_raises(self, exc_type, coordinator_with_mamba):
        coord, _mod, mock_ccm = coordinator_with_mamba
        mock_ccm.get_context_stats.side_effect = exc_type("stats boom")
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value.percent = 30.0
            stats = coord.get_context_stats()
        assert "mamba_stats" not in stats


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


class TestClearCache:
    def test_clear_cache_empties_cache(self, coordinator_no_mamba):
        coord, _mod = coordinator_no_mamba
        coord._cache["key"] = MagicMock()
        coord.clear_cache()
        assert coord._cache == {}

    def test_clear_cache_idempotent(self, coordinator_no_mamba):
        coord, _ = coordinator_no_mamba
        coord.clear_cache()
        assert coord._cache == {}


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        mod = _import_coordinator()
        for name in mod.__all__:
            assert hasattr(mod, name)
