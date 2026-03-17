#!/usr/bin/env python3
"""Start Agent Bus with proper environment setup."""

import logging
import os
import sys

# Get the directory containing this script
script_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(script_dir, "src")

# Add src to Python path
sys.path.insert(0, src_path)

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Set environment variables (force override to ensure correct values)
os.environ["PYTHONPATH"] = src_path
os.environ["OPA_URL"] = os.environ.get("OPA_URL") or "http://localhost:8181"
os.environ["REDIS_URL"] = os.environ.get("REDIS_URL") or "redis://:dev_password@localhost:6379/0"
os.environ["CONSTITUTIONAL_HASH"] = os.environ.get("CONSTITUTIONAL_HASH") or CONSTITUTIONAL_HASH
os.environ["MACI_STRICT_MODE"] = os.environ.get("MACI_STRICT_MODE") or "true"
os.environ["LOG_LEVEL"] = os.environ.get("LOG_LEVEL") or "INFO"
os.environ["ACGS_ENV"] = os.environ.get("ACGS_ENV") or "development"

logger = logging.getLogger(__name__)

# Now import and run
logger.info("Starting Agent Bus...")
logger.info(f"Python path: {sys.path[0]}")

import uvicorn
from enhanced_agent_bus.api.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")  # noqa: S104
