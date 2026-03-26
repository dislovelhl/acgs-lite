from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from packages.enhanced_agent_bus.schema_evolution import (
    SchemaCompatibility,
    SchemaVersion,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH

sys.modules.setdefault("src.core.shared.schema_registry", sys.modules[__name__])


class SchemaStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


class EventSchemaBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    event_id: str | None = Field(default=None, description="Unique event identifier")
    event_type: str = Field(default="", description="Event type discriminator")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)
    schema_version: str | None = Field(default=None)

    def model_post_init(self, __context: Any) -> None:
        if self.schema_version is None:
            schema_version = getattr(self.__class__, "SCHEMA_VERSION", None)
            self.schema_version = f"v{schema_version}" if schema_version is not None else "v1.0.0"
        if not self.event_type:
            schema_name = getattr(self.__class__, "SCHEMA_NAME", self.__class__.__name__)
            self.event_type = str(schema_name).lower()
        if not self.constitutional_hash:
            self.constitutional_hash = CONSTITUTIONAL_HASH


class RegisteredSchema(BaseModel):
    schema_class: type[EventSchemaBase]
    status: SchemaStatus = SchemaStatus.ACTIVE
    compatibility_mode: SchemaCompatibility = SchemaCompatibility.BACKWARD
    migration_from: SchemaVersion | None = None
    description: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SchemaRegistry:
    _instance: SchemaRegistry | None = None

    def __new__(cls) -> SchemaRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._schemas = {}
            cls._instance._migrations = {}
        return cls._instance

    def register(
        self,
        schema_class: type[EventSchemaBase],
        *,
        status: SchemaStatus = SchemaStatus.ACTIVE,
        compatibility_mode: SchemaCompatibility = SchemaCompatibility.BACKWARD,
        migration_from: SchemaVersion | None = None,
        description: str = "",
    ) -> None:
        schema_name = getattr(schema_class, "SCHEMA_NAME", schema_class.__name__)
        schema_version = getattr(schema_class, "SCHEMA_VERSION", SchemaVersion(1, 0, 0))
        self._schemas.setdefault(str(schema_name), {})[str(schema_version)] = RegisteredSchema(
            schema_class=schema_class,
            status=status,
            compatibility_mode=compatibility_mode,
            migration_from=migration_from,
            description=description,
        )

    def register_migration(
        self,
        schema_name: str,
        from_version: SchemaVersion,
        to_version: SchemaVersion,
        migration_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self._migrations[(schema_name, str(from_version), str(to_version))] = migration_fn

    def get(
        self, schema_name: str, version: SchemaVersion | str | None = None
    ) -> type[EventSchemaBase] | None:
        versions = self._schemas.get(schema_name, {})
        if not versions:
            return None
        if version is None:
            latest_key = sorted(versions.keys())[-1]
            return versions[latest_key].schema_class
        key = str(version)
        entry = versions.get(key)
        return entry.schema_class if entry is not None else None

    def get_migration(
        self, schema_name: str, from_version: SchemaVersion | str, to_version: SchemaVersion | str
    ) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
        return self._migrations.get((schema_name, str(from_version), str(to_version)))


def get_schema_registry() -> SchemaRegistry:
    return SchemaRegistry()


__all__ = [
    "CONSTITUTIONAL_HASH",
    "EventSchemaBase",
    "SchemaCompatibility",
    "SchemaRegistry",
    "SchemaStatus",
    "SchemaVersion",
    "get_schema_registry",
]
