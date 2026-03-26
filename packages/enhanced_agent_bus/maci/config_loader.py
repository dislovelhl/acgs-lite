"""
MACI Configuration Loader.

Supports loading MACI configuration from environment variables, JSON files,
YAML files, or dictionaries with type-safe extraction.

Constitutional Hash: 608508a9bd224290
"""

import json
import os
from pathlib import Path

from src.core.shared.type_guards import get_str, get_str_list, is_json_dict

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..maci_imports import (
    CONSTITUTIONAL_HASH,
    global_settings,
)
from .models import MACIAgentRoleConfig, MACIConfig, MACIRole
from .registry import MACIRoleRegistry


class MACIConfigLoader:
    """Loader for MACI configuration from multiple sources.

    Supports loading MACI configuration from environment variables, JSON files,
    YAML files, or dictionaries. Provides type-safe extraction with fallbacks.

    Attributes:
        constitutional_hash: Constitutional hash for validation
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        """Initialize the configuration loader.

        Args:
            constitutional_hash: Constitutional hash to use for validation
        """
        self.constitutional_hash = constitutional_hash

    def load(self, source: str | None = None) -> MACIConfig:
        """Load MACI configuration from a source.

        Automatically detects source type (JSON, YAML, or environment) and loads
        configuration accordingly.

        Args:
            source: Path to configuration file or None for environment variables

        Returns:
            MACIConfig instance
        """
        if source is None:
            return self.load_from_env()
        if source.endswith(".json"):
            return self.load_from_json(source)
        if source.endswith((".yaml", ".yml")):
            return self.load_from_yaml(source)
        return self.load_from_env()

    def load_from_dict(self, data: JSONDict) -> MACIConfig:
        """Load MACI config from a dictionary with type-safe extraction.

        Args:
            data: Configuration dictionary

        Returns:
            MACIConfig instance
        """
        # type-safe extraction of strict_mode
        strict_raw = data.get("strict_mode", True)
        strict = strict_raw if isinstance(strict_raw, bool) else True

        # type-safe extraction of default_role
        def_role: MACIRole | None = None
        def_role_str = data.get("default_role")
        if isinstance(def_role_str, str) and def_role_str:
            try:
                def_role = MACIRole(def_role_str.upper())
            except ValueError:
                pass  # Invalid role, keep as None

        # type-safe extraction of agents list
        agents: list[MACIAgentRoleConfig] = []
        agents_raw = data.get("agents", [])
        if isinstance(agents_raw, list):
            for a in agents_raw:
                if not is_json_dict(a):
                    continue
                # Get agent_id with fallback to id
                aid = get_str(a, "agent_id", "") or get_str(a, "id", "")
                role_str = get_str(a, "role", "")
                if aid and role_str:
                    try:
                        agents.append(
                            MACIAgentRoleConfig(
                                agent_id=aid,
                                role=MACIRole(role_str.upper()),
                                capabilities=get_str_list(a, "capabilities"),
                                metadata=a.get("metadata", {})
                                if is_json_dict(a.get("metadata", {}))
                                else {},
                            )
                        )
                    except ValueError:
                        pass  # Invalid role, skip this agent

        return MACIConfig(
            strict_mode=strict,
            agents=agents,
            default_role=def_role,
            constitutional_hash=get_str(data, "constitutional_hash", self.constitutional_hash),
        )

    def load_from_json(self, path: str) -> MACIConfig:
        """Load MACI configuration from a JSON file.

        Args:
            path: Path to JSON configuration file

        Returns:
            MACIConfig instance
        """
        content = Path(path).read_text(encoding="utf-8")
        return self.load_from_dict(json.loads(content))

    def load_from_yaml(self, path: str) -> MACIConfig:
        """Load MACI configuration from a YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            MACIConfig instance
        """
        try:
            import yaml

            content = Path(path).read_text(encoding="utf-8")
            return self.load_from_dict(yaml.safe_load(content))
        except ImportError:
            return MACIConfig()

    def load_from_env(self) -> MACIConfig:
        """Load MACI configuration from environment variables.

        Reads MACI_STRICT_MODE, MACI_DEFAULT_ROLE, and MACI_AGENT_* variables.

        Returns:
            MACIConfig instance
        """
        # Use centralized config for basic settings, fallback to env vars
        strict_env = os.getenv("MACI_STRICT_MODE")
        def_role_env = os.getenv("MACI_DEFAULT_ROLE")
        if strict_env is not None:
            strict = strict_env.lower() == "true"
        elif global_settings is not None:
            strict = global_settings.maci.strict_mode
        else:
            strict = True
        if def_role_env is not None:
            def_role_str = def_role_env
        elif global_settings is not None:
            def_role_str = global_settings.maci.default_role
        else:
            def_role_str = None

        def_role = MACIRole(def_role_str.upper()) if def_role_str else None

        # Dynamic agent parsing still requires environment variable iteration
        agents = []
        for k, v in os.environ.items():
            if k.startswith("MACI_AGENT_") and not k.endswith("_CAPABILITIES"):
                aid = k[11:].lower()
                caps = [
                    c.strip() for c in os.getenv(f"{k}_CAPABILITIES", "").split(",") if c.strip()
                ]
                try:
                    agents.append(
                        MACIAgentRoleConfig(
                            agent_id=aid, role=MACIRole(v.upper()), capabilities=caps
                        )
                    )
                except ValueError:
                    pass
        return MACIConfig(strict_mode=strict, agents=agents, default_role=def_role)


async def apply_maci_config(registry: MACIRoleRegistry, config: MACIConfig) -> int:
    """Apply MACI configuration to a registry.

    Args:
        registry: MACIRoleRegistry to configure
        config: MACIConfig with agent definitions

    Returns:
        Number of agents registered
    """
    count = 0
    for a in config.agents:
        # Ensure metadata is a proper dict (copy to avoid mutation)
        meta: JSONDict = dict(a.metadata) if a.metadata else {}
        if a.capabilities:
            meta["capabilities"] = a.capabilities
        await registry.register_agent(a.agent_id, a.role, metadata=meta)
        count += 1
    return count
