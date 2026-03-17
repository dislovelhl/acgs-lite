#!/bin/bash
# Run single test with verbose output
cd "$(dirname "$0")"
/usr/bin/python3 -m pytest tests/test_adaptive_governance.py::TestAdaptiveGovernance::test_governance_engine_initialization -v --tb=long 2>&1
