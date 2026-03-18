"""
Focused tests for SpecDeltaCompressor checksum hash mode behavior.
"""

from __future__ import annotations

import enhanced_agent_bus.context_optimization as context_optimization_module
from enhanced_agent_bus.context_optimization import SpecDeltaCompressor


def test_spec_checksum_uses_fast_kernel_when_available(monkeypatch) -> None:
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

    compressor = SpecDeltaCompressor()
    checksum = compressor._compute_checksum({"a": 1})

    assert called["value"] is True
    assert checksum == "000000000000beef"


def test_spec_checksum_falls_back_to_sha256_when_kernel_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(context_optimization_module, "FAST_HASH_AVAILABLE", False)

    compressor = SpecDeltaCompressor()
    checksum = compressor._compute_checksum({"a": 1})

    assert len(checksum) == 16
    int(checksum, 16)
