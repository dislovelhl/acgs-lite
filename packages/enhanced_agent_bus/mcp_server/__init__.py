from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 MCP Server - Model Context Protocol Integration for Constitutional AI Governance.

This module provides MCP (Model Context Protocol) server capabilities for the ACGS-2
Enhanced Agent Bus, enabling external AI systems to leverage constitutional governance
through a standardized interface.

Constitutional Hash: cdd01ef066bc6cf2
"""

from .config import MCPConfig  # noqa: E402
from .server import MCPServer, create_mcp_server  # noqa: E402

__all__ = [
    "MCPConfig",
    "MCPServer",
    "create_mcp_server",
]

__version__ = "0.1.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH
