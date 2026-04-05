"""
Focused tests for CachedGovernanceValidator cache hash mode behavior.
"""

from __future__ import annotations

import hashlib

import pytest

import enhanced_agent_bus.context_optimization as context_optimization_module
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.context_optimization import (
    CachedGovernanceValidator,
    ValidationContext,
)


def test_cached_validator_rejects_invalid_cache_hash_mode() -> None:
    with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
        CachedGovernanceValidator(cache_hash_mode="invalid")  # type: ignore[arg-type]


def test_cache_key_fast_mode_uses_kernel(monkeypatch) -> None:
    called = {"value": False}

    def _fake_fast_hash(value: str) -> int:
        called["value"] = True
        return 0xBEEF

    monkeypatch.setattr(context_optimization_module, "FAST_HASH_AVAILABLE", True)
    monkeypatch.setattr(
        context_optimization_module,
        "fast_hash",
        _fake_fast_hash,
        raising=False,
    )

    validator = CachedGovernanceValidator(cache_hash_mode="fast")
    context = ValidationContext(action="read", resource="policy", agent_id="agent-1")
    key = validator._cache_key(context)

    assert called["value"] is True
    assert key == "fast:000000000000beef"


def test_cache_key_fast_mode_falls_back_to_sha256(monkeypatch) -> None:
    monkeypatch.setattr(context_optimization_module, "FAST_HASH_AVAILABLE", False)

    validator = CachedGovernanceValidator(cache_hash_mode="fast")
    context = ValidationContext(action="read", resource="policy", agent_id="agent-1")
    key = validator._cache_key(context)

    key_data = {
        "action": "read",
        "resource": "policy",
        "agent_id": "agent-1",
        "tenant_id": None,
        "constitutional_hash": CONSTITUTIONAL_HASH,
    }
    content = context_optimization_module.json.dumps(key_data, sort_keys=True)
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert key == expected


def test_cache_key_default_mode_matches_sha256() -> None:
    validator = CachedGovernanceValidator()
    context = ValidationContext(action="read", resource="policy", agent_id="agent-1")
    key = validator._cache_key(context)
    assert len(key) == 64
    int(key, 16)
