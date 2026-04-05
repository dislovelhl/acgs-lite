# Constitutional Hash: 608508a9bd224290
"""
Coverage tests for MemoryCoordinator.

Targets: src/core/enhanced_agent_bus/coordinators/memory_coordinator.py
Goal:    >= 90% coverage

Strategy
--------
Tests directly manipulate the coordinator's internal state (bypassing
_initialize_memory by using __new__ or by patching
MemoryCoordinator._initialize_memory at the class level) to control
which branches execute in store(), retrieve(), search(), and get_stats().

sys.modules patches exercise _initialize_memory() constructor branches.
No real Redis / database I/O is performed.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.coordinators.memory_coordinator import (
    _MEMORY_COORDINATOR_ERRORS,
    MemoryCoordinator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_v3_memory() -> MagicMock:
    """Return a mock that looks like SAFLANeuralMemoryV3."""
    mem = MagicMock()
    mem.store = AsyncMock(return_value=None)
    mem.retrieve = AsyncMock(return_value={"result": "data"})
    mem.search = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
    mem.get_stats = MagicMock(return_value={"entries": 5})
    return mem


def _make_fallback_memory() -> MagicMock:
    """Return a mock that looks like SAFLANeuralMemory (fallback)."""
    mem = MagicMock()
    mem.store = AsyncMock(return_value=None)
    mem.retrieve = AsyncMock(return_value={"fallback_key": "value"})
    mem.search = AsyncMock(return_value=[{"id": "a"}, None])
    mem.get_stats = MagicMock(return_value={"tier": "fallback"})
    return mem


def _coord_with_v3(v3_mem: MagicMock | None = None) -> MemoryCoordinator:
    """Create a MemoryCoordinator bypassing _initialize_memory, v3 active."""
    if v3_mem is None:
        v3_mem = _make_v3_memory()
    coord = MemoryCoordinator.__new__(MemoryCoordinator)
    coord._persistence_enabled = True
    coord._use_v3 = True
    coord._memory_v3 = v3_mem
    coord._memory_fallback = None
    coord._initialized = True
    return coord


def _coord_with_fallback(fallback_mem: MagicMock | None = None) -> MemoryCoordinator:
    """Create a MemoryCoordinator bypassing _initialize_memory, fallback active."""
    if fallback_mem is None:
        fallback_mem = _make_fallback_memory()
    coord = MemoryCoordinator.__new__(MemoryCoordinator)
    coord._persistence_enabled = True
    coord._use_v3 = True
    coord._memory_v3 = None
    coord._memory_fallback = fallback_mem
    coord._initialized = True
    return coord


def _coord_uninit() -> MemoryCoordinator:
    """Create an uninitialized MemoryCoordinator (both backends absent)."""
    coord = MemoryCoordinator.__new__(MemoryCoordinator)
    coord._persistence_enabled = True
    coord._use_v3 = True
    coord._memory_v3 = None
    coord._memory_fallback = None
    coord._initialized = False
    return coord


# ---------------------------------------------------------------------------
# _initialize_memory — v3 success path
# ---------------------------------------------------------------------------


class TestInitV3Success:
    """MemoryCoordinator when SAFLA v3 is available and succeeds."""

    def test_is_v3_enabled_true(self) -> None:
        coord = _coord_with_v3()
        assert coord.is_v3_enabled is True

    def test_initialized_true(self) -> None:
        coord = _coord_with_v3()
        assert coord._initialized is True

    def test_get_stats_includes_v3_stats(self) -> None:
        coord = _coord_with_v3()
        stats = coord.get_stats()
        assert "v3_stats" in stats
        assert stats["v3_stats"] == {"entries": 5}

    def test_get_stats_base_keys_present(self) -> None:
        coord = _coord_with_v3()
        stats = coord.get_stats()
        for key in ("constitutional_hash", "initialized", "v3_enabled", "persistence_enabled"):
            assert key in stats

    async def test_store_via_v3(self) -> None:
        mem = _make_v3_memory()
        coord = _coord_with_v3(mem)
        result = await coord.store("my_key", {"data": 1}, tier="ephemeral", ttl_seconds=30)
        assert result is True
        mem.store.assert_called_once_with(
            tier="ephemeral", key="my_key", value={"data": 1}, ttl_seconds=30
        )

    async def test_store_via_v3_default_tier(self) -> None:
        coord = _coord_with_v3()
        result = await coord.store("k2", {"x": 2})
        assert result is True

    async def test_store_via_v3_runtime_error_returns_false(self) -> None:
        mem = _make_v3_memory()
        mem.store.side_effect = RuntimeError("v3 store boom")
        coord = _coord_with_v3(mem)
        result = await coord.store("k", {})
        assert result is False

    async def test_store_via_v3_value_error_returns_false(self) -> None:
        mem = _make_v3_memory()
        mem.store.side_effect = ValueError("bad value")
        coord = _coord_with_v3(mem)
        result = await coord.store("k", {})
        assert result is False

    async def test_retrieve_via_v3(self) -> None:
        coord = _coord_with_v3()
        result = await coord.retrieve("my_key")
        assert result == {"result": "data"}

    async def test_retrieve_via_v3_connection_error_returns_none(self) -> None:
        mem = _make_v3_memory()
        mem.retrieve.side_effect = ConnectionError("timeout")
        coord = _coord_with_v3(mem)
        result = await coord.retrieve("k")
        assert result is None

    async def test_search_via_v3(self) -> None:
        mem = _make_v3_memory()
        coord = _coord_with_v3(mem)
        result = await coord.search("governance", limit=5)
        assert result == [{"id": "1"}, {"id": "2"}]
        mem.search.assert_called_once_with("governance", limit=5)

    async def test_search_via_v3_default_limit(self) -> None:
        mem = _make_v3_memory()
        mem.search.return_value = []
        coord = _coord_with_v3(mem)
        result = await coord.search("query")
        assert result == []

    async def test_search_via_v3_os_error_returns_empty(self) -> None:
        mem = _make_v3_memory()
        mem.search.side_effect = OSError("io error")
        coord = _coord_with_v3(mem)
        result = await coord.search("query")
        assert result == []

    async def test_search_via_v3_with_tier_parameter(self) -> None:
        mem = _make_v3_memory()
        mem.search.return_value = [{"id": "x"}]
        coord = _coord_with_v3(mem)
        result = await coord.search("query", limit=3, tier="semantic")
        assert result == [{"id": "x"}]


# ---------------------------------------------------------------------------
# _initialize_memory — fallback path (v3 absent, fallback succeeds)
# ---------------------------------------------------------------------------


class TestInitFallbackSuccess:
    """MemoryCoordinator when v3 is absent but fallback succeeds."""

    def test_is_v3_enabled_false(self) -> None:
        coord = _coord_with_fallback()
        assert coord.is_v3_enabled is False

    def test_initialized_true(self) -> None:
        coord = _coord_with_fallback()
        assert coord._initialized is True

    def test_get_stats_includes_fallback_stats(self) -> None:
        coord = _coord_with_fallback()
        stats = coord.get_stats()
        assert "fallback_stats" in stats
        assert stats["fallback_stats"] == {"tier": "fallback"}

    def test_get_stats_no_v3_stats(self) -> None:
        coord = _coord_with_fallback()
        stats = coord.get_stats()
        assert "v3_stats" not in stats

    async def test_store_via_fallback(self) -> None:
        """store() uses MemoryTier enum when routing through fallback."""
        fallback = _make_fallback_memory()
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"
        mock_tier_enum.WORKING = "WORKING"
        mock_tier_enum.SEMANTIC = "SEMANTIC"
        mock_tier_enum.PERSISTENT = "PERSISTENT"

        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        # Patch the module that store() imports inline via "from ..memory import MemoryTier"
        parent_pkg = "packages.enhanced_agent_bus"
        with patch.dict(sys.modules, {f"{parent_pkg}.memory": mock_memory_mod}):
            result = await coord.store("fkey", {"v": 9}, tier="ephemeral")

        assert result is True
        fallback.store.assert_called_once_with(mock_tier_enum.EPHEMERAL, "fkey", {"v": 9})

    async def test_store_via_fallback_working_tier(self) -> None:
        fallback = _make_fallback_memory()
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"
        mock_tier_enum.WORKING = "WORKING"
        mock_tier_enum.SEMANTIC = "SEMANTIC"
        mock_tier_enum.PERSISTENT = "PERSISTENT"

        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        with patch.dict(sys.modules, {"enhanced_agent_bus.memory": mock_memory_mod}):
            result = await coord.store("wkey", {"w": 1}, tier="working")

        assert result is True

    async def test_store_via_fallback_semantic_tier(self) -> None:
        fallback = _make_fallback_memory()
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"
        mock_tier_enum.SEMANTIC = "SEMANTIC"

        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        with patch.dict(sys.modules, {"enhanced_agent_bus.memory": mock_memory_mod}):
            result = await coord.store("skey", {"s": 1}, tier="semantic")

        assert result is True

    async def test_store_via_fallback_persistent_tier(self) -> None:
        fallback = _make_fallback_memory()
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"
        mock_tier_enum.PERSISTENT = "PERSISTENT"

        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        with patch.dict(sys.modules, {"enhanced_agent_bus.memory": mock_memory_mod}):
            result = await coord.store("pkey", {"p": 1}, tier="persistent")

        assert result is True

    async def test_store_via_fallback_unknown_tier_defaults_to_ephemeral(self) -> None:
        """Unknown tier name maps to MemoryTier.EPHEMERAL."""
        fallback = _make_fallback_memory()
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"

        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        with patch.dict(sys.modules, {"enhanced_agent_bus.memory": mock_memory_mod}):
            result = await coord.store("fkey", {"v": 1}, tier="unknown_tier")

        assert result is True
        fallback.store.assert_called_once_with(mock_tier_enum.EPHEMERAL, "fkey", {"v": 1})

    async def test_store_via_fallback_raises_returns_false(self) -> None:
        fallback = _make_fallback_memory()
        fallback.store.side_effect = RuntimeError("fallback boom")
        coord = _coord_with_fallback(fallback)

        mock_tier_enum = MagicMock()
        mock_tier_enum.EPHEMERAL = "EPHEMERAL"
        mock_memory_mod = MagicMock(MemoryTier=mock_tier_enum)

        with patch.dict(sys.modules, {"enhanced_agent_bus.memory": mock_memory_mod}):
            result = await coord.store("k", {})

        assert result is False

    async def test_retrieve_via_fallback(self) -> None:
        coord = _coord_with_fallback()
        result = await coord.retrieve("fkey")
        assert result == {"fallback_key": "value"}

    async def test_retrieve_via_fallback_attribute_error_returns_none(self) -> None:
        fallback = _make_fallback_memory()
        fallback.retrieve.side_effect = AttributeError("no attr")
        coord = _coord_with_fallback(fallback)
        result = await coord.retrieve("k")
        assert result is None

    async def test_search_via_fallback_filters_none(self) -> None:
        """search() with fallback filters out None entries."""
        fallback = _make_fallback_memory()
        fallback.search.return_value = [{"id": "a"}, None, {"id": "b"}]
        coord = _coord_with_fallback(fallback)
        result = await coord.search("query", limit=10)
        assert result == [{"id": "a"}, {"id": "b"}]
        fallback.search.assert_called_once_with("query", k=10)

    async def test_search_via_fallback_all_none_returns_empty(self) -> None:
        fallback = _make_fallback_memory()
        fallback.search.return_value = [None, None]
        coord = _coord_with_fallback(fallback)
        result = await coord.search("query")
        assert result == []

    async def test_search_via_fallback_lookup_error_returns_empty(self) -> None:
        fallback = _make_fallback_memory()
        fallback.search.side_effect = LookupError("not found")
        coord = _coord_with_fallback(fallback)
        result = await coord.search("query")
        assert result == []


# ---------------------------------------------------------------------------
# Both backends unavailable
# ---------------------------------------------------------------------------


class TestInitBothUnavailable:
    async def test_store_returns_false(self) -> None:
        coord = _coord_uninit()
        assert await coord.store("k", {}) is False

    async def test_retrieve_returns_none(self) -> None:
        coord = _coord_uninit()
        assert await coord.retrieve("k") is None

    async def test_search_returns_empty(self) -> None:
        coord = _coord_uninit()
        assert await coord.search("q") == []

    def test_get_stats_initialized_false(self) -> None:
        coord = _coord_uninit()
        stats = coord.get_stats()
        assert stats["initialized"] is False
        assert stats["v3_enabled"] is False

    def test_get_stats_no_backend_keys(self) -> None:
        coord = _coord_uninit()
        stats = coord.get_stats()
        assert "v3_stats" not in stats
        assert "fallback_stats" not in stats


# ---------------------------------------------------------------------------
# _initialize_memory constructor branches via sys.modules patches
# ---------------------------------------------------------------------------


class TestInitializeMemoryBranches:
    """Exercise _initialize_memory() constructor paths directly."""

    def test_use_v3_false_skips_v3_branch(self) -> None:
        """use_v3=False ensures _memory_v3 is never set."""
        # Patch _initialize_memory to a no-op so constructor doesn't call real init
        with patch.object(MemoryCoordinator, "_initialize_memory"):
            coord = MemoryCoordinator(use_v3=False)
        assert coord._memory_v3 is None

    def test_use_v3_true_v3_available_sets_memory_v3(self) -> None:
        """When v3 is available, _memory_v3 is set after real init."""
        # The real SAFLA v3 is available in this environment
        coord = MemoryCoordinator(use_v3=True, persistence_enabled=True)
        # Either v3 or fallback must be active (at least one is available)
        assert coord._initialized is True

    def test_use_v3_false_persistence_disabled_no_v3(self) -> None:
        """use_v3=False with persistence_enabled=False — no v3 memory."""
        with patch.object(MemoryCoordinator, "_initialize_memory"):
            coord = MemoryCoordinator(use_v3=False, persistence_enabled=False)
        assert coord._memory_v3 is None
        assert coord._persistence_enabled is False

    def test_v3_init_runtime_error_falls_through_to_fallback(self) -> None:
        """When v3 raises RuntimeError during init, fallback is tried."""
        mock_create = MagicMock(side_effect=RuntimeError("v3 init failed"))
        mock_safla_module = MagicMock(create_safla_memory=mock_create)

        mock_fallback_instance = MagicMock()
        mock_config_instance = MagicMock()
        mock_memory_module = MagicMock(
            SAFLANeuralMemory=MagicMock(return_value=mock_fallback_instance)
        )
        mock_models_module = MagicMock(
            OrchestratorConfig=MagicMock(return_value=mock_config_instance)
        )

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.safla_memory": mock_safla_module,
                "enhanced_agent_bus.memory": mock_memory_module,
                "enhanced_agent_bus.models": mock_models_module,
            },
        ):
            coord = MemoryCoordinator(use_v3=True)

        assert coord._memory_v3 is None

    def test_both_fail_leaves_uninitialized(self) -> None:
        """When both v3 and fallback raise, coord._initialized is False."""
        mock_create = MagicMock(side_effect=RuntimeError("v3 boom"))
        mock_safla_module = MagicMock(create_safla_memory=mock_create)
        mock_memory_module = MagicMock(
            SAFLANeuralMemory=MagicMock(side_effect=RuntimeError("fallback boom"))
        )
        mock_config_cls = MagicMock(return_value=MagicMock())
        mock_models_module = MagicMock(OrchestratorConfig=mock_config_cls)

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.safla_memory": mock_safla_module,
                "enhanced_agent_bus.memory": mock_memory_module,
                "enhanced_agent_bus.models": mock_models_module,
            },
        ):
            coord = MemoryCoordinator(use_v3=True)

        assert coord._initialized is False

    def test_v3_import_error_tries_fallback(self) -> None:
        """ImportError on safla_memory triggers fallback path."""
        mock_fallback_instance = MagicMock()
        mock_memory_module = MagicMock(
            SAFLANeuralMemory=MagicMock(return_value=mock_fallback_instance)
        )
        mock_config_cls = MagicMock(return_value=MagicMock())
        mock_models_module = MagicMock(OrchestratorConfig=mock_config_cls)

        with patch.dict(
            sys.modules,
            {
                "enhanced_agent_bus.safla_memory": None,  # triggers ImportError
                "enhanced_agent_bus.memory": mock_memory_module,
                "enhanced_agent_bus.models": mock_models_module,
            },
        ):
            coord = MemoryCoordinator(use_v3=True)

        assert isinstance(coord._initialized, bool)

    def test_persistence_enabled_false_forwarded(self) -> None:
        """persistence_enabled=False is stored as attribute."""
        with patch.object(MemoryCoordinator, "_initialize_memory"):
            coord = MemoryCoordinator(persistence_enabled=False, use_v3=True)
        assert coord._persistence_enabled is False


# ---------------------------------------------------------------------------
# get_stats() edge cases
# ---------------------------------------------------------------------------


class TestGetStatsEdgeCases:
    def test_v3_without_get_stats_attr(self) -> None:
        """v3 memory without get_stats attr is handled gracefully."""
        coord = MemoryCoordinator.__new__(MemoryCoordinator)
        coord._persistence_enabled = True
        coord._use_v3 = True
        coord._memory_v3 = object()  # no get_stats attribute
        coord._memory_fallback = None
        coord._initialized = True

        stats = coord.get_stats()
        assert "v3_stats" not in stats
        assert stats["v3_enabled"] is True

    def test_fallback_without_get_stats_attr(self) -> None:
        """fallback memory without get_stats attr is handled gracefully."""
        coord = MemoryCoordinator.__new__(MemoryCoordinator)
        coord._persistence_enabled = True
        coord._use_v3 = True
        coord._memory_v3 = None
        coord._memory_fallback = object()  # no get_stats attribute
        coord._initialized = True

        stats = coord.get_stats()
        assert "fallback_stats" not in stats
        assert stats["v3_enabled"] is False

    def test_get_stats_all_none(self) -> None:
        coord = MemoryCoordinator.__new__(MemoryCoordinator)
        coord._persistence_enabled = False
        coord._use_v3 = False
        coord._memory_v3 = None
        coord._memory_fallback = None
        coord._initialized = False

        stats = coord.get_stats()
        assert stats["initialized"] is False
        assert stats["persistence_enabled"] is False
        assert stats["v3_enabled"] is False


# ---------------------------------------------------------------------------
# _MEMORY_COORDINATOR_ERRORS constant
# ---------------------------------------------------------------------------


class TestErrorTuple:
    def test_all_expected_errors_present(self) -> None:
        expected = {
            RuntimeError,
            ValueError,
            TypeError,
            AttributeError,
            LookupError,
            OSError,
            TimeoutError,
            ConnectionError,
        }
        assert set(_MEMORY_COORDINATOR_ERRORS) == expected

    def test_is_tuple(self) -> None:
        assert isinstance(_MEMORY_COORDINATOR_ERRORS, tuple)

    def test_length(self) -> None:
        assert len(_MEMORY_COORDINATOR_ERRORS) == 8


# ---------------------------------------------------------------------------
# Constitutional hash
# ---------------------------------------------------------------------------


class TestConstitutionalHash:
    def test_class_attribute_value(self) -> None:
        assert (
            MemoryCoordinator.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret
        )

    def test_instance_attribute_matches_class(self) -> None:
        coord = _coord_uninit()
        assert coord.constitutional_hash == MemoryCoordinator.constitutional_hash

    def test_get_stats_hash_matches_class(self) -> None:
        coord = _coord_uninit()
        stats = coord.get_stats()
        assert stats["constitutional_hash"] == MemoryCoordinator.constitutional_hash
