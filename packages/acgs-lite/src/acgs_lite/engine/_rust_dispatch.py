"""Rust hot-path dispatch methods for GovernanceEngine.

Extracted from ``core.py`` to keep that module focused on the Python
validation paths and engine lifecycle.
"""

from __future__ import annotations

from typing import Any

from acgs_lite.constitution import Severity
from acgs_lite.errors import ConstitutionalViolationError

from .rust import _RUST_ALLOW, _RUST_DENY, _RUST_DENY_CRITICAL
from .types import ValidationResult, Violation


class RustDispatchMixin:
    """Mixin providing Rust hot-path validation dispatch for GovernanceEngine."""

    # Type stubs for attributes provided by GovernanceEngine (the concrete host class).
    _rule_data: list[Any]
    _pooled_result: ValidationResult
    _pooled_escalate: ValidationResult
    _rule_excs: list[Any]
    _rule_id_to_exc_idx: dict[str, int]
    _rust_validator: Any
    strict: bool

    def _validate_rust_no_context(
        self,
        action: str,
        decision: int,
        data: int,
        rule_excs: list[Any],
        fast_records: Any,
    ) -> ValidationResult | None:
        if decision == _RUST_ALLOW:
            # exp108: _is_noop always True here
            fast_records.append(None)
            return self._pooled_result
        elif decision == _RUST_DENY_CRITICAL:
            # exp111: _data already Python int
            if not (0 <= data < len(rule_excs)):
                fast_records.append(None)
                raise ConstitutionalViolationError(
                    "Critical rule violation (index out of range)",
                    rule_id="UNKNOWN",
                    severity="critical",
                    action=action[:200],
                )
            _e_src = rule_excs[data]
            # exp108: _is_noop always True here
            fast_records.append(None)
            raise ConstitutionalViolationError(
                str(_e_src),
                rule_id=_e_src.rule_id,
                severity=_e_src.severity,
                action=action[:200],
            )
        elif decision == _RUST_DENY:
            # exp111: _data already Python int
            _bm = data
            _a200 = action[:200]
            _vlist: list[Violation] = []
            _bv: Violation | None = None
            while _bm:
                _idx = (_bm & -_bm).bit_length() - 1
                _bm &= _bm - 1
                _rd = self._rule_data[_idx]
                _v = Violation(_rd[0], _rd[1], _rd[2], _a200, _rd[4])
                _vlist.append(_v)
                if _bv is None and _v.severity.blocks():
                    _bv = _v
            # exp108: _is_noop always True here — append before possible raise so the
            # audit record is always emitted.
            fast_records.append(None)
            # strict=True is guaranteed at this call site (outer validate() guard).
            if _bv is not None:
                raise ConstitutionalViolationError(
                    f"Action blocked by rule {_bv.rule_id}: {_bv.rule_text}",
                    rule_id=_bv.rule_id,
                    severity=_bv.severity.value,
                    action=_a200,
                )
            _pool_e = self._pooled_escalate
            _pool_e.violations = _vlist
            _pool_e.action = action[:500]
            return _pool_e
        return None

    def _validate_rust_gov_context(
        self,
        action: str,
        decision: int,
        data: int,
        context: dict[str, Any],
        rule_excs: list[Any],
        fast_records: Any,
    ) -> ValidationResult | None:
        _merged_bm = 0
        _has_critical = False
        _crit_idx = -1
        if decision == _RUST_DENY_CRITICAL:
            # exp111: _data is already Python int (PyO3 i64→int auto-convert)
            _crit_idx = data
            _has_critical = True
        elif decision == _RUST_DENY:
            _merged_bm = data
        # exp97: replace dict.items() iteration with direct .get() for known keys.
        # Avoids iterator creation + key comparison per item; saves ~80ns/call.
        _ctx_det = context.get("action_detail")
        _ctx_desc = context.get("action_description")
        for _cv in (_ctx_det, _ctx_desc):
            if _cv is not None and isinstance(_cv, str):
                # exp271: Rust handles lowercasing internally
                _ctx_dec, _ctx_data = self._rust_validator.validate_hot(_cv)
                if _ctx_dec == _RUST_DENY_CRITICAL and not _has_critical:
                    # exp111: _ctx_data already Python int
                    _crit_idx = _ctx_data
                    _has_critical = True
                elif _ctx_dec == _RUST_DENY:
                    _merged_bm |= _ctx_data
        if _has_critical:
            if not (0 <= _crit_idx < len(rule_excs)):
                fast_records.append(None)
                raise ConstitutionalViolationError(
                    "Critical rule violation (index out of range)",
                    rule_id="UNKNOWN",
                    severity="critical",
                    action=action[:200],
                )
            _e_src = rule_excs[_crit_idx]
            # exp108: _is_noop always True here
            fast_records.append(None)
            raise ConstitutionalViolationError(
                str(_e_src),
                rule_id=_e_src.rule_id,
                severity=_e_src.severity,
                action=action[:200],
            )
        if _merged_bm:
            _a200 = action[:200]
            _vlist: list[Violation] = []
            # exp91: single-pass blocking detection — avoids any()+next() double scan.
            _bv_ctx: Violation | None = None
            while _merged_bm:
                _idx = (_merged_bm & -_merged_bm).bit_length() - 1
                _merged_bm &= _merged_bm - 1
                _rd = self._rule_data[_idx]
                _v = Violation(_rd[0], _rd[1], _rd[2], _a200, _rd[4])
                _vlist.append(_v)
                if _bv_ctx is None and _v.severity.blocks():
                    _bv_ctx = _v
            if _bv_ctx is not None and self.strict:
                raise ConstitutionalViolationError(
                    f"Action blocked by rule {_bv_ctx.rule_id}: {_bv_ctx.rule_text}",
                    rule_id=_bv_ctx.rule_id,
                    severity=_bv_ctx.severity.value,
                    action=_a200,
                )
            _pool_e = self._pooled_escalate
            _pool_e.violations = _vlist
            _pool_e.action = action[:500]
            # exp108: _is_noop always True here
            fast_records.append(None)
            return _pool_e
        # exp108: _is_noop always True here
        fast_records.append(None)
        return self._pooled_result

    def _validate_rust_metadata_context(
        self,
        action: str,
        decision: int,
        data: int,
        rule_excs: list[Any],
        fast_records: Any,
        is_noop: bool,
    ) -> ValidationResult | None:
        if decision == _RUST_ALLOW:
            if is_noop:
                # exp108: _is_noop always True here
                fast_records.append(None)
            return self._pooled_result
        elif decision == _RUST_DENY_CRITICAL:
            # exp111: _data already Python int
            if not (0 <= data < len(rule_excs)):
                if is_noop:
                    fast_records.append(None)
                raise ConstitutionalViolationError(
                    "Critical rule violation (index out of range)",
                    rule_id="UNKNOWN",
                    severity="critical",
                    action=action[:200],
                )
            _e_src = rule_excs[data]
            if is_noop:
                fast_records.append(None)
            raise ConstitutionalViolationError(
                str(_e_src),
                rule_id=_e_src.rule_id,
                severity=_e_src.severity,
                action=action[:200],
            )
        elif decision == _RUST_DENY:
            # exp111: _data already Python int
            _bm = data
            _a200 = action[:200]
            _vlist: list[Violation] = []
            while _bm:
                _idx = (_bm & -_bm).bit_length() - 1
                _bm &= _bm - 1
                _rd = self._rule_data[_idx]
                _vlist.append(Violation(_rd[0], _rd[1], _rd[2], _a200, _rd[4]))
            _pool_e = self._pooled_escalate
            _pool_e.violations = _vlist
            _pool_e.action = action[:500]
            if is_noop:
                fast_records.append(None)
            return _pool_e
        return None

    def _validate_rust_full(
        self,
        action: str,
        strict: bool,
        ctx_pairs: list[tuple[str, str]],
        rule_excs: list[Any],
        fast_records: Any,
    ) -> ValidationResult | None:
        # exp271: Rust handles lowercasing internally
        _decision, _violations, _blocking = self._rust_validator.validate_full(
            action, ctx_pairs
        )
        if _decision == _RUST_ALLOW:
            if fast_records is not None:
                fast_records.append(None)
                return self._pooled_result
        elif _decision == _RUST_DENY_CRITICAL:
            # exp83: O(1) dict lookup replaces O(n) linear scan
            _vt_id = _violations[0][0]
            _idx = self._rule_id_to_exc_idx.get(_vt_id)
            if _idx is None:
                _vt_id, _vt_text, _vt_sev, _, _ = _violations[0]
                raise ConstitutionalViolationError(
                    f"Action blocked by rule {_vt_id}: {_vt_text}",
                    rule_id=_vt_id,
                    severity=_vt_sev,
                    action=action[:200],
                )
            _e_src = rule_excs[_idx]
            raise ConstitutionalViolationError(
                str(_e_src),
                rule_id=_e_src.rule_id,
                severity=_e_src.severity,
                action=action[:200],
            )
        elif _decision == _RUST_DENY:
            _a200 = action[:200]
            _SEV = Severity
            _vlist = [
                Violation(rid, rtxt, _SEV(sev), _a200, cat)
                for rid, rtxt, sev, _, cat in _violations
            ]
            if _blocking and strict:
                # exp83: use O(1) dict lookup to clone the source exception metadata
                _bv = next((v for v in _vlist if v.severity.blocks()), _vlist[0])
                _exc_idx = self._rule_id_to_exc_idx.get(_bv.rule_id, -1)
                if _exc_idx >= 0:
                    _e_src = rule_excs[_exc_idx]
                    raise ConstitutionalViolationError(
                        str(_e_src),
                        rule_id=_e_src.rule_id,
                        severity=_e_src.severity,
                        action=_a200,
                    )
                raise ConstitutionalViolationError(
                    f"Action blocked by rule {_bv.rule_id}: {_bv.rule_text}",
                    rule_id=_bv.rule_id,
                    severity=_bv.severity.value,
                    action=_a200,
                )
            if fast_records is not None:
                _pool_e = self._pooled_escalate
                _pool_e.violations = _vlist
                _pool_e.action = action[:500]
                return _pool_e
        return None
