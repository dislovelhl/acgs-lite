"""
MCP Configuration Schema and Loader for ACGS-2 Enhanced Agent Bus.

Provides Pydantic models for all MCP server configurations with full
environment-variable and YAML-file loading support.  The default
configuration registers two servers:

  - **neural-mcp**: TypeScript MCP server (stdio transport) for neural
    domain analysis and pattern training.
  - **toolbox**: HTTP-based Toolbox server for governance utilities.

Configuration priority (highest → lowest):
  1. Explicit keyword arguments passed to ``MCPConfig`` / factory functions.
  2. Environment variables prefixed ``MCP_`` (see :func:`load_from_env`).
  3. YAML config file at path specified by ``MCP_CONFIG_FILE`` env var.
  4. Hard-coded defaults.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH

# Environment variable prefixes / names
_ENV_MCP_ENABLED = "MCP_ENABLED"
_ENV_MCP_CONFIG_FILE = "MCP_CONFIG_FILE"
_ENV_NEURAL_MCP_ENABLED = "NEURAL_MCP_ENABLED"
_ENV_NEURAL_MCP_COMMAND = "NEURAL_MCP_COMMAND"  # JSON-encoded list
_ENV_TOOLBOX_ENABLED = "TOOLBOX_ENABLED"
_ENV_TOOLBOX_URL = "TOOLBOX_URL"
_ENV_TOOLBOX_AUTH_TOKEN = "TOOLBOX_AUTH_TOKEN"
_ENV_TOOLBOX_TIMEOUT = "TOOLBOX_TIMEOUT"

# Default server identifiers
NEURAL_MCP_SERVER_NAME = "neural-mcp"
TOOLBOX_SERVER_NAME = "toolbox"

# Default values
_DEFAULT_TOOLBOX_URL = "http://toolbox:5000"
_DEFAULT_NEURAL_MCP_COMMAND = ["node", "/app/neural-mcp/dist/index.js"]
_DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# MCPServerConfig
# ---------------------------------------------------------------------------


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection.

    Transport-specific validation
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - ``transport='http'`` or ``'sse'`` — ``url`` **must** be provided.
    - ``transport='stdio'`` — ``command`` **must** be provided; ``url``
      is unused and ignored.

    Attributes:
        name: Unique logical identifier for this server within the bus.
        transport: Wire protocol used to communicate with the server.
        url: Base URL for HTTP/SSE servers.  Must be a valid HTTP(S) URL.
        command: Process command (argv) for stdio servers.
        auth_token: Optional Bearer token sent on every request.
        timeout: Per-call timeout in seconds.  Defaults to 30.0.
        enabled: When ``False`` the bus will skip this server entirely.
    """

    name: str = Field(..., min_length=1, max_length=64)
    transport: Literal["http", "stdio", "sse"]
    url: str | None = Field(
        default=None,
        description="Base URL for http/sse transports.",
    )
    command: list[str] | None = Field(
        default=None,
        description="Process argv for stdio transport.",
    )
    auth_token: str | None = Field(
        default=None,
        description="Bearer token appended to every HTTP request.",
    )
    timeout: float = Field(
        default=_DEFAULT_TIMEOUT,
        gt=0,
        description="Per-call timeout in seconds.",
    )
    enabled: bool = Field(
        default=True,
        description="When False the bus will skip this server.",
    )

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        """Strip whitespace and enforce lowercase-slug convention."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Server name must not be blank.")
        return stripped

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        """Ensure URL, when supplied, has an http(s)/ws(s) scheme."""
        if v is None:
            return v
        lower = v.lower()
        if not any(
            lower.startswith(scheme) for scheme in ("http://", "https://", "ws://", "wss://")
        ):
            raise ValueError(f"url must start with http://, https://, ws://, or wss://; got: {v!r}")
        return v.rstrip("/")

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: list[str] | None) -> list[str] | None:
        """Ensure command list, when supplied, is non-empty."""
        if v is not None and len(v) == 0:
            raise ValueError("command must contain at least one element.")
        return v

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> MCPServerConfig:
        """Cross-field validation: enforce transport-specific requirements.

        - ``http``/``sse`` → ``url`` required.
        - ``stdio``        → ``command`` required.
        """
        if self.transport in ("http", "sse"):
            if not self.url:
                raise ValueError(
                    f"MCPServerConfig '{self.name}': transport={self.transport!r} "
                    "requires 'url' to be set."
                )
        elif self.transport == "stdio":
            if not self.command:
                raise ValueError(
                    f"MCPServerConfig '{self.name}': transport='stdio' "
                    "requires 'command' to be set."
                )
        return self

    # ------------------------------------------------------------------ #
    # Serialisation helpers
    # ------------------------------------------------------------------ #

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe plain dict (no secrets)."""
        return {
            "name": self.name,
            "transport": self.transport,
            "url": self.url,
            "command": self.command,
            "auth_token": "***" if self.auth_token else None,
            "timeout": self.timeout,
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------------------
# MCPConfig
# ---------------------------------------------------------------------------


class MCPConfig(BaseModel):
    """Top-level MCP configuration consumed by the Enhanced Agent Bus.

    Attributes:
        enabled: Master on/off switch for all MCP integrations.
        servers: List of MCP server configs.  Duplicate ``name`` values
            are rejected at validation time.
        maci_role_overrides: Per-server allowlist overrides keyed by server
            name.  Values are sets of MACI role strings permitted for that
            server beyond the global defaults.
        constitutional_hash: Governance hash embedded in every config object
            for traceability.
    """

    enabled: bool = Field(
        default=True,
        description="Master on/off switch for all MCP integrations.",
    )
    servers: list[MCPServerConfig] = Field(
        default_factory=list,
        description="Ordered list of MCP server configurations.",
    )
    maci_role_overrides: dict[str, set[str]] = Field(
        default_factory=dict,
        description="Per-server additional MACI role allowlists.",
    )
    constitutional_hash: str = Field(
        default=_CONSTITUTIONAL_HASH,
        description="Governance fingerprint (must equal project hash).",
    )

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #

    @field_validator("constitutional_hash")
    @classmethod
    def _validate_constitutional_hash(cls, v: str) -> str:
        if v != _CONSTITUTIONAL_HASH:
            raise ValueError(
                f"constitutional_hash must be {_CONSTITUTIONAL_HASH!r}; got {v!r}. "
                "Do not customise this value."
            )
        return v

    @model_validator(mode="after")
    def _validate_unique_server_names(self) -> MCPConfig:
        """Reject duplicate server names."""
        seen: set[str] = set()
        for srv in self.servers:
            if srv.name in seen:
                raise ValueError(
                    f"Duplicate MCP server name: {srv.name!r}. Each server must have a unique name."
                )
            seen.add(srv.name)
        return self

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #

    def get_server(self, name: str) -> MCPServerConfig | None:
        """Return the server config with *name*, or ``None``."""
        for srv in self.servers:
            if srv.name == name:
                return srv
        return None

    @property
    def enabled_servers(self) -> list[MCPServerConfig]:
        """Return only the servers whose ``enabled`` flag is ``True``."""
        return [s for s in self.servers if s.enabled]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe plain dict (no secrets)."""
        return {
            "enabled": self.enabled,
            "servers": [s.as_dict() for s in self.servers],
            "maci_role_overrides": {k: sorted(v) for k, v in self.maci_role_overrides.items()},
            "constitutional_hash": self.constitutional_hash,
        }


# ---------------------------------------------------------------------------
# Default server definitions
# ---------------------------------------------------------------------------


def _default_neural_mcp_server() -> MCPServerConfig:
    """Return the default Neural-MCP server config (stdio transport)."""
    command_raw = os.getenv(_ENV_NEURAL_MCP_COMMAND)
    if command_raw:
        try:
            command: list[str] = json.loads(command_raw)
            if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
                raise ValueError("Expected JSON array of strings")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "mcp_config_neural_mcp_command_parse_error",
                env_var=_ENV_NEURAL_MCP_COMMAND,
                raw=command_raw,
                error=str(exc),
                fallback="using default command",
            )
            command = list(_DEFAULT_NEURAL_MCP_COMMAND)
    else:
        command = list(_DEFAULT_NEURAL_MCP_COMMAND)

    enabled_str = os.getenv(_ENV_NEURAL_MCP_ENABLED, "true").strip().lower()
    enabled = enabled_str not in ("false", "0", "no", "off")

    return MCPServerConfig(
        name=NEURAL_MCP_SERVER_NAME,
        transport="stdio",
        command=command,
        timeout=_DEFAULT_TIMEOUT,
        enabled=enabled,
    )


def _default_toolbox_server() -> MCPServerConfig:
    """Return the default Toolbox server config (http transport)."""
    url = os.getenv(_ENV_TOOLBOX_URL, _DEFAULT_TOOLBOX_URL)
    auth_token = os.getenv(_ENV_TOOLBOX_AUTH_TOKEN)
    enabled_str = os.getenv(_ENV_TOOLBOX_ENABLED, "true").strip().lower()
    enabled = enabled_str not in ("false", "0", "no", "off")

    timeout_raw = os.getenv(_ENV_TOOLBOX_TIMEOUT, str(_DEFAULT_TIMEOUT))
    try:
        timeout = float(timeout_raw)
        if timeout <= 0:
            raise ValueError("timeout must be positive")
    except ValueError:
        logger.warning(
            "mcp_config_toolbox_timeout_parse_error",
            raw=timeout_raw,
            fallback=_DEFAULT_TIMEOUT,
        )
        timeout = _DEFAULT_TIMEOUT

    return MCPServerConfig(
        name=TOOLBOX_SERVER_NAME,
        transport="http",
        url=url,
        auth_token=auth_token,
        timeout=timeout,
        enabled=enabled,
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_from_env() -> MCPConfig:
    """Construct an :class:`MCPConfig` driven entirely by environment variables.

    Recognised variables
    --------------------
    ``MCP_ENABLED``
        ``"true"`` / ``"false"`` — master switch.  Default: ``"true"``.
    ``NEURAL_MCP_ENABLED``
        Toggle for the neural-mcp server.  Default: ``"true"``.
    ``NEURAL_MCP_COMMAND``
        JSON-encoded list of strings, e.g. ``'["node", "dist/index.js"]'``.
    ``TOOLBOX_ENABLED``
        Toggle for the Toolbox server.  Default: ``"true"``.
    ``TOOLBOX_URL``
        Base URL for the Toolbox HTTP server.
        Default: ``"http://toolbox:5000"``.
    ``TOOLBOX_AUTH_TOKEN``
        Bearer token for Toolbox authentication.
    ``TOOLBOX_TIMEOUT``
        Per-call timeout in seconds.  Default: ``"30.0"``.

    Returns:
        :class:`MCPConfig` populated from environment.
    """
    mcp_enabled_str = os.getenv(_ENV_MCP_ENABLED, "true").strip().lower()
    mcp_enabled = mcp_enabled_str not in ("false", "0", "no", "off")

    config = MCPConfig(
        enabled=mcp_enabled,
        servers=[
            _default_neural_mcp_server(),
            _default_toolbox_server(),
        ],
    )

    logger.info(
        "mcp_config_loaded_from_env",
        enabled=config.enabled,
        server_count=len(config.servers),
        enabled_servers=[s.name for s in config.enabled_servers],
        constitutional_hash=_CONSTITUTIONAL_HASH,
    )
    return config


def load_from_yaml(path: str | Path) -> MCPConfig:
    """Load :class:`MCPConfig` from a YAML file.

    The YAML document must contain a top-level mapping.  Known keys:

    .. code-block:: yaml

        enabled: true
        constitutional_hash: 608508a9bd224290
        servers:
          - name: neural-mcp
            transport: stdio
            command: [node, dist/index.js]
            timeout: 30.0
            enabled: true
          - name: toolbox
            transport: http
            url: http://toolbox:5000
            auth_token: secret
            timeout: 30.0
            enabled: true
        maci_role_overrides:
          toolbox:
            - proposer
            - validator

    Note: ``maci_role_overrides`` values may be YAML sequences (lists) — they
    are automatically coerced to sets.

    Args:
        path: Filesystem path to the YAML config file.

    Returns:
        :class:`MCPConfig` built from the YAML document.

    Raises:
        FileNotFoundError: When *path* does not exist.
        ValueError: When the YAML document is malformed or fails validation.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PyYAML is required for YAML config loading. Install it with: pip install pyyaml"
        ) from exc

    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"MCP config YAML not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ACGSValidationError(
            f"MCP YAML config must be a mapping at the top level; "
            f"got {type(raw).__name__!r} from {resolved}",
            error_code="MCP_CONFIG_NOT_MAPPING",
        )

    # Coerce maci_role_overrides list values → sets
    overrides_raw: Any = raw.get("maci_role_overrides", {})
    if isinstance(overrides_raw, dict):
        raw["maci_role_overrides"] = {
            k: set(v) if isinstance(v, (list, set)) else v for k, v in overrides_raw.items()
        }

    try:
        config: MCPConfig = MCPConfig.model_validate(raw)  # type: ignore[assignment]
    except Exception as exc:
        raise ACGSValidationError(
            f"MCP YAML config at {resolved} failed validation: {exc}",
            error_code="MCP_CONFIG_VALIDATION_FAILED",
        ) from exc

    logger.info(
        "mcp_config_loaded_from_yaml",
        path=str(resolved),
        enabled=config.enabled,
        server_count=len(config.servers),
        enabled_servers=[s.name for s in config.enabled_servers],
        constitutional_hash=_CONSTITUTIONAL_HASH,
    )
    return config


