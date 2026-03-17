# Constitutional Hash: cdd01ef066bc6cf2
"""
Comprehensive tests for ultimate_agentic_system/config.py
==========================================================

Covers all classes, properties, validators, defaults, branches and edge cases
to achieve ≥95% line coverage.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import sys
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest
from src.core.shared.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers — import the module under test
# ---------------------------------------------------------------------------
from ..ultimate_agentic_system.config import (
    SystemCapabilities,
    SystemConfig,
    SystemVersion,
)


@pytest.fixture(autouse=True)
def _restore_meta_orchestrator_available():
    """Restore META_ORCHESTRATOR_AVAILABLE after each test.

    TestToOrchestratorConfigUnavailable patches META_ORCHESTRATOR_AVAILABLE to False
    directly on the config module. If the test crashes before the finally block or
    if xdist schedules other tests on the same worker, the flag stays False and
    breaks all subsequent tests that depend on OrchestratorConfig availability.
    This autouse fixture guarantees restoration. (PM-012 pattern)
    """
    import packages.enhanced_agent_bus.ultimate_agentic_system.availability as avail_mod
    import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

    orig_config_flag = config_mod.META_ORCHESTRATOR_AVAILABLE
    orig_avail_flag = avail_mod.META_ORCHESTRATOR_AVAILABLE

    yield

    config_mod.META_ORCHESTRATOR_AVAILABLE = orig_config_flag
    avail_mod.META_ORCHESTRATOR_AVAILABLE = orig_avail_flag


# ===========================================================================
# SystemVersion Enum
# ===========================================================================


class TestSystemVersion:
    """Tests for the SystemVersion enum."""

    def test_enum_members_exist(self):
        """All four version levels must be present."""
        assert SystemVersion.BASIC is not None
        assert SystemVersion.STANDARD is not None
        assert SystemVersion.ADVANCED is not None
        assert SystemVersion.ULTIMATE is not None

    def test_enum_values_are_unique(self):
        """Each member must have a distinct value."""
        values = [m.value for m in SystemVersion]
        assert len(values) == len(set(values))

    def test_enum_is_auto(self):
        """Values are assigned by auto() — they must be integers."""
        for member in SystemVersion:
            assert isinstance(member.value, int)

    def test_basic_is_smallest(self):
        """BASIC should be the first auto-assigned value."""
        assert SystemVersion.BASIC.value < SystemVersion.STANDARD.value

    def test_ordering(self):
        """Version levels should be ordered BASIC < STANDARD < ADVANCED < ULTIMATE."""
        assert SystemVersion.BASIC.value < SystemVersion.STANDARD.value
        assert SystemVersion.STANDARD.value < SystemVersion.ADVANCED.value
        assert SystemVersion.ADVANCED.value < SystemVersion.ULTIMATE.value

    def test_membership_check(self):
        """Membership check works correctly."""
        assert SystemVersion.BASIC in SystemVersion
        assert SystemVersion.ULTIMATE in SystemVersion

    def test_string_representation(self):
        """Name property reflects enum key."""
        assert SystemVersion.BASIC.name == "BASIC"
        assert SystemVersion.ULTIMATE.name == "ULTIMATE"

    def test_four_members_total(self):
        """Exactly four members defined."""
        assert len(list(SystemVersion)) == 4


# ===========================================================================
# SystemCapabilities — defaults
# ===========================================================================


class TestSystemCapabilitiesDefaults:
    """Test default values of SystemCapabilities."""

    def test_default_all_booleans_false(self):
        """All capability flags should default to False."""
        caps = SystemCapabilities()
        assert caps.meta_orchestrator is False
        assert caps.safla_memory_v3 is False
        assert caps.swarm_intelligence is False
        assert caps.workflow_evolution is False
        assert caps.research_integration is False
        assert caps.durable_execution is False
        assert caps.tool_documentation is False
        assert caps.mamba2_context is False
        assert caps.maci_enforcement is False
        assert caps.langgraph_workflows is False

    def test_default_constitutional_hash(self):
        """Default constitutional hash must match project constant."""
        caps = SystemCapabilities()
        assert caps.constitutional_hash == CONSTITUTIONAL_HASH
        assert caps.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_default_version_is_basic(self):
        """Default version must be BASIC."""
        caps = SystemCapabilities()
        assert caps.version is SystemVersion.BASIC

    def test_default_capability_count_zero(self):
        """When all flags are False, count must be 0."""
        caps = SystemCapabilities()
        assert caps.capability_count == 0

    def test_default_is_ultimate_false(self):
        """Not all capabilities enabled → is_ultimate is False."""
        caps = SystemCapabilities()
        assert caps.is_ultimate is False


# ===========================================================================
# SystemCapabilities — capability_count property
# ===========================================================================


class TestSystemCapabilitiesCapabilityCount:
    """Tests for the capability_count computed property."""

    def test_single_flag_counts_one(self):
        caps = SystemCapabilities(meta_orchestrator=True)
        assert caps.capability_count == 1

    def test_two_flags_counts_two(self):
        caps = SystemCapabilities(meta_orchestrator=True, safla_memory_v3=True)
        assert caps.capability_count == 2

    def test_all_ten_flags_enabled(self):
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
            mamba2_context=True,
            maci_enforcement=True,
            langgraph_workflows=True,
        )
        assert caps.capability_count == 10

    def test_count_with_only_extra_flags(self):
        """mamba2_context, maci_enforcement and langgraph_workflows contribute to count."""
        caps = SystemCapabilities(mamba2_context=True, maci_enforcement=True)
        assert caps.capability_count == 2

    def test_count_with_langgraph_only(self):
        caps = SystemCapabilities(langgraph_workflows=True)
        assert caps.capability_count == 1

    def test_count_unchanged_by_version_or_hash(self):
        """version and constitutional_hash are not counted."""
        caps = SystemCapabilities(
            version=SystemVersion.ULTIMATE,
            constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
        )
        assert caps.capability_count == 0

    def test_count_mixed_flags(self):
        caps = SystemCapabilities(
            meta_orchestrator=True,
            research_integration=True,
            durable_execution=True,
        )
        assert caps.capability_count == 3

    def test_count_all_but_one(self):
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
            mamba2_context=True,
            maci_enforcement=True,
            langgraph_workflows=False,  # one disabled
        )
        assert caps.capability_count == 9


# ===========================================================================
# SystemCapabilities — is_ultimate property
# ===========================================================================


class TestSystemCapabilitiesIsUltimate:
    """Tests for the is_ultimate computed property."""

    def test_not_ultimate_when_all_false(self):
        assert SystemCapabilities().is_ultimate is False

    def test_not_ultimate_when_partial(self):
        caps = SystemCapabilities(meta_orchestrator=True, safla_memory_v3=True)
        assert caps.is_ultimate is False

    def test_is_ultimate_requires_exactly_seven_flags(self):
        """is_ultimate checks 7 specific fields (not mamba2_context, maci_enforcement, langgraph)."""  # noqa: E501
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
        )
        assert caps.is_ultimate is True

    def test_extra_flags_do_not_matter_for_is_ultimate(self):
        """mamba2_context etc. not included in is_ultimate check."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
            mamba2_context=False,  # not required
            maci_enforcement=False,
            langgraph_workflows=False,
        )
        assert caps.is_ultimate is True

    def test_missing_one_of_seven_not_ultimate(self):
        # tool_documentation = False
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=False,
        )
        assert caps.is_ultimate is False

    def test_missing_research_integration(self):
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=False,
            durable_execution=True,
            tool_documentation=True,
        )
        assert caps.is_ultimate is False

    def test_missing_meta_orchestrator(self):
        caps = SystemCapabilities(
            meta_orchestrator=False,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
        )
        assert caps.is_ultimate is False


