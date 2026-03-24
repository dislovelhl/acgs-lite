#!/usr/bin/env bash
# Run the governance engine benchmark (autoresearch harness)
# Usage: ./scripts/test-benchmark.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
AUTORESEARCH_DIR="$(dirname "$PROJECT_DIR")/../../autoresearch"

cd "$AUTORESEARCH_DIR"
PYTHONPATH="$PROJECT_DIR/src:${PYTHONPATH:-}" python benchmark.py 2>&1 | \
  grep -E "^(composite_score|compliance_rate|p99_latency_ms|throughput_rps|false_negative_rate):"