def load_config() -> MCPConfig:
    """Load :class:`MCPConfig` using the priority chain.

    Priority order (highest first):

    1. YAML file at ``$MCP_CONFIG_FILE`` (when set and file exists).
    2. Environment variables (via :func:`load_from_env`).
    3. Merged result: YAML base + env overrides when *both* are present.

    When ``MCP_CONFIG_FILE`` is set but the file is missing a warning is
    logged and env-variable loading takes over.

    Returns:
        Fully validated :class:`MCPConfig`.
    """
    yaml_path_raw = os.getenv(_ENV_MCP_CONFIG_FILE, "").strip()

    if yaml_path_raw:
        yaml_path = Path(yaml_path_raw)
        if yaml_path.exists():
            logger.info(
                "mcp_config_loading_from_yaml",
                path=str(yaml_path),
                constitutional_hash=_CONSTITUTIONAL_HASH,
            )
            try:
                return load_from_yaml(yaml_path)
            except Exception as exc:
                logger.warning(
                    "mcp_config_yaml_load_failed",
                    path=str(yaml_path),
                    error=str(exc),
                    fallback="environment variables",
                )
        else:
            logger.warning(
                "mcp_config_yaml_file_missing",
                path=str(yaml_path),
                env_var=_ENV_MCP_CONFIG_FILE,
                fallback="environment variables",
            )

    return load_from_env()


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_cached_config: MCPConfig | None = None


def get_mcp_config(*, reload: bool = False) -> MCPConfig:
    """Return the cached :class:`MCPConfig` singleton.

    The singleton is initialised on first access using :func:`load_config`.
    Set *reload=True* to discard the cache and reload from sources.

    Args:
        reload: When ``True`` forces a fresh load regardless of cached state.

    Returns:
        The active :class:`MCPConfig` instance.
    """
    global _cached_config
    if _cached_config is None or reload:
        _cached_config = load_config()
    return _cached_config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # default server names
    "NEURAL_MCP_SERVER_NAME",
    "TOOLBOX_SERVER_NAME",
    # models
    "MCPConfig",
    "MCPServerConfig",
    # loaders
    "get_mcp_config",
    "load_config",
    "load_from_env",
    "load_from_yaml",
]
