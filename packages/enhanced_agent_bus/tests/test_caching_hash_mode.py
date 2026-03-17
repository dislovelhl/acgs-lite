"""
Focused tests for caching cache_key hash mode behavior.
"""

from __future__ import annotations

import hashlib

import pytest

import enhanced_agent_bus.caching as caching_module


def test_set_cache_hash_mode_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="Invalid cache hash mode"):
        caching_module.set_cache_hash_mode("invalid")


def test_cache_key_fast_mode_uses_kernel(monkeypatch) -> None:
    called = {"value": False}

    def _fake_fast_hash(value: str) -> int:
        called["value"] = True
        return 0xBEEF

    monkeypatch.setattr(caching_module, "FAST_HASH_AVAILABLE", True)
    monkeypatch.setattr(caching_module, "fast_hash", _fake_fast_hash, raising=False)
    caching_module.set_cache_hash_mode("fast")

    key = caching_module.cache_key("a", b=1)
    assert called["value"] is True
    assert key == "fast:000000000000beef"

    caching_module.set_cache_hash_mode("sha256")


def test_cache_key_fast_mode_falls_back_to_sha256(monkeypatch) -> None:
    monkeypatch.setattr(caching_module, "FAST_HASH_AVAILABLE", False)
    caching_module.set_cache_hash_mode("fast")

    key = caching_module.cache_key("a", b=1)
    key_data = "('a',):[('b', 1)]"
    expected = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    assert key == expected

    caching_module.set_cache_hash_mode("sha256")


def test_cache_key_default_mode_matches_sha256() -> None:
    caching_module.set_cache_hash_mode("sha256")
    key = caching_module.cache_key("x", y=2)
    assert len(key) == 16
    int(key, 16)
