# Constitutional Hash: 608508a9bd224290
# Sprint 55 — ifc/labels.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/ifc/labels.py.

Covers:
- Confidentiality enum values and ordering
- Integrity enum values and ordering
- IFCLabel defaults and construction
- IFCLabel.taint_merge (all combinations)
- IFCLabel.can_flow_to (all policy combinations)
- IFCLabel.to_dict / from_dict round-trip
- IFCLabel.__repr__
- IFCViolation construction and properties
- IFCViolation.is_confidentiality_violation
- IFCViolation.is_integrity_violation
- IFCViolation.to_dict
- taint_merge() variadic helper (0, 1, 2, N args)
"""

import pytest

from enhanced_agent_bus.ifc.labels import (
    Confidentiality,
    IFCLabel,
    IFCViolation,
    Integrity,
    taint_merge,
)

# ---------------------------------------------------------------------------
# Confidentiality enum
# ---------------------------------------------------------------------------


class TestConfidentiality:
    def test_values_are_ordered(self):
        assert Confidentiality.PUBLIC < Confidentiality.INTERNAL
        assert Confidentiality.INTERNAL < Confidentiality.CONFIDENTIAL
        assert Confidentiality.CONFIDENTIAL < Confidentiality.SECRET

    def test_integer_values(self):
        assert Confidentiality.PUBLIC.value == 0
        assert Confidentiality.INTERNAL.value == 1
        assert Confidentiality.CONFIDENTIAL.value == 2
        assert Confidentiality.SECRET.value == 3

    def test_names(self):
        assert Confidentiality.PUBLIC.name == "PUBLIC"
        assert Confidentiality.INTERNAL.name == "INTERNAL"
        assert Confidentiality.CONFIDENTIAL.name == "CONFIDENTIAL"
        assert Confidentiality.SECRET.name == "SECRET"

    def test_comparison_operators(self):
        assert Confidentiality.SECRET > Confidentiality.PUBLIC
        assert Confidentiality.PUBLIC <= Confidentiality.INTERNAL
        assert Confidentiality.CONFIDENTIAL >= Confidentiality.CONFIDENTIAL

    def test_is_int_enum(self):
        assert isinstance(Confidentiality.PUBLIC, int)
        assert int(Confidentiality.SECRET) == 3


# ---------------------------------------------------------------------------
# Integrity enum
# ---------------------------------------------------------------------------


class TestIntegrity:
    def test_values_are_ordered(self):
        assert Integrity.UNTRUSTED < Integrity.LOW
        assert Integrity.LOW < Integrity.MEDIUM
        assert Integrity.MEDIUM < Integrity.HIGH
        assert Integrity.HIGH < Integrity.TRUSTED

    def test_integer_values(self):
        assert Integrity.UNTRUSTED.value == 0
        assert Integrity.LOW.value == 1
        assert Integrity.MEDIUM.value == 2
        assert Integrity.HIGH.value == 3
        assert Integrity.TRUSTED.value == 4

    def test_names(self):
        assert Integrity.UNTRUSTED.name == "UNTRUSTED"
        assert Integrity.LOW.name == "LOW"
        assert Integrity.MEDIUM.name == "MEDIUM"
        assert Integrity.HIGH.name == "HIGH"
        assert Integrity.TRUSTED.name == "TRUSTED"

    def test_comparison_operators(self):
        assert Integrity.TRUSTED > Integrity.UNTRUSTED
        assert Integrity.MEDIUM <= Integrity.HIGH
        assert Integrity.HIGH >= Integrity.HIGH

    def test_is_int_enum(self):
        assert isinstance(Integrity.TRUSTED, int)
        assert int(Integrity.TRUSTED) == 4


# ---------------------------------------------------------------------------
# IFCLabel construction and defaults
# ---------------------------------------------------------------------------


class TestIFCLabelDefaults:
    def test_default_confidentiality(self):
        label = IFCLabel()
        assert label.confidentiality == Confidentiality.PUBLIC

    def test_default_integrity(self):
        label = IFCLabel()
        assert label.integrity == Integrity.MEDIUM

    def test_explicit_construction(self):
        label = IFCLabel(
            confidentiality=Confidentiality.SECRET,
            integrity=Integrity.TRUSTED,
        )
        assert label.confidentiality == Confidentiality.SECRET
        assert label.integrity == Integrity.TRUSTED

    def test_frozen_dataclass_immutable(self):
        label = IFCLabel()
        with pytest.raises(AttributeError):
            label.confidentiality = Confidentiality.SECRET  # type: ignore[misc]

    def test_equality(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.LOW)
        b = IFCLabel(Confidentiality.INTERNAL, Integrity.LOW)
        assert a == b

    def test_inequality(self):
        a = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        b = IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM)
        assert a != b


# ---------------------------------------------------------------------------
# IFCLabel.__repr__
# ---------------------------------------------------------------------------


class TestIFCLabelRepr:
    def test_repr_default(self):
        label = IFCLabel()
        r = repr(label)
        assert "PUBLIC" in r
        assert "MEDIUM" in r
        assert "IFCLabel" in r

    def test_repr_all_levels(self):
        label = IFCLabel(Confidentiality.SECRET, Integrity.TRUSTED)
        r = repr(label)
        assert "SECRET" in r
        assert "TRUSTED" in r


# ---------------------------------------------------------------------------
# IFCLabel.taint_merge
# ---------------------------------------------------------------------------


class TestTaintMerge:
    def test_same_label_identity(self):
        label = IFCLabel(Confidentiality.INTERNAL, Integrity.HIGH)
        merged = label.taint_merge(label)
        assert merged == label

    def test_confidentiality_escalates_to_max(self):
        a = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        b = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        merged = a.taint_merge(b)
        assert merged.confidentiality == Confidentiality.SECRET

    def test_confidentiality_escalates_symmetric(self):
        a = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        b = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        merged = a.taint_merge(b)
        assert merged.confidentiality == Confidentiality.SECRET

    def test_integrity_degrades_to_min(self):
        a = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        b = IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED)
        merged = a.taint_merge(b)
        assert merged.integrity == Integrity.UNTRUSTED

    def test_integrity_degrades_symmetric(self):
        a = IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED)
        b = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        merged = a.taint_merge(b)
        assert merged.integrity == Integrity.UNTRUSTED

    def test_both_escalate_degrade(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.HIGH)
        b = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.LOW)
        merged = a.taint_merge(b)
        assert merged.confidentiality == Confidentiality.CONFIDENTIAL
        assert merged.integrity == Integrity.LOW

    def test_returns_new_label(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.MEDIUM)
        b = IFCLabel(Confidentiality.INTERNAL, Integrity.MEDIUM)
        merged = a.taint_merge(b)
        assert merged is not a
        assert merged is not b

    def test_all_confidentiality_combinations(self):
        levels = list(Confidentiality)
        for x in levels:
            for y in levels:
                a = IFCLabel(x, Integrity.MEDIUM)
                b = IFCLabel(y, Integrity.MEDIUM)
                merged = a.taint_merge(b)
                assert merged.confidentiality == max(x, y)

    def test_all_integrity_combinations(self):
        levels = list(Integrity)
        for x in levels:
            for y in levels:
                a = IFCLabel(Confidentiality.PUBLIC, x)
                b = IFCLabel(Confidentiality.PUBLIC, y)
                merged = a.taint_merge(b)
                assert merged.integrity == min(x, y)


# ---------------------------------------------------------------------------
# IFCLabel.can_flow_to
# ---------------------------------------------------------------------------


class TestCanFlowTo:
    # --- no-write-down (confidentiality) ---

    def test_public_can_flow_to_public(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is True

    def test_public_can_flow_to_secret(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is True

    def test_secret_cannot_flow_to_public(self):
        src = IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is False

    def test_secret_cannot_flow_to_internal(self):
        src = IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.INTERNAL, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is False

    def test_confidential_can_flow_to_same(self):
        src = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is True

    # --- no-read-up (integrity) ---

    def test_trusted_can_flow_to_untrusted(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED)
        assert src.can_flow_to(dst) is True

    def test_untrusted_cannot_flow_to_trusted(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        assert src.can_flow_to(dst) is False

    def test_untrusted_cannot_flow_to_medium(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is False

    def test_medium_can_flow_to_medium(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM)
        assert src.can_flow_to(dst) is True

    # --- both policies violated ---

    def test_both_violated(self):
        # SECRET conf, UNTRUSTED integrity flowing to PUBLIC channel req TRUSTED
        src = IFCLabel(Confidentiality.SECRET, Integrity.UNTRUSTED)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        assert src.can_flow_to(dst) is False

    # --- conf ok, integrity violated ---

    def test_conf_ok_integrity_violated(self):
        src = IFCLabel(Confidentiality.PUBLIC, Integrity.LOW)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH)
        assert src.can_flow_to(dst) is False

    # --- conf violated, integrity ok ---

    def test_conf_violated_integrity_ok(self):
        src = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        dst = IFCLabel(Confidentiality.PUBLIC, Integrity.LOW)
        assert src.can_flow_to(dst) is False

    def test_full_lattice_sweep(self):
        """Exhaustive check: can_flow_to matches manual formula."""
        for c_src in Confidentiality:
            for i_src in Integrity:
                for c_dst in Confidentiality:
                    for i_dst in Integrity:
                        src = IFCLabel(c_src, i_src)
                        dst = IFCLabel(c_dst, i_dst)
                        expected = (c_dst >= c_src) and (i_src >= i_dst)
                        assert src.can_flow_to(dst) == expected


# ---------------------------------------------------------------------------
# IFCLabel serialization
# ---------------------------------------------------------------------------


class TestIFCLabelSerialization:
    def test_to_dict_keys(self):
        label = IFCLabel()
        d = label.to_dict()
        assert "confidentiality" in d
        assert "integrity" in d

    def test_to_dict_values_are_ints(self):
        label = IFCLabel(Confidentiality.SECRET, Integrity.TRUSTED)
        d = label.to_dict()
        assert d["confidentiality"] == 3
        assert d["integrity"] == 4

    def test_from_dict_round_trip(self):
        for conf in Confidentiality:
            for integ in Integrity:
                original = IFCLabel(conf, integ)
                restored = IFCLabel.from_dict(original.to_dict())
                assert restored == original

    def test_from_dict_explicit(self):
        label = IFCLabel.from_dict({"confidentiality": 2, "integrity": 3})
        assert label.confidentiality == Confidentiality.CONFIDENTIAL
        assert label.integrity == Integrity.HIGH

    def test_from_dict_zero_values(self):
        label = IFCLabel.from_dict({"confidentiality": 0, "integrity": 0})
        assert label.confidentiality == Confidentiality.PUBLIC
        assert label.integrity == Integrity.UNTRUSTED


# ---------------------------------------------------------------------------
# IFCViolation
# ---------------------------------------------------------------------------


class TestIFCViolation:
    def _make(
        self,
        src_conf=Confidentiality.SECRET,
        src_int=Integrity.LOW,
        dst_conf=Confidentiality.PUBLIC,
        dst_int=Integrity.HIGH,
        policy="no-write-down",
        detail="test detail",
    ):
        return IFCViolation(
            source_label=IFCLabel(src_conf, src_int),
            target_label=IFCLabel(dst_conf, dst_int),
            policy=policy,
            detail=detail,
        )

    def test_construction(self):
        v = self._make()
        assert v.policy == "no-write-down"
        assert v.detail == "test detail"

    def test_default_detail_empty(self):
        v = IFCViolation(
            source_label=IFCLabel(),
            target_label=IFCLabel(),
            policy="test",
        )
        assert v.detail == ""

    def test_frozen_immutable(self):
        v = self._make()
        with pytest.raises(AttributeError):
            v.policy = "other"  # type: ignore[misc]

    # is_confidentiality_violation

    def test_is_confidentiality_violation_true(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM),
            target_label=IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM),
            policy="no-write-down",
        )
        assert v.is_confidentiality_violation is True

    def test_is_confidentiality_violation_false_equal(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.INTERNAL, Integrity.MEDIUM),
            target_label=IFCLabel(Confidentiality.INTERNAL, Integrity.MEDIUM),
            policy="test",
        )
        assert v.is_confidentiality_violation is False

    def test_is_confidentiality_violation_false_target_higher(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.PUBLIC, Integrity.MEDIUM),
            target_label=IFCLabel(Confidentiality.SECRET, Integrity.MEDIUM),
            policy="test",
        )
        assert v.is_confidentiality_violation is False

    # is_integrity_violation

    def test_is_integrity_violation_true(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.PUBLIC, Integrity.UNTRUSTED),
            target_label=IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED),
            policy="no-read-up",
        )
        assert v.is_integrity_violation is True

    def test_is_integrity_violation_false_equal(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH),
            target_label=IFCLabel(Confidentiality.PUBLIC, Integrity.HIGH),
            policy="test",
        )
        assert v.is_integrity_violation is False

    def test_is_integrity_violation_false_source_higher(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED),
            target_label=IFCLabel(Confidentiality.PUBLIC, Integrity.LOW),
            policy="test",
        )
        assert v.is_integrity_violation is False

    # both violations

    def test_both_violations(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.SECRET, Integrity.UNTRUSTED),
            target_label=IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED),
            policy="both",
        )
        assert v.is_confidentiality_violation is True
        assert v.is_integrity_violation is True

    # neither violation

    def test_neither_violation(self):
        v = IFCViolation(
            source_label=IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED),
            target_label=IFCLabel(Confidentiality.SECRET, Integrity.UNTRUSTED),
            policy="neither",
        )
        assert v.is_confidentiality_violation is False
        assert v.is_integrity_violation is False

    # to_dict

    def test_to_dict_structure(self):
        v = self._make()
        d = v.to_dict()
        assert "source_label" in d
        assert "target_label" in d
        assert "policy" in d
        assert "detail" in d

    def test_to_dict_nested_labels(self):
        v = self._make(
            src_conf=Confidentiality.SECRET,
            src_int=Integrity.LOW,
            dst_conf=Confidentiality.PUBLIC,
            dst_int=Integrity.HIGH,
        )
        d = v.to_dict()
        assert d["source_label"]["confidentiality"] == 3
        assert d["source_label"]["integrity"] == 1
        assert d["target_label"]["confidentiality"] == 0
        assert d["target_label"]["integrity"] == 3

    def test_to_dict_policy_and_detail(self):
        v = self._make(policy="no-write-down", detail="flow blocked")
        d = v.to_dict()
        assert d["policy"] == "no-write-down"
        assert d["detail"] == "flow blocked"

    def test_to_dict_empty_detail(self):
        v = IFCViolation(
            source_label=IFCLabel(),
            target_label=IFCLabel(),
            policy="p",
        )
        d = v.to_dict()
        assert d["detail"] == ""


# ---------------------------------------------------------------------------
# taint_merge() variadic helper
# ---------------------------------------------------------------------------


class TestTaintMergeVariadic:
    def test_no_args_returns_default_label(self):
        result = taint_merge()
        assert result == IFCLabel()
        assert result.confidentiality == Confidentiality.PUBLIC
        assert result.integrity == Integrity.MEDIUM

    def test_single_arg_returns_same(self):
        label = IFCLabel(Confidentiality.SECRET, Integrity.TRUSTED)
        result = taint_merge(label)
        assert result == label

    def test_two_args(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.HIGH)
        b = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.LOW)
        result = taint_merge(a, b)
        assert result.confidentiality == Confidentiality.CONFIDENTIAL
        assert result.integrity == Integrity.LOW

    def test_three_args(self):
        a = IFCLabel(Confidentiality.PUBLIC, Integrity.TRUSTED)
        b = IFCLabel(Confidentiality.SECRET, Integrity.HIGH)
        c = IFCLabel(Confidentiality.INTERNAL, Integrity.UNTRUSTED)
        result = taint_merge(a, b, c)
        assert result.confidentiality == Confidentiality.SECRET
        assert result.integrity == Integrity.UNTRUSTED

    def test_many_args_confidentiality_is_max(self):
        labels = [IFCLabel(Confidentiality(i % 4), Integrity.TRUSTED) for i in range(10)]
        result = taint_merge(*labels)
        assert result.confidentiality == Confidentiality.SECRET

    def test_many_args_integrity_is_min(self):
        labels = [IFCLabel(Confidentiality.PUBLIC, Integrity(i % 5)) for i in range(10)]
        result = taint_merge(*labels)
        assert result.integrity == Integrity.UNTRUSTED

    def test_associativity(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.HIGH)
        b = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.MEDIUM)
        c = IFCLabel(Confidentiality.PUBLIC, Integrity.LOW)
        # (a merge b) merge c == a merge (b merge c)
        left = taint_merge(a, b, c)
        right = taint_merge(a, taint_merge(b, c))
        assert left == right

    def test_commutativity(self):
        a = IFCLabel(Confidentiality.INTERNAL, Integrity.HIGH)
        b = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.LOW)
        assert taint_merge(a, b) == taint_merge(b, a)

    def test_idempotency(self):
        label = IFCLabel(Confidentiality.CONFIDENTIAL, Integrity.MEDIUM)
        assert taint_merge(label, label) == label

    def test_all_same_returns_same(self):
        label = IFCLabel(Confidentiality.SECRET, Integrity.TRUSTED)
        result = taint_merge(label, label, label, label)
        assert result == label
