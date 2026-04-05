"""
Data Warehouse Integration
Constitutional Hash: 608508a9bd224290

Phase 10 Task 14: Data Warehouse Integration

Provides:
- Snowflake connector with incremental sync
- Redshift connector with efficient COPY commands
- BigQuery connector with streaming API
- Watermark-based incremental data sync
- Schema evolution handling
- Cron-based sync scheduling

This package exposes all public APIs for backward compatibility.
"""

# Constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Re-export all models
# Re-export connectors
from .connectors import (
    BigQueryConnector,
    DataWarehouseConnector,
    MockConnection,
    RedshiftConnector,
    SnowflakeConnector,
    create_connector,
)
from .models import (
    # Configuration dataclasses
    BigQueryConfig,
    # Exceptions
    DataWarehouseConnectionError,
    DataWarehouseError,
    RedshiftConfig,
    ScheduleConfig,
    # Enums
    SchemaAction,
    SchemaChange,
    SchemaEvolutionError,
    SnowflakeConfig,
    SyncConfig,
    SyncError,
    SyncMode,
    SyncResult,
    SyncStatus,
    WarehouseConfig,
    WarehouseType,
    Watermark,
    WatermarkError,
    # Validation functions (SQL injection prevention)
    validate_data_type,
    validate_default_value,
    validate_identifier,
)

# Re-export schema evolution manager
from .schema_evolution import SchemaEvolutionManager

# Re-export sync engine and scheduler
from .sync_engine import (
    DataSyncEngine,
    SyncScheduler,
    create_sync_engine,
)

# Re-export watermark manager
from .watermark import WatermarkManager

__all__ = [
    "CONSTITUTIONAL_HASH",
    "BigQueryConfig",
    "BigQueryConnector",
    # Sync Engine
    "DataSyncEngine",
    "DataWarehouseConnectionError",
    # Connectors
    "DataWarehouseConnector",
    # Exceptions
    "DataWarehouseError",
    "MockConnection",
    "RedshiftConfig",
    "RedshiftConnector",
    "ScheduleConfig",
    "SchemaAction",
    "SchemaChange",
    "SchemaEvolutionError",
    "SchemaEvolutionManager",
    "SnowflakeConfig",
    "SnowflakeConnector",
    "SyncConfig",
    "SyncError",
    "SyncMode",
    "SyncResult",
    "SyncScheduler",
    "SyncStatus",
    # Configuration dataclasses
    "WarehouseConfig",
    # Enums
    "WarehouseType",
    "Watermark",
    "WatermarkError",
    # Managers
    "WatermarkManager",
    "create_connector",
    "create_sync_engine",
]
