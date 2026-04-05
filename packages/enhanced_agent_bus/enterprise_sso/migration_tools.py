"""
Decision Log Import and Shadow Mode Migration Tools
Constitutional Hash: 608508a9bd224290

Phase 10 Task 9: Decision Log Import and Shadow Mode

Provides:
- CSV decision log import with schema mapping
- Duplicate detection and merging
- Shadow mode parallel execution
- Agreement rate metrics collection
- Gradual traffic routing (0% → 100%)
- Automatic rollback on error threshold breach
"""

import asyncio
import csv
import inspect
import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

MIGRATION_IMPORT_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    OSError,
)

# ============================================================================
# Enums
# ============================================================================


class ImportStatus(Enum):
    """Status of an import job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DecisionSource(Enum):
    """Source of a decision."""

    LEGACY = "legacy"
    ACGS2 = "acgs2"
    IMPORTED = "imported"


class ShadowModeState(Enum):
    """Shadow mode operational state."""

    DISABLED = "disabled"
    SHADOW_ONLY = "shadow_only"  # Legacy active, ACGS-2 shadow
    SPLIT = "split"  # Traffic split between systems
    ACTIVE = "active"  # ACGS-2 active, legacy shadow


class AgreementStatus(Enum):
    """Agreement status between systems."""

    MATCH = "match"
    MISMATCH = "mismatch"
    LEGACY_ERROR = "legacy_error"
    ACGS2_ERROR = "acgs2_error"
    TIMEOUT = "timeout"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SchemaMapping:
    """Mapping between legacy CSV columns and ACGS-2 fields."""

    source_column: str
    target_field: str
    transform: Callable[[str], object] | None = None
    required: bool = False
    default: object = None


@dataclass
class ImportedDecision:
    """A decision imported from legacy logs."""

    import_id: str
    original_id: str
    timestamp: datetime
    action: str
    resource: str
    decision: str  # allow/deny
    actor: str | None = None
    context: dict = field(default_factory=dict)
    source_row: int = 0
    duplicate_of: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ImportResult:
    """Result of a decision log import."""

    import_id: str
    status: ImportStatus
    total_rows: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    errors: list = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ShadowDecisionResult:
    """Result of a shadow mode decision comparison."""

    request_id: str
    legacy_decision: str | None = None
    legacy_latency_ms: float | None = None
    acgs2_decision: str | None = None
    acgs2_latency_ms: float | None = None
    agreement: AgreementStatus = AgreementStatus.MATCH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ShadowModeMetrics:
    """Aggregated metrics for shadow mode."""

    total_requests: int = 0
    matches: int = 0
    mismatches: int = 0
    legacy_errors: int = 0
    acgs2_errors: int = 0
    timeouts: int = 0
    average_legacy_latency_ms: float = 0.0
    average_acgs2_latency_ms: float = 0.0
    agreement_rate: float = 0.0
    window_start: datetime | None = None
    window_end: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class TrafficConfig:
    """Traffic routing configuration."""

    tenant_id: str
    acgs2_percentage: float = 0.0  # 0.0 to 100.0
    error_threshold: float = 5.0  # Rollback if error rate exceeds this
    min_samples: int = 100  # Minimum samples before auto-adjustment
    auto_rollback: bool = True
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ============================================================================
# Implementation Classes
# ============================================================================


class DecisionLogImporter:
    """Imports decision logs from CSV files."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._imported_decisions: dict[str, ImportedDecision] = {}
        self._import_results: dict[str, ImportResult] = {}

    async def import_csv(
        self,
        csv_content: str,
        mappings: list[SchemaMapping],
        tenant_id: str,
        detect_duplicates: bool = True,
    ) -> ImportResult:
        """Import decisions from CSV content."""
        import_id = str(uuid.uuid4())
        result = ImportResult(
            import_id=import_id, status=ImportStatus.RUNNING, start_time=datetime.now(UTC)
        )

        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            row_num = 0

            for row in reader:
                row_num += 1
                result.total_rows = row_num

                try:
                    decision = self._map_row_to_decision(row, mappings, import_id, row_num)

                    # Check for duplicates
                    if detect_duplicates:
                        duplicate = self._find_duplicate(decision)
                        if duplicate:
                            decision.duplicate_of = duplicate.import_id
                            result.duplicate_count += 1
                            continue

                    self._imported_decisions[decision.import_id] = decision
                    result.imported_count += 1

                except ValueError as e:
                    result.error_count += 1
                    result.errors.append({"row": row_num, "error": str(e)})

            result.status = ImportStatus.COMPLETED

        except MIGRATION_IMPORT_ERRORS as e:
            result.status = ImportStatus.FAILED
            result.errors.append({"error": str(e)})

        result.end_time = datetime.now(UTC)
        self._import_results[import_id] = result
        return result

    def _map_row_to_decision(
        self, row: dict, mappings: list[SchemaMapping], import_id: str, row_num: int
    ) -> ImportedDecision:
        """Map a CSV row to an ImportedDecision."""
        mapped_values = {}

        for mapping in mappings:
            value = row.get(mapping.source_column)

            if value is None or value == "":
                if mapping.required:
                    raise ValueError(f"Required field {mapping.source_column} is missing")
                value = mapping.default
            elif mapping.transform:
                value = mapping.transform(value)

            mapped_values[mapping.target_field] = value

        return ImportedDecision(
            import_id=f"{import_id}:{row_num}",
            original_id=mapped_values.get("original_id", str(row_num)),
            timestamp=mapped_values.get("timestamp", datetime.now(UTC)),
            action=mapped_values.get("action", "unknown"),
            resource=mapped_values.get("resource", "unknown"),
            decision=mapped_values.get("decision", "deny"),
            actor=mapped_values.get("actor"),
            context=mapped_values.get("context", {}),
            source_row=row_num,
            constitutional_hash=self.constitutional_hash,
        )

    def _find_duplicate(self, decision: ImportedDecision) -> ImportedDecision | None:
        """Find a duplicate decision based on key fields."""
        for existing in self._imported_decisions.values():
            if (
                existing.original_id == decision.original_id
                and existing.timestamp == decision.timestamp
                and existing.action == decision.action
                and existing.resource == decision.resource
            ):
                return existing
        return None

    def get_import_result(self, import_id: str) -> ImportResult | None:
        """Get result of an import job."""
        return self._import_results.get(import_id)

    def get_imported_decisions(self, import_id: str) -> list[ImportedDecision]:
        """Get all decisions from a specific import."""
        prefix = f"{import_id}:"
        return [d for d in self._imported_decisions.values() if d.import_id.startswith(prefix)]


