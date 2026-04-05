"""
Data Warehouse Models
Constitutional Hash: 608508a9bd224290

Contains all exception classes, enums, and dataclass configurations
for data warehouse integration.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

# ============================================================================
# SQL Injection Prevention
# ============================================================================

# Matches valid SQL identifiers: letters/underscore start, optional dotted parts.
# Hyphens are allowed within segments (e.g. BigQuery project IDs like "my-project").
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*){0,2}$")

# Allowed SQL data types (case-insensitive, with optional length specifiers)
_SQL_TYPE_BASE = re.compile(
    r"^(?:VARCHAR|INTEGER|INT|FLOAT|BOOLEAN|TIMESTAMP|DATE|TEXT|BIGINT|SMALLINT|"
    r"DECIMAL|NUMERIC|CHAR|DOUBLE|REAL|BINARY|VARBINARY|JSON|ARRAY|MAP|STRUCT|"
    r"STRING|NUMBER|VARIANT|OBJECT|SUPER|TIMESTAMPTZ|TIMESTAMP_TZ|TIMESTAMP_LTZ|"
    r"TIMESTAMP_NTZ)"
    r"(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?$",
    re.IGNORECASE,
)

# GCP project ID validation: 6-30 chars, lowercase letters/digits/hyphens,
# must start with a letter and not end with a hyphen.
_GCP_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")

# Safe default value literals: NULL, TRUE, FALSE, CURRENT_TIMESTAMP,
# quoted strings (no nested quotes), or numeric literals
_SAFE_DEFAULT_RE = re.compile(
    r"^(?:NULL|TRUE|FALSE|CURRENT_TIMESTAMP|'[^']*'|\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def validate_gcp_project_id(value: str) -> str:
    """Validate a GCP project ID.

    Args:
        value: The project ID string to validate.

    Returns:
        The validated project ID string.

    Raises:
        ValueError: If the project ID is invalid.
    """
    if not _GCP_PROJECT_ID_RE.fullmatch(value):
        raise ValueError(
            f"Invalid GCP project ID {value!r}. Must be 6-30 chars, lowercase letters/"
            "digits/hyphens, start with a letter, and not end with a hyphen."
        )
    return value


def validate_identifier(value: str, field_name: str) -> str:
    """Validate a SQL identifier to prevent injection.

    Args:
        value: The identifier string to validate.
        field_name: Name of the field (for error messages).

    Returns:
        The validated identifier string.

    Raises:
        ValueError: If the identifier contains invalid characters.
    """
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier for {field_name}: {value!r}")
    return value


def validate_data_type(value: str) -> str:
    """Validate a SQL data type against an allowlist.

    Args:
        value: The data type string to validate.

    Returns:
        The validated data type string.

    Raises:
        ValueError: If the data type is not in the allowlist.
    """
    if not _SQL_TYPE_BASE.fullmatch(value.strip()):
        raise ValueError(f"Invalid SQL data type: {value!r}")
    return value


def validate_default_value(value: str) -> str:
    """Validate a SQL default value against safe literal patterns.

    Args:
        value: The default value string to validate.

    Returns:
        The validated default value string.

    Raises:
        ValueError: If the default value doesn't match safe patterns.
    """
    if not _SAFE_DEFAULT_RE.fullmatch(value.strip()):
        raise ValueError(f"Unsafe default value: {value!r}")
    return value


# ============================================================================
# Exceptions
# ============================================================================


class DataWarehouseError(ACGSBaseError):
    """Base exception for data warehouse operations.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "DATA_WAREHOUSE_ERROR"


class DataWarehouseConnectionError(DataWarehouseError):
    """Error connecting to data warehouse."""

    http_status_code = 503  # Service Unavailable
    error_code = "DW_CONNECTION_ERROR"


class SyncError(DataWarehouseError):
    """Error during data sync operation."""

    http_status_code = 500
    error_code = "DW_SYNC_ERROR"


class SchemaEvolutionError(DataWarehouseError):
    """Error during schema evolution."""

    http_status_code = 500
    error_code = "DW_SCHEMA_EVOLUTION_ERROR"


class WatermarkError(DataWarehouseError):
    """Error with watermark operations."""

    http_status_code = 500
    error_code = "DW_WATERMARK_ERROR"


# ============================================================================
# Enums
# ============================================================================


class WarehouseType(Enum):
    """Supported data warehouse types."""

    SNOWFLAKE = "snowflake"
    REDSHIFT = "redshift"
    BIGQUERY = "bigquery"


class SyncMode(Enum):
    """Data sync modes."""

    FULL = "full"
    INCREMENTAL = "incremental"
    MERGE = "merge"


class SchemaAction(Enum):
    """Actions for schema evolution."""

    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_TYPE = "modify_type"
    RENAME_COLUMN = "rename_column"


