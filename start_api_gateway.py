#!/usr/bin/env python3
"""Start API Gateway with package-aware imports and environment setup."""

import logging
import os
import sys


script_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(script_dir, "src")
packages_path = os.path.join(script_dir, "packages")

# Ensure package imports resolve the same way under PM2 and local shells.
for path in (packages_path, src_path, script_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ["PYTHONPATH"] = os.pathsep.join(
    [path for path in (packages_path, script_dir, src_path, os.environ.get("PYTHONPATH", "")) if path]
)
os.environ["ENVIRONMENT"] = os.environ.get("ENVIRONMENT") or "development"
os.environ["AGENT_BUS_URL"] = os.environ.get("AGENT_BUS_URL") or "http://localhost:8000"
os.environ["LOG_LEVEL"] = os.environ.get("LOG_LEVEL") or "INFO"
if os.environ["ENVIRONMENT"].strip().lower() in {"development", "dev", "test", "testing", "local", "ci"}:
    os.environ["CSRF_ALLOW_EPHEMERAL_SECRET"] = (
        os.environ.get("CSRF_ALLOW_EPHEMERAL_SECRET") or "true"
    )

logger = logging.getLogger(__name__)
logger.info("Starting API Gateway...")
logger.info("Python path head: %s", sys.path[:2])

import uvicorn

from src.core.services.api_gateway.main import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level=os.environ["LOG_LEVEL"].lower())
