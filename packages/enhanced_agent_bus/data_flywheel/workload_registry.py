"""Helpers for canonical flywheel workload identifiers."""

from __future__ import annotations

import re

from .models import WorkloadKey

_SEGMENT_PATTERN = re.compile(r"[^a-z0-9._-]+")


def normalize_workload_segment(value: str) -> str:
    """Normalize arbitrary routing inputs into a workload-safe segment."""
    cleaned = value.strip().lower().replace(" ", "_").replace("/", "_")
    normalized = _SEGMENT_PATTERN.sub("_", cleaned).strip("._-")
    return normalized or "unknown"


def build_workload_key(
    *,
    tenant_id: str,
    service: str,
    route_or_tool: str,
    decision_kind: str,
    constitutional_hash: str,
) -> WorkloadKey:
    return WorkloadKey(
        tenant_id=tenant_id.strip(),
        service=normalize_workload_segment(service),
        route_or_tool=normalize_workload_segment(route_or_tool),
        decision_kind=normalize_workload_segment(decision_kind),
        constitutional_hash=constitutional_hash.strip(),
    )


__all__ = ["build_workload_key", "normalize_workload_segment"]
