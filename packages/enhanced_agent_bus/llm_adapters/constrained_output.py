"""Helpers for attaching constitution-derived structured output constraints."""

from __future__ import annotations

from re import sub
from typing import Any, Protocol

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .capability_matrix import CapabilityDimension, CapabilityLevel, ProviderCapabilityProfile

logger = get_logger(__name__)


class ResponseSchemaProvider(Protocol):
    """Protocol for constitutions that can export constrained-response schemas."""

    name: str

    def to_response_schema(self) -> JSONDict:
        """Return a JSON Schema describing provider output."""


def _schema_name(constitution: ResponseSchemaProvider) -> str:
    slug = sub(r"[^a-zA-Z0-9_]+", "_", constitution.name).strip("_").lower()
    return slug or "acgs_response"


def _supports_structured_output(capability_profile: ProviderCapabilityProfile) -> bool:
    capability = capability_profile.get_capability(CapabilityDimension.STRUCTURED_OUTPUT)
    return isinstance(capability.value, CapabilityLevel) and capability.value != CapabilityLevel.NONE


def _build_response_format(
    constitution: ResponseSchemaProvider,
    capability_profile: ProviderCapabilityProfile,
) -> JSONDict | None:
    schema = constitution.to_response_schema()
    exported_rule_count = schema.get("x-acgs-exported-rule-count", 0)
    if not isinstance(exported_rule_count, int) or exported_rule_count <= 0:
        return None

    if capability_profile.provider_type in {"openai", "azure"}:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": _schema_name(constitution),
                "schema": schema,
                "strict": True,
            },
        }

    logger.debug(
        "Skipping constrained response_format for unsupported structured-output provider",
        provider_id=capability_profile.provider_id,
        provider_type=capability_profile.provider_type,
    )
    return None


class ConstrainedOutputMixin:
    """Mixin that attaches constitution-derived structured-output constraints."""

    def attach_response_format(
        self,
        kwargs: dict[str, Any],
        constitution: ResponseSchemaProvider,
        capability_profile: ProviderCapabilityProfile | None,
    ) -> dict[str, Any]:
        return attach_response_format(kwargs, constitution, capability_profile)


def attach_response_format(
    kwargs: dict[str, Any],
    constitution: ResponseSchemaProvider,
    capability_profile: ProviderCapabilityProfile | None,
) -> dict[str, Any]:
    """Attach provider-specific response_format when supported and needed."""
    updated = dict(kwargs)
    if updated.get("response_format") is not None or capability_profile is None:
        return updated
    if not _supports_structured_output(capability_profile):
        return updated

    response_format = _build_response_format(constitution, capability_profile)
    if response_format is not None:
        updated["response_format"] = response_format
    return updated


__all__ = ["ConstrainedOutputMixin", "attach_response_format"]
