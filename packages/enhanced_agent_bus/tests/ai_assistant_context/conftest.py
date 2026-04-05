"""
Conftest for ai_assistant_context tests.
Constitutional Hash: 608508a9bd224290

Skips mamba-dependent tests when torch is not available since the
MambaHybridProcessor cannot be mocked without the real import.
"""

from __future__ import annotations

import importlib.util

import pytest

_TORCH_AVAILABLE = False
try:
    _TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None
except (ValueError, ModuleNotFoundError):
    pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip mamba long-context tests when torch is not installed."""
    if _TORCH_AVAILABLE:
        return

    skip_marker = pytest.mark.skip(reason="torch not available — mamba processor cannot be loaded")
    mamba_keywords = (
        "test_processlongcontext",
        "process_long_context",
        "mamba_init",
        "mamba_loaded",
    )
    for item in items:
        nodeid_lower = item.nodeid.lower()
        if any(kw in nodeid_lower for kw in mamba_keywords):
            item.add_marker(skip_marker)
