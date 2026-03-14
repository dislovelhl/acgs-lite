#!/usr/bin/env bash
# Run unit tests only (fast, no I/O, no external services)
# Usage: ./scripts/test-unit.sh [extra pytest args]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
PYTHONPATH="src:${PYTHONPATH:-}" python -m pytest tests/ \
  -m "unit" \
  -q --tb=short \
  --import-mode=importlib \
  "$@"
