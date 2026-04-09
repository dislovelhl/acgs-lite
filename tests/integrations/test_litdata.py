# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
"""Tests for acgs_lite.integrations.litdata — no litdata install required."""

from __future__ import annotations

import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Inject litdata stub BEFORE importing the module under test
# ---------------------------------------------------------------------------

_litdata_stub = types.ModuleType("litdata")


class _StubStreamingDataset:
    """Minimal StreamingDataset stub; holds a list of fake samples."""

    _items: list = []

    def __init__(self, input_dir: str, **kwargs: object) -> None:
        self.input_dir = input_dir

    def __getitem__(self, index: int) -> object:
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)


_litdata_stub.StreamingDataset = _StubStreamingDataset
sys.modules.setdefault("litdata", _litdata_stub)

# ---------------------------------------------------------------------------
# Now import the module under test (litdata stub is already in sys.modules)
# ---------------------------------------------------------------------------

from acgs_lite.integrations.litdata import LITDATA_AVAILABLE, ACGSGovernedDataset  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ds(items: list, strict: bool = True) -> ACGSGovernedDataset:
    """Build a dataset with injected items and a real ACGS constitution."""
    from acgs_lite.constitution import Constitution

    _StubStreamingDataset._items = items
    ds = ACGSGovernedDataset.__new__(ACGSGovernedDataset)
    _StubStreamingDataset.__init__(ds, "fake://path")
    # Manually init governance (bypass __init__ which calls super().__init__)
    from acgs_lite.audit import AuditLog
    from acgs_lite.engine import GovernanceEngine

    ds._constitution = Constitution.default()
    ds._agent_id = "test-ds"
    ds._strict = strict
    ds._audit_log = AuditLog()
    ds._engine = GovernanceEngine(
        ds._constitution,
        audit_log=ds._audit_log,
        strict=strict,
        audit_mode="full",
    )
    ds._samples_evaluated = 0
    ds._samples_filtered = 0
    ds._violation_rule_ids = []
    return ds


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_litdata_available_flag() -> None:
    """LITDATA_AVAILABLE reflects whether litdata is importable."""
    assert isinstance(LITDATA_AVAILABLE, bool)


def test_valid_sample_passes_through() -> None:
    """A benign sample is returned unchanged."""
    ds = _make_ds([{"text": "hello world"}])
    result = ds[0]
    assert result == {"text": "hello world"}
    assert ds.samples_evaluated == 1
    assert ds.samples_filtered == 0


def test_multiple_samples_counter() -> None:
    """samples_evaluated increments with each __getitem__ call."""
    ds = _make_ds([{"text": "a"}, {"text": "b"}, {"text": "c"}])
    for i in range(3):
        ds[i]
    assert ds.samples_evaluated == 3
    assert ds.samples_filtered == 0


def test_non_serializable_sample_passes_through() -> None:
    """Samples that cannot be serialized (e.g. raw objects) are passed through."""

    # A class instance with no JSON-serializable fields
    class _RawTensor:
        pass

    ds = _make_ds([_RawTensor()])
    result = ds[0]
    assert isinstance(result, _RawTensor)
    assert ds.samples_evaluated == 1
    assert ds.samples_filtered == 0


def test_violating_sample_strict_raises() -> None:
    """In strict mode, a constitutionally violating sample raises ConstitutionalViolationError."""
    from unittest.mock import patch

    from acgs_lite.errors import ConstitutionalViolationError

    ds = _make_ds([{"text": "clean data"}], strict=True)

    with (
        patch.object(
            ds._engine,
            "validate",
            side_effect=ConstitutionalViolationError("test violation", rule_id="R001"),
        ),
        pytest.raises(ConstitutionalViolationError),
    ):
        ds[0]
    assert ds.samples_filtered == 1


def test_violating_sample_non_strict_returns_none() -> None:
    """In non-strict mode, a violating sample returns None and increments filtered count."""
    from unittest.mock import patch

    from acgs_lite.errors import ConstitutionalViolationError

    ds = _make_ds([{"text": "clean data"}], strict=False)

    with patch.object(
        ds._engine,
        "validate",
        side_effect=ConstitutionalViolationError("test violation", rule_id="R002"),
    ):
        result = ds[0]
    assert result is None
    assert ds.samples_filtered == 1
    assert ds.samples_evaluated == 1


def test_violation_rule_id_tracked() -> None:
    """Violation rule IDs are accumulated for the provenance report."""
    from unittest.mock import patch

    from acgs_lite.errors import ConstitutionalViolationError

    ds = _make_ds([{"text": "a"}, {"text": "b"}], strict=False)

    violation = ConstitutionalViolationError("test violation", rule_id="R001")
    with patch.object(ds._engine, "validate", side_effect=violation):
        ds[0]
        ds[1]

    assert ds._violation_rule_ids == ["R001", "R001"]


def test_provenance_report_structure() -> None:
    """provenance_report() returns a dict with all required EU AI Act Article 10 fields."""
    ds = _make_ds([{"text": "x"}, {"text": "y"}])
    ds[0]
    ds[1]
    report = ds.provenance_report()
    assert report["constitutional_hash"] == "608508a9bd224290"
    assert report["agent_id"] == "test-ds"
    assert report["samples_evaluated"] == 2
    assert report["samples_filtered"] == 0
    assert report["filter_rate"] == 0.0
    assert isinstance(report["violation_rule_ids"], dict)
    assert "governance_stats" in report


def test_provenance_report_filter_rate() -> None:
    """filter_rate is calculated correctly from filtered / evaluated."""
    from unittest.mock import patch

    from acgs_lite.errors import ConstitutionalViolationError

    ds = _make_ds([{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}], strict=False)
    violation = ConstitutionalViolationError("test violation", rule_id="R001")

    call_count = 0

    def _side_effect(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise violation

    with patch.object(ds._engine, "validate", side_effect=_side_effect):
        for i in range(4):
            ds[i]

    report = ds.provenance_report()
    assert report["samples_evaluated"] == 4
    assert report["samples_filtered"] == 1
    assert report["filter_rate"] == 0.25


def test_no_litdata_guard() -> None:
    """LITDATA_AVAILABLE is True with stub; guard message references litdata install."""
    # The stub is loaded so LITDATA_AVAILABLE is True in this test run.
    # Test the guard path by calling __init__ after temporarily removing the stub.
    saved = sys.modules.pop("litdata", None)
    try:
        # Temporarily make litdata unavailable inside the module
        import acgs_lite.integrations.litdata as _mod

        old_flag = _mod.LITDATA_AVAILABLE
        _mod.LITDATA_AVAILABLE = False  # type: ignore[assignment]
        with pytest.raises(ImportError, match="litdata"):
            ACGSGovernedDataset("fake://path")
    finally:
        _mod.LITDATA_AVAILABLE = old_flag  # type: ignore[assignment]
        if saved is not None:
            sys.modules["litdata"] = saved
