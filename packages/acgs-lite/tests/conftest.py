"""Test configuration for acgs-lite.

Ensure pytest resolves the local ``src/`` tree before any installed package
copy so verification always exercises the workspace code under test.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SRC_PATH = str(SRC_DIR)
REPO_ROOT = Path(__file__).resolve().parents[3]

if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, SRC_PATH)

# Reuse the repository-wide pytest compatibility setup so package-root test runs
# get the same TestClient monkeypatches and environment defaults as repo-root runs.
runpy.run_path(str(REPO_ROOT / "conftest.py"), run_name="acgs_repo_conftest")