# ===========================================================================
# SystemCapabilities — mutation
# ===========================================================================


class TestSystemCapabilitiesMutation:
    """Test that dataclass fields can be set after instantiation."""

    def test_set_version(self):
        caps = SystemCapabilities()
        caps.version = SystemVersion.ULTIMATE
        assert caps.version is SystemVersion.ULTIMATE

    def test_set_flags_after_construction(self):
        caps = SystemCapabilities()
        caps.meta_orchestrator = True
        assert caps.capability_count == 1
        assert caps.is_ultimate is False


# ===========================================================================
# SystemConfig — defaults
# ===========================================================================


class TestSystemConfigDefaults:
    """Verify all SystemConfig default values."""

    def setup_method(self):
        self.cfg = SystemConfig()

    def test_default_constitutional_hash(self):
        assert self.cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_max_concurrent_tasks(self):
        assert self.cfg.max_concurrent_tasks == 100

    def test_default_task_timeout_seconds(self):
        assert self.cfg.task_timeout_seconds == 300.0

    def test_default_enable_persistence(self):
        assert self.cfg.enable_persistence is True

    def test_default_memory_db_path_none(self):
        assert self.cfg.memory_db_path is None

    def test_default_max_swarm_agents(self):
        assert self.cfg.max_swarm_agents == 50

    def test_default_enable_dynamic_spawning(self):
        assert self.cfg.enable_dynamic_spawning is True

    def test_default_evolution_strategy(self):
        assert self.cfg.evolution_strategy == "moderate"

    def test_default_max_evolutions_per_day(self):
        assert self.cfg.max_evolutions_per_day == 10

    def test_default_enable_ab_testing(self):
        assert self.cfg.enable_ab_testing is True

    def test_default_enable_research(self):
        assert self.cfg.enable_research is True

    def test_default_research_cache_enabled(self):
        assert self.cfg.research_cache_enabled is True

    def test_default_max_results_per_source(self):
        assert self.cfg.max_results_per_source == 10

    def test_default_enable_maci(self):
        assert self.cfg.enable_maci is True

    def test_default_maci_strict_mode(self):
        assert self.cfg.maci_strict_mode is True

    def test_default_enable_durable_execution(self):
        assert self.cfg.enable_durable_execution is True

    def test_default_checkpoint_db_path_none(self):
        assert self.cfg.checkpoint_db_path is None

    def test_default_checkpoint_interval(self):
        assert self.cfg.checkpoint_interval == 1

    def test_default_max_retries(self):
        assert self.cfg.max_retries == 3

    def test_default_recovery_strategy(self):
        assert self.cfg.recovery_strategy == "checkpoint"

    def test_default_enable_tool_documentation(self):
        assert self.cfg.enable_tool_documentation is True

    def test_default_include_default_tools(self):
        assert self.cfg.include_default_tools is True

    def test_default_tool_schema_format(self):
        assert self.cfg.tool_schema_format == "openai"

    def test_default_enable_caching(self):
        assert self.cfg.enable_caching is True

    def test_default_parallel_execution(self):
        assert self.cfg.parallel_execution is True


