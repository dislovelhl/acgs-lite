"""
ACGS-2 Enhanced Agent Bus - Schema Evolution Tests
Constitutional Hash: 608508a9bd224290

Tests for the event schema evolution strategy including:
- Schema versioning
- Backward compatibility validation
- Schema registry operations
- Migration utilities
"""

from datetime import datetime, timezone
from typing import ClassVar
from unittest.mock import patch

import pytest

import enhanced_agent_bus.schema_evolution as schema_evolution_module
from enhanced_agent_bus.schema_evolution import (
    AGENT_MESSAGE_SCHEMA_V1,
    AGENT_MESSAGE_SCHEMA_V1_1,
    AGENT_MESSAGE_SCHEMA_V1_2,
    CONSTITUTIONAL_HASH,
    CompatibilityChecker,
    EvolutionType,
    MigrationStatus,
    SchemaCompatibility,
    SchemaDefinition,
    SchemaEvolutionChange,
    SchemaFieldDefinition,
    SchemaMigration,
    SchemaMigrator,
    SchemaRegistry,
    SchemaVersion,
    VersionedMessageBase,
    create_default_registry,
)


@pytest.fixture(autouse=True)
def _reset_fast_hash_state():
    """Restore FAST_HASH_AVAILABLE *and* fast_hash after each test (PM-012 pattern).

    Uses ``patch.dict`` on the module's ``__dict__`` to atomically snapshot
    and restore both ``FAST_HASH_AVAILABLE`` and ``fast_hash``.  This avoids
    the ordering race between pytest's ``monkeypatch`` undo and fixture
    teardown that caused the previous ``delattr``/``setattr`` approach to
    fail under xdist loadscope — ``patch.dict`` restores the dict to its
    exact original state (adding back removed keys, removing added keys)
    in a single operation.
    """
    # patch.dict with clear=False snapshots the current __dict__ and restores
    # it on __exit__, including removing any keys that were added during the
    # test.  We pass an empty dict so nothing is changed at setup time.
    with patch.dict(schema_evolution_module.__dict__):
        yield


# ============================================================================
# Constitutional Hash Compliance Tests
# ============================================================================


