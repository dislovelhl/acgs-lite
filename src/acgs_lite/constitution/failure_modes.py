"""Typed failure-mode catalog and stabilizer protocol.

A *Semantic Stabilizer* is an executable consistency check between two artifacts
that emits a binary {pass, fail} bit. Each evaluation produces a
``StabilizerRecord`` that can be persisted to the audit ledger and (optionally)
emitted as a Prometheus counter increment.

This module is the foundation for F1 (Systematic Error Modelling) from the
QEC-vs-ACGS research and the input contract for F4 (Degeneracy in Correction):
F4's clusterer consumes the ``syndrome_vector`` produced by the catalog.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Protocol, runtime_checkable


class StabilizerOutcome(str, Enum):
    """Binary outcome of a stabilizer evaluation."""

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class StabilizerResult:
    """Single outcome of a stabilizer evaluation.

    Built before persistence; convert to a ``StabilizerRecord`` via
    ``to_record()`` when emitting to the catalog or audit ledger.
    """

    stabilizer_id: str
    outcome: StabilizerOutcome
    evidence: Mapping[str, Any] = field(default_factory=dict)
    rule_id: str | None = None

    def to_record(self) -> StabilizerRecord:
        """Convert to a persistable ``StabilizerRecord``."""
        return StabilizerRecord(
            stabilizer_id=self.stabilizer_id,
            outcome=self.outcome,
            emitted_at=datetime.now(timezone.utc),
            evidence=dict(self.evidence),
            rule_id=self.rule_id,
        )


@dataclass(frozen=True, slots=True)
class StabilizerRecord:
    """Durable record of a stabilizer evaluation outcome.

    Failure modes are typed by *which stabilizer fired*, giving F1 a
    deterministic, sourceable label without depending on hand-curated
    categories.
    """

    stabilizer_id: str
    outcome: StabilizerOutcome
    emitted_at: datetime
    evidence: Mapping[str, Any] = field(default_factory=dict)
    rule_id: str | None = None

    AUDIT_ENTRY_TYPE_PASS: ClassVar[str] = "stabilizer"
    AUDIT_ENTRY_TYPE_FAIL: ClassVar[str] = "failure_mode"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "stabilizer_id": self.stabilizer_id,
            "outcome": self.outcome.value,
            "emitted_at": self.emitted_at.isoformat(),
            "evidence": dict(self.evidence),
            "rule_id": self.rule_id,
        }

    def to_audit_entry_payload(self) -> dict[str, Any]:
        """Build an ``AuditEntry``-compatible kwargs payload.

        Caller still supplies ``id`` and ``agent_id`` when constructing the
        final ``AuditEntry``. The chosen ``type`` differentiates pass
        ("stabilizer") from fail ("failure_mode") so audit-log queries can
        filter on the failing subset directly.
        """
        is_pass = self.outcome == StabilizerOutcome.PASS
        return {
            "type": self.AUDIT_ENTRY_TYPE_PASS if is_pass else self.AUDIT_ENTRY_TYPE_FAIL,
            "valid": is_pass,
            "violations": [] if is_pass else [self.stabilizer_id],
            "metadata": {
                "stabilizer_id": self.stabilizer_id,
                "outcome": self.outcome.value,
                "evidence": dict(self.evidence),
                "rule_id": self.rule_id,
            },
        }


@runtime_checkable
class Stabilizer(Protocol):
    """Cross-representation consistency check producing a binary bit.

    Each implementation defines its own typed inputs via ``**kwargs`` on
    ``evaluate()``. Stabilizers are stateless and side-effect-free; emission
    to the catalog is the caller's responsibility (or a helper such as
    ``emit_from_fuzz_report``).
    """

    id: ClassVar[str]

    def evaluate(self, **kwargs: Any) -> StabilizerResult:
        """Evaluate the consistency check; return a binary outcome with evidence."""
        ...


class FailureModeCatalog:
    """Append-only catalog of stabilizer evaluation outcomes.

    Stabilizers are registered up-front; results are emitted as they arrive.
    Optionally bridges to an ``AuditLog`` for durable persistence and to a
    metrics collector (duck-typed) for Prometheus emission.

    Thread-safety: emission is not lock-guarded by default. Wrap calls in an
    external lock if multi-threaded emission is required; this matches the
    convention used by ``GovernanceDriftDetector`` in this package.
    """

    __slots__ = ("_records", "_stabilizers", "_audit_log", "_metrics_collector")

    def __init__(
        self,
        *,
        audit_log: Any | None = None,
        metrics_collector: Any | None = None,
    ) -> None:
        self._records: list[StabilizerRecord] = []
        self._stabilizers: dict[str, Stabilizer] = {}
        self._audit_log = audit_log
        self._metrics_collector = metrics_collector

    def register(self, stabilizer: Stabilizer) -> None:
        """Register a stabilizer by its id. Re-registering the same id replaces."""
        self._stabilizers[stabilizer.id] = stabilizer

    @property
    def registered_ids(self) -> tuple[str, ...]:
        """Tuple of registered stabilizer ids in insertion order."""
        return tuple(self._stabilizers.keys())

    def get(self, stabilizer_id: str) -> Stabilizer | None:
        """Look up a registered stabilizer by id."""
        return self._stabilizers.get(stabilizer_id)

    def emit(self, result: StabilizerResult, *, agent_id: str = "") -> StabilizerRecord:
        """Persist a stabilizer evaluation outcome.

        Appends to the catalog, optionally records to ``AuditLog``, optionally
        increments the Prometheus counter via ``record_stabilizer_result``.
        Returns the materialized ``StabilizerRecord``.
        """
        record = result.to_record()
        self._records.append(record)

        if self._audit_log is not None:
            self._record_to_audit_log(record, agent_id=agent_id)

        if self._metrics_collector is not None:
            self._record_to_metrics(record)

        return record

    def latest(self, n: int = 100) -> list[StabilizerRecord]:
        """Return the most recent ``n`` records (newest last)."""
        return list(self._records[-n:])

    def by_stabilizer(self, stabilizer_id: str) -> list[StabilizerRecord]:
        """Return all records for a given stabilizer id, in insertion order."""
        return [r for r in self._records if r.stabilizer_id == stabilizer_id]

    def syndrome_vector(self) -> dict[str, StabilizerOutcome | None]:
        """Most recent outcome per registered stabilizer (None if never emitted).

        This is the *Semantic Syndrome* vector input that F4's clusterer
        will consume — one bit per registered stabilizer.
        """
        latest_by_id: dict[str, StabilizerOutcome] = {}
        for r in reversed(self._records):
            if r.stabilizer_id not in latest_by_id:
                latest_by_id[r.stabilizer_id] = r.outcome
        return {sid: latest_by_id.get(sid) for sid in self._stabilizers}

    def clear(self) -> None:
        """Clear all accumulated records."""
        self._records.clear()

    def _record_to_audit_log(self, record: StabilizerRecord, *, agent_id: str) -> None:
        """Write the record as an ``AuditEntry``."""
        # Lazy: avoid coupling constitution/ to audit at module load time —
        # audit is the higher-level layer that may depend on constitution
        # primitives, never the reverse.
        assert self._audit_log is not None
        from acgs_lite.audit import AuditEntry  # noqa: PLC0415

        payload = record.to_audit_entry_payload()
        entry = AuditEntry(
            id=f"stabilizer-{record.stabilizer_id}-{record.emitted_at.timestamp():.6f}",
            agent_id=agent_id,
            **payload,
        )
        self._audit_log.record(entry)

    def _record_to_metrics(self, record: StabilizerRecord) -> None:
        """Increment the Prometheus stabilizer-results counter (if collector wired)."""
        # PR-B wires enhanced_agent_bus here; duck-typed to keep constitution/ dependency-free.
        recorder = getattr(self._metrics_collector, "record_stabilizer_result", None)
        if recorder is not None:
            recorder(record.stabilizer_id, record.outcome.value)


def emit_from_fuzz_report(
    *,
    catalog: FailureModeCatalog,
    fuzz_report: Any,
    eval_report: Any,
    stabilizer_id: str = "S_test_fixture",
    agent_id: str = "",
) -> int:
    """Run a stabilizer over each rule implicated by suspected bypasses.

    "Implicated rule" here means the rule the fuzz case **targeted**
    (``FuzzCase.rule_id``) — the rule that should have fired but did not.
    Rules that incidentally fired during the bypass attempt
    (``FuzzCase.violations``) are intentionally NOT emitted; F4's clusterer
    consumes the targeted-rule signal as the deterministic input contract.

    For every distinct targeted rule id, look up the rule's metrics in
    ``eval_report.rule_metrics`` (keys are canonicalised to upper-case)
    and emit one stabilizer evaluation. Returns the number of records emitted.

    A no-op (returns 0) if the stabilizer is not registered or no suspected
    bypass targets a rule with metrics in the eval report.
    """
    stabilizer = catalog.get(stabilizer_id)
    if stabilizer is None:
        return 0

    seen: set[str] = set()
    emitted = 0
    for case in getattr(fuzz_report, "suspected_bypasses", []):
        rule_id = getattr(case, "rule_id", None)
        if not rule_id:
            continue
        normalized = rule_id.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        if normalized not in getattr(eval_report, "rule_metrics", {}):
            continue
        result = stabilizer.evaluate(rule_id=normalized, eval_report=eval_report)
        catalog.emit(result, agent_id=agent_id)
        emitted += 1
    return emitted
