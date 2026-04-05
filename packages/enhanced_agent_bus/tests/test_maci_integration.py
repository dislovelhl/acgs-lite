"""
ACGS-2 Enhanced Agent Bus - MACI Integration Tests
Constitutional Hash: 608508a9bd224290

Tests for MACI role separation enforcement integration with EnhancedAgentBus
and MessageProcessor.
"""

import pytest

from enhanced_agent_bus.agent_bus import MACI_AVAILABLE, EnhancedAgentBus
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageType

# Skip if MACI not available, but mark as governance tests when run
# Constitutional Hash: 608508a9bd224290
pytestmark = [
    pytest.mark.skipif(not MACI_AVAILABLE, reason="MACI module not available"),
    pytest.mark.governance,
    pytest.mark.constitutional,
]

if MACI_AVAILABLE:
    from enhanced_agent_bus.maci_enforcement import MACIAction, MACIRole


class TestEnhancedAgentBusMACIIntegration:
    """Test MACI integration with EnhancedAgentBus."""

    def test_bus_maci_enabled_by_default(self):
        """Test that MACI is enabled by default per audit finding 2025-12."""
        bus = EnhancedAgentBus()
        # SECURITY: MACI enabled by default to prevent Gödel bypass attacks
        assert bus.maci_enabled
        assert bus.maci_registry is not None
        assert bus.maci_enforcer is not None

    def test_bus_maci_enabled(self):
        """Test enabling MACI on the bus."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.maci_enabled
        assert bus.maci_registry is not None
        assert bus.maci_enforcer is not None

    def test_bus_maci_strict_mode(self):
        """Test MACI strict mode configuration."""
        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=True)
        assert bus.maci_enabled
        assert bus._maci_strict_mode is True

    def test_bus_maci_non_strict_mode(self):
        """Test MACI non-strict mode configuration."""
        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=False)
        assert bus.maci_enabled
        assert bus._maci_strict_mode is False

    async def test_register_agent_with_maci_role(self):
        """Test registering an agent with a MACI role."""
        bus = EnhancedAgentBus(enable_maci=True)

        result = await bus.register_agent(
            agent_id="exec-agent",
            agent_type="executive",
            maci_role=MACIRole.EXECUTIVE,
        )

        assert result is True
        assert "exec-agent" in bus.agents
        assert bus.agents["exec-agent"]["maci_role"] == MACIRole.EXECUTIVE.value

        # Verify MACI registry
        maci_record = await bus.maci_registry.get_agent("exec-agent")
        assert maci_record is not None
        assert maci_record.role == MACIRole.EXECUTIVE

    async def test_register_agent_without_maci_role(self):
        """Test registering an agent without a MACI role when MACI enabled."""
        bus = EnhancedAgentBus(enable_maci=True)

        result = await bus.register_agent(
            agent_id="generic-agent",
            agent_type="default",
        )

        assert result is True
        assert "generic-agent" in bus.agents
        assert bus.agents["generic-agent"]["maci_role"] is None

        # Verify not in MACI registry
        maci_record = await bus.maci_registry.get_agent("generic-agent")
        assert maci_record is None

    async def test_register_all_maci_roles(self):
        """Test registering agents with all MACI roles."""
        bus = EnhancedAgentBus(enable_maci=True)

        for role, name in [
            (MACIRole.EXECUTIVE, "exec"),
            (MACIRole.LEGISLATIVE, "legis"),
            (MACIRole.JUDICIAL, "judge"),
        ]:
            result = await bus.register_agent(
                agent_id=f"{name}-agent",
                agent_type=role.value.lower(),
                maci_role=role,
            )
            assert result is True

        # Verify all registered
        exec_agents = await bus.maci_registry.get_agents_by_role(MACIRole.EXECUTIVE)
        legis_agents = await bus.maci_registry.get_agents_by_role(MACIRole.LEGISLATIVE)
        judge_agents = await bus.maci_registry.get_agents_by_role(MACIRole.JUDICIAL)

        assert len(exec_agents) == 1
        assert len(legis_agents) == 1
        assert len(judge_agents) == 1


class TestMessageProcessorMACIIntegration:
    """Test MACI integration with MessageProcessor."""

    def test_processor_maci_enabled_by_default(self):
        """Test that MACI is enabled by default per audit finding 2025-12."""
        processor = MessageProcessor()
        # SECURITY: MACI enabled by default to prevent Gödel bypass attacks
        assert processor._enable_maci is True
        # Registry is set via bus, not processor default
        assert processor._maci_registry is None

    def test_processor_maci_enabled(self):
        """Test enabling MACI in MessageProcessor."""
        processor = MessageProcessor(enable_maci=True)
        assert processor._enable_maci is True

    def test_processor_maci_with_registry(self):
        """Test MessageProcessor with external MACI registry."""
        from enhanced_agent_bus.maci_enforcement import MACIEnforcer, MACIRoleRegistry

        registry = MACIRoleRegistry()
        enforcer = MACIEnforcer(registry=registry)

        processor = MessageProcessor(
            enable_maci=True,
            maci_registry=registry,
            maci_enforcer=enforcer,
        )

        assert processor._enable_maci is True
        assert processor._maci_registry is registry
        assert processor._maci_enforcer is enforcer

    def test_auto_select_strategy_includes_maci(self):
        """Test that auto-select strategy wraps with MACI when enabled."""
        processor = MessageProcessor(enable_maci=True)

        strategy_name = processor._processing_strategy.get_name()
        assert "maci" in strategy_name.lower()

    def test_auto_select_strategy_excludes_maci_when_disabled(self):
        """Test that auto-select strategy doesn't include MACI when disabled."""
        processor = MessageProcessor(
            enable_maci=False
        )  # test-only: MACI off — testing MACI integration

        strategy_name = processor._processing_strategy.get_name()
        assert "maci" not in strategy_name.lower()


