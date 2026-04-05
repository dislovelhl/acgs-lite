"""Compatibility tests for the thin ``acgs`` namespace package."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

EXPECTED_EXPORTS = {
    "AuditEntry",
    "AuditLog",
    "Constitution",
    "ConstitutionalViolationError",
    "GovernanceEngine",
    "MACIEnforcer",
    "MACIRole",
    "Rule",
    "Severity",
    "ValidationResult",
    "Violation",
    "fail_closed",
}

CORE_SRC = Path(__file__).resolve().parents[1] / "src"


def load_acgs() -> object:
    """Import the core namespace from this package's source tree."""
    core_src = str(CORE_SRC)
    sys.modules.pop("acgs", None)
    if core_src in sys.path:
        sys.path.remove(core_src)
    sys.path.insert(0, core_src)
    return importlib.import_module("acgs")


def test_all_namespace_exports_are_importable() -> None:
    acgs = load_acgs()

    for name in EXPECTED_EXPORTS:
        assert hasattr(acgs, name), f"acgs.{name} not found"

    assert "__version__" in acgs.__all__
    assert EXPECTED_EXPORTS.issubset(set(acgs.__all__))


def test_constitution_default_works() -> None:
    acgs = load_acgs()
    constitution = acgs.Constitution.default()

    assert constitution.rules
    assert isinstance(constitution.hash, str)


def test_governance_engine_validate_returns_validation_result() -> None:
    acgs = load_acgs()
    constitution = acgs.Constitution.default()
    result = acgs.GovernanceEngine(constitution).validate("hello")

    assert isinstance(result, acgs.ValidationResult)


def test_maci_roles_exposed() -> None:
    acgs = load_acgs()
    assert acgs.MACIRole.PROPOSER.value == "proposer"
    assert acgs.MACIRole.VALIDATOR.value == "validator"
    assert acgs.MACIRole.EXECUTOR.value == "executor"
    assert acgs.MACIRole.OBSERVER.value == "observer"


def test_fail_closed_decorator_works() -> None:
    acgs = load_acgs()

    @acgs.fail_closed(deny_value=False)
    def guarded(value: bool) -> bool:
        if value:
            return True
        raise ValueError("boom")

    assert guarded(True) is True
    assert guarded(False) is False


def test_version_is_a_string() -> None:
    acgs = load_acgs()
    assert isinstance(acgs.__version__, str)
    assert acgs.__version__ == "1.0.0a1"


def test_five_line_quickstart_runs() -> None:
    acgs = load_acgs()
    namespace: dict[str, object] = {}
    quickstart = "\n".join(
        [
            "from acgs import Constitution, GovernanceEngine, Rule, Severity",
            'constitution = Constitution.from_rules([Rule(id="R1", text="No self-approval", severity=Severity.HIGH, keywords=["self-approve"])])',
            "engine = GovernanceEngine(constitution, strict=False)",
            'result = engine.validate("self-approve this change")',
            "assert not result.valid",
        ]
    )

    exec(quickstart, namespace)
    assert isinstance(namespace["result"], acgs.ValidationResult)
