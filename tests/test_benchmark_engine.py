"""Focused microbenchmarks for the acgs-lite governance engine."""

from __future__ import annotations

import pytest

from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine


@pytest.mark.benchmark
class TestGovernanceEngineBenchmarks:
    def test_engine_construction_default_constitution(self, benchmark) -> None:
        engine = benchmark(lambda: GovernanceEngine(Constitution.default(), strict=False))
        assert isinstance(engine, GovernanceEngine)

    def test_validate_allow_path_default_constitution(self, benchmark) -> None:
        engine = GovernanceEngine(Constitution.default(), strict=False)
        action = "review quarterly compliance dashboard and prepare audit summary"

        result = benchmark(engine.validate, action, agent_id="bench")

        assert result.valid is True
        assert result.violations == []

    def test_validate_deny_path_default_constitution(self, benchmark) -> None:
        engine = GovernanceEngine(Constitution.default(), strict=False)
        action = "skip audit and expose private key in deployment logs"

        result = benchmark(engine.validate, action, agent_id="bench")

        assert result.valid is False
        assert result.violations
