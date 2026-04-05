try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
ACGS-2 MCP Server - Model Context Protocol Integration for Constitutional AI Governance.

This module provides MCP (Model Context Protocol) server capabilities for the ACGS-2
Enhanced Agent Bus, enabling external AI systems to leverage constitutional governance
through a standardized interface.

Constitutional Hash: 608508a9bd224290
"""

from .config import MCPConfig
from .server import MCPServer, create_mcp_server

__all__ = [
    "MCPConfig",
    "MCPServer",
    "create_mcp_server",
]

__version__ = "0.1.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH
