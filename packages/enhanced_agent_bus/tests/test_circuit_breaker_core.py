"""Compatibility wrapper for legacy eval path.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _resolve_source() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = (
            parent / "tests" / "core" / "enhanced_agent_bus" / "test_circuit_breaker_coverage.py"
        )
        if candidate.is_file():
            return candidate
    raise ImportError(
        "Unable to locate tests/core/enhanced_agent_bus/test_circuit_breaker_coverage.py"
    )


try:
    _SOURCE = _resolve_source()
except ImportError as exc:
    pytest.skip(str(exc), allow_module_level=True)

_SPEC = importlib.util.spec_from_file_location("legacy_circuit_breaker_coverage", _SOURCE)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load compatibility tests from {_SOURCE}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name in dir(_MODULE):
    if _name.startswith("_"):
        continue
    globals()[_name] = getattr(_MODULE, _name)