class TestConstitutionalHashCompliance:
    """Test constitutional hash compliance in schema evolution."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_schema_definition_requires_valid_hash(self):
        """Test that schema definition requires valid constitutional hash."""
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            SchemaDefinition(
                schema_id="test",
                name="Test",
                version="1.0.0",
                constitutional_hash="invalid_hash",
            )

    def test_predefined_schemas_have_valid_hash(self):
        """Test all predefined schemas have valid constitutional hash."""
        assert AGENT_MESSAGE_SCHEMA_V1.constitutional_hash == CONSTITUTIONAL_HASH
        assert AGENT_MESSAGE_SCHEMA_V1_1.constitutional_hash == CONSTITUTIONAL_HASH
        assert AGENT_MESSAGE_SCHEMA_V1_2.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# SchemaVersion Tests
# ============================================================================


class TestSchemaVersion:
    """Test SchemaVersion parsing and comparison."""

    def test_parse_simple_version(self):
        """Test parsing simple version string."""
        v = SchemaVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.prerelease == ""

    def test_parse_version_with_prerelease(self):
        """Test parsing version with prerelease tag."""
        v = SchemaVersion.parse("1.0.0-beta")
        assert v.major == 1
        assert v.minor == 0
        assert v.patch == 0
        assert v.prerelease == "beta"

    def test_parse_invalid_version(self):
        """Test parsing invalid version raises error."""
        with pytest.raises(ValueError, match="Invalid version format"):
            SchemaVersion.parse("1.2")

    def test_version_string_representation(self):
        """Test version string representation."""
        v = SchemaVersion(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

        v_pre = SchemaVersion(major=1, minor=0, patch=0, prerelease="alpha")
        assert str(v_pre) == "1.0.0-alpha"

    def test_version_comparison_less_than(self):
        """Test version less than comparison."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.1.0")
        v3 = SchemaVersion.parse("2.0.0")

        assert v1 < v2
        assert v2 < v3
        assert v1 < v3

    def test_version_comparison_equal(self):
        """Test version equality comparison."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.0.0")

        assert v1 == v2
        assert not (v1 < v2)
        assert not (v1 > v2)

    def test_version_comparison_with_prerelease(self):
        """Test prerelease versions are lower than release."""
        v1 = SchemaVersion.parse("1.0.0-beta")
        v2 = SchemaVersion.parse("1.0.0")

        assert v1 < v2

    def test_version_hash(self):
        """Test version can be used in sets/dicts."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.0.0")
        v3 = SchemaVersion.parse("1.0.1")

        version_set = {v1, v2, v3}
        assert len(version_set) == 2

    def test_version_compatibility_backward(self):
        """Test backward compatibility check."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.1.0")

        # v2 (newer) should be backward compatible with v1 (older)
        assert v2.is_compatible_with(v1, SchemaCompatibility.BACKWARD)
        # v1 is not backward compatible with v2 (can't read newer data)
        assert not v1.is_compatible_with(v2, SchemaCompatibility.BACKWARD)

    def test_version_compatibility_forward(self):
        """Test forward compatibility check."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.1.0")

        # v1 (older) should be forward compatible with v2 (newer)
        assert v1.is_compatible_with(v2, SchemaCompatibility.FORWARD)

    def test_version_compatibility_full(self):
        """Test full compatibility requires same major and minor."""
        v1 = SchemaVersion.parse("1.0.0")
        v2 = SchemaVersion.parse("1.0.1")
        v3 = SchemaVersion.parse("1.1.0")

        assert v1.is_compatible_with(v2, SchemaCompatibility.FULL)
        assert not v1.is_compatible_with(v3, SchemaCompatibility.FULL)


# ============================================================================
# SchemaFieldDefinition Tests
# ============================================================================


class TestSchemaFieldDefinition:
    """Test SchemaFieldDefinition model."""

    def test_field_definition_basic(self):
        """Test basic field definition."""
        field = SchemaFieldDefinition(
            name="message_id",
            field_type="str",
        )
        assert field.name == "message_id"
        assert field.field_type == "str"
        assert field.required is True
        assert field.deprecated is False

    def test_field_definition_optional(self):
        """Test optional field definition."""
        field = SchemaFieldDefinition(
            name="metadata",
            field_type="dict",
            required=False,
            default={},
        )
        assert field.required is False
        assert field.default == {}

    def test_field_definition_deprecated(self):
        """Test deprecated field definition."""
        field = SchemaFieldDefinition(
            name="old_field",
            field_type="str",
            deprecated=True,
            deprecated_since="1.2.0",
        )
        assert field.deprecated is True
        assert field.deprecated_since == "1.2.0"


# ============================================================================
# SchemaDefinition Tests
# ============================================================================


