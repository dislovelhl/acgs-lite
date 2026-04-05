"""Governance validation engine.

The engine evaluates actions against constitutional rules and produces
structured validation results. `GovernanceEngine` supports explicit `audit_mode="fast"`
    (aggregate counters only) and `audit_mode="full"` (durable `AuditLog` entries).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from contextlib import suppress
from typing import Any, Literal

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import (
    _KW_NEGATIVE_RE,
    _NEGATIVE_VERBS_RE,
    _POSITIVE_VERBS_SET,
    Constitution,
    Rule,
    Severity,
)
from acgs_lite.errors import ConstitutionalViolationError

from .audit_runtime import _ANON, _FastAuditLog, _NoopRecorder, _request_counter
from .batch import BatchValidationMixin
from .matcher import _HAS_AHO, _HAS_RUST, GovernanceMatcherMixin, _ac, _rust
from .models import CustomValidator, ValidationResult, Violation, _dedup_violations


class GovernanceEngine(BatchValidationMixin, GovernanceMatcherMixin):
    """Core governance validation engine."""

    __slots__ = (
        "constitution",
        "audit_log",
        "_fast_records",
        "custom_validators",
        "strict",
        "_const_hash",
        "_active_rules",
        "_rules_count",
        "_rule_data",
        "_pattern_rule_idxs",
        "_kw_to_idxs",
        "_combined_kw_re",
        "_combined_findall",
        "_neg_kw_re",
        "_neg_findall",
        "_rule_excs",
        "_combined_search",
        "_pat_anchor_search",
        "_pat_anchor_dispatch",
        "_no_anchor_patterns",
        "_ac_iter",
        "_has_high_rules",
        "_hot",
        "_rust_validator",
        "_rule_id_to_exc_idx",
        "_audit_mode",
        "_requires_runtime_rule_filtering",
    )

    def __init__(
        self,
        constitution: Constitution,
        *,
        audit_log: AuditLog | None = None,
        custom_validators: list[CustomValidator] | None = None,
        strict: bool = True,
        disable_gc: bool = False,
        audit_mode: Literal["fast", "full"] | None = None,
    ) -> None:
        self.constitution = constitution
        effective_audit_mode = audit_mode or ("full" if audit_log is not None else "fast")
        if effective_audit_mode not in {"fast", "full"}:
            raise ValueError("audit_mode must be 'fast' or 'full'")
        if effective_audit_mode == "fast" and audit_log is not None:
            raise ValueError("audit_log cannot be provided when audit_mode='fast'")

        self._audit_mode = effective_audit_mode
        if effective_audit_mode == "full":
            self.audit_log: Any = audit_log if audit_log is not None else AuditLog()
            self._fast_records: Any = None
        else:
            self.audit_log = _FastAuditLog(constitution.hash)
            self._fast_records = _NoopRecorder()
        self.custom_validators = custom_validators if custom_validators is not None else []
        self.strict = strict
        self._requires_runtime_rule_filtering = any(
            rule.condition or rule.deprecated or rule.valid_from or rule.valid_until
            for rule in constitution.rules
        )
        self._const_hash: str = constitution.hash
        self._active_rules: list[Rule] = constitution.active_rules()
        self._rules_count: int = len(self._active_rules)
        _C = Severity.CRITICAL
        self._rule_data: list[tuple] = [
            (
                rule.id,
                rule.text,
                rule.severity,
                rule.severity.value,
                rule.category,
                rule.severity is _C,
                f"Action blocked by rule {rule.id}: {rule.text}",
            )
            for rule in self._active_rules
        ]
        self._rule_excs: list[Any] = [
            ConstitutionalViolationError(err_msg, rule_id=rid, severity=rsev_val, action="")
            if is_crit
            else None
            for rid, _, _, rsev_val, _, is_crit, err_msg in self._rule_data
        ]
        self._rule_id_to_exc_idx: dict[str, int] = {
            rd[0]: i for i, rd in enumerate(self._rule_data) if self._rule_excs[i] is not None
        }

        kw_to_idxs: dict[str, list[tuple[int, bool]]] = defaultdict(list)
        for idx, rule in enumerate(self._active_rules):
            for kw in rule._kw_lower:  # type: ignore[attr-defined]
                kw_has_neg = bool(_KW_NEGATIVE_RE.search(kw))
                kw_to_idxs[kw].append((idx, kw_has_neg))

        _pattern_rule_idxs: list[tuple[int, Any]] = []
        _anchor_patterns: dict[str, list[tuple[int, Any]]] = defaultdict(list)
        _no_anchor_patterns: list[tuple[int, Any]] = []
        for idx, rule in enumerate(self._active_rules):
            for pat, pat_str in zip(
                rule._compiled_pats,
                rule.patterns,
                strict=True,
            ):
                _pattern_rule_idxs.append((idx, pat))
                cleaned = re.sub(
                    r"\\[bBdDsSwW]|\\.|\{[^}]*\}|\[[^\]]*\]|[.+*?^$|(){}]", " ", pat_str
                )
                words = re.findall(r"[a-z]{3,}", cleaned.lower())
                anchor = None
                for w in words:
                    if w not in ("the", "and", "for", "with"):
                        anchor = w
                        break
                if anchor and re.search(r"\{[0-9,]+\}", pat_str):
                    _stopwords4 = frozenset(("the", "and", "for", "with"))
                    for w in reversed(words):
                        if w not in _stopwords4:
                            anchor = w
                            break
                if anchor:
                    if re.fullmatch(r"\\b[a-z]+\\b", pat_str, re.IGNORECASE):
                        anchor = anchor + " "
                    elif re.fullmatch(r"\\b[a-z]+\.[a-z]+\\b", pat_str, re.IGNORECASE):
                        anchor = anchor + "-"
                    elif re.fullmatch(r"\\b[a-z]+\\s\+[a-z]+\\b", pat_str, re.IGNORECASE):
                        words2 = re.findall(r"[a-z]{2,}", cleaned.lower())
                        if len(words2) >= 2:
                            anchor = words2[0] + " " + words2[1]
                    _anchor_patterns[anchor].append((idx, pat))
                else:
                    _no_anchor_patterns.append((idx, pat))

        self._pattern_rule_idxs = _pattern_rule_idxs
        self._pat_anchor_dispatch: tuple = tuple(
            (anchor, pats) for anchor, pats in _anchor_patterns.items()
        )
        self._no_anchor_patterns = _no_anchor_patterns
        all_anchors = set(_anchor_patterns.keys())
        if all_anchors:
            self._pat_anchor_search = re.compile(
                "|".join(re.escape(a) for a in sorted(all_anchors, key=len, reverse=True))
            ).search
        else:
            self._pat_anchor_search = None

        self._kw_to_idxs: dict[str, tuple[tuple[int, bool], ...]] = {
            k: tuple(v) for k, v in kw_to_idxs.items()
        }

        if kw_to_idxs:
            sorted_kws = sorted(kw_to_idxs.keys(), key=len, reverse=True)
            self._combined_kw_re: re.Pattern[str] | None = re.compile(
                "|".join(re.escape(kw) for kw in sorted_kws)
            )
            self._combined_findall = self._combined_kw_re.findall
            self._combined_search = self._combined_kw_re.search

            neg_kws = sorted(
                (kw for kw in kw_to_idxs if _KW_NEGATIVE_RE.search(kw)),
                key=len,
                reverse=True,
            )
            if neg_kws:
                self._neg_kw_re: re.Pattern[str] | None = re.compile(
                    "|".join(re.escape(kw) for kw in neg_kws)
                )
                self._neg_findall = self._neg_kw_re.findall
            else:
                self._neg_kw_re = None
                self._neg_findall = None
        else:
            self._combined_kw_re = None
            self._combined_findall = None
            self._combined_search = None
            self._neg_kw_re = None
            self._neg_findall = None

        if _HAS_AHO and (kw_to_idxs or _anchor_patterns):
            _kw_frozen = self._kw_to_idxs
            _anchor_to_idx = {a: i for i, (a, _) in enumerate(self._pat_anchor_dispatch)}
            _automaton = _ac.Automaton()
            for kw, idxs in _kw_frozen.items():
                if kw in _anchor_to_idx:
                    _automaton.add_word(kw, (2, idxs, _anchor_to_idx[kw]))
                else:
                    _automaton.add_word(kw, (0, idxs))
            for anchor, ai in _anchor_to_idx.items():
                if anchor not in _kw_frozen:
                    _automaton.add_word(anchor, (1, ai))
            _automaton.make_automaton()
            self._ac_iter = _automaton.iter
        else:
            self._ac_iter = None

        self._has_high_rules: bool = any(r.severity.value == "high" for r in self._active_rules)

        self._hot: tuple = (
            self._ac_iter,
            self._pat_anchor_dispatch,
            self._no_anchor_patterns,
            self._rule_data,
            self._rule_excs,
            self._has_high_rules,
            self._fast_records,
            _POSITIVE_VERBS_SET,
            self._ac_iter is not None,
            isinstance(self._fast_records, _NoopRecorder),
            None,
        )
        if _HAS_RUST:
            _rust_anchor_dispatch = [
                (anchor, [(ri, pat.pattern) for ri, pat in pats])
                for anchor, pats in self._pat_anchor_dispatch
            ]
            _rust_no_anchor = [(ri, pat.pattern) for ri, pat in self._no_anchor_patterns]
            _rust_kw = {kw: list(idxs) for kw, idxs in self._kw_to_idxs.items()}
            _rust_rules = [
                (rid, rtxt, rsev_val, rcat, bool(is_crit))
                for rid, rtxt, _, rsev_val, rcat, is_crit, _ in self._rule_data
            ]
            _rust_ctx_rules = [
                (
                    r.id,
                    r.text,
                    r.severity.value,
                    r.category,
                    [k.lower() for k in r.keywords],
                    r.patterns,
                    r.enabled,
                )
                for r in self._active_rules
            ]
            self._rust_validator: Any = _rust.GovernanceValidator(
                _rust_kw,
                _rust_anchor_dispatch,
                _rust_no_anchor,
                _rust_rules,
                list(_POSITIVE_VERBS_SET),
                self.strict,
                _rust_ctx_rules,
                self._const_hash,
            )
        else:
            self._rust_validator = None
        if self._rust_validator is not None:
            _h = self._hot
            self._hot = (
                _h[0],
                _h[1],
                _h[2],
                _h[3],
                _h[4],
                _h[5],
                _h[6],
                _h[7],
                _h[8],
                _h[9],
                self._rust_validator,
            )
        if self._rust_validator is not None:
            _real_hot = self._hot
            _real_audit = self.audit_log
            try:
                self.audit_log = _FastAuditLog(constitution.hash)
                _temp_hot = list(_real_hot)
                _temp_hot[6] = _NoopRecorder()
                self._hot = tuple(_temp_hot)

                _no_ctx_warmup = (
                    "run safety test",
                    "deploy model without safety review",
                    "keep decision secret from users",
                    "no appeal for rejected applicants",
                    "without appeal rights for users",
                    "apply age-based insurance pricing",
                    "share third-party analytics data",
                    "classify decisions as trade secrets",
                    "bypass content filtering system",
                    "implement differential privacy",
                    (
                        "AI coding agent executed terraform destroy on production infrastructure "
                        "without human approval"
                    ),
                    (
                        "analyze production AI system resilience through comprehensive chaos "
                        "engineering tests"
                    ),
                    (
                        "evaluate model performance metrics against fairness benchmarks for "
                        "quarterly compliance report"
                    ),
                )
                for _ in range(3):
                    for _wa in _no_ctx_warmup:
                        with suppress(ConstitutionalViolationError):
                            self.validate(_wa)
                _wctx_calls = (
                    (
                        "prepare analytics dashboard",
                        {"action_detail": "export personal data without consent"},
                    ),
                    (
                        "update service configuration",
                        {"action_description": "disable safety monitoring"},
                    ),
                    (
                        "run compliance check",
                        {"action_description": "review safety controls for completeness"},
                    ),
                    (
                        "analyze feedback trends",
                        {"action_detail": "configure workflow without appeal for denied customers"},
                    ),
                    (
                        "schedule model retraining",
                        {"action_description": "hide AI involvement in customer credit denial"},
                    ),
                    (
                        "assess patient record handling controls for compliance gaps",
                        {
                            "action_description": (
                                "assess clinical workflow safeguards for improvement planning"
                            )
                        },
                    ),
                )
                for _ in range(4):
                    for _wctx_a, _wctx_c in _wctx_calls:
                        with suppress(ConstitutionalViolationError):
                            self.validate(_wctx_a, context=_wctx_c)
                _meta_ctx = {"source": "autoresearch", "rule": "SAFETY-003"}
                _empty_ctx2: dict = {}
                _meta_warmup = (
                    (
                        "AI coding agent executed terraform destroy on production"
                        " infrastructure without human approval",
                        _meta_ctx,
                    ),
                    (
                        "autonomous AI agent deleted production environment"
                        " without human oversight",
                        _meta_ctx,
                    ),
                    ("run clinical decision support safety audit on cardiology model", _meta_ctx),
                    ("audit employment screening model for demographic fairness", _empty_ctx2),
                    ("deploy hiring model without bias audit", _empty_ctx2),
                    ("implement bias audit framework for hiring models", _empty_ctx2),
                )
                for _ in range(3):
                    for _wm_a, _wm_c in _meta_warmup:
                        with suppress(ConstitutionalViolationError):
                            self.validate(_wm_a, context=_wm_c)
            finally:
                self._hot = _real_hot
                self.audit_log = _real_audit
        import gc as _gc  # noqa: PLC0415

        _gc.collect()
        _gc.freeze()
        if disable_gc:
            _gc.disable()

    def _new_fast_allow_result(self) -> ValidationResult:
        """Return an isolated fast-path allow result."""
        return ValidationResult(
            True,
            self._const_hash,
            [],
            self._rules_count,
            0.0,
            0,
            "",
            "",
            _ANON,
        )

    def _new_fast_result(
        self,
        *,
        valid: bool,
        violations: list[Violation],
        action: str,
    ) -> ValidationResult:
        """Return an isolated fast-path result.

        Fast-mode validation used to reuse mutable ValidationResult instances.
        That leaked state across repeated or concurrent validations because
        callers observed the same object reference. Returning a fresh object
        preserves fast-mode semantics without cross-request aliasing.
        """
        return ValidationResult(
            valid,
            self._const_hash,
            list(violations),
            self._rules_count,
            0.0,
            0,
            "",
            action[:500],
            _ANON,
        )

    def _runtime_active_rules(self, context: dict[str, Any] | None) -> list[Rule]:
        """Resolve rules that are currently enforceable for the given runtime context."""
        ctx = context or {}
        evaluation_time = self._resolve_runtime_evaluation_time(ctx)
        return [
            rule
            for rule in self.constitution.rules
            if rule.enabled
            and not rule.deprecated
            and rule.condition_matches(ctx)
            and rule.is_valid_at(evaluation_time)
        ]

    @staticmethod
    def _resolve_runtime_evaluation_time(context: dict[str, Any]) -> str:
        """Resolve the timestamp used for temporal rule activation."""
        for key in ("timestamp", "evaluation_time", "valid_at", "at"):
            value = context.get(key)
            if isinstance(value, str) and value:
                return value
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    def _validate_with_runtime_rule_filtering(
        self,
        action: str,
        *,
        agent_id: str,
        context: dict[str, Any] | None,
    ) -> ValidationResult:
        """Validate using per-call rule activation semantics.

        This path is intentionally slower than the hot path, but it preserves correct
        behavior for constitutions that use context-gated, deprecated, or time-bounded rules.
        """
        start = time.perf_counter()
        applicable_rules = self._runtime_active_rules(context)
        text_lower = action.lower()
        has_neg = bool(_NEGATIVE_VERBS_RE.search(text_lower))
        has_pos = (not has_neg) and any(w in _POSITIVE_VERBS_SET for w in text_lower.split()[:4])
        action_trimmed = action[:500]
        action_200 = action[:200]
        violations: list[Violation] = []

        for rule in applicable_rules:
            if rule.matches_with_signals(text_lower, has_neg, has_pos):
                violations.append(
                    Violation(
                        rule_id=rule.id,
                        rule_text=rule.text,
                        severity=rule.severity,
                        matched_content=action_200,
                        category=rule.category,
                    )
                )

        if context and ("action_detail" in context or "action_description" in context):
            for key, value in context.items():
                if key not in ("action_detail", "action_description") or not isinstance(value, str):
                    continue
                value_lower = value.lower()
                value_has_neg = bool(_NEGATIVE_VERBS_RE.search(value_lower))
                value_has_pos = (not value_has_neg) and any(
                    word in _POSITIVE_VERBS_SET for word in value_lower.split()[:4]
                )
                for rule in applicable_rules:
                    if rule.matches_with_signals(value_lower, value_has_neg, value_has_pos):
                        violations.append(
                            Violation(
                                rule_id=rule.id,
                                rule_text=rule.text,
                                severity=rule.severity,
                                matched_content=f"context[{key}]: {value[:100]}",
                                category=rule.category,
                            )
                        )

        if self.custom_validators and (
            not violations or not any(v.severity == Severity.CRITICAL for v in violations)
        ):
            ctx = context or {}
            for validator in self.custom_validators:
                try:
                    violations.extend(validator(action, ctx))
                except Exception as exc:
                    violations.append(
                        Violation(
                            "CUSTOM-ERROR",
                            f"Custom validator failed: {exc}",
                            Severity.HIGH,
                            action_200,
                            "validator-error",
                        )
                    )

        unique_violations = violations if len(violations) <= 1 else _dedup_violations(violations)
        blocking = [violation for violation in unique_violations if violation.severity.blocks()]
        if self.strict and blocking:
            violation = blocking[0]
            if self._fast_records is not None:
                self._fast_records.append(None)
            raise ConstitutionalViolationError(
                f"Action blocked by rule {violation.rule_id}: {violation.rule_text}",
                rule_id=violation.rule_id,
                severity=violation.severity.value,
                action=action_200,
            )

        valid = not bool(blocking)
        latency_ms = (time.perf_counter() - start) * 1000
        request_id = str(next(_request_counter))
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result = ValidationResult(
            valid=valid,
            constitutional_hash=self._const_hash,
            violations=unique_violations,
            rules_checked=len(applicable_rules),
            latency_ms=latency_ms,
            request_id=request_id,
            timestamp=timestamp,
            action=action_trimmed,
            agent_id=agent_id,
        )

        if self._fast_records is not None:
            self._fast_records.append(None)
        else:
            violation_rule_ids = {violation.rule_id for violation in unique_violations}
            rule_evaluations = []
            for rule in self.constitution.rules:
                active = rule in applicable_rules
                rule_evaluations.append(
                    {
                        "rule_id": rule.id,
                        "severity": rule.severity.value,
                        "evaluated": active,
                        "matched": rule.id in violation_rule_ids,
                        "reason": (
                            "violation"
                            if rule.id in violation_rule_ids
                            else "no_match"
                            if active
                            else "inactive"
                        ),
                    }
                )
            self.audit_log.record(
                AuditEntry(
                    id=request_id,
                    type="validation",
                    agent_id=agent_id,
                    action=action_trimmed,
                    valid=valid,
                    violations=[violation.rule_id for violation in unique_violations],
                    constitutional_hash=self._const_hash,
                    latency_ms=latency_ms,
                    timestamp=timestamp,
                    metadata={"rule_evaluations": rule_evaluations},
                )
            )

        return result

    def _validate_python_regex(
        self,
        action: str,
        strict: bool,
        text_lower: str,
        positive_verb_mode: bool,
        violations: list[Violation] | None,
    ) -> list[Violation] | None:
        action_200 = action[:200]
        if positive_verb_mode:
            kw_matches = self._neg_findall(text_lower)
            if kw_matches:
                fired = 0
                for kw in kw_matches:
                    for rule_idx, _ in self._kw_to_idxs.get(kw, []):
                        _bit = 1 << rule_idx
                        if fired & _bit:
                            continue
                        fired |= _bit
                        rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                        if strict and is_crit:
                            _e_src = self._rule_excs[rule_idx]
                            raise ConstitutionalViolationError(
                                str(_e_src),
                                rule_id=_e_src.rule_id,
                                severity=_e_src.severity,
                                action=action_200,
                            )
                        if violations is None:
                            violations = []
                        violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
                for rule_idx, pat in self._pattern_rule_idxs:
                    if not (fired & (1 << rule_idx)) and pat.search(text_lower):
                        fired |= 1 << rule_idx
                        rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                        if strict and is_crit:
                            _e_src = self._rule_excs[rule_idx]
                            raise ConstitutionalViolationError(
                                str(_e_src),
                                rule_id=_e_src.rule_id,
                                severity=_e_src.severity,
                                action=action_200,
                            )
                        if violations is None:
                            violations = []
                        violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
            elif self._pattern_rule_idxs:
                if self._pat_anchor_search is None or self._pat_anchor_search(text_lower):
                    for rule_idx, pat in self._pattern_rule_idxs:
                        if pat.search(text_lower):
                            rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                            if strict and is_crit:
                                _e_src = self._rule_excs[rule_idx]
                                raise ConstitutionalViolationError(
                                    str(_e_src),
                                    rule_id=_e_src.rule_id,
                                    severity=_e_src.severity,
                                    action=action_200,
                                )
                            if violations is None:
                                violations = []
                            violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
            return violations
        elif self._combined_findall is not None:
            _m = self._combined_search(text_lower)
            if _m:
                fired = 0
                kw0 = _m.group(0)
                for rule_idx, _ in self._kw_to_idxs.get(kw0, []):
                    fired |= 1 << rule_idx
                    rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                    if strict and is_crit:
                        _e_src = self._rule_excs[rule_idx]
                        raise ConstitutionalViolationError(
                            str(_e_src),
                            rule_id=_e_src.rule_id,
                            severity=_e_src.severity,
                            action=action_200,
                        )
                    if violations is None:
                        violations = []
                    violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
                if self._combined_search(text_lower, _m.end()) is not None:
                    for kw in self._combined_findall(text_lower):
                        for rule_idx, _ in self._kw_to_idxs.get(kw, []):
                            _bit = 1 << rule_idx
                            if fired & _bit:
                                continue
                            fired |= _bit
                            rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                            if strict and is_crit:
                                _e_src = self._rule_excs[rule_idx]
                                raise ConstitutionalViolationError(
                                    str(_e_src),
                                    rule_id=_e_src.rule_id,
                                    severity=_e_src.severity,
                                    action=action_200,
                                )
                            if violations is None:
                                violations = []
                            violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
                if self._pat_anchor_search is None or self._pat_anchor_search(text_lower):
                    for rule_idx, pat in self._pattern_rule_idxs:
                        if not (fired & (1 << rule_idx)) and pat.search(text_lower):
                            fired |= 1 << rule_idx
                            rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                            if strict and is_crit:
                                _e_src = self._rule_excs[rule_idx]
                                raise ConstitutionalViolationError(
                                    str(_e_src),
                                    rule_id=_e_src.rule_id,
                                    severity=_e_src.severity,
                                    action=action_200,
                                )
                            if violations is None:
                                violations = []
                            violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
            elif self._pattern_rule_idxs:
                if self._pat_anchor_search is None or self._pat_anchor_search(text_lower):
                    for rule_idx, pat in self._pattern_rule_idxs:
                        if pat.search(text_lower):
                            rid, rtxt, rsev, _, rcat, is_crit, _ = self._rule_data[rule_idx]
                            if strict and is_crit:
                                _e_src = self._rule_excs[rule_idx]
                                raise ConstitutionalViolationError(
                                    str(_e_src),
                                    rule_id=_e_src.rule_id,
                                    severity=_e_src.severity,
                                    action=action_200,
                                )
                            if violations is None:
                                violations = []
                            violations.append(Violation(rid, rtxt, rsev, action_200, rcat))
            return violations
        return violations

    def validate(
        self,
        action: str,
        *,
        agent_id: str = "anonymous",
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate an action against the constitution."""
        if self._requires_runtime_rule_filtering:
            return self._validate_with_runtime_rule_filtering(
                action,
                agent_id=agent_id,
                context=context,
            )
        strict = self.strict
        (
            _ac_iter,
            _anchor_dispatch,
            _no_anchor_pats,
            _rule_data,
            _rule_excs,
            _has_high,
            _fast_records,
            _pos_verbs,
            _has_ac,
            _is_noop,
            _rv,
        ) = self._hot
        if _rv is not None and _fast_records is not None and strict:
            _action_lower = action if action.islower() else action.lower()
            _decision, _data = _rv.validate_hot(_action_lower)
            _has_gov_ctx = context is not None and (
                "action_description" in context or "action_detail" in context
            )
            if _has_gov_ctx:
                _result = self._validate_rust_gov_context(
                    action,
                    _decision,
                    _data,
                    context,
                    _rule_excs,
                    _fast_records,
                )
                if _result is not None:
                    return _result
            else:
                _result = self._validate_rust_no_context(
                    action,
                    _decision,
                    _data,
                    _rule_excs,
                    _fast_records,
                )
                if _result is not None:
                    return _result
        elif _rv is not None and context and strict:
            _ctx_pairs = [
                (k, v)
                for k, v in context.items()
                if isinstance(v, str) and k in ("action_detail", "action_description")
            ]
            if not _ctx_pairs:
                _decision, _data = _rv.validate_hot(action.lower())
                _result = self._validate_rust_metadata_context(
                    action,
                    _decision,
                    _data,
                    _rule_excs,
                    _fast_records,
                    _is_noop,
                )
                if _result is not None:
                    return _result
            else:
                _result = self._validate_rust_full(
                    action,
                    strict,
                    _ctx_pairs,
                    _rule_excs,
                    _fast_records,
                )
                if _result is not None:
                    return _result
        start = time.perf_counter()
        violations = None
        action_trimmed = action[:500]
        action_200 = action[:200]

        text_lower = action.lower()
        _first_word, _, _ = text_lower.partition(" ")
        if _has_ac and _first_word in _pos_verbs:
            violations = self._validate_python_ac(
                action,
                strict,
                text_lower,
                True,
                violations,
            )
        elif _has_ac:
            violations = self._validate_python_ac(
                action,
                strict,
                text_lower,
                False,
                violations,
            )
        elif _first_word in _POSITIVE_VERBS_SET and self._neg_findall is not None:
            violations = self._validate_python_regex(
                action,
                strict,
                text_lower,
                True,
                violations,
            )
        elif self._combined_findall is not None:
            violations = self._validate_python_regex(
                action,
                strict,
                text_lower,
                False,
                violations,
            )

        if context and ("action_detail" in context or "action_description" in context):
            for key, value in context.items():
                if key in ("action_detail", "action_description") and isinstance(value, str):
                    val_lower = value.lower()
                    val_neg = bool(_NEGATIVE_VERBS_RE.search(val_lower))
                    val_pos = (not val_neg) and any(
                        w in _POSITIVE_VERBS_SET for w in val_lower.split()[:4]
                    )
                    for rule in self._active_rules:
                        if rule.matches_with_signals(val_lower, val_neg, val_pos):
                            if violations is None:
                                violations = []
                            violations.append(
                                Violation(
                                    rule_id=rule.id,
                                    rule_text=rule.text,
                                    severity=rule.severity,
                                    matched_content=f"context[{key}]: {value[:100]}",
                                    category=rule.category,
                                )
                            )

        if self.custom_validators and (
            not violations or not any(v.severity == Severity.CRITICAL for v in violations)
        ):
            ctx = context or {}
            for validator in self.custom_validators:
                try:
                    custom_violations = validator(action, ctx)
                    if violations is None:
                        violations = []
                    violations.extend(custom_violations)
                except Exception as e:
                    if violations is None:
                        violations = []
                    violations.append(
                        Violation(
                            "CUSTOM-ERROR",
                            f"Custom validator failed: {e}",
                            Severity.HIGH,
                            action_200,
                            "validator-error",
                        )
                    )

        if violations is None:
            if _fast_records is not None:
                _fast_records.append(None)
                return self._new_fast_allow_result()
            request_id = next(_request_counter)
            latency_ms = (time.perf_counter() - start) * 1000
            now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            result = ValidationResult(
                True,
                self._const_hash,
                [],
                self._rules_count,
                latency_ms,
                request_id,
                now_ts,
                action_trimmed,
                agent_id,
            )
            rule_evaluations = []
            for rule in self.constitution.rules:
                rule_evaluations.append(
                    {
                        "rule_id": rule.id,
                        "severity": rule.severity.value,
                        "evaluated": True,
                        "matched": False,
                        "reason": "no_violation",
                    }
                )

            self.audit_log.record(
                AuditEntry(
                    id=request_id,
                    type="validation",
                    agent_id=agent_id,
                    action=action_trimmed,
                    valid=True,
                    violations=[],
                    constitutional_hash=self._const_hash,
                    latency_ms=latency_ms,
                    timestamp=now_ts,
                    metadata={"rule_evaluations": rule_evaluations},
                )
            )
            return result

        unique_violations = violations if len(violations) == 1 else _dedup_violations(violations)

        if _has_high or not strict:
            blocking = [v for v in unique_violations if v.severity.blocks()]
            if strict and blocking:
                violation = blocking[0]
                raise ConstitutionalViolationError(
                    f"Action blocked by rule {violation.rule_id}: {violation.rule_text}",
                    rule_id=violation.rule_id,
                    severity=violation.severity.value,
                    action=action_200,
                )
            valid = not bool(blocking)
        else:
            valid = True

        if _fast_records is not None:
            _fast_records.append(None)
            return self._new_fast_result(valid=valid, violations=unique_violations, action=action)

        request_id = next(_request_counter)
        latency_ms = (time.perf_counter() - start) * 1000

        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result = ValidationResult(
            valid=valid,
            constitutional_hash=self._const_hash,
            violations=unique_violations,
            rules_checked=self._rules_count,
            latency_ms=latency_ms,
            request_id=request_id,
            timestamp=now_ts,
            action=action_trimmed,
            agent_id=agent_id,
        )

        rule_evaluations = []
        violation_rule_ids = {v.rule_id for v in unique_violations}

        for rule in self.constitution.rules:
            rule_evaluations.append(
                {
                    "rule_id": rule.id,
                    "severity": rule.severity.value,
                    "evaluated": True,
                    "matched": rule.id in violation_rule_ids,
                    "reason": "violation" if rule.id in violation_rule_ids else "no_match",
                }
            )

        self.audit_log.record(
            AuditEntry(
                id=str(request_id),
                type="validation",
                agent_id=agent_id,
                action=action_trimmed,
                valid=valid,
                violations=[v.rule_id for v in unique_violations],
                constitutional_hash=self._const_hash,
                latency_ms=result.latency_ms,
                timestamp=now_ts,
                metadata={"rule_evaluations": rule_evaluations},
            )
        )

        return result

    def add_validator(self, validator: CustomValidator) -> None:
        """Register a custom validator function."""
        self.custom_validators.append(validator)

    @property
    def audit_mode(self) -> str:
        """Current audit mode: 'fast' (aggregate-only) or 'full' (durable log)."""
        return self._audit_mode

    @property
    def stats(self) -> dict[str, Any]:
        """Return engine statistics."""
        if isinstance(self._fast_records, _NoopRecorder):
            total = len(self._fast_records)
            return {
                "total_validations": total,
                "compliance_rate": None,
                "rules_count": len(self.constitution.rules),
                "constitutional_hash": self._const_hash,
                "avg_latency_ms": None,
                "audit_mode": self.audit_mode,
                "audit_entry_count": 0,
                "audit_metrics_complete": False,
            }
        entries = self.audit_log.entries
        total = len(entries)
        valid_count = sum(1 for e in entries if e.valid)
        return {
            "total_validations": total,
            "compliance_rate": valid_count / total if total > 0 else 1.0,
            "rules_count": len(self.constitution.rules),
            "constitutional_hash": self._const_hash,
            "avg_latency_ms": (sum(e.latency_ms for e in entries) / total if total > 0 else 0.0),
            "audit_mode": self.audit_mode,
            "audit_entry_count": total,
            "audit_metrics_complete": True,
        }


__all__ = [
    "CustomValidator",
    "GovernanceEngine",
    "Severity",
    "ValidationResult",
    "Violation",
    "_ANON",
    "_FastAuditLog",
    "_NoopRecorder",
    "_dedup_violations",
    "_request_counter",
]