# ===========================================================================
# SystemConfig — custom construction
# ===========================================================================


class TestSystemConfigCustomConstruction:
    """Test constructing SystemConfig with non-default values."""

    def test_custom_max_concurrent_tasks(self):
        cfg = SystemConfig(max_concurrent_tasks=200)
        assert cfg.max_concurrent_tasks == 200

    def test_custom_task_timeout(self):
        cfg = SystemConfig(task_timeout_seconds=60.0)
        assert cfg.task_timeout_seconds == 60.0

    def test_custom_memory_db_path(self):
        cfg = SystemConfig(memory_db_path="/tmp/test.db")  # noqa: S108
        assert cfg.memory_db_path == "/tmp/test.db"  # noqa: S108

    def test_custom_checkpoint_db_path(self):
        cfg = SystemConfig(checkpoint_db_path="/tmp/ckpt.db")  # noqa: S108
        assert cfg.checkpoint_db_path == "/tmp/ckpt.db"  # noqa: S108

    def test_custom_evolution_strategy(self):
        cfg = SystemConfig(evolution_strategy="aggressive")
        assert cfg.evolution_strategy == "aggressive"

    def test_conservative_evolution_strategy(self):
        cfg = SystemConfig(evolution_strategy="conservative")
        assert cfg.evolution_strategy == "conservative"

    def test_disable_all_features(self):
        cfg = SystemConfig(
            enable_persistence=False,
            enable_dynamic_spawning=False,
            enable_ab_testing=False,
            enable_research=False,
            research_cache_enabled=False,
            enable_maci=False,
            maci_strict_mode=False,
            enable_durable_execution=False,
            enable_tool_documentation=False,
            include_default_tools=False,
            enable_caching=False,
            parallel_execution=False,
        )
        assert cfg.enable_persistence is False
        assert cfg.enable_dynamic_spawning is False
        assert cfg.enable_ab_testing is False
        assert cfg.enable_research is False
        assert cfg.research_cache_enabled is False
        assert cfg.enable_maci is False
        assert cfg.maci_strict_mode is False
        assert cfg.enable_durable_execution is False
        assert cfg.enable_tool_documentation is False
        assert cfg.include_default_tools is False
        assert cfg.enable_caching is False
        assert cfg.parallel_execution is False

    def test_anthropic_tool_schema_format(self):
        cfg = SystemConfig(tool_schema_format="anthropic")
        assert cfg.tool_schema_format == "anthropic"

    def test_restart_recovery_strategy(self):
        cfg = SystemConfig(recovery_strategy="restart")
        assert cfg.recovery_strategy == "restart"

    def test_skip_recovery_strategy(self):
        cfg = SystemConfig(recovery_strategy="skip")
        assert cfg.recovery_strategy == "skip"

    def test_custom_max_swarm_agents(self):
        cfg = SystemConfig(max_swarm_agents=5)
        assert cfg.max_swarm_agents == 5

    def test_custom_max_retries(self):
        cfg = SystemConfig(max_retries=5)
        assert cfg.max_retries == 5

    def test_custom_checkpoint_interval(self):
        cfg = SystemConfig(checkpoint_interval=10)
        assert cfg.checkpoint_interval == 10


