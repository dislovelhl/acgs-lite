try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
MCP Server Configuration for ACGS-2 Constitutional Governance.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class TransportType(Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    WEBSOCKET = "websocket"


@dataclass
class MCPConfig:
    """Configuration for the ACGS-2 MCP Server."""

    # Server identification
    server_name: str = "acgs2-governance"
    server_version: str = "0.1.0"
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Transport configuration
    transport_type: TransportType = TransportType.STDIO
    host: str = "127.0.0.1"
    port: int = 8090

    # Constitutional governance settings
    strict_mode: bool = True
    fail_closed: bool = True
    enable_maci: bool = True  # MACI role separation

    # Performance settings
    max_concurrent_requests: int = 100
    request_timeout_ms: int = 5000  # P99 <5ms target
    enable_caching: bool = True
    cache_ttl_seconds: int = 300

    # Feature flags
    enable_tools: bool = True
    enable_resources: bool = True
    enable_prompts: bool = True
    enable_audit_logging: bool = True

    # Tool-specific configuration
    enabled_tools: list[str] = field(
        default_factory=lambda: [
            "validate_constitutional_compliance",
            "get_active_principles",
            "query_governance_precedents",
            "submit_governance_request",
            "get_governance_metrics",
        ]
    )

    # Resource-specific configuration
    enabled_resources: list[str] = field(
        default_factory=lambda: [
            "constitutional_principles",
            "governance_metrics",
            "recent_decisions",
            "audit_trail",
        ]
    )

    # Security settings — fail-closed: require auth by default
    require_authentication: bool = True
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_minute: int = 1000

    # Logging settings
    log_level: str = "INFO"
    log_requests: bool = True
    log_responses: bool = False  # Sensitive data protection

    def to_dict(self) -> JSONDict:
        """Convert config to dictionary."""
        return {
            "server_name": self.server_name,
            "server_version": self.server_version,
            "constitutional_hash": self.constitutional_hash,
            "transport_type": self.transport_type.value,
            "host": self.host,
            "port": self.port,
            "strict_mode": self.strict_mode,
            "fail_closed": self.fail_closed,
            "enable_maci": self.enable_maci,
            "max_concurrent_requests": self.max_concurrent_requests,
            "request_timeout_ms": self.request_timeout_ms,
            "enable_caching": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "enable_tools": self.enable_tools,
            "enable_resources": self.enable_resources,
            "enable_prompts": self.enable_prompts,
            "enable_audit_logging": self.enable_audit_logging,
            "enabled_tools": self.enabled_tools,
            "enabled_resources": self.enabled_resources,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "MCPConfig":
        """Create config from dictionary."""
        if "transport_type" in data and isinstance(data["transport_type"], str):
            data["transport_type"] = TransportType(data["transport_type"])
        return cls(**data)

    def validate(self) -> bool:
        """Validate configuration."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash: {self.constitutional_hash}. "
                f"Expected: {CONSTITUTIONAL_HASH}"
            )

        if self.request_timeout_ms > 5000 and self.strict_mode:
            raise ValueError("Request timeout exceeds P99 <5ms target in strict mode")

        if self.fail_closed is False and self.strict_mode:
            raise ValueError(
                "fail_closed must be True in strict mode for constitutional compliance"
            )

        return True
