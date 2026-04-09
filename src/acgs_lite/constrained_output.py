"""Fail-closed provider-specific structured output builders."""

from __future__ import annotations

import logging
import os
from re import sub
from typing import Any, Protocol

from acgs_lite.provider_capabilities import (
    CapabilityLevel,
    CapabilityStability,
    CapabilitySupportLevel,
    RequestShape,
)

logger = logging.getLogger(__name__)

_ALLOW_PREVIEW_ENV = "ACGS_ALLOW_PREVIEW_MODEL_CAPABILITIES"


class ResponseSchemaProvider(Protocol):
    """Protocol for constitutions that can export constrained-response schemas."""

    name: str

    def to_response_schema(self) -> dict[str, Any]:
        """Return a JSON Schema describing provider output."""


class StructuredOutputProfile(Protocol):
    """Capability surface needed for request-shape injection."""

    support_level: CapabilitySupportLevel
    request_shape: RequestShape
    stability: CapabilityStability
    structured_output: Any


def _schema_name(constitution: ResponseSchemaProvider) -> str:
    slug = sub(r"[^a-zA-Z0-9_]+", "_", constitution.name).strip("_").lower()
    return slug or "acgs_response"


def _allow_preview_capabilities() -> bool:
    return os.getenv(_ALLOW_PREVIEW_ENV, "").lower() in {"1", "true", "yes"}


def _can_inject_request_shape(capability_profile: StructuredOutputProfile) -> bool:
    if capability_profile.structured_output in {CapabilityLevel.NONE, CapabilityLevel.NONE.value}:
        return False
    if capability_profile.support_level != CapabilitySupportLevel.DOCUMENTED:
        return False
    if capability_profile.request_shape == RequestShape.NONE:
        return False
    return (
        capability_profile.stability != CapabilityStability.PREVIEW
        or _allow_preview_capabilities()
    )


def _build_openai_response_format(schema: dict[str, Any], constitution: ResponseSchemaProvider) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _schema_name(constitution),
            "schema": schema,
            "strict": True,
        },
    }


def _build_anthropic_output_config(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "schema": schema,
        }
    }


def _build_google_config(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "response_mime_type": "application/json",
        "response_json_schema": schema,
    }


def attach_response_format(
    kwargs: dict[str, Any],
    constitution: ResponseSchemaProvider,
    capability_profile: StructuredOutputProfile | None,
) -> dict[str, Any]:
    """Attach provider-specific request shape when it is explicitly documented."""
    updated = dict(kwargs)
    if capability_profile is None or not _can_inject_request_shape(capability_profile):
        if capability_profile is not None and capability_profile.request_shape != RequestShape.NONE:
            logger.info(
                "Skipping structured-output injection due to capability guardrail",
                extra={
                    "request_shape": capability_profile.request_shape.value,
                    "support_level": capability_profile.support_level.value,
                    "stability": capability_profile.stability.value,
                },
            )
        return updated

    schema = constitution.to_response_schema()
    exported_rule_count = schema.get("x-acgs-exported-rule-count", 0)
    if not isinstance(exported_rule_count, int) or exported_rule_count <= 0:
        return updated

    if capability_profile.request_shape == RequestShape.OPENAI_RESPONSE_FORMAT_JSON_SCHEMA:
        if updated.get("response_format") is None:
            updated["response_format"] = _build_openai_response_format(schema, constitution)
        return updated

    if capability_profile.request_shape == RequestShape.ANTHROPIC_OUTPUT_CONFIG_JSON_SCHEMA:
        existing_output_config = updated.get("output_config", {})
        if not isinstance(existing_output_config, dict):
            existing_output_config = {}
        updated["output_config"] = {
            **existing_output_config,
            **_build_anthropic_output_config(schema),
        }
        return updated

    if capability_profile.request_shape == RequestShape.GOOGLE_CONFIG_JSON_SCHEMA:
        existing_config = updated.get("config", {})
        if not isinstance(existing_config, dict):
            existing_config = {}
        updated["config"] = {**existing_config, **_build_google_config(schema)}
        return updated

    return updated


__all__ = ["attach_response_format"]
