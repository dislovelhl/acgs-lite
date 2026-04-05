#!/usr/bin/env python3
"""Start the acgs-lite governance backend for the dashboard.

Usage:
    python scripts/start-backend.py [--port 8100]
"""

import argparse
import sys
from pathlib import Path

# Add acgs-lite to path
ACGS_LITE_SRC = Path(__file__).resolve().parent.parent.parent / "acgs-lite" / "src"
sys.path.insert(0, str(ACGS_LITE_SRC))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start acgs-lite governance backend")
    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    from acgs_lite.server import create_governance_app

    app = create_governance_app()
    print(f"Starting acgs-lite governance backend on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
