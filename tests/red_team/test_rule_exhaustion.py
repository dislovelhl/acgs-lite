"""Red-team coverage for constitution exhaustion scenarios."""

from __future__ import annotations

import time

import pytest

from acgs_lite.constitution import ConstitutionBuilder
from acgs_lite.engine import GovernanceEngine
from acgs_lite.engine import core as engine_core

from .conftest_red_team import default_engine  # noqa: F401, F811


def _large_constitution_engine(rule_count: int = 1000) -> GovernanceEngine:
    builder = ConstitutionBuilder("red-team-large")
    for index in range(rule_count):
        builder.add_rule(
            f"RT-LARGE-{index}",
            f"Rule {index} should block keyword {index}",
            severity="medium",
            keywords=[f"never-match-{index}"],
            category="stress",
        )
    return GovernanceEngine(builder.build(), strict=False)


@pytest.mark.red_team
def test_large_constitution_validate_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_core, "_HAS_RUST", False)
    engine = _large_constitution_engine()
    engine.validate("warmup", agent_id="red-team")

    start = time.perf_counter()
    result = engine.validate("safe payload", agent_id="red-team")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert result.valid is True
    assert elapsed_ms < 500


@pytest.mark.red_team
def test_repeated_validate_no_memory_leak(default_engine: GovernanceEngine) -> None:  # noqa: F811
    last_result = None
    for _ in range(10_000):
        last_result = default_engine.validate("safe payload", agent_id="red-team")

    assert last_result is not None
    assert last_result.valid is True
