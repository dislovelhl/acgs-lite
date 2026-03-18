"""
Targeted tests for Rust-accelerated percentile computation in metrics_collector.
"""

from __future__ import annotations

import enhanced_agent_bus.constitutional.metrics_collector as metrics_collector_module
from enhanced_agent_bus.constitutional.metrics_collector import GovernanceMetricsCollector


def test_compute_percentiles_uses_rust_kernel_when_available(monkeypatch):
    collector = GovernanceMetricsCollector()
    called = {"value": False}

    def _fake_kernel(values: list[float], percentiles: list[float]) -> list[float]:
        called["value"] = True
        assert values == sorted(values)
        assert percentiles == [50.0, 95.0, 99.0]
        return [2.0, 4.0, 5.0]

    monkeypatch.setattr(metrics_collector_module, "PERF_KERNELS_AVAILABLE", True)
    monkeypatch.setattr(
        metrics_collector_module,
        "compute_percentiles_floor_index",
        _fake_kernel,
        raising=False,
    )

    assert collector._compute_percentiles([5.0, 1.0, 4.0, 2.0, 3.0]) == (2.0, 4.0, 5.0)
    assert called["value"] is True


def test_compute_percentiles_python_fallback_preserves_semantics(monkeypatch):
    collector = GovernanceMetricsCollector()
    monkeypatch.setattr(metrics_collector_module, "PERF_KERNELS_AVAILABLE", False)

    # n=2 -> p50 idx=int(2*0.5)=1, p95 idx=1, p99 idx=1 => all upper value
    assert collector._compute_percentiles([100.0, 200.0]) == (200.0, 200.0, 200.0)
