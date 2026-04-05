from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

"""
Tests for ACGS-2 Data Warehouse Integration
Constitutional Hash: 608508a9bd224290

Phase 10 Task 14: Data Warehouse Integration Tests

Tests for:
- Snowflake connector initialization and operations
- Redshift connector with COPY commands
- BigQuery connector with streaming API
- Incremental data sync with watermarking
- Schema evolution handling
- Cron-based sync scheduling
"""

import asyncio
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError
from enhanced_agent_bus.enterprise_sso.data_warehouse import (
    CONSTITUTIONAL_HASH,
    BigQueryConfig,
    BigQueryConnector,
    DataSyncEngine,
    DataWarehouseConnectionError,
    DataWarehouseConnector,
    DataWarehouseError,
    MockConnection,
    RedshiftConfig,
    RedshiftConnector,
    ScheduleConfig,
    SchemaAction,
    SchemaChange,
    SchemaEvolutionError,
    SchemaEvolutionManager,
    SnowflakeConfig,
    SnowflakeConnector,
    SyncConfig,
    SyncMode,
    SyncResult,
    SyncScheduler,
    SyncStatus,
    WarehouseConfig,
    WarehouseType,
    Watermark,
    WatermarkError,
    WatermarkManager,
    create_connector,
    create_sync_engine,
    validate_data_type,
    validate_default_value,
    validate_identifier,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def snowflake_config():
    """Create Snowflake configuration for testing."""
    return SnowflakeConfig(
        host="account.snowflakecomputing.com",
        database="ACGS2_DB",
        schema_name="PUBLIC",
        account="test_account",
        warehouse="COMPUTE_WH",
        role="ANALYST",
        credentials={"username": "test_user", "password": "test_pass"},
    )


@pytest.fixture
def redshift_config():
    """Create Redshift configuration for testing."""
    return RedshiftConfig(
        host="my-cluster.us-east-1.redshift.amazonaws.com",
        database="acgs2_db",
        schema_name="public",
        port=5439,
        iam_role="arn:aws:iam::123456789:role/RedshiftRole",
        s3_staging_bucket="s3://my-staging-bucket",
        region="us-east-1",
        credentials={"username": "admin", "password": "secret"},
    )


@pytest.fixture
def bigquery_config():
    """Create BigQuery configuration for testing."""
    return BigQueryConfig(
        host="bigquery.googleapis.com",
        database="acgs2",
        project_id="my-project-123",
        dataset="governance_data",
        location="US",
        use_streaming=True,
        credentials={"type": "service_account"},
    )


@pytest.fixture
def sync_config():
    """Create sync configuration for testing."""
    return SyncConfig(
        source_table="source_events",
        target_table="target_events",
        sync_mode=SyncMode.INCREMENTAL,
        watermark_column="updated_at",
        batch_size=1000,
    )


@pytest.fixture
def schedule_config():
    """Create schedule configuration for testing."""
    return ScheduleConfig(
        cron_expression="0 * * * *",  # Every hour
        enabled=True,
        timezone="UTC",
        max_concurrent=1,
    )


# ============================================================================
# Test Cases - Constitutional Hash Validation
# ============================================================================


class TestConstitutionalHashValidation:
    """Tests for constitutional hash enforcement."""

    def test_constitutional_hash_constant(self):
        """Test constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_warehouse_config_includes_hash(self, snowflake_config):
        """Test warehouse config includes constitutional hash."""
        assert snowflake_config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_invalid_constitutional_hash_raises(self):
        """Test that invalid constitutional hash raises error."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            SnowflakeConfig(
                host="test.snowflake.com",
                database="test",
                account="test",
                constitutional_hash="invalid-hash",
            )

    def test_sync_config_includes_hash(self, sync_config):
        """Test sync config includes constitutional hash."""
        assert sync_config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_schedule_config_includes_hash(self, schedule_config):
        """Test schedule config includes constitutional hash."""
        assert schedule_config.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Cases - Snowflake Connector
# ============================================================================


