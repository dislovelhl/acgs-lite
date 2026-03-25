"""
CLI for starting the ACGS-2 MCP Server.
Constitutional Hash: 608508a9bd224290
"""

import argparse
import asyncio
import logging
import sys

from .config import MCPConfig, TransportType
from .server import create_mcp_server


def main():
    parser = argparse.ArgumentParser(description="ACGS-2 MCP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio", help="Transport type"
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    config = MCPConfig(
        server_name="acgs2-governance",
        server_version="3.0.0",
        transport_type=TransportType.STDIO if args.transport == "stdio" else TransportType.SSE,
    )

    server = create_mcp_server(config=config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    finally:
        # Stop is handled inside start()'s finally block or similar,
        # but we ensure it's called if we were managing the loop ourselves.
        pass


if __name__ == "__main__":
    main()
