#!/bin/bash
# Run full test suite with coverage
# Constitutional Hash: 1e4d568382fcb7c0fdd8a37feab217f77edd080769fff8630bb5714e0c3b9693

set -e

echo "========================================="
echo "ACGS-2 Enhanced Agent Bus - Full Test Suite"
echo "Constitutional Hash: 1e4d568382fcb7c0fdd8a37feab217f77edd080769fff8630bb5714e0c3b9693"
echo "========================================="

cd "$(dirname "$0")"

echo ""
echo "Step 1: Removing Python bytecode cache..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Step 2: Clearing pytest cache..."
rm -rf .pytest_cache 2>/dev/null || true

echo ""
echo "Step 3: Running full test suite with coverage..."
# Run full test suite without -x to see all results
/usr/bin/python3 -m pytest tests/ -v --cov=. --cov-report=term-missing --tb=short 2>&1

exit_code=$?
echo ""
echo "========================================="
if [ $exit_code -eq 0 ]; then
    echo "Full test suite completed successfully!"
else
    echo "Test suite finished with exit code: $exit_code"
fi
echo "========================================="
exit $exit_code