class TestSnowflakeConnector:
    """Tests for Snowflake connector."""

    def test_create_snowflake_config(self, snowflake_config):
        """Test creating Snowflake configuration."""
        assert snowflake_config.warehouse_type == WarehouseType.SNOWFLAKE
        assert snowflake_config.account == "test_account"
        assert snowflake_config.warehouse == "COMPUTE_WH"
        assert snowflake_config.role == "ANALYST"

    def test_snowflake_connection_string(self, snowflake_config):
        """Test Snowflake connection string generation."""
        conn_str = snowflake_config.get_connection_string()
        assert "snowflake://" in conn_str
        assert "test_account" in conn_str

    async def test_snowflake_connect(self, snowflake_config):
        """Test connecting to Snowflake."""
        connector = SnowflakeConnector(snowflake_config)
        assert not connector.is_connected

        await connector.connect()
        assert connector.is_connected

        await connector.disconnect()
        assert not connector.is_connected

    async def test_snowflake_execute_query(self, snowflake_config):
        """Test executing query on Snowflake."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        result = await connector.execute_query("SELECT 1")
        assert result is not None
        assert len(result) > 0

        await connector.disconnect()

    async def test_snowflake_execute_batch(self, snowflake_config):
        """Test batch execution on Snowflake."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        data = [{"id": i, "name": f"item_{i}"} for i in range(100)]
        rows = await connector.execute_batch("INSERT INTO test VALUES (%s)", data)
        assert rows == 100

        await connector.disconnect()

    async def test_snowflake_get_table_schema(self, snowflake_config):
        """Test getting table schema from Snowflake."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        schema = await connector.get_table_schema("EVENTS")
        assert "table_name" in schema
        assert "columns" in schema
        assert schema["constitutional_hash"] == CONSTITUTIONAL_HASH

        await connector.disconnect()

    async def test_snowflake_health_check(self, snowflake_config):
        """Test Snowflake health check."""
        connector = SnowflakeConnector(snowflake_config)

        # Not connected
        health = await connector.health_check()
        assert health["healthy"] is False

        # Connected
        await connector.connect()
        health = await connector.health_check()
        assert health["healthy"] is True
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

        await connector.disconnect()

    async def test_snowflake_not_connected_raises(self, snowflake_config):
        """Test that operations on disconnected connector raise error."""
        connector = SnowflakeConnector(snowflake_config)

        with pytest.raises(DataWarehouseConnectionError, match="Not connected"):
            await connector.execute_query("SELECT 1")


# ============================================================================
# Test Cases - Redshift Connector
# ============================================================================


class TestRedshiftConnector:
    """Tests for Redshift connector."""

    def test_create_redshift_config(self, redshift_config):
        """Test creating Redshift configuration."""
        assert redshift_config.warehouse_type == WarehouseType.REDSHIFT
        assert redshift_config.port == 5439
        assert redshift_config.iam_role is not None

    def test_redshift_connection_string(self, redshift_config):
        """Test Redshift connection string generation."""
        conn_str = redshift_config.get_connection_string()
        assert "jdbc:redshift://" in conn_str
        assert "5439" in conn_str

    async def test_redshift_connect(self, redshift_config):
        """Test connecting to Redshift."""
        connector = RedshiftConnector(redshift_config)
        assert not connector.is_connected

        await connector.connect()
        assert connector.is_connected

        await connector.disconnect()

    async def test_redshift_execute_query(self, redshift_config):
        """Test executing query on Redshift."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        result = await connector.execute_query("SELECT 1")
        assert result is not None

        await connector.disconnect()

    async def test_redshift_execute_batch(self, redshift_config):
        """Test batch execution on Redshift."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        data = [{"id": i, "value": f"val_{i}"} for i in range(500)]
        rows = await connector.execute_batch("INSERT INTO test VALUES (%s)", data, batch_size=100)
        assert rows == 500

        await connector.disconnect()

    async def test_redshift_get_table_schema(self, redshift_config):
        """Test getting table schema from Redshift."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        schema = await connector.get_table_schema("events")
        assert "table_name" in schema
        assert schema["constitutional_hash"] == CONSTITUTIONAL_HASH

        await connector.disconnect()

    async def test_redshift_copy_from_s3(self, redshift_config):
        """Test COPY command from S3."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        # This would execute COPY command
        rows = await connector.copy_from_s3(
            target_table="events",
            s3_path="s3://bucket/data/events.csv",
        )
        assert isinstance(rows, int)

        await connector.disconnect()

    async def test_redshift_unload_to_s3(self, redshift_config):
        """Test UNLOAD command to S3."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        path = await connector.unload_to_s3(
            query="SELECT * FROM events",
            s3_path="s3://bucket/exports/events_",
        )
        assert "s3://" in path

        await connector.disconnect()


# ============================================================================
# Test Cases - BigQuery Connector
# ============================================================================