class TestMACIProcessingStrategyIntegration:
    """Test MACIProcessingStrategy integration."""

    def test_maci_strategy_creation(self):
        """Test creating MACIProcessingStrategy."""
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        inner = PythonProcessingStrategy()
        maci = MACIProcessingStrategy(inner_strategy=inner)

        assert maci.registry is not None
        assert maci.enforcer is not None
        assert "maci" in maci.get_name().lower()

    def test_maci_strategy_with_external_registry(self):
        """Test MACIProcessingStrategy with external registry."""
        from enhanced_agent_bus.maci_enforcement import MACIEnforcer, MACIRoleRegistry
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        registry = MACIRoleRegistry()
        enforcer = MACIEnforcer(registry=registry)
        inner = PythonProcessingStrategy()

        maci = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=registry,
            maci_enforcer=enforcer,
        )

        assert maci.registry is registry
        assert maci.enforcer is enforcer

    async def test_maci_strategy_validates_messages(self):
        """Test that MACI strategy validates messages."""
        from enhanced_agent_bus.maci_enforcement import MACIEnforcer, MACIRoleRegistry
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        registry = MACIRoleRegistry()
        enforcer = MACIEnforcer(registry=registry, strict_mode=False)
        inner = PythonProcessingStrategy()

        maci = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=registry,
            maci_enforcer=enforcer,
            strict_mode=False,  # Non-strict allows unregistered
        )

        message = AgentMessage(
            from_agent="unknown-agent",
            to_agent="target-agent",
            content={"data": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
            message_type=MessageType.TASK_REQUEST,
        )

        # Should pass in non-strict mode even without registration
        result = await maci.process(message, {})
        # Result depends on inner strategy, but should not fail on MACI
        assert result is not None


class TestMACIEndToEndIntegration:
    """End-to-end tests for MACI integration."""

    async def test_full_maci_workflow(self):
        """Test complete MACI workflow with bus and processor."""
        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=False)

        # Register agents with roles
        await bus.register_agent(
            agent_id="policy-proposer",
            agent_type="executive",
            maci_role=MACIRole.EXECUTIVE,
        )
        await bus.register_agent(
            agent_id="rule-extractor",
            agent_type="legislative",
            maci_role=MACIRole.LEGISLATIVE,
        )
        await bus.register_agent(
            agent_id="validator",
            agent_type="judicial",
            maci_role=MACIRole.JUDICIAL,
        )

        # Verify all roles registered
        exec_agents = await bus.maci_registry.get_agents_by_role(MACIRole.EXECUTIVE)
        legis_agents = await bus.maci_registry.get_agents_by_role(MACIRole.LEGISLATIVE)
        judge_agents = await bus.maci_registry.get_agents_by_role(MACIRole.JUDICIAL)

        assert len(exec_agents) == 1
        assert len(legis_agents) == 1
        assert len(judge_agents) == 1

        # Verify processor has MACI enabled
        assert bus.processor._enable_maci is True

    async def test_maci_role_separation_enforced(self):
        """Test that role separation is enforced in message processing."""

        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=True)

        # Register an executive agent
        await bus.register_agent(
            agent_id="exec-agent",
            agent_type="executive",
            maci_role=MACIRole.EXECUTIVE,
        )

        # The executive is registered, MACI enforcer should track it
        exec_record = await bus.maci_registry.get_agent("exec-agent")
        assert exec_record is not None
        # Use value comparison to avoid enum identity issues with different imports
        assert exec_record.role.value == MACIRole.EXECUTIVE.value

        # Verify enforcer can check permissions using value-based comparison
        # to avoid import path mismatch between test and source modules
        from enhanced_agent_bus.maci_enforcement import ROLE_PERMISSIONS

        exec_permissions = {a.value for a in ROLE_PERMISSIONS.get(exec_record.role, set())}
        can_propose = MACIAction.PROPOSE.value in exec_permissions
        can_validate = MACIAction.VALIDATE.value in exec_permissions

        assert can_propose is True  # Executives can propose
        assert can_validate is False  # Executives cannot validate


class TestMACIConstitutionalCompliance:
    """Test constitutional compliance with MACI."""

    def test_maci_bus_has_constitutional_hash(self):
        """Test that MACI-enabled bus maintains constitutional hash."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH

    def test_maci_registry_has_constitutional_hash(self):
        """Test that MACI registry has constitutional hash."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.maci_registry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_maci_enforcer_has_constitutional_hash(self):
        """Test that MACI enforcer has constitutional hash."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.maci_enforcer.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_agent_record_has_constitutional_hash(self):
        """Test that MACI agent records have constitutional hash."""
        bus = EnhancedAgentBus(enable_maci=True)

        await bus.register_agent(
            agent_id="test-agent",
            maci_role=MACIRole.JUDICIAL,
        )

        record = await bus.maci_registry.get_agent("test-agent")
        assert record.constitutional_hash == CONSTITUTIONAL_HASH
