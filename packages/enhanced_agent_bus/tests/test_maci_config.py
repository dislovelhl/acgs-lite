"""
ACGS-2 Enhanced Agent Bus - MACI Configuration Tests
Constitutional Hash: 608508a9bd224290

Tests for configuration-based MACI role management.
"""

import json
import os
import tempfile

import pytest

from enhanced_agent_bus.maci_enforcement import (
    CONSTITUTIONAL_HASH,
    MACIAgentRoleConfig,
    MACIConfig,
    MACIConfigLoader,
    MACIRole,
    MACIRoleRegistry,
    apply_maci_config,
)

# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMACIAgentRoleConfig:
    """Test MACIAgentRoleConfig dataclass."""

    def test_basic_creation(self):
        """Test basic config creation."""
        config = MACIAgentRoleConfig(
            agent_id="test-agent",
            role=MACIRole.EXECUTIVE,
        )
        assert config.agent_id == "test-agent"
        assert config.role == MACIRole.EXECUTIVE
        assert config.capabilities == []
        assert config.metadata == {}

    def test_with_capabilities(self):
        """Test config with capabilities."""
        config = MACIAgentRoleConfig(
            agent_id="test-agent",
            role=MACIRole.LEGISLATIVE,
            capabilities=["analyze", "extract"],
        )
        assert config.capabilities == ["analyze", "extract"]

    def test_with_metadata(self):
        """Test config with metadata."""
        config = MACIAgentRoleConfig(
            agent_id="test-agent",
            role=MACIRole.JUDICIAL,
            metadata={"priority": "high", "version": "1.0"},
        )
        assert config.metadata["priority"] == "high"
        assert config.metadata["version"] == "1.0"

    def test_string_role_normalization(self):
        """Test that string roles are normalized to enum."""
        config = MACIAgentRoleConfig(
            agent_id="test-agent",
            role="executive",  # type: ignore
        )
        assert config.role == MACIRole.EXECUTIVE

    def test_uppercase_string_role(self):
        """Test uppercase string role normalization."""
        config = MACIAgentRoleConfig(
            agent_id="test-agent",
            role="LEGISLATIVE",  # type: ignore
        )
        assert config.role == MACIRole.LEGISLATIVE


class TestMACIConfig:
    """Test MACIConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MACIConfig()
        assert config.strict_mode is True
        assert config.agents == []
        assert config.default_role is None
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_agents(self):
        """Test config with agent list."""
        agents = [
            MACIAgentRoleConfig(agent_id="exec", role=MACIRole.EXECUTIVE),
            MACIAgentRoleConfig(agent_id="legis", role=MACIRole.LEGISLATIVE),
        ]
        config = MACIConfig(agents=agents)
        assert len(config.agents) == 2

    def test_get_role_for_agent(self):
        """Test getting role for a specific agent."""
        agents = [
            MACIAgentRoleConfig(agent_id="exec-1", role=MACIRole.EXECUTIVE),
            MACIAgentRoleConfig(agent_id="judge-1", role=MACIRole.JUDICIAL),
        ]
        config = MACIConfig(agents=agents)

        assert config.get_role_for_agent("exec-1") == MACIRole.EXECUTIVE
        assert config.get_role_for_agent("judge-1") == MACIRole.JUDICIAL
        assert config.get_role_for_agent("unknown") is None

    def test_get_role_with_default(self):
        """Test default role fallback."""
        config = MACIConfig(default_role=MACIRole.EXECUTIVE)
        assert config.get_role_for_agent("any-agent") == MACIRole.EXECUTIVE

    def test_get_agent_config(self):
        """Test getting full agent configuration."""
        agents = [
            MACIAgentRoleConfig(
                agent_id="exec-1",
                role=MACIRole.EXECUTIVE,
                capabilities=["propose"],
            ),
        ]
        config = MACIConfig(agents=agents)

        agent_config = config.get_agent_config("exec-1")
        assert agent_config is not None
        assert agent_config.capabilities == ["propose"]

        assert config.get_agent_config("unknown") is None


class TestMACIConfigLoader:
    """Test MACIConfigLoader class."""

    def test_loader_initialization(self):
        """Test loader initialization."""
        loader = MACIConfigLoader()
        assert loader.constitutional_hash == CONSTITUTIONAL_HASH

    def test_load_from_dict(self):
        """Test loading from dictionary."""
        loader = MACIConfigLoader()
        config_dict = {
            "strict_mode": False,
            "default_role": "executive",
            "agents": [
                {"agent_id": "exec-1", "role": "executive"},
                {"agent_id": "legis-1", "role": "legislative"},
            ],
        }

        config = loader.load_from_dict(config_dict)

        assert config.strict_mode is False
        assert config.default_role == MACIRole.EXECUTIVE
        assert len(config.agents) == 2
        assert config.agents[0].agent_id == "exec-1"
        assert config.agents[0].role == MACIRole.EXECUTIVE

    def test_load_from_dict_with_capabilities(self):
        """Test loading with capabilities from dictionary."""
        loader = MACIConfigLoader()
        config_dict = {
            "agents": [
                {
                    "agent_id": "test-agent",
                    "role": "judicial",
                    "capabilities": ["validate", "audit"],
                    "metadata": {"version": "2.0"},
                },
            ],
        }

        config = loader.load_from_dict(config_dict)

        assert len(config.agents) == 1
        assert config.agents[0].capabilities == ["validate", "audit"]
        assert config.agents[0].metadata["version"] == "2.0"

    def test_load_from_dict_alternate_id_key(self):
        """Test loading with 'id' instead of 'agent_id'."""
        loader = MACIConfigLoader()
        config_dict = {
            "agents": [
                {"id": "alt-agent", "role": "executive"},
            ],
        }

        config = loader.load_from_dict(config_dict)

        assert len(config.agents) == 1
        assert config.agents[0].agent_id == "alt-agent"

    def test_load_from_json(self):
        """Test loading from JSON file."""
        loader = MACIConfigLoader()

        config_dict = {
            "strict_mode": True,
            "agents": [
                {"agent_id": "json-agent", "role": "legislative"},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_dict, f)
            temp_path = f.name

        try:
            config = loader.load_from_json(temp_path)
            assert config.strict_mode is True
            assert len(config.agents) == 1
            assert config.agents[0].agent_id == "json-agent"
        finally:
            os.unlink(temp_path)

    def test_load_from_yaml(self):
        """Test loading from YAML file."""
        pytest.importorskip("yaml")

        loader = MACIConfigLoader()

        yaml_content = """
