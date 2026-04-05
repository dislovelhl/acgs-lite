"""
Data Warehouse Connectors
Constitutional Hash: 608508a9bd224290

Provides abstract base class and implementations for connecting to
various data warehouses: Snowflake, Redshift, and BigQuery.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .models import (
    BigQueryConfig,
    DataWarehouseConnectionError,
    RedshiftConfig,
    SchemaAction,
    SchemaChange,
    SchemaEvolutionError,
    SnowflakeConfig,
    SyncError,
    WarehouseConfig,
    WarehouseType,
    validate_identifier,
)

_WAREHOUSE_CONNECTOR_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# ============================================================================
# Abstract Base Connector
# ============================================================================


class DataWarehouseConnector(ABC):
    """Abstract base class for data warehouse connectors."""

    def __init__(self, config: WarehouseConfig):
        """Initialize connector with configuration."""
        if config.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash: {config.constitutional_hash}")
        self.config = config
        self._connection: Any | None = None  # MockConnection or real connection
        self._pool: list[Any] = []
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the warehouse."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the warehouse."""

    @abstractmethod
    async def execute_query(self, query: str, params: dict | None = None) -> list:
        """Execute a query and return results."""

    @abstractmethod
    async def execute_batch(self, query: str, data: list, batch_size: int = 1000) -> int:
        """Execute batch insert/update."""

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> dict:
        """Get schema information for a table."""

    @abstractmethod
    async def apply_schema_change(self, change: SchemaChange) -> bool:
        """Apply a schema evolution change."""

    async def health_check(self) -> dict:
        """Check connection health."""
        try:
            if not self._connected:
                return {
                    "healthy": False,
                    "message": "Not connected",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
            # Try a simple query
            await self.execute_query("SELECT 1")
            return {
                "healthy": True,
                "message": "Connection OK",
                "warehouse_type": self.config.warehouse_type.value,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        except _WAREHOUSE_CONNECTOR_ERRORS as e:
            return {
                "healthy": False,
                "message": str(e),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }


# ============================================================================
# Mock Connection (for testing without actual warehouse)
# ============================================================================


class MockConnection:
    """Mock connection for testing."""

    def __init__(self, warehouse_type: WarehouseType, config: WarehouseConfig):
        """Initialize mock connection."""
        self.warehouse_type = warehouse_type
        self.config = config
        self._connected = False
        self._data_store: dict = {}
        self._query_log: list = []

    async def connect(self) -> None:
        """Simulate connection."""
        await asyncio.sleep(0.01)  # Simulate network delay
        self._connected = True

    async def close(self) -> None:
        """Simulate disconnection."""
        self._connected = False

    async def execute(self, query: str, params: dict | None = None) -> list:
        """Simulate query execution."""
        self._query_log.append({"query": query, "params": params})

        # Return mock data based on query type
        if "SELECT 1" in query:
            return [{"result": 1}]
        elif "information_schema" in query.lower() or "svv_columns" in query.lower():
            return [
                {
                    "column_name": "id",
                    "data_type": "INTEGER",
                    "is_nullable": "NO",
                    "column_default": None,
                },
                {
                    "column_name": "name",
                    "data_type": "VARCHAR(255)",
                    "is_nullable": "YES",
                    "column_default": None,
                },
                {
                    "column_name": "created_at",
                    "data_type": "TIMESTAMP",
                    "is_nullable": "NO",
                    "column_default": "CURRENT_TIMESTAMP",
                },
            ]
        elif query.startswith("SELECT"):
            return []
        else:
            return []

    async def execute_batch(self, query: str, data: list) -> int:
        """Simulate batch execution."""
        self._query_log.append({"query": query, "batch_size": len(data)})
        return len(data)


# ============================================================================
# Snowflake Connector
# ============================================================================


class SnowflakeConnector(DataWarehouseConnector):
    """Snowflake data warehouse connector."""

    def __init__(self, config: SnowflakeConfig):
        """Initialize Snowflake connector."""
        super().__init__(config)
        self.snowflake_config = config
        self._cursor = None

    async def connect(self) -> None:
        """Establish connection to Snowflake."""
        try:
            # In production, use snowflake-connector-python
            # For now, create a mock connection
            self._connection = MockConnection(
                warehouse_type=WarehouseType.SNOWFLAKE,
                config=self.config,
            )
            await self._connection.connect()
            self._connected = True
        except _WAREHOUSE_CONNECTOR_ERRORS as e:
            raise DataWarehouseConnectionError(f"Failed to connect to Snowflake: {e}") from e

    async def disconnect(self) -> None:
        """Close Snowflake connection."""
        if self._connection:
            await self._connection.close()
            self._connected = False
            self._connection = None

    async def execute_query(self, query: str, params: dict | None = None) -> list:
        """Execute a query on Snowflake."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to Snowflake")
        return list(await self._connection.execute(query, params))  # type: ignore[arg-type]

    async def execute_batch(self, query: str, data: list, batch_size: int = 1000) -> int:
        """Execute batch insert using Snowflake's PUT/COPY pattern."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to Snowflake")

        total_rows = 0
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            rows = await self._connection.execute_batch(query, batch)
            total_rows += rows

        return total_rows

    async def get_table_schema(self, table_name: str) -> dict:
        """Get Snowflake table schema."""
        validated_table = validate_identifier(table_name, "table_name")
        validated_schema = validate_identifier(self.snowflake_config.schema_name, "schema_name")
        query = (
            "SELECT column_name, data_type, is_nullable, column_default"
            " FROM information_schema.columns"
            f" WHERE table_name = '{validated_table.upper()}'"  # nosec B608
            f" AND table_schema = '{validated_schema.upper()}'"  # nosec B608
            " ORDER BY ordinal_position"
        )
        results = await self.execute_query(query)
        return {
            "table_name": table_name,
            "columns": results,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def apply_schema_change(self, change: SchemaChange) -> bool:
        """Apply schema evolution on Snowflake."""
        sql = self._generate_alter_sql(change)
        try:
            await self.execute_query(sql)
            return True
        except (RuntimeError, ValueError, DataWarehouseConnectionError, OSError):
            return False

    def _generate_alter_sql(self, change: SchemaChange) -> str:
        """Generate ALTER TABLE SQL for Snowflake.

        Note: SchemaChange.__post_init__ validates all fields at construction time.
        """
        table = f'"{self.snowflake_config.schema_name}"."{change.table_name}"'

        if change.action == SchemaAction.ADD_COLUMN:
            nullable = "" if change.nullable else " NOT NULL"
            default = f" DEFAULT {change.default_value}" if change.default_value else ""
            return f'ALTER TABLE {table} ADD COLUMN "{change.column_name}" {change.data_type}{nullable}{default}'

        elif change.action == SchemaAction.DROP_COLUMN:
            return f'ALTER TABLE {table} DROP COLUMN "{change.column_name}"'

        elif change.action == SchemaAction.MODIFY_TYPE:
            return f'ALTER TABLE {table} ALTER COLUMN "{change.column_name}" SET DATA TYPE {change.data_type}'

        elif change.action == SchemaAction.RENAME_COLUMN:
            return f'ALTER TABLE {table} RENAME COLUMN "{change.column_name}" TO "{change.new_column_name}"'

        raise SchemaEvolutionError(f"Unsupported action: {change.action}")

    async def stage_and_copy(self, data: list, target_table: str, stage_name: str = "@~") -> int:
        """Stage data and COPY into Snowflake table."""
        # In production, this would:
        # 1. Write data to a temporary file
        # 2. PUT the file to an internal/external stage
        # 3. COPY INTO the target table
        safe_table = validate_identifier(target_table, "target_table")
        return await self.execute_batch(f"INSERT INTO {safe_table} VALUES (%s)", data)  # nosec B608


# ============================================================================
# Redshift Connector
# ============================================================================


class RedshiftConnector(DataWarehouseConnector):
    """Amazon Redshift data warehouse connector."""

    def __init__(self, config: RedshiftConfig):
        """Initialize Redshift connector."""
        super().__init__(config)
        self.redshift_config = config

    async def connect(self) -> None:
        """Establish connection to Redshift."""
        try:
            # In production, use psycopg2 or redshift_connector
            self._connection = MockConnection(
                warehouse_type=WarehouseType.REDSHIFT,
                config=self.config,
            )
            await self._connection.connect()
            self._connected = True
        except _WAREHOUSE_CONNECTOR_ERRORS as e:
            raise DataWarehouseConnectionError(f"Failed to connect to Redshift: {e}") from e

    async def disconnect(self) -> None:
        """Close Redshift connection."""
        if self._connection:
            await self._connection.close()
            self._connected = False
            self._connection = None

    async def execute_query(self, query: str, params: dict | None = None) -> list:
        """Execute a query on Redshift."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to Redshift")
        return list(await self._connection.execute(query, params))  # type: ignore[arg-type]

    async def execute_batch(self, query: str, data: list, batch_size: int = 1000) -> int:
        """Execute batch insert on Redshift."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to Redshift")

        total_rows = 0
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            rows = await self._connection.execute_batch(query, batch)
            total_rows += rows

        return total_rows

    async def get_table_schema(self, table_name: str) -> dict:
        """Get Redshift table schema from SVV_COLUMNS."""
        validated_table = validate_identifier(table_name, "table_name")
        validated_schema = validate_identifier(self.redshift_config.schema_name, "schema_name")
        query = (
            "SELECT column_name, data_type, is_nullable, column_default"
            " FROM svv_columns"
            f" WHERE table_name = '{validated_table}'"  # nosec B608
            f" AND table_schema = '{validated_schema}'"  # nosec B608
            " ORDER BY ordinal_position"
        )
        results = await self.execute_query(query)
        return {
            "table_name": table_name,
            "columns": results,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def apply_schema_change(self, change: SchemaChange) -> bool:
        """Apply schema evolution on Redshift."""
        sql = self._generate_alter_sql(change)
        try:
            await self.execute_query(sql)
            return True
        except (RuntimeError, ValueError, DataWarehouseConnectionError, OSError):
            return False

    def _generate_alter_sql(self, change: SchemaChange) -> str:
        """Generate ALTER TABLE SQL for Redshift.

        Note: SchemaChange.__post_init__ validates all fields at construction time.
        """
        table = f'"{self.redshift_config.schema_name}"."{change.table_name}"'

        if change.action == SchemaAction.ADD_COLUMN:
            nullable = "" if change.nullable else " NOT NULL"
            default = f" DEFAULT {change.default_value}" if change.default_value else ""
            return f'ALTER TABLE {table} ADD COLUMN "{change.column_name}" {change.data_type}{nullable}{default}'

        elif change.action == SchemaAction.DROP_COLUMN:
            return f'ALTER TABLE {table} DROP COLUMN "{change.column_name}"'

        elif change.action == SchemaAction.RENAME_COLUMN:
            return f'ALTER TABLE {table} RENAME COLUMN "{change.column_name}" TO "{change.new_column_name}"'

        # Redshift doesn't support MODIFY TYPE directly
        raise SchemaEvolutionError(f"Unsupported action for Redshift: {change.action}")

    async def copy_from_s3(
        self,
        target_table: str,
        s3_path: str,
        iam_role: str | None = None,
        file_format: str = "CSV",
    ) -> int:
        """Execute COPY command from S3."""
        role = iam_role or self.redshift_config.iam_role
        if not role:
            raise SyncError("IAM role required for S3 COPY")

        safe_table = validate_identifier(target_table, "target_table")
        copy_sql = f"""
            COPY {safe_table}
            FROM '{s3_path}'
            IAM_ROLE '{role}'
            FORMAT AS {file_format}
            IGNOREHEADER 1
        """
        await self.execute_query(copy_sql)
        # Return affected rows (mocked)
        return 0

    async def unload_to_s3(
        self,
        query: str,
        s3_path: str,
        iam_role: str | None = None,
        file_format: str = "CSV",
    ) -> str:
        """Execute UNLOAD command to S3."""
        role = iam_role or self.redshift_config.iam_role
        if not role:
            raise SyncError("IAM role required for S3 UNLOAD")

        unload_sql = f"""
            UNLOAD ('{query}')
            TO '{s3_path}'
            IAM_ROLE '{role}'
            FORMAT AS {file_format}
            HEADER
        """
        await self.execute_query(unload_sql)
        return s3_path


# ============================================================================
# BigQuery Connector
# ============================================================================


class BigQueryConnector(DataWarehouseConnector):
    """Google BigQuery data warehouse connector."""

    def __init__(self, config: BigQueryConfig):
        """Initialize BigQuery connector."""
        super().__init__(config)
        self.bq_config = config
        self._client = None

    async def connect(self) -> None:
        """Establish connection to BigQuery."""
        try:
            # In production, use google-cloud-bigquery
            self._connection = MockConnection(
                warehouse_type=WarehouseType.BIGQUERY,
                config=self.config,
            )
            await self._connection.connect()
            self._connected = True
        except _WAREHOUSE_CONNECTOR_ERRORS as e:
            raise DataWarehouseConnectionError(f"Failed to connect to BigQuery: {e}") from e

    async def disconnect(self) -> None:
        """Close BigQuery connection."""
        if self._connection:
            await self._connection.close()
            self._connected = False
            self._connection = None

    async def execute_query(self, query: str, params: dict | None = None) -> list:
        """Execute a query on BigQuery."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to BigQuery")
        return list(await self._connection.execute(query, params))  # type: ignore[arg-type]

    async def execute_batch(self, query: str, data: list, batch_size: int = 1000) -> int:
        """Execute batch insert on BigQuery."""
        if not self._connected:
            raise DataWarehouseConnectionError("Not connected to BigQuery")

        if self.bq_config.use_streaming:
            return await self._streaming_insert(data, batch_size)
        else:
            return await self._batch_insert(query, data, batch_size)

    async def _streaming_insert(self, data: list, batch_size: int = 500) -> int:
        """Insert rows using BigQuery streaming API."""
        total_rows = 0
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            # In production, use insertAll API
            rows = await self._connection.execute_batch("STREAMING_INSERT", batch)
            total_rows += rows
        return total_rows

    async def _batch_insert(self, query: str, data: list, batch_size: int = 1000) -> int:
        """Insert rows using load job."""
        total_rows = 0
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            rows = await self._connection.execute_batch(query, batch)
            total_rows += rows
        return total_rows

    async def get_table_schema(self, table_name: str) -> dict:
        """Get BigQuery table schema."""
        validated_table = validate_identifier(table_name, "table_name")
        query = (
            "SELECT column_name, data_type, is_nullable"
            f" FROM `{self.bq_config.project_id}.{self.bq_config.dataset}.INFORMATION_SCHEMA.COLUMNS`"
            f" WHERE table_name = '{validated_table}'"  # nosec B608
            " ORDER BY ordinal_position"
        )
        results = await self.execute_query(query)
        return {
            "table_name": table_name,
            "columns": results,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    async def apply_schema_change(self, change: SchemaChange) -> bool:
        """Apply schema evolution on BigQuery."""
        sql = self._generate_alter_sql(change)
        try:
            await self.execute_query(sql)
            return True
        except (RuntimeError, ValueError, DataWarehouseConnectionError, OSError):
            return False

    def _generate_alter_sql(self, change: SchemaChange) -> str:
        """Generate ALTER TABLE SQL for BigQuery.

        Note: SchemaChange.__post_init__ validates all fields at construction time.
        """
        table = f"`{self.bq_config.project_id}.{self.bq_config.dataset}.{change.table_name}`"

        if change.action == SchemaAction.ADD_COLUMN:
            return f"ALTER TABLE {table} ADD COLUMN `{change.column_name}` {change.data_type}"

        elif change.action == SchemaAction.DROP_COLUMN:
            return f"ALTER TABLE {table} DROP COLUMN `{change.column_name}`"

        elif change.action == SchemaAction.RENAME_COLUMN:
            return f"ALTER TABLE {table} RENAME COLUMN `{change.column_name}` TO `{change.new_column_name}`"

        raise SchemaEvolutionError(f"Unsupported action for BigQuery: {change.action}")

    async def create_external_table(self, table_name: str, _source_uri: str, schema: list) -> bool:
        """Create an external table pointing to GCS."""
        # In production, this would create an external table
        return True


# ============================================================================
# Factory Function
# ============================================================================


def create_connector(config: WarehouseConfig) -> DataWarehouseConnector:
    """Factory function to create appropriate connector."""
    if config.constitutional_hash != CONSTITUTIONAL_HASH:
        raise ValueError(f"Invalid constitutional hash: {config.constitutional_hash}")

    if isinstance(config, SnowflakeConfig):
        return SnowflakeConnector(config)
    elif isinstance(config, RedshiftConfig):
        return RedshiftConnector(config)
    elif isinstance(config, BigQueryConfig):
        return BigQueryConnector(config)
    else:
        raise ValueError(f"Unsupported warehouse type: {config.warehouse_type}")