class ShadowModeExecutor:
    """Executes decisions in shadow mode for comparison."""

    def __init__(
        self,
        legacy_evaluator: Callable,
        acgs2_evaluator: Callable,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.legacy_evaluator = legacy_evaluator
        self.acgs2_evaluator = acgs2_evaluator
        self.constitutional_hash = constitutional_hash
        self._results: list[ShadowDecisionResult] = []
        self._state = ShadowModeState.DISABLED

    async def execute_shadow(
        self, request_id: str, action: str, resource: str, context: dict
    ) -> ShadowDecisionResult:
        """Execute decision on both systems and compare."""
        result = ShadowDecisionResult(
            request_id=request_id, constitutional_hash=self.constitutional_hash
        )

        # Execute on legacy system
        try:
            start = datetime.now(UTC)
            result.legacy_decision = await self._execute_legacy(action, resource, context)
            result.legacy_latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        except (RuntimeError, ValueError, ConnectionError, TimeoutError):
            result.agreement = AgreementStatus.LEGACY_ERROR

        # Execute on ACGS-2
        try:
            start = datetime.now(UTC)
            result.acgs2_decision = await self._execute_acgs2(action, resource, context)
            result.acgs2_latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        except (RuntimeError, ValueError, ConnectionError, TimeoutError):
            if result.agreement == AgreementStatus.LEGACY_ERROR:
                pass  # Keep legacy error
            else:
                result.agreement = AgreementStatus.ACGS2_ERROR

        # Compare results
        if result.agreement not in (AgreementStatus.LEGACY_ERROR, AgreementStatus.ACGS2_ERROR):
            if result.legacy_decision == result.acgs2_decision:
                result.agreement = AgreementStatus.MATCH
            else:
                result.agreement = AgreementStatus.MISMATCH

        self._results.append(result)
        return result

    async def _execute_legacy(self, action: str, resource: str, context: dict) -> str:
        """Execute on legacy system."""
        if inspect.iscoroutinefunction(self.legacy_evaluator):
            return await self.legacy_evaluator(action, resource, context)  # type: ignore[no-any-return]
        return self.legacy_evaluator(action, resource, context)  # type: ignore[no-any-return]

    async def _execute_acgs2(self, action: str, resource: str, context: dict) -> str:
        """Execute on ACGS-2 system."""
        if inspect.iscoroutinefunction(self.acgs2_evaluator):
            return await self.acgs2_evaluator(action, resource, context)  # type: ignore[no-any-return]
        return self.acgs2_evaluator(action, resource, context)  # type: ignore[no-any-return]

    def get_metrics(
        self, window_start: datetime | None = None, window_end: datetime | None = None
    ) -> ShadowModeMetrics:
        """Calculate aggregated metrics for a time window."""
        window_start = window_start or datetime.min.replace(tzinfo=UTC)
        window_end = window_end or datetime.now(UTC)

        filtered = [r for r in self._results if window_start <= r.timestamp <= window_end]

        if not filtered:
            return ShadowModeMetrics(
                window_start=window_start,
                window_end=window_end,
                constitutional_hash=self.constitutional_hash,
            )

        metrics = ShadowModeMetrics(
            total_requests=len(filtered),
            matches=sum(1 for r in filtered if r.agreement == AgreementStatus.MATCH),
            mismatches=sum(1 for r in filtered if r.agreement == AgreementStatus.MISMATCH),
            legacy_errors=sum(1 for r in filtered if r.agreement == AgreementStatus.LEGACY_ERROR),
            acgs2_errors=sum(1 for r in filtered if r.agreement == AgreementStatus.ACGS2_ERROR),
            timeouts=sum(1 for r in filtered if r.agreement == AgreementStatus.TIMEOUT),
            window_start=window_start,
            window_end=window_end,
            constitutional_hash=self.constitutional_hash,
        )

        # Calculate latencies
        legacy_latencies = [
            r.legacy_latency_ms for r in filtered if r.legacy_latency_ms is not None
        ]
        acgs2_latencies = [r.acgs2_latency_ms for r in filtered if r.acgs2_latency_ms is not None]

        if legacy_latencies:
            metrics.average_legacy_latency_ms = sum(legacy_latencies) / len(legacy_latencies)
        if acgs2_latencies:
            metrics.average_acgs2_latency_ms = sum(acgs2_latencies) / len(acgs2_latencies)

        # Calculate agreement rate
        valid_comparisons = metrics.matches + metrics.mismatches
        if valid_comparisons > 0:
            metrics.agreement_rate = (metrics.matches / valid_comparisons) * 100.0

        return metrics

    def set_state(self, state: ShadowModeState) -> None:
        """Set the shadow mode state."""
        self._state = state

    def get_state(self) -> ShadowModeState:
        """Get the current shadow mode state."""
        return self._state


class TrafficRouter:
    """Routes traffic between legacy and ACGS-2 systems."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._configs: dict[str, TrafficConfig] = {}
        self._request_counts: dict[str, int] = {}
        self._error_counts: dict[str, int] = {}

    def configure_tenant(
        self,
        tenant_id: str,
        acgs2_percentage: float = 0.0,
        error_threshold: float = 5.0,
        min_samples: int = 100,
        auto_rollback: bool = True,
    ) -> TrafficConfig:
        """Configure traffic routing for a tenant."""
        config = TrafficConfig(
            tenant_id=tenant_id,
            acgs2_percentage=max(0.0, min(100.0, acgs2_percentage)),
            error_threshold=error_threshold,
            min_samples=min_samples,
            auto_rollback=auto_rollback,
            constitutional_hash=self.constitutional_hash,
        )
        self._configs[tenant_id] = config
        self._request_counts[tenant_id] = 0
        self._error_counts[tenant_id] = 0
        return config

    def route_request(self, tenant_id: str, request_id: str) -> str:
        """Route a request to either legacy or ACGS-2."""
        config = self._configs.get(tenant_id)
        if not config:
            return "legacy"  # Default to legacy

        # Check for auto-rollback
        if config.auto_rollback and self._should_rollback(tenant_id):
            config.acgs2_percentage = 0.0
            return "legacy"

        # Deterministic routing based on request_id hash
        self._request_counts[tenant_id] = self._request_counts.get(tenant_id, 0) + 1
        hash_value = hash(request_id) % 100

        if hash_value < config.acgs2_percentage:
            return "acgs2"
        return "legacy"

    def record_error(self, tenant_id: str, system: str) -> None:
        """Record an error for a system."""
        if system == "acgs2":
            self._error_counts[tenant_id] = self._error_counts.get(tenant_id, 0) + 1

    def _should_rollback(self, tenant_id: str) -> bool:
        """Check if we should rollback to legacy."""
        config = self._configs.get(tenant_id)
        if not config:
            return False

        request_count = self._request_counts.get(tenant_id, 0)
        error_count = self._error_counts.get(tenant_id, 0)

        if request_count < config.min_samples:
            return False

        error_rate = (error_count / request_count) * 100.0
        return error_rate > config.error_threshold

    def get_config(self, tenant_id: str) -> TrafficConfig | None:
        """Get traffic configuration for a tenant."""
        return self._configs.get(tenant_id)

    def update_percentage(self, tenant_id: str, new_percentage: float) -> TrafficConfig:
        """Update the ACGS-2 traffic percentage."""
        config = self._configs.get(tenant_id)
        if not config:
            return self.configure_tenant(tenant_id, new_percentage)

        config.acgs2_percentage = max(0.0, min(100.0, new_percentage))
        config.last_updated = datetime.now(UTC)
        return config

    def get_error_rate(self, tenant_id: str) -> float:
        """Get current error rate for a tenant."""
        request_count = self._request_counts.get(tenant_id, 0)
        error_count = self._error_counts.get(tenant_id, 0)

        if request_count == 0:
            return 0.0
        return (error_count / request_count) * 100.0