class TestSchemaDefinition:
    """Test SchemaDefinition model."""

    def test_schema_definition_basic(self):
        """Test basic schema definition."""
        schema = SchemaDefinition(
            schema_id="test_schema",
            name="TestMessage",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="data", field_type="dict", required=False),
            ],
        )
        assert schema.schema_id == "test_schema"
        assert schema.name == "TestMessage"
        assert schema.version == "1.0.0"
        assert len(schema.fields) == 2

    def test_schema_get_version(self):
        """Test getting parsed version."""
        schema = SchemaDefinition(
            schema_id="test",
            name="Test",
            version="1.2.3",
        )
        v = schema.get_version()
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_schema_compute_fingerprint(self):
        """Test computing schema fingerprint."""
        schema = SchemaDefinition(
            schema_id="test",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        fingerprint = schema.compute_fingerprint()
        assert len(fingerprint) == 16
        assert isinstance(fingerprint, str)

    def test_schema_fingerprint_consistency(self):
        """Test fingerprint is consistent for same schema."""
        schema1 = SchemaDefinition(
            schema_id="test1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        schema2 = SchemaDefinition(
            schema_id="test2",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        assert schema1.compute_fingerprint() == schema2.compute_fingerprint()

    def test_schema_fingerprint_uses_fast_kernel_when_available(self):
        """Test schema fingerprint uses fast hash kernel when available.

        Patches the globals dict that ``compute_fingerprint`` actually
        resolves names through (its ``__globals__``), which may differ
        from ``schema_evolution_module.__dict__`` under importlib import
        mode.  The autouse ``patch.dict`` still restores the module-level
        dict after the test.
        """
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        # Patch both the test-visible module dict AND the method's own
        # globals dict (they can be different objects under importlib).
        method_globals = SchemaDefinition.compute_fingerprint.__globals__
        schema_evolution_module.FAST_HASH_AVAILABLE = True
        schema_evolution_module.fast_hash = _fake_fast_hash
        orig_avail = method_globals.get("FAST_HASH_AVAILABLE")
        orig_fh = method_globals.get("fast_hash")
        method_globals["FAST_HASH_AVAILABLE"] = True
        method_globals["fast_hash"] = _fake_fast_hash

        try:
            schema = SchemaDefinition(
                schema_id="test",
                name="Test",
                version="1.0.0",
                fields=[SchemaFieldDefinition(name="id", field_type="str")],
            )
            fingerprint = schema.compute_fingerprint()

            assert called["value"] is True
            assert fingerprint == "000000000000beef"
        finally:
            # Restore method globals to avoid polluting other tests.
            method_globals["FAST_HASH_AVAILABLE"] = orig_avail
            method_globals["fast_hash"] = orig_fh

    def test_schema_fingerprint_falls_back_to_sha256(self):
        """Test schema fingerprint falls back when fast hash is unavailable.

        Uses direct assignment; cleanup handled by autouse ``patch.dict``.
        """
        schema_evolution_module.FAST_HASH_AVAILABLE = False

        schema = SchemaDefinition(
            schema_id="test",
            name="Test",
            version="1.0.0",
            fields=[SchemaFieldDefinition(name="id", field_type="str")],
        )
        fingerprint = schema.compute_fingerprint()

        assert len(fingerprint) == 16
        int(fingerprint, 16)

    def test_schema_get_required_fields(self):
        """Test getting required fields."""
        schema = SchemaDefinition(
            schema_id="test",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str", required=True),
                SchemaFieldDefinition(name="data", field_type="dict", required=False),
            ],
        )
        required = schema.get_required_fields()
        assert len(required) == 1
        assert required[0].name == "id"

    def test_schema_get_optional_fields(self):
        """Test getting optional fields."""
        schema = SchemaDefinition(
            schema_id="test",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str", required=True),
                SchemaFieldDefinition(name="data", field_type="dict", required=False),
            ],
        )
        optional = schema.get_optional_fields()
        assert len(optional) == 1
        assert optional[0].name == "data"


# ============================================================================
# CompatibilityChecker Tests
# ============================================================================