class TestBigQueryConnector:
    """Tests for BigQuery connector."""

    def test_create_bigquery_config(self, bigquery_config):
        """Test creating BigQuery configuration."""
        assert bigquery_config.warehouse_type == WarehouseType.BIGQUERY
        assert bigquery_config.project_id == "my-project-123"
        assert bigquery_config.dataset == "governance_data"
        assert bigquery_config.use_streaming is True

    def test_bigquery_connection_string(self, bigquery_config):
        """Test BigQuery connection identifier."""
        conn_str = bigquery_config.get_connection_string()
        assert "bigquery://" in conn_str
        assert "my-project-123" in conn_str

    async def test_bigquery_connect(self, bigquery_config):
        """Test connecting to BigQuery."""
        connector = BigQueryConnector(bigquery_config)
        assert not connector.is_connected

        await connector.connect()
        assert connector.is_connected

        await connector.disconnect()

    async def test_bigquery_execute_query(self, bigquery_config):
        """Test executing query on BigQuery."""
        connector = BigQueryConnector(bigquery_config)
        await connector.connect()

        result = await connector.execute_query("SELECT 1")
        assert result is not None

        await connector.disconnect()

    async def test_bigquery_streaming_insert(self, bigquery_config):
        """Test streaming insert on BigQuery."""
        connector = BigQueryConnector(bigquery_config)
        await connector.connect()

        data = [{"id": i, "event": f"event_{i}"} for i in range(100)]
        rows = await connector.execute_batch("INSERT", data)
        assert rows == 100

        await connector.disconnect()

    async def test_bigquery_batch_insert(self, bigquery_config):
        """Test batch insert on BigQuery (non-streaming)."""
        bigquery_config.use_streaming = False
        connector = BigQueryConnector(bigquery_config)
        await connector.connect()

        data = [{"id": i} for i in range(50)]
        rows = await connector.execute_batch("INSERT", data)
        assert rows == 50

        await connector.disconnect()

    async def test_bigquery_get_table_schema(self, bigquery_config):
        """Test getting table schema from BigQuery."""
        connector = BigQueryConnector(bigquery_config)
        await connector.connect()

        schema = await connector.get_table_schema("events")
        assert "table_name" in schema
        assert schema["constitutional_hash"] == CONSTITUTIONAL_HASH

        await connector.disconnect()


# ============================================================================
# Test Cases - Watermark Manager
# ============================================================================


class TestWatermarkManager:
    """Tests for watermark management."""

    def test_create_watermark_manager(self):
        """Test creating watermark manager."""
        manager = WatermarkManager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_watermark(self):
        """Test creating a new watermark."""
        manager = WatermarkManager()
        wm = manager.create_watermark(
            table_name="events",
            column_name="updated_at",
            initial_value="2024-01-01T00:00:00Z",
        )

        assert wm.table_name == "events"
        assert wm.column_name == "updated_at"
        assert wm.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_watermark(self):
        """Test getting watermark for a table."""
        manager = WatermarkManager()
        manager.create_watermark("events", "updated_at")

        wm = manager.get_watermark("events")
        assert wm is not None
        assert wm.table_name == "events"

    def test_get_watermark_not_exists(self):
        """Test getting non-existent watermark returns None."""
        manager = WatermarkManager()
        wm = manager.get_watermark("nonexistent")
        assert wm is None

    def test_update_watermark(self):
        """Test updating existing watermark."""
        manager = WatermarkManager()
        manager.create_watermark("events", "updated_at")

        updated = manager.update_watermark(
            table_name="events",
            last_value="2024-06-15T12:00:00Z",
            row_count=1000,
            sync_id="sync-123",
        )

        assert updated.last_value == "2024-06-15T12:00:00Z"
        assert updated.row_count == 1000

    def test_update_watermark_not_exists_raises(self):
        """Test updating non-existent watermark raises error."""
        manager = WatermarkManager()

        with pytest.raises(WatermarkError, match="No watermark found"):
            manager.update_watermark("nonexistent", "value", 100, "sync-1")

    def test_list_watermarks(self):
        """Test listing all watermarks."""
        manager = WatermarkManager()
        manager.create_watermark("table1", "col1")
        manager.create_watermark("table2", "col2")

        watermarks = manager.list_watermarks()
        assert len(watermarks) == 2

    def test_delete_watermark(self):
        """Test deleting a watermark."""
        manager = WatermarkManager()
        manager.create_watermark("events", "updated_at")

        result = manager.delete_watermark("events")
        assert result is True
        assert manager.get_watermark("events") is None

    def test_delete_watermark_not_exists(self):
        """Test deleting non-existent watermark returns False."""
        manager = WatermarkManager()
        result = manager.delete_watermark("nonexistent")
        assert result is False

    def test_watermark_to_dict(self):
        """Test watermark serialization."""
        manager = WatermarkManager()
        wm = manager.create_watermark("events", "updated_at", "2024-01-01")

        data = wm.to_dict()
        assert "table_name" in data
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_watermark_from_dict(self):
        """Test watermark deserialization."""
        data = {
            "table_name": "events",
            "column_name": "updated_at",
            "last_value": "2024-01-01",
            "last_sync_at": datetime.now(UTC).isoformat(),
            "sync_id": "sync-123",
            "row_count": 500,
        }

        wm = Watermark.from_dict(data)
        assert wm.table_name == "events"
        assert wm.row_count == 500

    def test_watermark_manager_to_dict(self):
        """Test exporting all watermarks as dict."""
        manager = WatermarkManager()
        manager.create_watermark("t1", "c1")
        manager.create_watermark("t2", "c2")

        data = manager.to_dict()
        assert "watermarks" in data
        assert len(data["watermarks"]) == 2
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Test Cases - Schema Evolution
# ============================================================================


