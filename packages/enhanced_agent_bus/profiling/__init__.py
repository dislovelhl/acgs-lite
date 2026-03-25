# ACGS-2 Model Profiling Module
# Constitutional Hash: 608508a9bd224290
"""
Model profiling utilities for GPU acceleration evaluation.

This module provides profiling capabilities to measure:
- Model inference latency (P50, P95, P99)
- CPU utilization during inference
- Memory allocation patterns
- Compute vs I/O bound classification

Usage:
    from profiling import ModelProfiler, profile_inference

    profiler = ModelProfiler()
    with profiler.track("impact_scorer"):
        result = model.predict(input_data)

    metrics = profiler.get_metrics()
"""

from .model_profiler import (
    ModelProfiler,
    ProfilingMetrics,
    get_global_profiler,
    profile_inference,
)

__all__ = [
    "ModelProfiler",
    "ProfilingMetrics",
    "get_global_profiler",
    "profile_inference",
]
