"""
Schema Evolution Manager
Constitutional Hash: 608508a9bd224290

Manages schema evolution across source and target data warehouses.
Detects schema differences and applies changes.
"""

from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .models import SchemaAction, SchemaChange

if TYPE_CHECKING:
    from .connectors import DataWarehouseConnector

SCHEMA_CHANGE_APPLICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


class SchemaEvolutionManager:
    """Manages schema evolution across source and target."""

    def __init__(self, connector: "DataWarehouseConnector"):
        """Initialize schema evolution manager."""
        self.connector = connector
        self._pending_changes: list[SchemaChange] = []
        self._applied_changes: list[SchemaChange] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def detect_changes(self, source_schema: dict, target_schema: dict) -> list[SchemaChange]:
        """Detect schema differences between source and target."""
        changes = []

        source_columns = {col["column_name"]: col for col in source_schema.get("columns", [])}
        target_columns = {col["column_name"]: col for col in target_schema.get("columns", [])}

        # Detect new columns
        for col_name, col_info in source_columns.items():
            if col_name not in target_columns:
                changes.append(
                    SchemaChange(
                        action=SchemaAction.ADD_COLUMN,
                        table_name=target_schema["table_name"],
                        column_name=col_name,
                        data_type=col_info.get("data_type", "VARCHAR(255)"),
                        nullable=col_info.get("is_nullable", "YES") == "YES",
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )
                )

        # Detect dropped columns (optional, usually not auto-applied)
        for col_name in target_columns:
            if col_name not in source_columns:
                changes.append(
                    SchemaChange(
                        action=SchemaAction.DROP_COLUMN,
                        table_name=target_schema["table_name"],
                        column_name=col_name,
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )
                )

        self._pending_changes = changes
        return changes

    async def apply_changes(
        self, changes: list[SchemaChange] | None = None, dry_run: bool = False
    ) -> list[dict]:
        """Apply pending schema changes."""
        to_apply = changes or self._pending_changes
        results = []

        for change in to_apply:
            if dry_run:
                results.append(
                    {
                        "change": change.to_dict(),
                        "status": "dry_run",
                        "applied": False,
                    }
                )
            else:
                try:
                    success = await self.connector.apply_schema_change(change)
                    if success:
                        self._applied_changes.append(change)
                    results.append(
                        {
                            "change": change.to_dict(),
                            "status": "success" if success else "failed",
                            "applied": success,
                        }
                    )
                except SCHEMA_CHANGE_APPLICATION_ERRORS as e:
                    results.append(
                        {
                            "change": change.to_dict(),
                            "status": "error",
                            "applied": False,
                            "error": str(e),
                        }
                    )

        if not dry_run:
            self._pending_changes = [
                c for c in self._pending_changes if c not in self._applied_changes
            ]

        return results

    def get_pending_changes(self) -> list[SchemaChange]:
        """Get list of pending schema changes."""
        return self._pending_changes

    def get_applied_changes(self) -> list[SchemaChange]:
        """Get list of applied schema changes."""
        return self._applied_changes
