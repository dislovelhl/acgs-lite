"""Regression tests for per-call ``strict`` override on ``GovernanceEngine.validate``.

Covers the T-04 structural fix from ``TODOS.md``: callers should be able to
pass ``strict=True``/``strict=False`` per invocation without mutating
``self.strict`` (which is shared across threads and integrations).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import threading

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine.core import GovernanceEngine
from acgs_lite.errors import ConstitutionalViolationError


def _make_engine(*, strict: bool = True) -> GovernanceEngine:
    rules = [
        Rule(
            id="T-SEC",
            text="No secrets",
            severity=Severity.CRITICAL,
            keywords=["secret"],
            category="security",
        ),
    ]
    return GovernanceEngine(Constitution.from_rules(rules), strict=strict)


class TestPerCallStrictOverride:
    def test_override_false_on_strict_engine_returns_invalid(self) -> None:
        engine = _make_engine(strict=True)
        # Without override, the strict engine raises.
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("leak secret data")
        # With per-call strict=False, same action returns invalid result.
        result = engine.validate("leak secret data", strict=False)
        assert result.valid is False
        assert any(v.rule_id == "T-SEC" for v in result.violations)

    def test_override_true_on_nonstrict_engine_raises(self) -> None:
        engine = _make_engine(strict=False)
        # Without override, non-strict engine returns invalid result.
        result = engine.validate("leak secret data")
        assert result.valid is False
        # With per-call strict=True, same action raises.
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("leak secret data", strict=True)

    def test_override_none_uses_instance_strict(self) -> None:
        engine = _make_engine(strict=True)
        with pytest.raises(ConstitutionalViolationError):
            engine.validate("leak secret data", strict=None)

    def test_override_does_not_mutate_instance_strict(self) -> None:
        engine = _make_engine(strict=True)
        engine.validate("leak secret data", strict=False)
        assert engine.strict is True

    def test_override_does_not_leak_on_exception(self) -> None:
        import contextlib

        engine = _make_engine(strict=True)
        # strict=False should not raise, but even if something inside raised,
        # we must not leave self.strict flipped.
        with contextlib.suppress(Exception):
            engine.validate("leak secret data", strict=False)
        assert engine.strict is True


class TestConcurrentMixedStrict:
    def test_parallel_threads_with_opposite_strict_do_not_interfere(self) -> None:
        """Two threads hammering the same shared engine with opposite strict
        overrides must each see their own strict semantics."""
        engine = _make_engine(strict=True)
        barrier = threading.Barrier(2)
        errors: list[str] = []

        def strict_caller() -> None:
            barrier.wait()
            for _ in range(200):
                try:
                    engine.validate("leak secret data", strict=True)
                except ConstitutionalViolationError:
                    continue
                errors.append("strict=True did not raise")
                return

        def non_strict_caller() -> None:
            barrier.wait()
            for _ in range(200):
                try:
                    result = engine.validate("leak secret data", strict=False)
                except ConstitutionalViolationError:
                    errors.append("strict=False raised")
                    return
                if result.valid:
                    errors.append("strict=False returned valid=True")
                    return

        t1 = threading.Thread(target=strict_caller)
        t2 = threading.Thread(target=non_strict_caller)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == [], errors
        assert engine.strict is True