class TestSchemaEvolution:
    """Tests for schema evolution handling."""

    def test_create_schema_change(self):
        """Test creating a schema change."""
        change = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="events",
            column_name="new_field",
            data_type="VARCHAR(255)",
            nullable=True,
        )

        assert change.action == SchemaAction.ADD_COLUMN
        assert change.constitutional_hash == CONSTITUTIONAL_HASH

    def test_schema_change_to_dict(self):
        """Test schema change serialization."""
        change = SchemaChange(
            action=SchemaAction.RENAME_COLUMN,
            table_name="events",
            column_name="old_name",
            new_column_name="new_name",
        )

        data = change.to_dict()
        assert data["action"] == "rename_column"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_schema_evolution_manager_detect_changes(self, snowflake_config):
        """Test detecting schema differences."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        manager = SchemaEvolutionManager(connector)

        source_schema = {
            "table_name": "events",
            "columns": [
                {"column_name": "id", "data_type": "INTEGER"},
                {"column_name": "name", "data_type": "VARCHAR(255)"},
                {"column_name": "new_field", "data_type": "TEXT"},  # New
            ],
        }

        target_schema = {
            "table_name": "events",
            "columns": [
                {"column_name": "id", "data_type": "INTEGER"},
                {"column_name": "name", "data_type": "VARCHAR(255)"},
            ],
        }

        changes = await manager.detect_changes(source_schema, target_schema)
        assert len(changes) > 0
        assert any(c.action == SchemaAction.ADD_COLUMN for c in changes)

        await connector.disconnect()

    async def test_schema_evolution_apply_dry_run(self, snowflake_config):
        """Test applying schema changes in dry run mode."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        manager = SchemaEvolutionManager(connector)
        manager._pending_changes = [
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="events",
                column_name="test_col",
                data_type="VARCHAR(100)",
            )
        ]

        results = await manager.apply_changes(dry_run=True)
        assert len(results) == 1
        assert results[0]["status"] == "dry_run"
        assert results[0]["applied"] is False

        await connector.disconnect()

    async def test_schema_evolution_apply_changes(self, snowflake_config):
        """Test applying schema changes."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        manager = SchemaEvolutionManager(connector)
        changes = [
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="events",
                column_name="test_col",
                data_type="VARCHAR(100)",
            )
        ]

        results = await manager.apply_changes(changes=changes)
        assert len(results) == 1
        # Mock connection always succeeds
        assert results[0]["applied"] is True

        await connector.disconnect()

    def test_get_pending_changes(self, snowflake_config):
        """Test getting pending schema changes."""
        connector = SnowflakeConnector(snowflake_config)
        manager = SchemaEvolutionManager(connector)

        assert len(manager.get_pending_changes()) == 0

        manager._pending_changes.append(
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="t",
                column_name="c",
                data_type="INT",
            )
        )

        assert len(manager.get_pending_changes()) == 1


# ============================================================================
# Test Cases - Data Sync Engine
# ============================================================================


class TestDataSyncEngine:
    """Tests for data sync engine."""

    async def test_create_sync_engine(self, snowflake_config, redshift_config):
        """Test creating sync engine."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)

        engine = DataSyncEngine(source, target)
        assert engine.source == source
        assert engine.target == target
        assert engine.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_sync_table_full(self, snowflake_config, redshift_config, sync_config):
        """Test full table sync."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        await source.connect()
        await target.connect()

        engine = DataSyncEngine(source, target)
        sync_config.sync_mode = SyncMode.FULL

        result = await engine.sync_table(sync_config)

        assert result.status == SyncStatus.COMPLETED
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
        assert result.sync_id is not None

        await source.disconnect()
        await target.disconnect()

    async def test_sync_table_incremental(self, snowflake_config, redshift_config, sync_config):
        """Test incremental table sync."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        await source.connect()
        await target.connect()

        engine = DataSyncEngine(source, target)
        sync_config.sync_mode = SyncMode.INCREMENTAL

        result = await engine.sync_table(sync_config)

        assert result.status == SyncStatus.COMPLETED
        # Watermark should be created for incremental
        assert engine.watermark_manager.get_watermark(sync_config.source_table) is not None

        await source.disconnect()
        await target.disconnect()

    async def test_check_schema_compatibility(self, snowflake_config, redshift_config, sync_config):
        """Test schema compatibility check."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        await source.connect()
        await target.connect()

        engine = DataSyncEngine(source, target)

        result = await engine.check_schema_compatibility(sync_config)

        assert "compatible" in result
        assert "source_schema" in result
        assert "target_schema" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

        await source.disconnect()
        await target.disconnect()

    async def test_evolve_schema(self, snowflake_config, redshift_config, sync_config):
        """Test schema evolution."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        await source.connect()
        await target.connect()

        engine = DataSyncEngine(source, target)

        # This returns empty since mock schemas are identical
        results = await engine.evolve_schema(sync_config, dry_run=True)
        assert isinstance(results, list)

        await source.disconnect()
        await target.disconnect()

    def test_get_sync_status(self, snowflake_config, redshift_config):
        """Test getting sync status."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)

        engine = DataSyncEngine(source, target)

        # No sync running
        status = engine.get_sync_status("nonexistent")
        assert status is None

    def test_list_syncs(self, snowflake_config, redshift_config):
        """Test listing sync operations."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)

        engine = DataSyncEngine(source, target)
        syncs = engine.list_syncs()
        assert isinstance(syncs, list)

    def test_build_sync_query_rejects_invalid_source_identifier(
        self,
        snowflake_config,
        redshift_config,
        sync_config,
    ):
        """Ensure source table names are validated before query construction."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)

        sync_config.source_table = "source_events; DROP TABLE users"
        with pytest.raises((ValueError, ACGSValidationError), match="Invalid SQL identifier"):
            engine._build_sync_query(sync_config, watermark=None)

    def test_build_sync_query_rejects_unsafe_filter(
        self,
        snowflake_config,
        redshift_config,
        sync_config,
    ):
        """Ensure filter conditions with SQL control tokens are blocked."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)

        sync_config.filter_condition = "1=1; DROP TABLE x"
        with pytest.raises((ValueError, ACGSValidationError), match="Unsafe filter_condition"):
            engine._build_sync_query(sync_config, watermark=None)

    def test_filter_accepts_simple_equality(
        self,
        snowflake_config,
        redshift_config,
        sync_config,
    ):
        """Valid simple equality filter should be accepted."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "status = 'active'"
        query, _params = engine._build_sync_query(sync_config, watermark=None)
        assert "status = 'active'" in query

    def test_filter_accepts_and_joined_clauses(
        self,
        snowflake_config,
        redshift_config,
        sync_config,
    ):
        """Valid AND-joined clauses should be accepted."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "status = 'active' AND age > 18"
        query, _params = engine._build_sync_query(sync_config, watermark=None)
        assert "status = 'active' AND age > 18" in query

    def test_filter_rejects_or_clauses(self, snowflake_config, redshift_config, sync_config):
        """OR clauses are not in the allowed grammar and should be rejected."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "status = 'active' OR role = 'admin'"
        with pytest.raises(
            (ValueError, ACGSValidationError), match="does not match allowed grammar"
        ):
            engine._build_sync_query(sync_config, watermark=None)

    def test_filter_rejects_subquery(self, snowflake_config, redshift_config, sync_config):
        """Subqueries should be rejected by grammar check."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "id IN ((SELECT id FROM other_table))"
        with pytest.raises((ValueError, ACGSValidationError)):
            engine._build_sync_query(sync_config, watermark=None)

    def test_filter_rejects_union(self, snowflake_config, redshift_config, sync_config):
        """UNION injection should be rejected."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "1=1 UNION SELECT * FROM secrets"
        with pytest.raises((ValueError, ACGSValidationError)):
            engine._build_sync_query(sync_config, watermark=None)

    def test_filter_rejects_empty_clause(self, snowflake_config, redshift_config, sync_config):
        """Empty clause in filter should be rejected."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        sync_config.filter_condition = "status = 'active' AND  AND age > 1"
        with pytest.raises((ValueError, ACGSValidationError)):
            engine._build_sync_query(sync_config, watermark=None)


