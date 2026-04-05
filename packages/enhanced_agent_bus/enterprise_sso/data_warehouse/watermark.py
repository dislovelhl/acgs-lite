"""
Watermark Manager
Constitutional Hash: 608508a9bd224290

Manages watermarks for incremental data sync tracking.
Provides CRUD operations and state management for sync progress.
"""

import hashlib
from datetime import UTC, datetime, timezone

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .models import Watermark, WatermarkError


class WatermarkManager:
    """Manages watermarks for incremental data sync."""

    def __init__(self):
        """Initialize watermark manager."""
        self._watermarks: dict[str, Watermark] = {}
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def get_watermark(self, table_name: str) -> Watermark | None:
        """Get watermark for a table."""
        return self._watermarks.get(table_name)

    def set_watermark(self, watermark: Watermark) -> None:
        """Set watermark for a table."""
        if watermark.constitutional_hash != CONSTITUTIONAL_HASH:
            raise WatermarkError("Invalid constitutional hash in watermark")
        self._watermarks[watermark.table_name] = watermark

    def update_watermark(
        self,
        table_name: str,
        last_value: object,
        row_count: int,
        sync_id: str,
    ) -> Watermark:
        """Update existing watermark with new values."""
        existing = self._watermarks.get(table_name)
        if not existing:
            raise WatermarkError(f"No watermark found for table: {table_name}")

        updated = Watermark(
            table_name=table_name,
            column_name=existing.column_name,
            last_value=last_value,
            last_sync_at=datetime.now(UTC),
            sync_id=sync_id,
            row_count=row_count,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        self._watermarks[table_name] = updated
        return updated

    def create_watermark(
        self,
        table_name: str,
        column_name: str,
        initial_value: object = None,
    ) -> Watermark:
        """Create a new watermark for a table."""
        sync_id = hashlib.sha256(
            f"{table_name}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        watermark = Watermark(
            table_name=table_name,
            column_name=column_name,
            last_value=initial_value,
            last_sync_at=datetime.now(UTC),
            sync_id=sync_id,
            row_count=0,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        self._watermarks[table_name] = watermark
        return watermark

    def list_watermarks(self) -> list[Watermark]:
        """List all tracked watermarks."""
        return list(self._watermarks.values())

    def delete_watermark(self, table_name: str) -> bool:
        """Delete watermark for a table."""
        if table_name in self._watermarks:
            del self._watermarks[table_name]
            return True
        return False

    def to_dict(self) -> dict:
        """Export all watermarks as dictionary."""
        return {
            "watermarks": {name: wm.to_dict() for name, wm in self._watermarks.items()},
            "constitutional_hash": self.constitutional_hash,
        }