strict_mode: false
default_role: judicial
agents:
  - agent_id: yaml-exec
    role: executive
  - agent_id: yaml-judge
    role: judicial
    capabilities:
      - validate
      - audit
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = loader.load_from_yaml(temp_path)
            assert config.strict_mode is False
            assert config.default_role == MACIRole.JUDICIAL
            assert len(config.agents) == 2
            assert config.agents[0].agent_id == "yaml-exec"
            assert config.agents[1].capabilities == ["validate", "audit"]
        finally:
            os.unlink(temp_path)

    def test_load_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        loader = MACIConfigLoader()

        # Patch global_settings to None to ensure env vars are used
        import enhanced_agent_bus.maci_enforcement as maci_enforcement

        monkeypatch.setattr(maci_enforcement, "global_settings", None)

        # Set environment variables
        monkeypatch.setenv("MACI_STRICT_MODE", "false")
        monkeypatch.setenv("MACI_DEFAULT_ROLE", "executive")
        monkeypatch.setenv("MACI_AGENT_PROPOSER", "executive")
        monkeypatch.setenv("MACI_AGENT_PROPOSER_CAPABILITIES", "propose,synthesize")
        monkeypatch.setenv("MACI_AGENT_VALIDATOR", "judicial")

        config = loader.load_from_env()

        assert config.strict_mode is False
        assert config.default_role == MACIRole.EXECUTIVE
        assert len(config.agents) == 2

        # Find agents by id
        proposer = next((a for a in config.agents if a.agent_id == "proposer"), None)
        validator = next((a for a in config.agents if a.agent_id == "validator"), None)

        assert proposer is not None
        assert proposer.role == MACIRole.EXECUTIVE
        assert "propose" in proposer.capabilities
        assert "synthesize" in proposer.capabilities

        assert validator is not None
        assert validator.role == MACIRole.JUDICIAL

    def test_load_from_env_strict_mode_default(self, monkeypatch):
        """Test that strict mode defaults to True."""
        loader = MACIConfigLoader()

        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith("MACI_"):
                monkeypatch.delenv(key, raising=False)

        config = loader.load_from_env()
        assert config.strict_mode is True

    def test_load_auto_detect_json(self):
        """Test auto-detection for JSON files."""
        loader = MACIConfigLoader()

        config_dict = {"agents": [{"agent_id": "auto", "role": "executive"}]}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_dict, f)
            temp_path = f.name

        try:
            config = loader.load(temp_path)
            assert len(config.agents) == 1
            assert config.agents[0].agent_id == "auto"
        finally:
            os.unlink(temp_path)

    def test_load_auto_detect_yaml(self):
        """Test auto-detection for YAML files."""
        pytest.importorskip("yaml")

        loader = MACIConfigLoader()

        yaml_content = "agents:\n  - agent_id: auto-yaml\n    role: legislative\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            config = loader.load(temp_path)
            assert len(config.agents) == 1
            assert config.agents[0].agent_id == "auto-yaml"
        finally:
            os.unlink(temp_path)

    def test_load_none_uses_env(self, monkeypatch):
        """Test that load(None) uses environment variables."""
        loader = MACIConfigLoader()

        # Clear existing MACI env vars
        for key in list(os.environ.keys()):
            if key.startswith("MACI_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("MACI_AGENT_ENVTEST", "executive")

        config = loader.load(None)

        envtest = next((a for a in config.agents if a.agent_id == "envtest"), None)
        assert envtest is not None


class TestApplyMACIConfig:
    """Test apply_maci_config function."""

    async def test_apply_config_to_registry(self):
        """Test applying configuration to a registry."""
        registry = MACIRoleRegistry()
        config = MACIConfig(
            agents=[
                MACIAgentRoleConfig(
                    agent_id="apply-exec",
                    role=MACIRole.EXECUTIVE,
                    capabilities=["propose"],
                ),
                MACIAgentRoleConfig(
                    agent_id="apply-legis",
                    role=MACIRole.LEGISLATIVE,
                ),
            ],
        )

        count = await apply_maci_config(registry, config)

        assert count == 2

        exec_record = await registry.get_agent("apply-exec")
        assert exec_record is not None
        assert exec_record.role == MACIRole.EXECUTIVE

        legis_record = await registry.get_agent("apply-legis")
        assert legis_record is not None
        assert legis_record.role == MACIRole.LEGISLATIVE

    async def test_apply_empty_config(self):
        """Test applying empty configuration."""
        registry = MACIRoleRegistry()
        config = MACIConfig()

        count = await apply_maci_config(registry, config)

        assert count == 0

    async def test_apply_config_with_metadata(self):
        """Test that metadata is preserved when applying config."""
        registry = MACIRoleRegistry()
        config = MACIConfig(
            agents=[
                MACIAgentRoleConfig(
                    agent_id="meta-agent",
                    role=MACIRole.JUDICIAL,
                    capabilities=["validate"],
                    metadata={"priority": "high"},
                ),
            ],
        )

        await apply_maci_config(registry, config)

        record = await registry.get_agent("meta-agent")
        assert record is not None
        # Metadata should be included
        assert record.metadata.get("capabilities") == ["validate"]
        assert record.metadata.get("priority") == "high"


class TestMACIConfigIntegration:
    """Integration tests for MACI configuration."""

    async def test_full_config_workflow(self):
        """Test complete configuration workflow."""
        # 1. Create configuration
        loader = MACIConfigLoader()
        config_dict = {
            "strict_mode": True,
            "agents": [
                {"agent_id": "policy-agent", "role": "executive"},
                {"agent_id": "rule-agent", "role": "legislative"},
                {"agent_id": "audit-agent", "role": "judicial"},
            ],
        }
        config = loader.load_from_dict(config_dict)

        # 2. Create registry and apply config
        registry = MACIRoleRegistry()
        count = await apply_maci_config(registry, config)

        assert count == 3

        # 3. Verify all agents registered correctly
        exec_agents = await registry.get_agents_by_role(MACIRole.EXECUTIVE)
        legis_agents = await registry.get_agents_by_role(MACIRole.LEGISLATIVE)
        judge_agents = await registry.get_agents_by_role(MACIRole.JUDICIAL)

        assert len(exec_agents) == 1
        assert len(legis_agents) == 1
        assert len(judge_agents) == 1

        assert exec_agents[0].agent_id == "policy-agent"
        assert legis_agents[0].agent_id == "rule-agent"
        assert judge_agents[0].agent_id == "audit-agent"

    def test_constitutional_hash_preserved(self):
        """Test that constitutional hash is preserved in config."""
        config = MACIConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

        loader = MACIConfigLoader()
        assert loader.constitutional_hash == CONSTITUTIONAL_HASH

        loaded_config = loader.load_from_dict({"agents": []})
        assert loaded_config.constitutional_hash == CONSTITUTIONAL_HASH