# ===========================================================================
# SystemConfig.to_orchestrator_config — META_ORCHESTRATOR_AVAILABLE = True
# ===========================================================================


class TestToOrchestratorConfigAvailable:
    """Test to_orchestrator_config when META_ORCHESTRATOR_AVAILABLE is True."""

    def test_returns_orchestrator_config(self):
        """Should return an OrchestratorConfig instance when available."""
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig()
        orch = cfg.to_orchestrator_config()
        from ..meta_orchestrator import OrchestratorConfig

        assert isinstance(orch, OrchestratorConfig)

    def test_constitutional_hash_preserved(self):
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig()
        orch = cfg.to_orchestrator_config()
        assert orch.constitutional_hash == CONSTITUTIONAL_HASH

    def test_max_swarm_agents_capped_at_8_when_larger(self):
        """When max_swarm_agents > 8, OrchestratorConfig should receive 8."""
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(max_swarm_agents=50)
        orch = cfg.to_orchestrator_config()
        assert orch.max_swarm_agents == 8  # min(50, 8) = 8

    def test_max_swarm_agents_passes_through_when_smaller(self):
        """When max_swarm_agents <= 8, value is passed as-is."""
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(max_swarm_agents=4)
        orch = cfg.to_orchestrator_config()
        assert orch.max_swarm_agents == 4  # min(4, 8) = 4

    def test_enable_maci_passed(self):
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(enable_maci=False)
        orch = cfg.to_orchestrator_config()
        assert orch.enable_maci is False

    def test_enable_research_passed(self):
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(enable_research=False)
        orch = cfg.to_orchestrator_config()
        assert orch.enable_research is False

    def test_auto_evolution_limit_passed(self):
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(max_evolutions_per_day=5)
        orch = cfg.to_orchestrator_config()
        assert orch.auto_evolution_limit == 5

    def test_swarm_agents_exactly_eight_passes(self):
        """Boundary case: max_swarm_agents=8 should pass through unchanged."""
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(max_swarm_agents=8)
        orch = cfg.to_orchestrator_config()
        assert orch.max_swarm_agents == 8

    def test_swarm_agents_zero_passes(self):
        """Boundary: min(0, 8) = 0."""
        from ..ultimate_agentic_system.availability import META_ORCHESTRATOR_AVAILABLE

        if not META_ORCHESTRATOR_AVAILABLE:
            pytest.skip("Meta-Orchestrator not available in this environment")

        cfg = SystemConfig(max_swarm_agents=0)
        orch = cfg.to_orchestrator_config()
        assert orch.max_swarm_agents == 0


# ===========================================================================
# SystemConfig.to_orchestrator_config — META_ORCHESTRATOR_AVAILABLE = False
# ===========================================================================


class TestToOrchestratorConfigUnavailable:
    """Test to_orchestrator_config when META_ORCHESTRATOR_AVAILABLE is False."""

    def test_raises_runtime_error_when_unavailable(self):
        """Should raise RuntimeError if META_ORCHESTRATOR_AVAILABLE is False."""
        import importlib

        import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

        # Patch the availability flag inside the config module's own namespace
        original = config_mod.META_ORCHESTRATOR_AVAILABLE
        config_mod.META_ORCHESTRATOR_AVAILABLE = False
        try:
            cfg = config_mod.SystemConfig()
            with pytest.raises(RuntimeError, match="Meta-Orchestrator not available"):
                cfg.to_orchestrator_config()
        finally:
            config_mod.META_ORCHESTRATOR_AVAILABLE = original

    def test_error_message_exact(self):
        import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

        original = config_mod.META_ORCHESTRATOR_AVAILABLE
        config_mod.META_ORCHESTRATOR_AVAILABLE = False
        try:
            cfg = config_mod.SystemConfig()
            with pytest.raises(RuntimeError) as exc_info:
                cfg.to_orchestrator_config()
            assert "Meta-Orchestrator not available" in str(exc_info.value)
        finally:
            config_mod.META_ORCHESTRATOR_AVAILABLE = original