# ============================================================================
# Test Cases - Sync Scheduler
# ============================================================================


class TestSyncScheduler:
    """Tests for sync scheduler."""

    async def test_create_scheduler(self, snowflake_config, redshift_config):
        """Test creating scheduler."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)

        scheduler = SyncScheduler(engine)
        assert scheduler.constitutional_hash == CONSTITUTIONAL_HASH
        assert not scheduler.is_running

    def test_add_schedule(self, snowflake_config, redshift_config, sync_config, schedule_config):
        """Test adding a sync schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        scheduler.add_schedule("hourly_sync", sync_config, schedule_config)

        schedules = scheduler.list_schedules()
        assert "hourly_sync" in schedules

    def test_remove_schedule(self, snowflake_config, redshift_config, sync_config, schedule_config):
        """Test removing a sync schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        scheduler.add_schedule("test", sync_config, schedule_config)
        result = scheduler.remove_schedule("test")

        assert result is True
        assert "test" not in scheduler.list_schedules()

    def test_remove_schedule_not_exists(self, snowflake_config, redshift_config):
        """Test removing non-existent schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        result = scheduler.remove_schedule("nonexistent")
        assert result is False

    def test_get_schedule(self, snowflake_config, redshift_config, sync_config, schedule_config):
        """Test getting a specific schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        scheduler.add_schedule("test", sync_config, schedule_config)
        schedule = scheduler.get_schedule("test")

        assert schedule is not None
        assert schedule[0] == sync_config
        assert schedule[1] == schedule_config

    def test_parse_cron(self, snowflake_config, redshift_config):
        """Test cron expression parsing."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        parsed = scheduler.parse_cron("0 */2 * * *")
        assert parsed["minute"] == "0"
        assert parsed["hour"] == "*/2"

    def test_parse_cron_invalid(self, snowflake_config, redshift_config):
        """Test invalid cron expression raises error."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        with pytest.raises((ValueError, ACGSValidationError), match="Invalid cron expression"):
            scheduler.parse_cron("invalid")

    def test_should_run_enabled(self, snowflake_config, redshift_config, schedule_config):
        """Test should_run with enabled schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        # Every minute should match
        schedule_config.cron_expression = "* * * * *"
        now = datetime.now(UTC)

        result = scheduler.should_run(schedule_config, now)
        assert result is True

    def test_should_run_disabled(self, snowflake_config, redshift_config, schedule_config):
        """Test should_run with disabled schedule."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        schedule_config.enabled = False
        now = datetime.now(UTC)

        result = scheduler.should_run(schedule_config, now)
        assert result is False

    async def test_scheduler_start_stop(self, snowflake_config, redshift_config):
        """Test starting and stopping scheduler."""
        source = SnowflakeConnector(snowflake_config)
        target = RedshiftConnector(redshift_config)
        engine = DataSyncEngine(source, target)
        scheduler = SyncScheduler(engine)

        await scheduler.start()
        assert scheduler.is_running

        await scheduler.stop()
        assert not scheduler.is_running


# ============================================================================
# Test Cases - Factory Functions
# ============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_connector_snowflake(self, snowflake_config):
        """Test creating Snowflake connector via factory."""
        connector = create_connector(snowflake_config)
        assert isinstance(connector, SnowflakeConnector)

    def test_create_connector_redshift(self, redshift_config):
        """Test creating Redshift connector via factory."""
        connector = create_connector(redshift_config)
        assert isinstance(connector, RedshiftConnector)

    def test_create_connector_bigquery(self, bigquery_config):
        """Test creating BigQuery connector via factory."""
        connector = create_connector(bigquery_config)
        assert isinstance(connector, BigQueryConnector)

    def test_create_connector_invalid_hash(self, snowflake_config):
        """Test factory rejects invalid constitutional hash."""
        snowflake_config.constitutional_hash = "invalid"
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            create_connector(snowflake_config)

    def test_create_sync_engine(self, snowflake_config, redshift_config):
        """Test creating sync engine via factory."""
        engine = create_sync_engine(snowflake_config, redshift_config)
        assert isinstance(engine, DataSyncEngine)
        assert isinstance(engine.source, SnowflakeConnector)
        assert isinstance(engine.target, RedshiftConnector)


# ============================================================================
# Test Cases - Data Serialization
# ============================================================================


class TestDataSerialization:
    """Tests for data serialization."""

    def test_warehouse_config_to_dict(self, snowflake_config):
        """Test warehouse config serialization redacts credentials."""
        data = snowflake_config.to_dict()

        assert "credentials" in data
        # Credentials should be redacted
        for key in data["credentials"]:
            assert data["credentials"][key] == "***REDACTED***"

    def test_sync_config_to_dict(self, sync_config):
        """Test sync config serialization."""
        data = sync_config.to_dict()

        assert data["source_table"] == "source_events"
        assert data["sync_mode"] == "incremental"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_sync_result_to_dict(self):
        """Test sync result serialization."""
        result = SyncResult(
            sync_id="sync-123",
            status=SyncStatus.COMPLETED,
            source_table="src",
            target_table="tgt",
            rows_processed=1000,
            rows_inserted=1000,
        )

        data = result.to_dict()
        assert data["sync_id"] == "sync-123"
        assert data["status"] == "completed"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_schedule_config_to_dict(self, schedule_config):
        """Test schedule config serialization."""
        data = schedule_config.to_dict()

        assert data["cron_expression"] == "0 * * * *"
        assert data["enabled"] is True
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Test Cases - Error Handling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_connection_error(self):
        """Test DataWarehouseConnectionError exception."""
        error = DataWarehouseConnectionError("Failed to connect")
        assert "Failed to connect" in str(error)
        assert isinstance(error, DataWarehouseError)

    def test_sync_error(self):
        """Test SyncError exception."""
        from enhanced_agent_bus.enterprise_sso.data_warehouse import SyncError

        error = SyncError("Sync failed")
        assert "Sync failed" in str(error)
        assert isinstance(error, DataWarehouseError)

    def test_schema_evolution_error(self):
        """Test SchemaEvolutionError exception."""
        error = SchemaEvolutionError("Cannot modify column")
        assert "Cannot modify column" in str(error)
        assert isinstance(error, DataWarehouseError)

    def test_watermark_error(self):
        """Test WatermarkError exception."""
        error = WatermarkError("Invalid watermark")
        assert "Invalid watermark" in str(error)
        assert isinstance(error, DataWarehouseError)


# ============================================================================
# Test Cases - Mock Connection
# ============================================================================


class TestMockConnection:
    """Tests for mock connection."""

    async def test_mock_connection_lifecycle(self):
        """Test mock connection connect/disconnect."""
        conn = MockConnection(
            warehouse_type=WarehouseType.SNOWFLAKE,
            config=WarehouseConfig(
                warehouse_type=WarehouseType.SNOWFLAKE,
                host="test",
                database="test",
            ),
        )

        assert not conn._connected

        await conn.connect()
        assert conn._connected

        await conn.close()
        assert not conn._connected

    async def test_mock_connection_execute(self):
        """Test mock connection query execution."""
        conn = MockConnection(
            warehouse_type=WarehouseType.SNOWFLAKE,
            config=WarehouseConfig(
                warehouse_type=WarehouseType.SNOWFLAKE,
                host="test",
                database="test",
            ),
        )
        await conn.connect()

        result = await conn.execute("SELECT 1")
        assert len(result) > 0
        assert result[0]["result"] == 1

    async def test_mock_connection_batch(self):
        """Test mock connection batch execution."""
        conn = MockConnection(
            warehouse_type=WarehouseType.SNOWFLAKE,
            config=WarehouseConfig(
                warehouse_type=WarehouseType.SNOWFLAKE,
                host="test",
                database="test",
            ),
        )
        await conn.connect()

        data = [{"id": i} for i in range(50)]
        rows = await conn.execute_batch("INSERT", data)
        assert rows == 50


# ============================================================================
# Test Cases - Integration Patterns
# ============================================================================


class TestIntegrationPatterns:
    """Tests for common integration patterns."""

    async def test_snowflake_to_redshift_sync(self, snowflake_config, redshift_config, sync_config):
        """Test Snowflake to Redshift sync pattern."""
        engine = create_sync_engine(snowflake_config, redshift_config)

        await engine.source.connect()
        await engine.target.connect()

        result = await engine.sync_table(sync_config)

        assert result.status == SyncStatus.COMPLETED
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

        await engine.source.disconnect()
        await engine.target.disconnect()

    async def test_bigquery_to_snowflake_sync(self, bigquery_config, snowflake_config, sync_config):
        """Test BigQuery to Snowflake sync pattern."""
        source = BigQueryConnector(bigquery_config)
        target = SnowflakeConnector(snowflake_config)
        engine = DataSyncEngine(source, target)

        await source.connect()
        await target.connect()

        result = await engine.sync_table(sync_config)

        assert result.status == SyncStatus.COMPLETED

        await source.disconnect()
        await target.disconnect()

    async def test_incremental_sync_with_transform(self, snowflake_config, redshift_config):
        """Test incremental sync with transformation function."""

        def transform(row):
            if isinstance(row, dict):
                row["transformed"] = True
            return row

        config = SyncConfig(
            source_table="events",
            target_table="events_transformed",
            sync_mode=SyncMode.INCREMENTAL,
            watermark_column="created_at",
            transform_fn=transform,
        )

        engine = create_sync_engine(snowflake_config, redshift_config)
        await engine.source.connect()
        await engine.target.connect()

        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED

        await engine.source.disconnect()
        await engine.target.disconnect()

    async def test_sync_with_column_mapping(self, snowflake_config, redshift_config):
        """Test sync with column mapping."""
        config = SyncConfig(
            source_table="source_events",
            target_table="target_events",
            sync_mode=SyncMode.FULL,
            column_mapping={
                "src_id": "id",
                "src_name": "name",
                "src_timestamp": "created_at",
            },
        )

        engine = create_sync_engine(snowflake_config, redshift_config)
        await engine.source.connect()
        await engine.target.connect()

        result = await engine.sync_table(config)
        assert result.status == SyncStatus.COMPLETED

        await engine.source.disconnect()
        await engine.target.disconnect()


# ============================================================================
# Test Cases - SQL Injection Prevention
# ============================================================================


class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention in SchemaChange and connectors."""

    # ---- SchemaChange __post_init__ validation ----

    def test_schema_change_rejects_table_name_injection(self):
        """SchemaChange must reject malicious table_name."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="users; DROP TABLE users--",
                column_name="email",
                data_type="VARCHAR(255)",
            )

    def test_schema_change_rejects_column_name_injection(self):
        """SchemaChange must reject malicious column_name."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="users",
                column_name="email' OR '1'='1",
                data_type="VARCHAR(255)",
            )

    def test_schema_change_rejects_new_column_name_injection(self):
        """SchemaChange must reject malicious new_column_name."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            SchemaChange(
                action=SchemaAction.RENAME_COLUMN,
                table_name="users",
                column_name="old_name",
                new_column_name="new'; DROP TABLE users--",
            )

    def test_schema_change_rejects_invalid_data_type(self):
        """SchemaChange must reject invalid data_type."""
        with pytest.raises(ValueError, match="Invalid SQL data type"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="users",
                column_name="email",
                data_type="VARCHAR(255); DROP TABLE users--",
            )

    def test_schema_change_rejects_malicious_default_value(self):
        """SchemaChange must reject SQL injection in default_value."""
        with pytest.raises(ValueError, match="Unsafe default value"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="users",
                column_name="status",
                data_type="VARCHAR(50)",
                default_value="'active'); DROP TABLE users--",
            )

    def test_schema_change_accepts_valid_fields(self):
        """SchemaChange must accept valid identifiers and types."""
        change = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="users",
            column_name="email",
            data_type="VARCHAR(255)",
            default_value="NULL",
        )
        assert change.table_name == "users"
        assert change.column_name == "email"
        assert change.data_type == "VARCHAR(255)"

    def test_schema_change_accepts_dotted_identifiers(self):
        """SchemaChange must accept valid dotted identifiers."""
        change = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="schema_name.table_name",
            column_name="column1",
            data_type="INTEGER",
        )
        assert change.table_name == "schema_name.table_name"

    def test_schema_change_accepts_safe_default_values(self):
        """SchemaChange must accept safe literal default values."""
        for default in [
            "NULL",
            "TRUE",
            "FALSE",
            "CURRENT_TIMESTAMP",
            "'active'",
            "0",
            "3.14",
        ]:
            change = SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="users",
                column_name="col",
                data_type="VARCHAR(50)",
                default_value=default,
            )
            assert str(change.default_value) == default

    # ---- Validation function unit tests ----

    def test_validate_identifier_rejects_semicolons(self):
        """validate_identifier must reject semicolons."""
        with pytest.raises(ValueError):
            validate_identifier("users;--", "test")

    def test_validate_identifier_rejects_spaces(self):
        """validate_identifier must reject spaces."""
        with pytest.raises(ValueError):
            validate_identifier("DROP TABLE", "test")

    def test_validate_identifier_rejects_quotes(self):
        """validate_identifier must reject quotes."""
        with pytest.raises(ValueError):
            validate_identifier("users'", "test")

    def test_validate_identifier_accepts_valid(self):
        """validate_identifier must accept valid identifiers."""
        assert validate_identifier("users", "test") == "users"
        assert validate_identifier("schema.table", "test") == "schema.table"
        assert validate_identifier("db.schema.table", "test") == "db.schema.table"
        assert validate_identifier("_private", "test") == "_private"

    def test_validate_data_type_rejects_injection(self):
        """validate_data_type must reject injection payloads."""
        with pytest.raises(ValueError):
            validate_data_type("INTEGER; DROP TABLE users")

    def test_validate_data_type_accepts_with_length(self):
        """validate_data_type must accept types with length specifiers."""
        assert validate_data_type("VARCHAR(255)") == "VARCHAR(255)"
        assert validate_data_type("DECIMAL(10, 2)") == "DECIMAL(10, 2)"
        assert validate_data_type("INTEGER") == "INTEGER"
        assert validate_data_type("TIMESTAMP") == "TIMESTAMP"

    def test_validate_default_value_rejects_subquery(self):
        """validate_default_value must reject subquery injection."""
        with pytest.raises(ValueError):
            validate_default_value("(SELECT password FROM users LIMIT 1)")

    def test_validate_default_value_rejects_nested_quotes(self):
        """validate_default_value must reject values with nested quote escapes."""
        with pytest.raises(ValueError):
            validate_default_value("'val'); DROP TABLE users--")

    # ---- Connector get_table_schema injection tests ----

    async def test_snowflake_get_table_schema_rejects_injection(self, snowflake_config):
        """Snowflake get_table_schema must reject injected table names."""
        connector = SnowflakeConnector(snowflake_config)
        await connector.connect()

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await connector.get_table_schema("events' UNION SELECT 1,2,3--")

        await connector.disconnect()

    async def test_redshift_get_table_schema_rejects_injection(self, redshift_config):
        """Redshift get_table_schema must reject injected table names."""
        connector = RedshiftConnector(redshift_config)
        await connector.connect()

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await connector.get_table_schema("events'; DROP TABLE users--")

        await connector.disconnect()

    async def test_bigquery_get_table_schema_rejects_injection(self, bigquery_config):
        """BigQuery get_table_schema must reject injected table names."""
        connector = BigQueryConnector(bigquery_config)
        await connector.connect()

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            await connector.get_table_schema("events` UNION ALL SELECT 1--")

        await connector.disconnect()

    # ---- Connector _generate_alter_sql injection tests (via SchemaChange) ----

    def test_alter_sql_injection_blocked_at_schema_change(self):
        """SQL injection in ALTER TABLE DDL is blocked at SchemaChange construction."""
        injection_payloads = [
            {"table_name": "users; DROP TABLE users--", "column_name": "x", "data_type": "INT"},
            {"table_name": "users", "column_name": "x; DROP TABLE y--", "data_type": "INT"},
            {"table_name": "users", "column_name": "x", "data_type": "INT; DROP TABLE z"},
            {
                "table_name": "users",
                "column_name": "x",
                "data_type": "INT",
                "default_value": "0); DROP TABLE a--",
            },
        ]
        for payload in injection_payloads:
            with pytest.raises(ValueError):
                SchemaChange(action=SchemaAction.ADD_COLUMN, **payload)
