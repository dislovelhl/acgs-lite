#!/usr/bin/env bash
# Run the full test suite with coverage report
# Usage: ./scripts/test-all.sh [extra pytest args]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
PYTHONPATH="src:${PYTHONPATH:-}" python -m pytest tests/ \
  -q --tb=short \
  --import-mode=importlib \
  --cov=acgs_lite \
  --cov-report=term-missing:skip-covered \
  "$@"
