"""
ACGS-2 Enhanced Agent Bus API Entry Point
Constitutional Hash: 608508a9bd224290
"""

import uvicorn

from .config import DEFAULT_API_PORT

if __name__ == "__main__":
    uvicorn.run(
        "enhanced_agent_bus.api:app",
        host="127.0.0.1",
        port=int(DEFAULT_API_PORT),
        reload=False,
        log_level="info",
    )