class SyncStatus(Enum):
    """Sync job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# Configuration Data Classes
# ============================================================================


@dataclass
class WarehouseConfig:
    """Base warehouse connection configuration."""

    warehouse_type: WarehouseType = field(default=WarehouseType.SNOWFLAKE)
    host: str = ""
    database: str = ""
    schema_name: str = "public"
    credentials: dict = field(default_factory=dict)
    connection_timeout: int = 30
    query_timeout: int = 300
    pool_size: int = 5
    ssl_enabled: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash: {self.constitutional_hash}. "
                f"Expected: {CONSTITUTIONAL_HASH}"
            )

    def to_dict(self) -> dict:
        """Convert to dictionary with redacted credentials."""
        return {
            "warehouse_type": self.warehouse_type.value,
            "host": self.host,
            "database": self.database,
            "schema_name": self.schema_name,
            "credentials": {k: "***REDACTED***" for k in self.credentials},
            "connection_timeout": self.connection_timeout,
            "query_timeout": self.query_timeout,
            "pool_size": self.pool_size,
            "ssl_enabled": self.ssl_enabled,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SnowflakeConfig(WarehouseConfig):
    """Snowflake-specific configuration."""

    warehouse_type: WarehouseType = field(default=WarehouseType.SNOWFLAKE)
    account: str = ""
    warehouse: str = "COMPUTE_WH"
    role: str = "PUBLIC"
    authenticator: str = "snowflake"  # or 'externalbrowser', 'oauth'

    def get_connection_string(self) -> str:
        """Get Snowflake connection string."""
        return f"snowflake://{self.account}/{self.database}/{self.schema_name}"


@dataclass
class RedshiftConfig(WarehouseConfig):
    """Redshift-specific configuration."""

    warehouse_type: WarehouseType = field(default=WarehouseType.REDSHIFT)
    port: int = 5439
    iam_role: str | None = None
    s3_staging_bucket: str | None = None
    region: str = "us-east-1"

    def get_connection_string(self) -> str:
        """Get Redshift connection string (JDBC-style)."""
        return f"jdbc:redshift://{self.host}:{self.port}/{self.database}"


@dataclass
class BigQueryConfig(WarehouseConfig):
    """BigQuery-specific configuration."""

    warehouse_type: WarehouseType = field(default=WarehouseType.BIGQUERY)
    project_id: str = ""
    dataset: str = ""
    location: str = "US"
    credentials_path: str | None = None
    use_streaming: bool = True

    def get_connection_string(self) -> str:
        """Get BigQuery connection identifier."""
        return f"bigquery://{self.project_id}/{self.dataset}"


# ============================================================================
# Sync/Watermark Data Classes
# ============================================================================


@dataclass
class Watermark:
    """Watermark for incremental sync tracking."""

    table_name: str
    column_name: str
    last_value: str | int | float | None
    last_sync_at: datetime
    sync_id: str
    row_count: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "table_name": self.table_name,
            "column_name": self.column_name,
            "last_value": str(self.last_value) if self.last_value else None,
            "last_sync_at": self.last_sync_at.isoformat(),
            "sync_id": self.sync_id,
            "row_count": self.row_count,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Watermark":
        """Create from dictionary."""
        return cls(
            table_name=data["table_name"],
            column_name=data["column_name"],
            last_value=data.get("last_value"),
            last_sync_at=datetime.fromisoformat(data["last_sync_at"]),
            sync_id=data["sync_id"],
            row_count=data.get("row_count", 0),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


@dataclass
class SyncConfig:
    """Configuration for data sync operations."""

    source_table: str
    target_table: str
    sync_mode: SyncMode = SyncMode.INCREMENTAL
    watermark_column: str | None = None
    batch_size: int = 10000
    max_retries: int = 3
    retry_delay: float = 5.0
    transform_fn: Callable | None = None
    filter_condition: str | None = None
    column_mapping: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source_table": self.source_table,
            "target_table": self.target_table,
            "sync_mode": self.sync_mode.value,
            "watermark_column": self.watermark_column,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "has_transform": self.transform_fn is not None,
            "filter_condition": self.filter_condition,
            "column_mapping": self.column_mapping,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""

    sync_id: str
    status: SyncStatus
    source_table: str
    target_table: str
    rows_processed: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_deleted: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    watermark: Watermark | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "sync_id": self.sync_id,
            "status": self.status.value,
            "source_table": self.source_table,
            "target_table": self.target_table,
            "rows_processed": self.rows_processed,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_deleted": self.rows_deleted,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "watermark": self.watermark.to_dict() if self.watermark else None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class SchemaChange:
    """Represents a schema change for evolution."""

    action: SchemaAction
    table_name: str
    column_name: str
    new_column_name: str | None = None
    data_type: str | None = None
    nullable: bool = True
    default_value: Any | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        """Validate fields to prevent SQL injection in DDL generation."""
        validate_identifier(self.table_name, "table_name")
        validate_identifier(self.column_name, "column_name")
        if self.new_column_name is not None:
            validate_identifier(self.new_column_name, "new_column_name")
        if self.data_type is not None:
            validate_data_type(self.data_type)
        if self.default_value is not None:
            validate_default_value(str(self.default_value))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "new_column_name": self.new_column_name,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "default_value": str(self.default_value) if self.default_value else None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ScheduleConfig:
    """Configuration for scheduled sync jobs."""

    cron_expression: str
    enabled: bool = True
    timezone: str = "UTC"
    max_concurrent: int = 1
    timeout_seconds: int = 3600
    retry_on_failure: bool = True
    notification_email: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "timezone": self.timezone,
            "max_concurrent": self.max_concurrent,
            "timeout_seconds": self.timeout_seconds,
            "retry_on_failure": self.retry_on_failure,
            "notification_email": self.notification_email,
            "constitutional_hash": self.constitutional_hash,
        }