class TestCompatibilityChecker:
    """Test CompatibilityChecker."""

    def test_add_optional_field_is_backward_compatible(self):
        """Test adding optional field is backward compatible."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="metadata", field_type="dict", required=False),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.BACKWARD)
        is_compatible, changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is True
        assert len(changes) == 1
        assert changes[0].evolution_type == EvolutionType.ADD_FIELD
        assert changes[0].is_breaking is False

    def test_add_required_field_is_not_backward_compatible(self):
        """Test adding required field without default is not backward compatible."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="2.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="new_required", field_type="str", required=True),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.BACKWARD)
        is_compatible, changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is False
        assert any(c.is_breaking for c in changes)

    def test_remove_optional_field_is_forward_compatible(self):
        """Test removing optional field is forward compatible."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="optional", field_type="str", required=False),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.FORWARD)
        is_compatible, changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is True
        assert len(changes) == 1
        assert changes[0].evolution_type == EvolutionType.REMOVE_FIELD

    def test_remove_required_field_is_not_forward_compatible(self):
        """Test removing required field is not forward compatible."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="required", field_type="str", required=True),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="2.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.FORWARD)
        is_compatible, _changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is False

    def test_type_change_compatible(self):
        """Test compatible type change (int to float)."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="value", field_type="int"),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="value", field_type="float"),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.BACKWARD)
        is_compatible, changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is True
        assert len(changes) == 1
        assert changes[0].evolution_type == EvolutionType.CHANGE_TYPE
        assert changes[0].is_breaking is False

    def test_detect_deprecation(self):
        """Test detecting field deprecation."""
        old_schema = SchemaDefinition(
            schema_id="v1",
            name="Test",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="old_field", field_type="str"),
            ],
        )
        new_schema = SchemaDefinition(
            schema_id="v2",
            name="Test",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="old_field", field_type="str", deprecated=True),
            ],
        )

        checker = CompatibilityChecker(SchemaCompatibility.BACKWARD)
        is_compatible, changes = checker.check_compatibility(old_schema, new_schema)

        assert is_compatible is True
        deprecation_changes = [
            c for c in changes if c.evolution_type == EvolutionType.DEPRECATE_FIELD
        ]
        assert len(deprecation_changes) == 1


# ============================================================================
# SchemaRegistry Tests
# ============================================================================


class TestSchemaRegistry:
    """Test SchemaRegistry."""

    def test_register_schema(self):
        """Test registering a schema."""
        registry = SchemaRegistry()
        schema = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )

        success, message = registry.register(schema, check_compatibility=False)
        assert success is True
        assert "registered successfully" in message

    def test_register_duplicate_version_fails(self):
        """Test registering duplicate version fails."""
        registry = SchemaRegistry()
        schema = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
        )

        registry.register(schema, check_compatibility=False)
        success, message = registry.register(schema, check_compatibility=False)

        assert success is False
        assert "already exists" in message

    def test_get_schema(self):
        """Test retrieving a schema."""
        registry = SchemaRegistry()
        schema = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
        )
        registry.register(schema, check_compatibility=False)

        retrieved = registry.get_schema("TestMessage", "1.0.0")
        assert retrieved is not None
        assert retrieved.schema_id == "test_v1"

    def test_get_latest_schema(self):
        """Test retrieving latest schema version."""
        registry = SchemaRegistry()

        schema_v1 = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
        )
        schema_v2 = SchemaDefinition(
            schema_id="test_v2",
            name="TestMessage",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="new_field", field_type="str", required=False),
            ],
        )

        registry.register(schema_v1, check_compatibility=False)
        registry.register(schema_v2, check_compatibility=False)

        latest = registry.get_schema("TestMessage")
        assert latest is not None
        assert latest.version == "1.1.0"

    def test_get_all_versions(self):
        """Test getting all versions of a schema."""
        registry = SchemaRegistry()

        for v in ["1.0.0", "1.1.0", "1.2.0"]:
            schema = SchemaDefinition(
                schema_id=f"test_{v}",
                name="TestMessage",
                version=v,
            )
            registry.register(schema, check_compatibility=False)

        versions = registry.get_all_versions("TestMessage")
        assert versions == ["1.0.0", "1.1.0", "1.2.0"]

    def test_get_latest_version(self):
        """Test getting latest version string."""
        registry = SchemaRegistry()

        for v in ["1.0.0", "1.1.0"]:
            schema = SchemaDefinition(
                schema_id=f"test_{v}",
                name="TestMessage",
                version=v,
            )
            registry.register(schema, check_compatibility=False)

        latest = registry.get_latest_version("TestMessage")
        assert latest == "1.1.0"

    def test_deprecate_schema(self):
        """Test deprecating a schema."""
        registry = SchemaRegistry()
        schema = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
        )
        registry.register(schema, check_compatibility=False)

        success = registry.deprecate_schema("TestMessage", "1.0.0")
        assert success is True

        retrieved = registry.get_schema("TestMessage", "1.0.0")
        assert retrieved.deprecated is True

    def test_compatibility_check_on_register(self):
        """Test compatibility is checked on registration."""
        registry = SchemaRegistry(compatibility_mode=SchemaCompatibility.BACKWARD)

        schema_v1 = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        registry.register(schema_v1, check_compatibility=False)

        # Try to register breaking change
        schema_v2 = SchemaDefinition(
            schema_id="test_v2",
            name="TestMessage",
            version="2.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="required_new", field_type="str", required=True),
            ],
        )

        success, message = registry.register(schema_v2, check_compatibility=True)
        assert success is False
        assert "not compatible" in message


# ============================================================================
# SchemaMigrator Tests
# ============================================================================


class TestSchemaMigrator:
    """Test SchemaMigrator."""

    @pytest.fixture
    def registry_with_schemas(self):
        """Create registry with test schemas."""
        registry = SchemaRegistry()

        schema_v1 = SchemaDefinition(
            schema_id="test_v1",
            name="TestMessage",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="data", field_type="str"),
            ],
        )
        schema_v2 = SchemaDefinition(
            schema_id="test_v2",
            name="TestMessage",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="data", field_type="str"),
                SchemaFieldDefinition(
                    name="metadata", field_type="dict", required=False, default={}
                ),
            ],
        )

        registry.register(schema_v1, check_compatibility=False)
        registry.register(schema_v2, check_compatibility=False)

        return registry

    def test_create_migration(self, registry_with_schemas):
        """Test creating a migration."""
        migrator = SchemaMigrator(registry_with_schemas)

        migration = migrator.create_migration("TestMessage", "1.0.0", "1.1.0")

        assert migration is not None
        assert migration.from_version == "1.0.0"
        assert migration.to_version == "1.1.0"
        assert migration.schema_name == "TestMessage"
        assert len(migration.changes) > 0

    def test_migrate_data_auto(self, registry_with_schemas):
        """Test automatic data migration."""
        migrator = SchemaMigrator(registry_with_schemas)

        old_data = {"id": "123", "data": "test"}
        new_data, success = migrator.migrate_data(old_data, "TestMessage", "1.0.0", "1.1.0")

        assert success is True
        assert new_data["id"] == "123"
        assert new_data["data"] == "test"
        assert "metadata" in new_data
        assert new_data["_schema_version"] == "1.1.0"
        assert new_data["_constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_migrate_data_custom_transform(self, registry_with_schemas):
        """Test migration with custom transform function."""
        migrator = SchemaMigrator(registry_with_schemas)

        def custom_transform(data: dict) -> dict:
            result = data.copy()
            result["metadata"] = {"migrated": True}
            result["data"] = result["data"].upper()
            return result

        migration = migrator.create_migration("TestMessage", "1.0.0", "1.1.0")
        migrator.register_migration(migration, custom_transform)

        old_data = {"id": "123", "data": "test"}
        new_data, success = migrator.migrate_data(old_data, "TestMessage", "1.0.0", "1.1.0")

        assert success is True
        assert new_data["data"] == "TEST"
        assert new_data["metadata"] == {"migrated": True}

    def test_get_migration_path(self, registry_with_schemas):
        """Test getting migration path."""
        migrator = SchemaMigrator(registry_with_schemas)

        path = migrator.get_migration_path("TestMessage", "1.0.0", "1.1.0")
        assert path == ["1.0.0", "1.1.0"]

    def test_migration_rollback_supported(self, registry_with_schemas):
        """Test migration rollback support flag."""
        migrator = SchemaMigrator(registry_with_schemas)

        migration = migrator.create_migration("TestMessage", "1.0.0", "1.1.0")

        # Non-breaking changes should support rollback
        assert migration.rollback_supported is True


# ============================================================================
# SchemaMigration Tests
# ============================================================================


class TestSchemaMigration:
    """Test SchemaMigration model."""

    def test_migration_model_basic(self):
        """Test basic migration model."""
        migration = SchemaMigration(
            migration_id="test_migration",
            from_version="1.0.0",
            to_version="1.1.0",
            schema_name="TestMessage",
        )

        assert migration.migration_id == "test_migration"
        assert migration.status == MigrationStatus.PENDING
        assert migration.constitutional_hash == CONSTITUTIONAL_HASH

    def test_migration_with_changes(self):
        """Test migration with changes."""
        change = SchemaEvolutionChange(
            change_id="add_field",
            evolution_type=EvolutionType.ADD_FIELD,
            field_name="new_field",
            new_value="str",
            is_breaking=False,
        )

        migration = SchemaMigration(
            migration_id="test_migration",
            from_version="1.0.0",
            to_version="1.1.0",
            schema_name="TestMessage",
            changes=[change],
        )

        assert len(migration.changes) == 1
        assert migration.changes[0].field_name == "new_field"


# ============================================================================
# VersionedMessageBase Tests
# ============================================================================


class TestVersionedMessageBase:
    """Test VersionedMessageBase."""

    def test_versioned_message_defaults(self):
        """Test versioned message has correct defaults."""

        class MyMessage(VersionedMessageBase):
            _schema_version: ClassVar[str] = "1.0.0"
            _schema_name: ClassVar[str] = "MyMessage"
            data: str = ""

        msg = MyMessage()
        assert msg.get_schema_version() == "1.0.0"
        assert msg.get_schema_name() == "MyMessage"
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Predefined Schema Tests
# ============================================================================


class TestPredefinedSchemas:
    """Test predefined AgentMessage schemas."""

    def test_agent_message_v1_fields(self):
        """Test AgentMessage v1 has required fields."""
        schema = AGENT_MESSAGE_SCHEMA_V1
        field_names = {f.name for f in schema.fields}

        assert "message_id" in field_names
        assert "conversation_id" in field_names
        assert "content" in field_names
        assert "from_agent" in field_names
        assert "to_agent" in field_names
        assert "message_type" in field_names
        assert "constitutional_hash" in field_names

    def test_agent_message_v1_1_adds_session_fields(self):
        """Test AgentMessage v1.1 adds session fields."""
        v1_fields = {f.name for f in AGENT_MESSAGE_SCHEMA_V1.fields}
        v1_1_fields = {f.name for f in AGENT_MESSAGE_SCHEMA_V1_1.fields}

        new_fields = v1_1_fields - v1_fields
        assert "session_id" in new_fields
        assert "session_context" in new_fields

    def test_agent_message_v1_2_adds_pqc_fields(self):
        """Test AgentMessage v1.2 adds PQC fields."""
        v1_1_fields = {f.name for f in AGENT_MESSAGE_SCHEMA_V1_1.fields}
        v1_2_fields = {f.name for f in AGENT_MESSAGE_SCHEMA_V1_2.fields}

        new_fields = v1_2_fields - v1_1_fields
        assert "pqc_signature" in new_fields
        assert "pqc_public_key" in new_fields
        assert "pqc_algorithm" in new_fields

    def test_schema_versions_are_compatible(self):
        """Test that schema versions are backward compatible."""
        checker = CompatibilityChecker(SchemaCompatibility.BACKWARD)

        # v1.1 should be backward compatible with v1.0
        is_compat_1, _ = checker.check_compatibility(
            AGENT_MESSAGE_SCHEMA_V1, AGENT_MESSAGE_SCHEMA_V1_1
        )
        assert is_compat_1 is True

        # v1.2 should be backward compatible with v1.1
        is_compat_2, _ = checker.check_compatibility(
            AGENT_MESSAGE_SCHEMA_V1_1, AGENT_MESSAGE_SCHEMA_V1_2
        )
        assert is_compat_2 is True


# ============================================================================
# Default Registry Tests
# ============================================================================


class TestDefaultRegistry:
    """Test default registry factory."""

    def test_create_default_registry(self):
        """Test creating default registry."""
        registry = create_default_registry()

        assert registry.get_schema("AgentMessage", "1.0.0") is not None
        assert registry.get_schema("AgentMessage", "1.1.0") is not None
        assert registry.get_schema("AgentMessage", "1.2.0") is not None

    def test_default_registry_latest_version(self):
        """Test default registry has correct latest version."""
        registry = create_default_registry()

        latest = registry.get_latest_version("AgentMessage")
        assert latest == "1.2.0"

    def test_default_registry_all_versions(self):
        """Test default registry has all versions."""
        registry = create_default_registry()

        versions = registry.get_all_versions("AgentMessage")
        assert "1.0.0" in versions
        assert "1.1.0" in versions
        assert "1.2.0" in versions


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.integration
class TestSchemaEvolutionIntegration:
    """Integration tests for schema evolution."""

    def test_full_evolution_workflow(self):
        """Test complete schema evolution workflow."""
        # Create registry
        registry = SchemaRegistry(compatibility_mode=SchemaCompatibility.BACKWARD)

        # Register initial schema
        schema_v1 = SchemaDefinition(
            schema_id="workflow_v1",
            name="WorkflowEvent",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="event_id", field_type="str"),
                SchemaFieldDefinition(name="event_type", field_type="str"),
                SchemaFieldDefinition(name="payload", field_type="dict"),
            ],
        )
        success, _ = registry.register(schema_v1, check_compatibility=False)
        assert success is True

        # Evolve schema with optional field
        schema_v2 = SchemaDefinition(
            schema_id="workflow_v2",
            name="WorkflowEvent",
            version="1.1.0",
            fields=[
                SchemaFieldDefinition(name="event_id", field_type="str"),
                SchemaFieldDefinition(name="event_type", field_type="str"),
                SchemaFieldDefinition(name="payload", field_type="dict"),
                SchemaFieldDefinition(
                    name="metadata", field_type="dict", required=False, default={}
                ),
                SchemaFieldDefinition(name="timestamp", field_type="datetime", required=False),
            ],
        )
        success, _ = registry.register(schema_v2, check_compatibility=True)
        assert success is True

        # Create migrator and migrate data
        migrator = SchemaMigrator(registry)
        old_data = {
            "event_id": "evt-123",
            "event_type": "task_completed",
            "payload": {"result": "success"},
        }

        new_data, success = migrator.migrate_data(old_data, "WorkflowEvent", "1.0.0", "1.1.0")

        assert success is True
        assert new_data["event_id"] == "evt-123"
        assert "metadata" in new_data
        assert new_data["_schema_version"] == "1.1.0"

    def test_breaking_change_prevention(self):
        """Test that breaking changes are prevented."""
        registry = SchemaRegistry(compatibility_mode=SchemaCompatibility.BACKWARD)

        # Register initial schema
        schema_v1 = SchemaDefinition(
            schema_id="msg_v1",
            name="Message",
            version="1.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
            ],
        )
        registry.register(schema_v1, check_compatibility=False)

        # Try to register breaking change (new required field)
        schema_v2 = SchemaDefinition(
            schema_id="msg_v2",
            name="Message",
            version="2.0.0",
            fields=[
                SchemaFieldDefinition(name="id", field_type="str"),
                SchemaFieldDefinition(name="required_field", field_type="str", required=True),
            ],
        )
        success, message = registry.register(schema_v2, check_compatibility=True)

        assert success is False
        assert "not compatible" in message