# ===========================================================================
# __all__ exports
# ===========================================================================


class TestModuleExports:
    """Verify __all__ contains exactly the expected names."""

    def test_all_exports(self):
        import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

        assert "SystemVersion" in config_mod.__all__
        assert "SystemCapabilities" in config_mod.__all__
        assert "SystemConfig" in config_mod.__all__
        assert "CONSTITUTIONAL_HASH" in config_mod.__all__

    def test_constitutional_hash_export_value(self):
        import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

        assert config_mod.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# ===========================================================================
# Dataclass field introspection
# ===========================================================================


class TestDataclassFields:
    """Introspect dataclass structure to ensure correct field declarations."""

    def test_system_capabilities_has_correct_field_count(self):
        """SystemCapabilities has 12 fields."""
        f = fields(SystemCapabilities)
        assert len(f) == 12

    def test_system_config_has_correct_fields(self):
        """SystemConfig must have all expected field names."""
        field_names = {f.name for f in fields(SystemConfig)}
        expected = {
            "constitutional_hash",
            "max_concurrent_tasks",
            "task_timeout_seconds",
            "enable_persistence",
            "memory_db_path",
            "max_swarm_agents",
            "enable_dynamic_spawning",
            "evolution_strategy",
            "max_evolutions_per_day",
            "enable_ab_testing",
            "enable_research",
            "research_cache_enabled",
            "max_results_per_source",
            "enable_maci",
            "maci_strict_mode",
            "enable_durable_execution",
            "checkpoint_db_path",
            "checkpoint_interval",
            "max_retries",
            "recovery_strategy",
            "enable_tool_documentation",
            "include_default_tools",
            "tool_schema_format",
            "enable_caching",
            "parallel_execution",
        }
        assert expected.issubset(field_names)

    def test_system_capabilities_field_names(self):
        """SystemCapabilities must have all expected field names."""
        field_names = {f.name for f in fields(SystemCapabilities)}
        expected = {
            "meta_orchestrator",
            "safla_memory_v3",
            "swarm_intelligence",
            "workflow_evolution",
            "research_integration",
            "durable_execution",
            "tool_documentation",
            "mamba2_context",
            "maci_enforcement",
            "langgraph_workflows",
            "constitutional_hash",
            "version",
        }
        assert expected == field_names


# ===========================================================================
# Integration — round-trip config
# ===========================================================================


class TestIntegration:
    """Integration-level sanity checks combining multiple classes."""

    def test_full_system_config_to_capabilities_roundtrip(self):
        """Constructing config and capabilities from same settings stays consistent."""
        cfg = SystemConfig(enable_maci=True, enable_research=True)
        caps = SystemCapabilities(
            maci_enforcement=cfg.enable_maci,
            research_integration=cfg.enable_research,
        )
        assert caps.capability_count == 2

    def test_all_capabilities_leads_to_ultimate(self):
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
            version=SystemVersion.ULTIMATE,
        )
        assert caps.is_ultimate is True
        assert caps.version is SystemVersion.ULTIMATE

    def test_constitutional_hash_consistent_across_classes(self):
        cfg = SystemConfig()
        caps = SystemCapabilities()
        assert cfg.constitutional_hash == caps.constitutional_hash == CONSTITUTIONAL_HASH

    def test_system_config_is_dataclass(self):
        """SystemConfig should be a proper dataclass."""
        assert hasattr(SystemConfig, "__dataclass_fields__")

    def test_system_capabilities_is_dataclass(self):
        assert hasattr(SystemCapabilities, "__dataclass_fields__")

    def test_capability_count_reflects_dynamic_changes(self):
        caps = SystemCapabilities()
        assert caps.capability_count == 0
        caps.meta_orchestrator = True
        assert caps.capability_count == 1
        caps.safla_memory_v3 = True
        assert caps.capability_count == 2
        caps.meta_orchestrator = False
        assert caps.capability_count == 1

    def test_system_version_advanced_assigned(self):
        caps = SystemCapabilities(version=SystemVersion.ADVANCED)
        assert caps.version is SystemVersion.ADVANCED

    def test_system_version_standard_assigned(self):
        caps = SystemCapabilities(version=SystemVersion.STANDARD)
        assert caps.version is SystemVersion.STANDARD
