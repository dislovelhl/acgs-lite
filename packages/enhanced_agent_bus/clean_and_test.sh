#!/bin/bash
# Clean bytecode cache and run tests
# Constitutional Hash: 1e4d568382fcb7c0fdd8a37feab217f77edd080769fff8630bb5714e0c3b9693

set -e

echo "========================================="
echo "ACGS-2 Enhanced Agent Bus - Clean & Test"
echo "Constitutional Hash: 1e4d568382fcb7c0fdd8a37feab217f77edd080769fff8630bb5714e0c3b9693"
echo "========================================="

cd "$(dirname "$0")"

echo ""
echo "Step 1: Removing Python bytecode cache..."
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Step 2: Clearing pytest cache..."
rm -rf .pytest_cache

echo "Step 3: Running environment check tests..."
python3 -m pytest tests/test_environment_check.py -v -s || {
    echo "⚠ Environment check failed! Please review the output above."
    exit 1
}

echo ""
echo "Step 4: Running constitutional validation tests..."
python3 -m pytest tests/test_constitutional_validation.py::TestMessageProcessor -v --tb=short

echo ""
echo "Step 5: Running enhanced agent bus tests..."
python3 -m pytest tests/test_constitutional_validation.py::TestEnhancedAgentBus -v --tb=short

echo ""
echo "✓ All tests completed"
