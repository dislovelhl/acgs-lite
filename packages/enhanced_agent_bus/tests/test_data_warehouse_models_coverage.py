# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for enterprise_sso/data_warehouse/models.py.

Targets ≥95% coverage of all classes, functions, and branches.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.enterprise_sso.data_warehouse.models import (
    _GCP_PROJECT_ID_RE,
    _SAFE_DEFAULT_RE,
    _SQL_TYPE_BASE,
    # Regex patterns (module-level constants)
    IDENTIFIER_RE,
    BigQueryConfig,
    DataWarehouseConnectionError,
    # Exceptions
    DataWarehouseError,
    RedshiftConfig,
    ScheduleConfig,
    SchemaAction,
    SchemaChange,
    SchemaEvolutionError,
    SnowflakeConfig,
    SyncConfig,
    SyncError,
    SyncMode,
    SyncResult,
    SyncStatus,
    # Dataclasses
    WarehouseConfig,
    # Enums
    WarehouseType,
    Watermark,
    WatermarkError,
    validate_data_type,
    validate_default_value,
    validate_gcp_project_id,
    # Validation functions
    validate_identifier,
)

# ============================================================================
# Module-level regex patterns
# ============================================================================


class TestIdentifierRE:
    """Tests for IDENTIFIER_RE pattern."""

    def test_simple_identifier(self):
        assert IDENTIFIER_RE.fullmatch("my_table") is not None

    def test_identifier_with_uppercase(self):
        assert IDENTIFIER_RE.fullmatch("MyTable") is not None

    def test_identifier_starting_with_underscore(self):
        assert IDENTIFIER_RE.fullmatch("_private") is not None

    def test_dotted_identifier_two_parts(self):
        assert IDENTIFIER_RE.fullmatch("schema.table") is not None

    def test_dotted_identifier_three_parts(self):
        assert IDENTIFIER_RE.fullmatch("project.schema.table") is not None

    def test_identifier_with_hyphen(self):
        # Hyphens allowed for BigQuery project IDs
        assert IDENTIFIER_RE.fullmatch("my-project") is not None

    def test_identifier_with_digits(self):
        assert IDENTIFIER_RE.fullmatch("table1") is not None

    def test_invalid_starts_with_digit(self):
        assert IDENTIFIER_RE.fullmatch("1table") is None

    def test_invalid_empty(self):
        assert IDENTIFIER_RE.fullmatch("") is None

    def test_invalid_special_chars(self):
        assert IDENTIFIER_RE.fullmatch("table!name") is None

    def test_four_part_dotted_invalid(self):
        # Only up to 3 parts allowed
        assert IDENTIFIER_RE.fullmatch("a.b.c.d") is None


