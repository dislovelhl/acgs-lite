"""
Data Sync Engine and Scheduler
Constitutional Hash: 608508a9bd224290

Provides the DataSyncEngine for orchestrating data synchronization
between source and target warehouses, and SyncScheduler for
automated cron-based sync jobs.
"""

import asyncio
import hashlib
import re
from datetime import UTC, datetime, timezone

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .connectors import DataWarehouseConnector, create_connector
from .models import (
    ScheduleConfig,
    SyncConfig,
    SyncMode,
    SyncResult,
    SyncStatus,
    WarehouseConfig,
    Watermark,
)
from .schema_evolution import SchemaEvolutionManager
from .watermark import WatermarkManager

SYNC_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


class DataSyncEngine:
    """Engine for orchestrating data synchronization."""

    _IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*){0,2}$")
    _UNSAFE_FILTER_TOKENS = (
        ";",
        "--",
        "/*",
        "*/",
        " drop ",
        " alter ",
        " insert ",
        " update ",
        " delete ",
        " truncate ",
        " create ",
        " grant ",
        " revoke ",
    )

    def __init__(
        self,
        source_connector: DataWarehouseConnector,
        target_connector: DataWarehouseConnector,
    ):
        """Initialize sync engine."""
        self.source = source_connector
        self.target = target_connector
        self.watermark_manager = WatermarkManager()
        self.schema_manager = SchemaEvolutionManager(target_connector)
        self._running_syncs: dict[str, SyncResult] = {}
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def sync_table(self, config: SyncConfig) -> SyncResult:
        """Synchronize a table from source to target."""
        sync_id = hashlib.sha256(
            f"{config.source_table}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        result = SyncResult(
            sync_id=sync_id,
            status=SyncStatus.RUNNING,
            source_table=config.source_table,
            target_table=config.target_table,
            started_at=datetime.now(UTC),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        self._running_syncs[sync_id] = result

        try:
            # Get watermark if incremental
            watermark = None
            if config.sync_mode == SyncMode.INCREMENTAL:
                watermark = self.watermark_manager.get_watermark(config.source_table)
                if watermark is None and config.watermark_column:
                    watermark = self.watermark_manager.create_watermark(
                        config.source_table, config.watermark_column
                    )

            # Build query
            query, query_params = self._build_sync_query(config, watermark)

            # Execute sync
            source_data = await self.source.execute_query(query, query_params or None)
            result.rows_processed = len(source_data)

            if source_data:
                # Apply transformations
                if config.transform_fn:
                    source_data = [config.transform_fn(row) for row in source_data]

                # Apply column mapping
                if config.column_mapping:
                    source_data = self._apply_column_mapping(source_data, config.column_mapping)

                # Insert into target
                target_table = self._validate_identifier(config.target_table, "target_table")
                rows_inserted = await self.target.execute_batch(
                    f"INSERT INTO {target_table} VALUES (%s)",  # nosec B608
                    source_data,
                    config.batch_size,
                )
                result.rows_inserted = rows_inserted

                # Update watermark
                if watermark and isinstance(last_row := source_data[-1], dict):
                    if last_value := last_row.get(config.watermark_column):
                        result.watermark = self.watermark_manager.update_watermark(
                            config.source_table,
                            last_value,
                            len(source_data),
                            sync_id,
                        )

            result.status = SyncStatus.COMPLETED
            result.completed_at = datetime.now(UTC)

        except SYNC_EXECUTION_ERRORS as e:
            result.status = SyncStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(UTC)

        return result

    def _validate_identifier(self, value: str, field_name: str) -> str:
        """Validate SQL identifiers to prevent injection via table/column names."""
        if not self._IDENTIFIER_RE.fullmatch(value):
            raise ACGSValidationError(
                f"Invalid SQL identifier for {field_name}: {value!r}",
                error_code="DW_INVALID_SQL_IDENTIFIER",
            )
        return value

    _SAFE_LITERAL = r"(?:'[^']*'|\d+(?:\.\d+)?|NULL|TRUE|FALSE)"
    _SAFE_FILTER_CLAUSE_RE = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_.]*"
        r"\s+"
        r"(?:=|!=|<>|<=?|>=?|(?:NOT\s+)?LIKE|(?:NOT\s+)?IN|IS(?:\s+NOT)?\s+NULL)"
        r"(?:"
        r"\s+"
        + _SAFE_LITERAL
        + r"|\s*\(\s*"
        + _SAFE_LITERAL
        + r"(?:\s*,\s*"
        + _SAFE_LITERAL
        + r")*\s*\)"
        r")?"
        r"$",
        re.IGNORECASE,
    )

    def _validate_filter_condition(self, condition: str) -> str:
        """Validate filter condition against SQL injection using restricted grammar.

        Accepts only simple ``<column> <op> <literal>`` clauses joined by ``AND``.
        The blocklist is kept as a defence-in-depth secondary check.
        """
        # Defence-in-depth: blocklist first
        lowered = f" {condition.lower()} "
        if any(token in lowered for token in self._UNSAFE_FILTER_TOKENS):
            raise ACGSValidationError(
                "Unsafe filter_condition detected",
                error_code="DW_UNSAFE_FILTER",
            )

        # Grammar check: split on AND, validate each clause individually
        clauses = re.split(r"\s+AND\s+", condition.strip(), flags=re.IGNORECASE)
        for clause in clauses:
            stripped = clause.strip()
            if not stripped:
                raise ACGSValidationError(
                    "Empty clause in filter_condition",
                    error_code="DW_EMPTY_FILTER_CLAUSE",
                )
            if not self._SAFE_FILTER_CLAUSE_RE.fullmatch(stripped):
                raise ACGSValidationError(
                    f"Filter clause does not match allowed grammar: {stripped!r}",
                    error_code="DW_INVALID_FILTER_GRAMMAR",
                )
            if col_match := re.match(r"^([A-Za-z_][A-Za-z0-9_.]*)", stripped):
                self._validate_identifier(col_match.group(1), "filter_column")
        return condition

    def _build_sync_query(
        self,
        config: SyncConfig,
        watermark: Watermark | None,
    ) -> tuple[str, JSONDict]:
        """Build the sync query and bound parameters based on configuration."""
        source_table = self._validate_identifier(config.source_table, "source_table")
        query = f"SELECT * FROM {source_table}"  # nosec B608
        params: JSONDict = {}

        conditions: list[str] = []
        if filter_condition := config.filter_condition:
            conditions.append(self._validate_filter_condition(filter_condition))

        if config.sync_mode == SyncMode.INCREMENTAL and watermark and watermark.last_value:
            watermark_column = self._validate_identifier(watermark.column_name, "watermark_column")
            conditions.append(f"{watermark_column} > %(watermark)s")
            params["watermark"] = watermark.last_value

        if conditions:
            query = f"{query} WHERE {' AND '.join(conditions)}"

        if watermark:
            query += " ORDER BY " + self._validate_identifier(
                watermark.column_name,
                "watermark_column",
            )

        return query, params

    def _apply_column_mapping(self, data: list, mapping: dict) -> list:
        """Apply column mapping to data."""
        return [
            {tgt_col: row[src_col] for src_col, tgt_col in mapping.items() if src_col in row}
            if isinstance(row, dict)
            else row
            for row in data
        ]

    async def check_schema_compatibility(self, config: SyncConfig) -> dict:
        """Check if source and target schemas are compatible."""
        source_schema = await self.source.get_table_schema(config.source_table)
        target_schema = await self.target.get_table_schema(config.target_table)

        changes = await self.schema_manager.detect_changes(source_schema, target_schema)

        return {
            "compatible": len(changes) == 0,
            "source_schema": source_schema,
            "target_schema": target_schema,
            "required_changes": [c.to_dict() for c in changes],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def evolve_schema(self, config: SyncConfig, dry_run: bool = False) -> list:
        """Apply schema evolution to make target compatible with source."""
        compatibility = await self.check_schema_compatibility(config)
        if compatibility["compatible"]:
            return []

        return await self.schema_manager.apply_changes(dry_run=dry_run)

    def get_sync_status(self, sync_id: str) -> SyncResult | None:
        """Get status of a sync operation."""
        return self._running_syncs.get(sync_id)

    def list_syncs(self) -> list[SyncResult]:
        """List all sync operations."""
        return list(self._running_syncs.values())


class SyncScheduler:
    """Scheduler for automated data sync jobs."""

    def __init__(self, sync_engine: DataSyncEngine):
        """Initialize scheduler."""
        self.engine = sync_engine
        self._schedules: dict[str, tuple[SyncConfig, ScheduleConfig]] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def add_schedule(
        self,
        name: str,
        sync_config: SyncConfig,
        schedule_config: ScheduleConfig,
    ) -> None:
        """Add a sync schedule."""
        if schedule_config.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ConstitutionalViolationError(
                "Invalid constitutional hash in schedule config",
                error_code="DW_HASH_MISMATCH",
            )
        self._schedules[name] = (sync_config, schedule_config)

    def remove_schedule(self, name: str) -> bool:
        """Remove a sync schedule."""
        if name not in self._schedules:
            return False
        del self._schedules[name]
        return True

    def get_schedule(self, name: str) -> tuple[SyncConfig, ScheduleConfig] | None:
        """Get a specific schedule."""
        return self._schedules.get(name)

    def list_schedules(self) -> dict:
        """List all schedules."""
        return {
            name: {
                "sync_config": sc.to_dict(),
                "schedule_config": sched.to_dict(),
            }
            for name, (sc, sched) in self._schedules.items()
        }

    def parse_cron(self, expression: str) -> dict:
        """Parse cron expression into components."""
        parts = expression.split()
        if len(parts) != 5:
            raise ACGSValidationError(
                f"Invalid cron expression: {expression}",
                error_code="DW_INVALID_CRON",
            )

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day_of_month": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    def should_run(self, schedule_config: ScheduleConfig, current_time: datetime) -> bool:
        """Check if schedule should run at current time."""
        if not schedule_config.enabled:
            return False

        cron = self.parse_cron(schedule_config.cron_expression)
        schedule_fields = (
            ("minute", current_time.minute),
            ("hour", current_time.hour),
            ("day_of_month", current_time.day),
            ("month", current_time.month),
            ("day_of_week", current_time.weekday()),
        )
        return all(
            cron[field] == "*" or int(cron[field]) == current_value
            for field, current_value in schedule_fields
        )

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            current_time = datetime.now(UTC)

            for _name, (sync_config, schedule_config) in self._schedules.items():
                if self.should_run(schedule_config, current_time):
                    try:
                        await self.engine.sync_table(sync_config)
                    except (RuntimeError, ValueError, ConnectionError, OSError):
                        if schedule_config.retry_on_failure:
                            # Would implement retry logic here
                            pass

            # Wait for next minute
            await asyncio.sleep(60)

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running


# ============================================================================
# Factory Function
# ============================================================================


def create_sync_engine(
    source_config: WarehouseConfig,
    target_config: WarehouseConfig,
) -> DataSyncEngine:
    """Create a sync engine with source and target connectors."""
    source = create_connector(source_config)
    target = create_connector(target_config)
    return DataSyncEngine(source, target)
