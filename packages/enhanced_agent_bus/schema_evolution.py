"""
ACGS-2 Enhanced Agent Bus - Schema Evolution
Constitutional Hash: cdd01ef066bc6cf2

Versioned schema metadata and compatibility helpers for message evolution.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import total_ordering

from pydantic import BaseModel, Field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

try:
    from .rust.fast_hash import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional acceleration
    fast_hash = None
    FAST_HASH_AVAILABLE = False


class SchemaCompatibility(str, Enum):
    BACKWARD = "backward"
    FORWARD = "forward"
    FULL = "full"


class EvolutionType(str, Enum):
    ADD_FIELD = "add_field"
    REMOVE_FIELD = "remove_field"
    CHANGE_TYPE = "change_type"
    DEPRECATE_FIELD = "deprecate_field"


class MigrationStatus(str, Enum):
    PENDING = "pending"
    REGISTERED = "registered"
    APPLIED = "applied"
    FAILED = "failed"


@total_ordering
@dataclass(frozen=True)
class SchemaVersion:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @classmethod
    def parse(cls, value: str) -> "SchemaVersion":
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value)
        if match is None:
            raise ValueError(f"Invalid version format: {value}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
        )

    def __str__(self) -> str:
        suffix = f"-{self.prerelease}" if self.prerelease else ""
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SchemaVersion):
            return NotImplemented
        left = (self.major, self.minor, self.patch)
        right = (other.major, other.minor, other.patch)
        if left != right:
            return left < right
        if self.prerelease == other.prerelease:
            return False
        if not self.prerelease:
            return False
        if not other.prerelease:
            return True
        return self.prerelease < other.prerelease

    def is_compatible_with(
        self, other: "SchemaVersion", mode: SchemaCompatibility
    ) -> bool:
        if mode == SchemaCompatibility.BACKWARD:
            return self.major == other.major and self >= other
        if mode == SchemaCompatibility.FORWARD:
            return self.major == other.major and self <= other
        return self.major == other.major and self.minor == other.minor


@dataclass
class SchemaFieldDefinition:
    name: str
    field_type: str
    required: bool = True
    default: object | None = None
    deprecated: bool = False
    deprecated_since: str = ""


@dataclass
class SchemaDefinition:
    schema_id: str
    name: str
    version: str
    fields: list[SchemaFieldDefinition] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    deprecated: bool = False

    def __post_init__(self) -> None:
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError("Invalid constitutional hash")

    def get_version(self) -> SchemaVersion:
        return SchemaVersion.parse(self.version)

    def compute_fingerprint(self) -> str:
        payload = "|".join(
            [
                self.name,
                self.version,
                self.constitutional_hash,
                *(
                    f"{field.name}:{field.field_type}:{field.required}:"
                    f"{field.default!r}:{field.deprecated}:{field.deprecated_since}"
                    for field in self.fields
                ),
            ]
        )
        if FAST_HASH_AVAILABLE and fast_hash is not None:
            return f"{fast_hash(payload):016x}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def get_required_fields(self) -> list[SchemaFieldDefinition]:
        return [field for field in self.fields if field.required]

    def get_optional_fields(self) -> list[SchemaFieldDefinition]:
        return [field for field in self.fields if not field.required]


@dataclass
class SchemaEvolutionChange:
    change_id: str
    evolution_type: EvolutionType
    field_name: str
    old_value: object | None = None
    new_value: object | None = None
    is_breaking: bool = False
    description: str = ""


class CompatibilityChecker:
    def __init__(self, compatibility_mode: SchemaCompatibility) -> None:
        self.compatibility_mode = compatibility_mode

    def check_compatibility(
        self, old_schema: SchemaDefinition, new_schema: SchemaDefinition
    ) -> tuple[bool, list[SchemaEvolutionChange]]:
        old_fields = {field.name: field for field in old_schema.fields}
        new_fields = {field.name: field for field in new_schema.fields}
        changes: list[SchemaEvolutionChange] = []

        for name, field_info in new_fields.items():
            if name not in old_fields:
                is_breaking = field_info.required and field_info.default is None
                changes.append(
                    SchemaEvolutionChange(
                        change_id=f"add_{name}",
                        evolution_type=EvolutionType.ADD_FIELD,
                        field_name=name,
                        new_value=field_info.field_type,
                        is_breaking=is_breaking,
                    )
                )
                continue

            old_field = old_fields[name]
            if old_field.field_type != field_info.field_type:
                is_breaking = not self._is_type_change_compatible(
                    old_field.field_type, field_info.field_type
                )
                changes.append(
                    SchemaEvolutionChange(
                        change_id=f"change_type_{name}",
                        evolution_type=EvolutionType.CHANGE_TYPE,
                        field_name=name,
                        old_value=old_field.field_type,
                        new_value=field_info.field_type,
                        is_breaking=is_breaking,
                    )
                )
            if not old_field.deprecated and field_info.deprecated:
                changes.append(
                    SchemaEvolutionChange(
                        change_id=f"deprecate_{name}",
                        evolution_type=EvolutionType.DEPRECATE_FIELD,
                        field_name=name,
                        old_value=False,
                        new_value=True,
                        is_breaking=False,
                    )
                )

        for name, old_field_info in old_fields.items():
            if name in new_fields:
                continue
            changes.append(
                SchemaEvolutionChange(
                    change_id=f"remove_{name}",
                    evolution_type=EvolutionType.REMOVE_FIELD,
                    field_name=name,
                    old_value=old_field_info.field_type,
                    is_breaking=old_field_info.required,
                )
            )

        return self._evaluate(changes), changes

    def _evaluate(self, changes: list[SchemaEvolutionChange]) -> bool:
        if self.compatibility_mode == SchemaCompatibility.BACKWARD:
            return not any(
                change.evolution_type == EvolutionType.ADD_FIELD and change.is_breaking
                or change.evolution_type == EvolutionType.CHANGE_TYPE and change.is_breaking
                for change in changes
            )
        if self.compatibility_mode == SchemaCompatibility.FORWARD:
            return not any(
                change.evolution_type == EvolutionType.REMOVE_FIELD and change.is_breaking
                or change.evolution_type == EvolutionType.CHANGE_TYPE and change.is_breaking
                for change in changes
            )
        return not any(change.is_breaking for change in changes)

    @staticmethod
    def _is_type_change_compatible(old_type: str, new_type: str) -> bool:
        if old_type == new_type:
            return True
        compatible_pairs = {
            ("int", "float"),
        }
        return (old_type, new_type) in compatible_pairs


@dataclass
class SchemaMigration:
    migration_id: str
    from_version: str
    to_version: str
    schema_name: str
    changes: list[SchemaEvolutionChange] = field(default_factory=list)
    status: MigrationStatus = MigrationStatus.PENDING
    constitutional_hash: str = CONSTITUTIONAL_HASH
    rollback_supported: bool = True


class SchemaRegistry:
    def __init__(
        self, compatibility_mode: SchemaCompatibility = SchemaCompatibility.BACKWARD
    ) -> None:
        self.compatibility_mode = compatibility_mode
        self._schemas: dict[str, dict[str, SchemaDefinition]] = {}

    def register(
        self, schema: SchemaDefinition, check_compatibility: bool = True
    ) -> tuple[bool, str]:
        versions = self._schemas.setdefault(schema.name, {})
        if schema.version in versions:
            return False, f"Schema {schema.name} version {schema.version} already exists"

        latest = self.get_schema(schema.name)
        if check_compatibility and latest is not None:
            checker = CompatibilityChecker(self.compatibility_mode)
            is_compatible, _changes = checker.check_compatibility(latest, schema)
            if not is_compatible:
                return False, f"Schema {schema.name} version {schema.version} is not compatible"

        versions[schema.version] = schema
        return True, f"Schema {schema.name} version {schema.version} registered successfully"

    def get_schema(self, schema_name: str, version: str | None = None) -> SchemaDefinition | None:
        versions = self._schemas.get(schema_name, {})
        if not versions:
            return None
        if version is None:
            latest_version = self.get_latest_version(schema_name)
            return versions.get(latest_version) if latest_version is not None else None
        return versions.get(version)

    def get_all_versions(self, schema_name: str) -> list[str]:
        versions = self._schemas.get(schema_name, {})
        return [str(version) for version in sorted(SchemaVersion.parse(v) for v in versions)]

    def get_latest_version(self, schema_name: str) -> str | None:
        versions = self.get_all_versions(schema_name)
        return versions[-1] if versions else None

    def deprecate_schema(self, schema_name: str, version: str) -> bool:
        schema = self.get_schema(schema_name, version)
        if schema is None:
            return False
        schema.deprecated = True
        return True


class SchemaMigrator:
    def __init__(self, registry: SchemaRegistry) -> None:
        self.registry = registry
        self._migrations: dict[tuple[str, str, str], SchemaMigration] = {}
        self._transforms: dict[tuple[str, str, str], Callable[[dict], dict]] = {}

    def create_migration(
        self, schema_name: str, from_version: str, to_version: str
    ) -> SchemaMigration:
        old_schema = self.registry.get_schema(schema_name, from_version)
        new_schema = self.registry.get_schema(schema_name, to_version)
        if old_schema is None or new_schema is None:
            raise ValueError("Schema versions must exist before creating a migration")

        checker = CompatibilityChecker(self.registry.compatibility_mode)
        _is_compatible, changes = checker.check_compatibility(old_schema, new_schema)
        migration = SchemaMigration(
            migration_id=f"{schema_name}:{from_version}->{to_version}",
            from_version=from_version,
            to_version=to_version,
            schema_name=schema_name,
            changes=changes,
            rollback_supported=not any(change.is_breaking for change in changes),
        )
        self._migrations[(schema_name, from_version, to_version)] = migration
        return migration

    def register_migration(
        self, migration: SchemaMigration, transform: Callable[[dict], dict]
    ) -> None:
        key = (migration.schema_name, migration.from_version, migration.to_version)
        migration.status = MigrationStatus.REGISTERED
        self._migrations[key] = migration
        self._transforms[key] = transform

    def get_migration_path(
        self, schema_name: str, from_version: str, to_version: str
    ) -> list[str]:
        if self.registry.get_schema(schema_name, from_version) is None:
            return []
        if self.registry.get_schema(schema_name, to_version) is None:
            return []
        return [from_version, to_version]

    def migrate_data(
        self, data: dict, schema_name: str, from_version: str, to_version: str
    ) -> tuple[dict, bool]:
        old_schema = self.registry.get_schema(schema_name, from_version)
        new_schema = self.registry.get_schema(schema_name, to_version)
        if old_schema is None or new_schema is None:
            return data, False

        key = (schema_name, from_version, to_version)
        migration = self._migrations.get(key) or self.create_migration(
            schema_name, from_version, to_version
        )

        transformed = dict(data)
        transform = self._transforms.get(key)
        if transform is not None:
            transformed = transform(transformed)
        else:
            new_field_map = {field.name: field for field in new_schema.fields}
            for field_name, field in new_field_map.items():
                if field_name not in transformed and field.default is not None:
                    transformed[field_name] = field.default

        transformed["_schema_version"] = to_version
        transformed["_constitutional_hash"] = CONSTITUTIONAL_HASH
        migration.status = MigrationStatus.APPLIED
        return transformed, True


class VersionedMessageBase(BaseModel):
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)

    def get_schema_version(self) -> str:
        return getattr(type(self), "_schema_version", "1.0.0")

    def get_schema_name(self) -> str:
        return getattr(type(self), "_schema_name", type(self).__name__)


AGENT_MESSAGE_SCHEMA_V1 = SchemaDefinition(
    schema_id="agent_message_v1",
    name="AgentMessage",
    version="1.0.0",
    fields=[
        SchemaFieldDefinition(name="message_id", field_type="str"),
        SchemaFieldDefinition(name="conversation_id", field_type="str"),
        SchemaFieldDefinition(name="content", field_type="dict"),
        SchemaFieldDefinition(name="from_agent", field_type="str"),
        SchemaFieldDefinition(name="to_agent", field_type="str"),
        SchemaFieldDefinition(name="message_type", field_type="str"),
        SchemaFieldDefinition(name="constitutional_hash", field_type="str"),
    ],
)

AGENT_MESSAGE_SCHEMA_V1_1 = SchemaDefinition(
    schema_id="agent_message_v1_1",
    name="AgentMessage",
    version="1.1.0",
    fields=[
        *AGENT_MESSAGE_SCHEMA_V1.fields,
        SchemaFieldDefinition(name="session_id", field_type="str", required=False),
        SchemaFieldDefinition(name="session_context", field_type="dict", required=False),
    ],
)

AGENT_MESSAGE_SCHEMA_V1_2 = SchemaDefinition(
    schema_id="agent_message_v1_2",
    name="AgentMessage",
    version="1.2.0",
    fields=[
        *AGENT_MESSAGE_SCHEMA_V1_1.fields,
        SchemaFieldDefinition(name="pqc_signature", field_type="str", required=False),
        SchemaFieldDefinition(name="pqc_public_key", field_type="str", required=False),
        SchemaFieldDefinition(name="pqc_algorithm", field_type="str", required=False),
    ],
)


def create_default_registry() -> SchemaRegistry:
    registry = SchemaRegistry(compatibility_mode=SchemaCompatibility.BACKWARD)
    for schema in (
        AGENT_MESSAGE_SCHEMA_V1,
        AGENT_MESSAGE_SCHEMA_V1_1,
        AGENT_MESSAGE_SCHEMA_V1_2,
    ):
        registry.register(schema, check_compatibility=False)
    return registry


__all__ = [
    "AGENT_MESSAGE_SCHEMA_V1",
    "AGENT_MESSAGE_SCHEMA_V1_1",
    "AGENT_MESSAGE_SCHEMA_V1_2",
    "CONSTITUTIONAL_HASH",
    "FAST_HASH_AVAILABLE",
    "CompatibilityChecker",
    "EvolutionType",
    "MigrationStatus",
    "SchemaCompatibility",
    "SchemaDefinition",
    "SchemaEvolutionChange",
    "SchemaFieldDefinition",
    "SchemaMigration",
    "SchemaMigrator",
    "SchemaRegistry",
    "SchemaVersion",
    "VersionedMessageBase",
    "create_default_registry",
    "fast_hash",
]