class TestGCPProjectIDRE:
    """Tests for _GCP_PROJECT_ID_RE pattern."""

    def test_valid_project_id(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("my-project-123") is not None

    def test_valid_simple(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("myproject") is not None

    def test_invalid_starts_with_digit(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("1project") is None

    def test_invalid_ends_with_hyphen(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("my-project-") is None

    def test_invalid_uppercase(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("MyProject") is None

    def test_invalid_empty(self):
        assert _GCP_PROJECT_ID_RE.fullmatch("") is None

    def test_single_letter(self):
        # Single letter: starts with letter, but ends with a letter or digit required
        # "a" — ends with a letter, which satisfies [a-z0-9] at end
        assert _GCP_PROJECT_ID_RE.fullmatch("a") is None  # regex needs at least 2 chars

    def test_two_letters(self):
        # GCP project IDs require 6-30 characters, so "ab" (2 chars) is invalid
        assert _GCP_PROJECT_ID_RE.fullmatch("ab") is None

    def test_six_letter_minimum(self):
        # Minimum valid GCP project ID: 6 characters
        assert _GCP_PROJECT_ID_RE.fullmatch("abcdef") is not None


class TestSQLTypeRE:
    """Tests for _SQL_TYPE_BASE pattern."""

    def test_varchar(self):
        assert _SQL_TYPE_BASE.fullmatch("VARCHAR") is not None

    def test_varchar_with_length(self):
        assert _SQL_TYPE_BASE.fullmatch("VARCHAR(255)") is not None

    def test_decimal_with_precision_scale(self):
        assert _SQL_TYPE_BASE.fullmatch("DECIMAL(10, 2)") is not None

    def test_integer(self):
        assert _SQL_TYPE_BASE.fullmatch("INTEGER") is not None

    def test_float(self):
        assert _SQL_TYPE_BASE.fullmatch("FLOAT") is not None

    def test_boolean(self):
        assert _SQL_TYPE_BASE.fullmatch("BOOLEAN") is not None

    def test_timestamp(self):
        assert _SQL_TYPE_BASE.fullmatch("TIMESTAMP") is not None

    def test_json(self):
        assert _SQL_TYPE_BASE.fullmatch("JSON") is not None

    def test_string(self):
        assert _SQL_TYPE_BASE.fullmatch("STRING") is not None

    def test_case_insensitive(self):
        assert _SQL_TYPE_BASE.fullmatch("varchar") is not None
        assert _SQL_TYPE_BASE.fullmatch("Integer") is not None

    def test_invalid_type(self):
        assert _SQL_TYPE_BASE.fullmatch("BLOB") is None

    def test_invalid_injection(self):
        assert _SQL_TYPE_BASE.fullmatch("VARCHAR; DROP TABLE users") is None

    def test_all_supported_types(self):
        types = [
            "VARCHAR",
            "INTEGER",
            "INT",
            "FLOAT",
            "BOOLEAN",
            "TIMESTAMP",
            "DATE",
            "TEXT",
            "BIGINT",
            "SMALLINT",
            "DECIMAL",
            "NUMERIC",
            "CHAR",
            "DOUBLE",
            "REAL",
            "BINARY",
            "VARBINARY",
            "JSON",
            "ARRAY",
            "MAP",
            "STRUCT",
            "STRING",
            "NUMBER",
            "VARIANT",
            "OBJECT",
            "SUPER",
            "TIMESTAMPTZ",
            "TIMESTAMP_TZ",
            "TIMESTAMP_LTZ",
            "TIMESTAMP_NTZ",
        ]
        for t in types:
            assert _SQL_TYPE_BASE.fullmatch(t) is not None, f"Type {t!r} should be valid"

    def test_spaces_around_length(self):
        assert _SQL_TYPE_BASE.fullmatch("VARCHAR( 255 )") is not None


class TestSafeDefaultRE:
    """Tests for _SAFE_DEFAULT_RE pattern."""

    def test_null(self):
        assert _SAFE_DEFAULT_RE.fullmatch("NULL") is not None

    def test_true(self):
        assert _SAFE_DEFAULT_RE.fullmatch("TRUE") is not None

    def test_false(self):
        assert _SAFE_DEFAULT_RE.fullmatch("FALSE") is not None

    def test_current_timestamp(self):
        assert _SAFE_DEFAULT_RE.fullmatch("CURRENT_TIMESTAMP") is not None

    def test_quoted_string(self):
        assert _SAFE_DEFAULT_RE.fullmatch("'hello world'") is not None

    def test_empty_quoted_string(self):
        assert _SAFE_DEFAULT_RE.fullmatch("''") is not None

    def test_integer_literal(self):
        assert _SAFE_DEFAULT_RE.fullmatch("42") is not None

    def test_float_literal(self):
        assert _SAFE_DEFAULT_RE.fullmatch("3.14") is not None

    def test_case_insensitive_null(self):
        assert _SAFE_DEFAULT_RE.fullmatch("null") is not None

    def test_invalid_injection(self):
        assert _SAFE_DEFAULT_RE.fullmatch("'; DROP TABLE users; --") is None

    def test_invalid_unquoted_string(self):
        assert _SAFE_DEFAULT_RE.fullmatch("hello") is None

    def test_invalid_nested_quotes(self):
        assert _SAFE_DEFAULT_RE.fullmatch("'it's'") is None


# ============================================================================
# Validation functions
# ============================================================================


class TestValidateIdentifier:
    """Tests for validate_identifier()."""

    def test_valid_simple(self):
        assert validate_identifier("my_table", "table_name") == "my_table"

    def test_valid_dotted(self):
        assert validate_identifier("schema.table", "field") == "schema.table"

    def test_valid_three_parts(self):
        result = validate_identifier("project.schema.table", "field")
        assert result == "project.schema.table"

    def test_valid_with_hyphen(self):
        assert validate_identifier("my-project", "project") == "my-project"

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier for table_name"):
            validate_identifier("1invalid", "table_name")

    def test_invalid_special_chars_raises(self):
        with pytest.raises(ValueError):
            validate_identifier("table; DROP", "name")

    def test_error_message_includes_field_name(self):
        with pytest.raises(ValueError, match="my_field"):
            validate_identifier("!!bad!!", "my_field")

    def test_error_message_includes_value(self):
        with pytest.raises(ValueError, match="bad-value"):
            validate_identifier("bad-value!", "field")


class TestValidateGCPProjectID:
    """Tests for validate_gcp_project_id()."""

    def test_valid_project_id(self):
        assert validate_gcp_project_id("my-project-123") == "my-project-123"

    def test_valid_simple(self):
        assert validate_gcp_project_id("myproject") == "myproject"

    def test_valid_with_numbers(self):
        assert validate_gcp_project_id("project123") == "project123"

    def test_invalid_uppercase_raises(self):
        with pytest.raises(ValueError, match="Invalid GCP project ID"):
            validate_gcp_project_id("MyProject")

    def test_invalid_starts_with_digit_raises(self):
        with pytest.raises(ValueError):
            validate_gcp_project_id("1project")

    def test_invalid_ends_with_hyphen_raises(self):
        with pytest.raises(ValueError):
            validate_gcp_project_id("project-")

    def test_error_message_includes_value(self):
        with pytest.raises(ValueError, match="InvalidProject"):
            validate_gcp_project_id("InvalidProject")


class TestValidateDataType:
    """Tests for validate_data_type()."""

    def test_valid_varchar(self):
        assert validate_data_type("VARCHAR") == "VARCHAR"

    def test_valid_with_length(self):
        assert validate_data_type("VARCHAR(100)") == "VARCHAR(100)"

    def test_valid_integer(self):
        assert validate_data_type("INTEGER") == "INTEGER"

    def test_valid_strips_whitespace_for_check(self):
        # strip() applied before match, but returns original value
        result = validate_data_type("  FLOAT  ")
        assert result == "  FLOAT  "

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid SQL data type"):
            validate_data_type("BLOB")

    def test_invalid_injection_raises(self):
        with pytest.raises(ValueError):
            validate_data_type("VARCHAR; DROP TABLE users")

    def test_error_message_includes_value(self):
        with pytest.raises(ValueError, match="FAKETYPE"):
            validate_data_type("FAKETYPE")


class TestValidateDefaultValue:
    """Tests for validate_default_value()."""

    def test_valid_null(self):
        assert validate_default_value("NULL") == "NULL"

    def test_valid_true(self):
        assert validate_default_value("TRUE") == "TRUE"

    def test_valid_false(self):
        assert validate_default_value("FALSE") == "FALSE"

    def test_valid_current_timestamp(self):
        assert validate_default_value("CURRENT_TIMESTAMP") == "CURRENT_TIMESTAMP"

    def test_valid_quoted_string(self):
        assert validate_default_value("'default'") == "'default'"

    def test_valid_integer(self):
        assert validate_default_value("0") == "0"

    def test_valid_float(self):
        assert validate_default_value("1.5") == "1.5"

    def test_valid_strips_whitespace_for_check(self):
        # strip() applied before match, returns original
        result = validate_default_value("  NULL  ")
        assert result == "  NULL  "

    def test_invalid_unquoted_raises(self):
        with pytest.raises(ValueError, match="Unsafe default value"):
            validate_default_value("hello")

    def test_invalid_injection_raises(self):
        with pytest.raises(ValueError):
            validate_default_value("'; DROP TABLE users; --")

    def test_error_message_includes_value(self):
        with pytest.raises(ValueError, match="bad_default"):
            validate_default_value("bad_default")


# ============================================================================
# Exceptions
# ============================================================================


class TestDataWarehouseError:
    """Tests for DataWarehouseError and subclasses."""

    def test_data_warehouse_error_is_exception(self):
        err = DataWarehouseError("test error")
        assert isinstance(err, DataWarehouseError)

    def test_data_warehouse_error_http_status(self):
        assert DataWarehouseError.http_status_code == 500

    def test_data_warehouse_error_code(self):
        assert DataWarehouseError.error_code == "DATA_WAREHOUSE_ERROR"

    def test_data_warehouse_error_message(self):
        err = DataWarehouseError("something went wrong")
        assert "something went wrong" in str(err)

    def test_connection_error_http_status(self):
        assert DataWarehouseConnectionError.http_status_code == 503

    def test_connection_error_code(self):
        assert DataWarehouseConnectionError.error_code == "DW_CONNECTION_ERROR"

    def test_connection_error_inherits(self):
        err = DataWarehouseConnectionError("conn failed")
        assert isinstance(err, DataWarehouseError)

    def test_sync_error_http_status(self):
        assert SyncError.http_status_code == 500

    def test_sync_error_code(self):
        assert SyncError.error_code == "DW_SYNC_ERROR"

    def test_sync_error_inherits(self):
        err = SyncError("sync failed")
        assert isinstance(err, DataWarehouseError)

    def test_schema_evolution_error_http_status(self):
        assert SchemaEvolutionError.http_status_code == 500

    def test_schema_evolution_error_code(self):
        assert SchemaEvolutionError.error_code == "DW_SCHEMA_EVOLUTION_ERROR"

    def test_schema_evolution_error_inherits(self):
        err = SchemaEvolutionError("schema error")
        assert isinstance(err, DataWarehouseError)

    def test_watermark_error_http_status(self):
        assert WatermarkError.http_status_code == 500

    def test_watermark_error_code(self):
        assert WatermarkError.error_code == "DW_WATERMARK_ERROR"

    def test_watermark_error_inherits(self):
        err = WatermarkError("watermark error")
        assert isinstance(err, DataWarehouseError)

    def test_raise_and_catch_hierarchy(self):
        with pytest.raises(DataWarehouseError):
            raise DataWarehouseConnectionError("caught as base")

    def test_all_subclasses_catchable_as_base(self):
        for cls in [DataWarehouseConnectionError, SyncError, SchemaEvolutionError, WatermarkError]:
            with pytest.raises(DataWarehouseError):
                raise cls("test")


# ============================================================================
# Enums
# ============================================================================


class TestWarehouseType:
    def test_snowflake(self):
        assert WarehouseType.SNOWFLAKE.value == "snowflake"

    def test_redshift(self):
        assert WarehouseType.REDSHIFT.value == "redshift"

    def test_bigquery(self):
        assert WarehouseType.BIGQUERY.value == "bigquery"

    def test_all_values(self):
        values = {t.value for t in WarehouseType}
        assert values == {"snowflake", "redshift", "bigquery"}

    def test_from_value(self):
        assert WarehouseType("snowflake") == WarehouseType.SNOWFLAKE


class TestSyncMode:
    def test_full(self):
        assert SyncMode.FULL.value == "full"

    def test_incremental(self):
        assert SyncMode.INCREMENTAL.value == "incremental"

    def test_merge(self):
        assert SyncMode.MERGE.value == "merge"

    def test_all_values(self):
        values = {m.value for m in SyncMode}
        assert values == {"full", "incremental", "merge"}

    def test_from_value(self):
        assert SyncMode("merge") == SyncMode.MERGE


class TestSchemaAction:
    def test_add_column(self):
        assert SchemaAction.ADD_COLUMN.value == "add_column"

    def test_drop_column(self):
        assert SchemaAction.DROP_COLUMN.value == "drop_column"

    def test_modify_type(self):
        assert SchemaAction.MODIFY_TYPE.value == "modify_type"

    def test_rename_column(self):
        assert SchemaAction.RENAME_COLUMN.value == "rename_column"

    def test_all_values(self):
        values = {a.value for a in SchemaAction}
        assert values == {"add_column", "drop_column", "modify_type", "rename_column"}


class TestSyncStatus:
    def test_pending(self):
        assert SyncStatus.PENDING.value == "pending"

    def test_running(self):
        assert SyncStatus.RUNNING.value == "running"

    def test_completed(self):
        assert SyncStatus.COMPLETED.value == "completed"

    def test_failed(self):
        assert SyncStatus.FAILED.value == "failed"

    def test_cancelled(self):
        assert SyncStatus.CANCELLED.value == "cancelled"

    def test_all_values(self):
        values = {s.value for s in SyncStatus}
        assert values == {"pending", "running", "completed", "failed", "cancelled"}


# ============================================================================
# WarehouseConfig
# ============================================================================


class TestWarehouseConfig:
    def test_default_values(self):
        cfg = WarehouseConfig()
        assert cfg.warehouse_type == WarehouseType.SNOWFLAKE
        assert cfg.host == ""
        assert cfg.database == ""
        assert cfg.schema_name == "public"
        assert cfg.credentials == {}
        assert cfg.connection_timeout == 30
        assert cfg.query_timeout == 300
        assert cfg.pool_size == 5
        assert cfg.ssl_enabled is True
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = WarehouseConfig(
            warehouse_type=WarehouseType.REDSHIFT,
            host="myhost",
            database="mydb",
            schema_name="myschema",
            credentials={"user": "admin", "password": "secret"},
            connection_timeout=60,
            query_timeout=600,
            pool_size=10,
            ssl_enabled=False,
        )
        assert cfg.warehouse_type == WarehouseType.REDSHIFT
        assert cfg.host == "myhost"
        assert cfg.database == "mydb"
        assert cfg.schema_name == "myschema"
        assert cfg.credentials == {"user": "admin", "password": "secret"}
        assert cfg.connection_timeout == 60
        assert cfg.query_timeout == 600
        assert cfg.pool_size == 10
        assert cfg.ssl_enabled is False

    def test_invalid_constitutional_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            WarehouseConfig(constitutional_hash="badbadbadbadbad0")  # pragma: allowlist secret

    def test_to_dict_structure(self):
        cfg = WarehouseConfig(
            host="myhost",
            database="mydb",
            credentials={"user": "admin", "token": "secret"},
        )
        d = cfg.to_dict()
        assert d["warehouse_type"] == "snowflake"
        assert d["host"] == "myhost"
        assert d["database"] == "mydb"
        assert d["schema_name"] == "public"
        assert d["connection_timeout"] == 30
        assert d["query_timeout"] == 300
        assert d["pool_size"] == 5
        assert d["ssl_enabled"] is True
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_redacts_credentials(self):
        cfg = WarehouseConfig(credentials={"user": "admin", "token": "mysecret"})
        d = cfg.to_dict()
        for _key, val in d["credentials"].items():
            assert val == "***REDACTED***"
        assert set(d["credentials"].keys()) == {"user", "token"}

    def test_to_dict_empty_credentials(self):
        cfg = WarehouseConfig()
        d = cfg.to_dict()
        assert d["credentials"] == {}

    def test_credentials_is_independent_default(self):
        cfg1 = WarehouseConfig()
        cfg2 = WarehouseConfig()
        cfg1.credentials["key"] = "val"
        assert cfg2.credentials == {}


# ============================================================================
# SnowflakeConfig
# ============================================================================


class TestSnowflakeConfig:
    def test_default_values(self):
        cfg = SnowflakeConfig()
        assert cfg.warehouse_type == WarehouseType.SNOWFLAKE
        assert cfg.account == ""
        assert cfg.warehouse == "COMPUTE_WH"
        assert cfg.role == "PUBLIC"
        assert cfg.authenticator == "snowflake"

    def test_custom_values(self):
        cfg = SnowflakeConfig(
            account="myaccount",
            warehouse="MY_WH",
            role="SYSADMIN",
            authenticator="oauth",
            host="myhost",
            database="mydb",
        )
        assert cfg.account == "myaccount"
        assert cfg.warehouse == "MY_WH"
        assert cfg.role == "SYSADMIN"
        assert cfg.authenticator == "oauth"

    def test_get_connection_string(self):
        cfg = SnowflakeConfig(account="myaccount", database="mydb", schema_name="myschema")
        conn_str = cfg.get_connection_string()
        assert conn_str == "snowflake://myaccount/mydb/myschema"

    def test_get_connection_string_defaults(self):
        cfg = SnowflakeConfig()
        conn_str = cfg.get_connection_string()
        # account="", database="", schema_name defaults to "public"
        assert conn_str == "snowflake:////public"

    def test_inherits_warehouse_config(self):
        assert issubclass(SnowflakeConfig, WarehouseConfig)

    def test_inherits_to_dict(self):
        cfg = SnowflakeConfig(credentials={"user": "u"})
        d = cfg.to_dict()
        assert d["credentials"] == {"user": "***REDACTED***"}

    def test_invalid_hash_propagates(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            SnowflakeConfig(constitutional_hash="0000000000000000")  # pragma: allowlist secret


# ============================================================================
# RedshiftConfig
# ============================================================================


class TestRedshiftConfig:
    def test_default_values(self):
        cfg = RedshiftConfig()
        assert cfg.warehouse_type == WarehouseType.REDSHIFT
        assert cfg.port == 5439
        assert cfg.iam_role is None
        assert cfg.s3_staging_bucket is None
        assert cfg.region == "us-east-1"

    def test_custom_values(self):
        cfg = RedshiftConfig(
            host="myhost",
            database="mydb",
            port=5440,
            iam_role="arn:aws:iam::123:role/MyRole",
            s3_staging_bucket="mybucket",
            region="eu-west-1",
        )
        assert cfg.port == 5440
        assert cfg.iam_role == "arn:aws:iam::123:role/MyRole"
        assert cfg.s3_staging_bucket == "mybucket"
        assert cfg.region == "eu-west-1"

    def test_get_connection_string(self):
        cfg = RedshiftConfig(host="myhost", port=5439, database="mydb")
        conn_str = cfg.get_connection_string()
        assert conn_str == "jdbc:redshift://myhost:5439/mydb"

    def test_get_connection_string_custom_port(self):
        cfg = RedshiftConfig(host="h", port=1234, database="db")
        assert "1234" in cfg.get_connection_string()

    def test_inherits_warehouse_config(self):
        assert issubclass(RedshiftConfig, WarehouseConfig)


# ============================================================================
# BigQueryConfig
# ============================================================================


class TestBigQueryConfig:
    def test_default_values(self):
        cfg = BigQueryConfig()
        assert cfg.warehouse_type == WarehouseType.BIGQUERY
        assert cfg.project_id == ""
        assert cfg.dataset == ""
        assert cfg.location == "US"
        assert cfg.credentials_path is None
        assert cfg.use_streaming is True

    def test_custom_values(self):
        cfg = BigQueryConfig(
            project_id="my-project",
            dataset="my_dataset",
            location="EU",
            credentials_path="/path/to/creds.json",
            use_streaming=False,
        )
        assert cfg.project_id == "my-project"
        assert cfg.dataset == "my_dataset"
        assert cfg.location == "EU"
        assert cfg.credentials_path == "/path/to/creds.json"
        assert cfg.use_streaming is False

    def test_get_connection_string(self):
        cfg = BigQueryConfig(project_id="my-project", dataset="my_dataset")
        conn_str = cfg.get_connection_string()
        assert conn_str == "bigquery://my-project/my_dataset"

    def test_get_connection_string_defaults(self):
        cfg = BigQueryConfig()
        conn_str = cfg.get_connection_string()
        # project_id="", dataset="" → "bigquery:///"
        assert conn_str == "bigquery:///"

    def test_inherits_warehouse_config(self):
        assert issubclass(BigQueryConfig, WarehouseConfig)


# ============================================================================
# Watermark
# ============================================================================


class TestWatermark:
    def _make(self, **kwargs):
        defaults = {
            "table_name": "users",
            "column_name": "updated_at",
            "last_value": "2024-01-01T00:00:00",
            "last_sync_at": datetime(2024, 1, 1, 0, 0, 0),
            "sync_id": "sync-001",
        }
        defaults.update(kwargs)
        return Watermark(**defaults)

    def test_basic_creation(self):
        wm = self._make()
        assert wm.table_name == "users"
        assert wm.column_name == "updated_at"
        assert wm.last_value == "2024-01-01T00:00:00"
        assert wm.row_count == 0
        assert wm.constitutional_hash == CONSTITUTIONAL_HASH

    def test_row_count_default(self):
        wm = self._make()
        assert wm.row_count == 0

    def test_custom_row_count(self):
        wm = self._make(row_count=500)
        assert wm.row_count == 500

    def test_last_value_integer(self):
        wm = self._make(last_value=42)
        assert wm.last_value == 42

    def test_last_value_float(self):
        wm = self._make(last_value=3.14)
        assert wm.last_value == 3.14

    def test_last_value_none(self):
        wm = self._make(last_value=None)
        assert wm.last_value is None

    def test_to_dict_basic(self):
        now = datetime(2024, 6, 15, 12, 0, 0)
        wm = Watermark(
            table_name="orders",
            column_name="created_at",
            last_value="2024-06-01",
            last_sync_at=now,
            sync_id="sync-abc",
            row_count=100,
        )
        d = wm.to_dict()
        assert d["table_name"] == "orders"
        assert d["column_name"] == "created_at"
        assert d["last_value"] == "2024-06-01"
        assert d["last_sync_at"] == now.isoformat()
        assert d["sync_id"] == "sync-abc"
        assert d["row_count"] == 100
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_last_value_none(self):
        now = datetime(2024, 1, 1)
        wm = Watermark(
            table_name="t",
            column_name="c",
            last_value=None,
            last_sync_at=now,
            sync_id="s1",
        )
        d = wm.to_dict()
        assert d["last_value"] is None

    def test_to_dict_last_value_integer(self):
        now = datetime(2024, 1, 1)
        wm = Watermark(
            table_name="t",
            column_name="c",
            last_value=99,
            last_sync_at=now,
            sync_id="s1",
        )
        d = wm.to_dict()
        assert d["last_value"] == "99"

    def test_from_dict_roundtrip(self):
        now = datetime(2024, 3, 20, 10, 30, 0)
        original = Watermark(
            table_name="products",
            column_name="modified_at",
            last_value="2024-03-01",
            last_sync_at=now,
            sync_id="sync-xyz",
            row_count=250,
        )
        d = original.to_dict()
        restored = Watermark.from_dict(d)
        assert restored.table_name == original.table_name
        assert restored.column_name == original.column_name
        assert restored.last_value == original.last_value
        assert restored.sync_id == original.sync_id
        assert restored.row_count == original.row_count
        assert restored.constitutional_hash == CONSTITUTIONAL_HASH

    def test_from_dict_missing_optional_fields(self):
        data = {
            "table_name": "t",
            "column_name": "c",
            "last_sync_at": "2024-01-01T00:00:00",
            "sync_id": "s1",
        }
        wm = Watermark.from_dict(data)
        assert wm.last_value is None
        assert wm.row_count == 0
        assert wm.constitutional_hash == CONSTITUTIONAL_HASH

    def test_from_dict_custom_hash(self):
        data = {
            "table_name": "t",
            "column_name": "c",
            "last_sync_at": "2024-01-01T00:00:00",
            "sync_id": "s1",
            "constitutional_hash": "custom_hash_value",
        }
        wm = Watermark.from_dict(data)
        assert wm.constitutional_hash == "custom_hash_value"


# ============================================================================
# SyncConfig
# ============================================================================


class TestSyncConfig:
    def test_basic_creation(self):
        cfg = SyncConfig(source_table="src", target_table="tgt")
        assert cfg.source_table == "src"
        assert cfg.target_table == "tgt"
        assert cfg.sync_mode == SyncMode.INCREMENTAL
        assert cfg.watermark_column is None
        assert cfg.batch_size == 10000
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 5.0
        assert cfg.transform_fn is None
        assert cfg.filter_condition is None
        assert cfg.column_mapping == {}
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_sync_mode(self):
        cfg = SyncConfig(source_table="s", target_table="t", sync_mode=SyncMode.FULL)
        assert cfg.sync_mode == SyncMode.FULL

    def test_with_transform_fn(self):
        def fn(x):
            return x

        cfg = SyncConfig(source_table="s", target_table="t", transform_fn=fn)
        assert cfg.transform_fn is fn

    def test_with_column_mapping(self):
        mapping = {"src_col": "dst_col", "id": "user_id"}
        cfg = SyncConfig(source_table="s", target_table="t", column_mapping=mapping)
        assert cfg.column_mapping == mapping

    def test_to_dict_no_transform(self):
        cfg = SyncConfig(source_table="src", target_table="tgt")
        d = cfg.to_dict()
        assert d["source_table"] == "src"
        assert d["target_table"] == "tgt"
        assert d["sync_mode"] == "incremental"
        assert d["watermark_column"] is None
        assert d["batch_size"] == 10000
        assert d["max_retries"] == 3
        assert d["retry_delay"] == 5.0
        assert d["has_transform"] is False
        assert d["filter_condition"] is None
        assert d["column_mapping"] == {}
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_transform(self):
        cfg = SyncConfig(
            source_table="src",
            target_table="tgt",
            transform_fn=lambda x: x,
        )
        d = cfg.to_dict()
        assert d["has_transform"] is True

    def test_to_dict_full_mode(self):
        cfg = SyncConfig(
            source_table="s",
            target_table="t",
            sync_mode=SyncMode.MERGE,
            watermark_column="updated_at",
            batch_size=500,
            max_retries=5,
            retry_delay=10.0,
            filter_condition="status = 'active'",
            column_mapping={"a": "b"},
        )
        d = cfg.to_dict()
        assert d["sync_mode"] == "merge"
        assert d["watermark_column"] == "updated_at"
        assert d["batch_size"] == 500
        assert d["max_retries"] == 5
        assert d["retry_delay"] == 10.0
        assert d["filter_condition"] == "status = 'active'"
        assert d["column_mapping"] == {"a": "b"}

    def test_column_mapping_independent_default(self):
        cfg1 = SyncConfig(source_table="s", target_table="t")
        cfg2 = SyncConfig(source_table="s", target_table="t")
        cfg1.column_mapping["key"] = "val"
        assert cfg2.column_mapping == {}


# ============================================================================
# SyncResult
# ============================================================================


class TestSyncResult:
    def _make(self, **kwargs):
        defaults = {
            "sync_id": "sync-001",
            "status": SyncStatus.COMPLETED,
            "source_table": "src",
            "target_table": "tgt",
        }
        defaults.update(kwargs)
        return SyncResult(**defaults)

    def test_default_values(self):
        result = self._make()
        assert result.sync_id == "sync-001"
        assert result.status == SyncStatus.COMPLETED
        assert result.rows_processed == 0
        assert result.rows_inserted == 0
        assert result.rows_updated == 0
        assert result.rows_deleted == 0
        assert result.started_at is None
        assert result.completed_at is None
        assert result.error_message is None
        assert result.watermark is None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        now = datetime(2024, 5, 1, 8, 0, 0)
        result = self._make(
            rows_processed=1000,
            rows_inserted=800,
            rows_updated=150,
            rows_deleted=50,
            started_at=now,
            completed_at=now,
            error_message=None,
        )
        assert result.rows_processed == 1000
        assert result.rows_inserted == 800
        assert result.rows_updated == 150
        assert result.rows_deleted == 50
        assert result.started_at == now
        assert result.completed_at == now

    def test_failed_status_with_error(self):
        result = self._make(status=SyncStatus.FAILED, error_message="Connection refused")
        assert result.status == SyncStatus.FAILED
        assert result.error_message == "Connection refused"

    def test_to_dict_basic(self):
        result = self._make()
        d = result.to_dict()
        assert d["sync_id"] == "sync-001"
        assert d["status"] == "completed"
        assert d["source_table"] == "src"
        assert d["target_table"] == "tgt"
        assert d["rows_processed"] == 0
        assert d["rows_inserted"] == 0
        assert d["rows_updated"] == 0
        assert d["rows_deleted"] == 0
        assert d["started_at"] is None
        assert d["completed_at"] is None
        assert d["error_message"] is None
        assert d["watermark"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_datetimes(self):
        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 5, 0)
        result = self._make(started_at=start, completed_at=end)
        d = result.to_dict()
        assert d["started_at"] == start.isoformat()
        assert d["completed_at"] == end.isoformat()

    def test_to_dict_with_watermark(self):
        now = datetime(2024, 1, 1)
        wm = Watermark(
            table_name="tgt",
            column_name="updated_at",
            last_value="2024-01-01",
            last_sync_at=now,
            sync_id="sync-001",
            row_count=100,
        )
        result = self._make(watermark=wm)
        d = result.to_dict()
        assert d["watermark"] is not None
        assert d["watermark"]["table_name"] == "tgt"
        assert d["watermark"]["sync_id"] == "sync-001"

    def test_to_dict_started_at_none(self):
        result = self._make(started_at=None)
        assert result.to_dict()["started_at"] is None

    def test_to_dict_completed_at_none(self):
        result = self._make(completed_at=None)
        assert result.to_dict()["completed_at"] is None

    def test_all_status_values(self):
        for status in SyncStatus:
            result = self._make(status=status)
            d = result.to_dict()
            assert d["status"] == status.value


# ============================================================================
# SchemaChange
# ============================================================================


class TestSchemaChange:
    def test_add_column_basic(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="users",
            column_name="email",
            data_type="VARCHAR(255)",
        )
        assert sc.action == SchemaAction.ADD_COLUMN
        assert sc.table_name == "users"
        assert sc.column_name == "email"
        assert sc.data_type == "VARCHAR(255)"
        assert sc.nullable is True
        assert sc.default_value is None
        assert sc.new_column_name is None
        assert sc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_rename_column(self):
        sc = SchemaChange(
            action=SchemaAction.RENAME_COLUMN,
            table_name="orders",
            column_name="old_name",
            new_column_name="new_name",
        )
        assert sc.new_column_name == "new_name"

    def test_drop_column(self):
        sc = SchemaChange(
            action=SchemaAction.DROP_COLUMN,
            table_name="products",
            column_name="deprecated_field",
        )
        assert sc.action == SchemaAction.DROP_COLUMN

    def test_modify_type(self):
        sc = SchemaChange(
            action=SchemaAction.MODIFY_TYPE,
            table_name="events",
            column_name="payload",
            data_type="TEXT",
        )
        assert sc.data_type == "TEXT"

    def test_with_default_value(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="users",
            column_name="active",
            data_type="BOOLEAN",
            default_value="TRUE",
        )
        assert sc.default_value == "TRUE"

    def test_with_nullable_false(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="users",
            column_name="name",
            data_type="VARCHAR(100)",
            nullable=False,
        )
        assert sc.nullable is False

    def test_invalid_table_name_raises(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier for table_name"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="1invalid",
                column_name="col",
            )

    def test_invalid_column_name_raises(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier for column_name"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="valid_table",
                column_name="!bad_col",
            )

    def test_invalid_new_column_name_raises(self):
        with pytest.raises(ValueError, match="Invalid SQL identifier for new_column_name"):
            SchemaChange(
                action=SchemaAction.RENAME_COLUMN,
                table_name="valid_table",
                column_name="old_col",
                new_column_name="1bad",
            )

    def test_invalid_data_type_raises(self):
        with pytest.raises(ValueError, match="Invalid SQL data type"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="t",
                column_name="c",
                data_type="BLOB",
            )

    def test_invalid_default_value_raises(self):
        with pytest.raises(ValueError, match="Unsafe default value"):
            SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="t",
                column_name="c",
                data_type="VARCHAR(10)",
                default_value="bad_value",
            )

    def test_new_column_name_none_no_validation(self):
        # new_column_name=None should not be validated
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="t",
            column_name="c",
            new_column_name=None,
        )
        assert sc.new_column_name is None

    def test_data_type_none_no_validation(self):
        sc = SchemaChange(
            action=SchemaAction.DROP_COLUMN,
            table_name="t",
            column_name="c",
            data_type=None,
        )
        assert sc.data_type is None

    def test_default_value_none_no_validation(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="t",
            column_name="c",
            default_value=None,
        )
        assert sc.default_value is None

    def test_to_dict_basic(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="users",
            column_name="score",
            data_type="INTEGER",
            nullable=False,
        )
        d = sc.to_dict()
        assert d["action"] == "add_column"
        assert d["table_name"] == "users"
        assert d["column_name"] == "score"
        assert d["new_column_name"] is None
        assert d["data_type"] == "INTEGER"
        assert d["nullable"] is False
        assert d["default_value"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_default_value(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="t",
            column_name="c",
            data_type="INTEGER",
            default_value="0",
        )
        d = sc.to_dict()
        assert d["default_value"] == "0"

    def test_to_dict_with_new_column_name(self):
        sc = SchemaChange(
            action=SchemaAction.RENAME_COLUMN,
            table_name="t",
            column_name="old_name",
            new_column_name="new_name",
        )
        d = sc.to_dict()
        assert d["new_column_name"] == "new_name"

    def test_to_dict_default_value_none(self):
        sc = SchemaChange(
            action=SchemaAction.DROP_COLUMN,
            table_name="t",
            column_name="c",
        )
        d = sc.to_dict()
        assert d["default_value"] is None

    def test_dotted_table_name_valid(self):
        sc = SchemaChange(
            action=SchemaAction.ADD_COLUMN,
            table_name="schema.users",
            column_name="col",
        )
        assert sc.table_name == "schema.users"

    def test_all_actions(self):
        for action in SchemaAction:
            sc = SchemaChange(
                action=action,
                table_name="t",
                column_name="c",
            )
            d = sc.to_dict()
            assert d["action"] == action.value


# ============================================================================
# ScheduleConfig
# ============================================================================


class TestScheduleConfig:
    def test_default_values(self):
        cfg = ScheduleConfig(cron_expression="0 * * * *")
        assert cfg.cron_expression == "0 * * * *"
        assert cfg.enabled is True
        assert cfg.timezone == "UTC"
        assert cfg.max_concurrent == 1
        assert cfg.timeout_seconds == 3600
        assert cfg.retry_on_failure is True
        assert cfg.notification_email is None
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = ScheduleConfig(
            cron_expression="0 0 * * *",
            enabled=False,
            timezone="America/New_York",
            max_concurrent=5,
            timeout_seconds=7200,
            retry_on_failure=False,
            notification_email="admin@example.com",
        )
        assert cfg.enabled is False
        assert cfg.timezone == "America/New_York"
        assert cfg.max_concurrent == 5
        assert cfg.timeout_seconds == 7200
        assert cfg.retry_on_failure is False
        assert cfg.notification_email == "admin@example.com"

    def test_to_dict_basic(self):
        cfg = ScheduleConfig(cron_expression="30 6 * * 1")
        d = cfg.to_dict()
        assert d["cron_expression"] == "30 6 * * 1"
        assert d["enabled"] is True
        assert d["timezone"] == "UTC"
        assert d["max_concurrent"] == 1
        assert d["timeout_seconds"] == 3600
        assert d["retry_on_failure"] is True
        assert d["notification_email"] is None
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_disabled(self):
        cfg = ScheduleConfig(cron_expression="* * * * *", enabled=False)
        d = cfg.to_dict()
        assert d["enabled"] is False

    def test_to_dict_with_email(self):
        cfg = ScheduleConfig(
            cron_expression="0 1 * * *",
            notification_email="ops@example.com",
        )
        d = cfg.to_dict()
        assert d["notification_email"] == "ops@example.com"

    def test_to_dict_no_retry(self):
        cfg = ScheduleConfig(cron_expression="* * * * *", retry_on_failure=False)
        d = cfg.to_dict()
        assert d["retry_on_failure"] is False

    def test_to_dict_contains_hash(self):
        cfg = ScheduleConfig(cron_expression="0 0 1 * *")
        d = cfg.to_dict()
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Integration / cross-class tests
# ============================================================================


class TestIntegration:
    """Cross-class integration tests."""

    def test_sync_result_with_full_watermark_roundtrip(self):
        """SyncResult with embedded Watermark serializes correctly."""
        now = datetime(2024, 6, 1, 12, 0, 0)
        wm = Watermark(
            table_name="events",
            column_name="event_time",
            last_value="2024-06-01T11:59:59",
            last_sync_at=now,
            sync_id="sync-999",
            row_count=5000,
        )
        result = SyncResult(
            sync_id="sync-999",
            status=SyncStatus.COMPLETED,
            source_table="events",
            target_table="events_dw",
            rows_processed=5000,
            rows_inserted=4500,
            rows_updated=500,
            rows_deleted=0,
            started_at=now,
            completed_at=now,
            watermark=wm,
        )
        d = result.to_dict()
        assert d["watermark"]["table_name"] == "events"
        assert d["watermark"]["row_count"] == 5000
        assert d["rows_processed"] == 5000

    def test_warehouse_configs_inherit_constitutional_hash(self):
        """All warehouse config types default to the constitutional hash."""
        configs = [WarehouseConfig(), SnowflakeConfig(), RedshiftConfig(), BigQueryConfig()]
        for cfg in configs:
            assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_schema_change_all_valid_data_types(self):
        """SchemaChange accepts all allowed SQL data types."""
        for dtype in ["VARCHAR(50)", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP", "JSON"]:
            sc = SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="t",
                column_name="c",
                data_type=dtype,
            )
            assert sc.data_type == dtype

    def test_schema_change_all_safe_defaults(self):
        """SchemaChange accepts all safe default patterns."""
        safe_defaults = ["NULL", "TRUE", "FALSE", "CURRENT_TIMESTAMP", "'value'", "42", "3.14"]
        for default in safe_defaults:
            sc = SchemaChange(
                action=SchemaAction.ADD_COLUMN,
                table_name="t",
                column_name="c",
                default_value=default,
            )
            assert sc.default_value == default

    def test_sync_config_all_sync_modes(self):
        """SyncConfig serializes all SyncMode values correctly."""
        for mode in SyncMode:
            cfg = SyncConfig(source_table="s", target_table="t", sync_mode=mode)
            d = cfg.to_dict()
            assert d["sync_mode"] == mode.value

    def test_warehouse_to_dict_preserves_warehouse_type(self):
        """to_dict serializes warehouse_type as enum value string."""
        for wtype in WarehouseType:
            cfg = WarehouseConfig(warehouse_type=wtype)
            d = cfg.to_dict()
            assert d["warehouse_type"] == wtype.value
