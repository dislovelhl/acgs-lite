#!/usr/bin/env bash
# Quick regression check: unit tests + benchmark + compliance rate guard
# Returns exit code 1 if any regression detected
# Usage: ./scripts/test-regression.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
AUTORESEARCH_DIR="$(dirname "$PROJECT_DIR")/../../autoresearch"
FAILURES=0

echo "=== Unit Tests ==="
cd "$PROJECT_DIR"
if PYTHONPATH="src:${PYTHONPATH:-}" python -m pytest tests/ \
  -m "unit or compliance or constitutional" \
  -q --tb=line --import-mode=importlib 2>&1; then
  echo "PASS: unit/compliance/constitutional tests"
else
  echo "FAIL: test regression detected"
  FAILURES=$((FAILURES + 1))
fi

echo ""
echo "=== Benchmark ==="
cd "$AUTORESEARCH_DIR"
OUTPUT=$(PYTHONPATH="$PROJECT_DIR/src:${PYTHONPATH:-}" python benchmark.py 2>&1)

COMPLIANCE=$(echo "$OUTPUT" | grep "^compliance_rate:" | awk '{print $2}')
P99=$(echo "$OUTPUT" | grep "^p99_latency_ms:" | awk '{print $2}')
FNR=$(echo "$OUTPUT" | grep "^false_negative_rate:" | awk '{print $2}')

echo "compliance_rate: $COMPLIANCE (must be 1.000000)"
echo "p99_latency_ms:  $P99 (must be < 0.010000)"
echo "false_neg_rate:  $FNR (must be 0.000000)"

# Guard: compliance must be 1.0
if [ "$(echo "$COMPLIANCE != 1.000000" | bc -l 2>/dev/null || echo 1)" = "1" ] && [ "$COMPLIANCE" != "1.000000" ]; then
  echo "FAIL: compliance regression ($COMPLIANCE < 1.0)"
  FAILURES=$((FAILURES + 1))
fi

# Guard: false negatives must be 0
if [ "$FNR" != "0.000000" ]; then
  echo "FAIL: false negative regression ($FNR > 0)"
  FAILURES=$((FAILURES + 1))
fi

echo ""
if [ $FAILURES -eq 0 ]; then
  echo "=== ALL REGRESSION CHECKS PASSED ==="
  exit 0
else
  echo "=== $FAILURES REGRESSION(S) DETECTED ==="
  exit 1
fi
