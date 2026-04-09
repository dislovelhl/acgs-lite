"""Pinned provider capability manifest and runtime lookup helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


class CapabilityLevel(str, Enum):
    """Level of support for a capability."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    ADVANCED = "advanced"
    FULL = "full"


class CapabilitySupportLevel(str, Enum):
    """How strong the capability evidence is."""

    DOCUMENTED = "documented"
    INFERRED = "inferred"
    UNSUPPORTED = "unsupported"


class CapabilityStability(str, Enum):
    """Stability tier for a capability entry."""

    STABLE = "stable"
    PREVIEW = "preview"
    LEGACY = "legacy"


class RequestShape(str, Enum):
    """Exact provider request-shape supported by a profile."""

    NONE = "none"
    OPENAI_RESPONSE_FORMAT_JSON_SCHEMA = "openai.response_format.json_schema"
    ANTHROPIC_OUTPUT_CONFIG_JSON_SCHEMA = "anthropic.output_config.json_schema"
    GOOGLE_CONFIG_JSON_SCHEMA = "google.config.json_schema"


@dataclass(slots=True)
class ProviderCapabilityProfile:
    """Pinned provider/model capability profile used by acgs-lite runtime."""

    provider_id: str
    model_id: str
    display_name: str
    provider_type: str
    structured_output: CapabilityLevel = CapabilityLevel.NONE
    support_level: CapabilitySupportLevel = CapabilitySupportLevel.UNSUPPORTED
    request_shape: RequestShape = RequestShape.NONE
    evidence_source: str = ""
    checked_at: str = ""
    stability: CapabilityStability = CapabilityStability.STABLE
    aliases: tuple[str, ...] = ()
    is_active: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderCapabilityProfile:
        """Build a profile from manifest data."""
        aliases_raw = data.get("aliases", [])
        aliases = tuple(str(alias) for alias in aliases_raw) if isinstance(aliases_raw, list) else ()
        return cls(
            provider_id=str(data["provider_id"]),
            model_id=str(data["model_id"]),
            display_name=str(data["display_name"]),
            provider_type=str(data["provider_type"]),
            structured_output=CapabilityLevel(str(data.get("structured_output", CapabilityLevel.NONE.value))),
            support_level=CapabilitySupportLevel(
                str(data.get("support_level", CapabilitySupportLevel.UNSUPPORTED.value))
            ),
            request_shape=RequestShape(str(data.get("request_shape", RequestShape.NONE.value))),
            evidence_source=str(data.get("evidence_source", "")),
            checked_at=str(data.get("checked_at", "")),
            stability=CapabilityStability(
                str(data.get("stability", CapabilityStability.STABLE.value))
            ),
            aliases=aliases,
            is_active=bool(data.get("is_active", True)),
        )

    def matches(self, model: str, provider_name: str | None = None) -> bool:
        """Return True when the model matches exactly or via a declared alias."""
        if provider_name is not None and provider_name != self.provider_type:
            return False
        return model == self.model_id or model in self.aliases

    def supports_runtime_structured_output(self, *, allow_preview: bool = False) -> bool:
        """Return True when runtime request-shape injection is explicitly safe."""
        if self.structured_output == CapabilityLevel.NONE:
            return False
        if self.support_level != CapabilitySupportLevel.DOCUMENTED:
            return False
        if self.request_shape == RequestShape.NONE:
            return False
        return self.stability != CapabilityStability.PREVIEW or allow_preview

    def to_dict(self) -> dict[str, Any]:
        """Serialize the profile into manifest shape."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "provider_type": self.provider_type,
            "structured_output": self.structured_output.value,
            "support_level": self.support_level.value,
            "request_shape": self.request_shape.value,
            "evidence_source": self.evidence_source,
            "checked_at": self.checked_at,
            "stability": self.stability.value,
            "aliases": list(self.aliases),
            "is_active": self.is_active,
        }


@dataclass(slots=True)
class ManifestValidationIssue:
    """Validation issue for the pinned capability manifest."""

    code: str
    model_id: str
    message: str


def _manifest_path() -> Path:
    return Path(__file__).with_name("provider_capabilities_manifest.json")


def load_capability_manifest() -> list[ProviderCapabilityProfile]:
    """Load the pinned runtime capability manifest."""
    raw = json.loads(_manifest_path().read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("provider capability manifest must be a list")
    return [ProviderCapabilityProfile.from_dict(item) for item in raw if isinstance(item, dict)]


def get_manifest_path() -> Path:
    """Return the pinned manifest path."""
    return _manifest_path()


def validate_capability_manifest(
    profiles: list[ProviderCapabilityProfile] | None = None,
    *,
    max_age_days: int = 45,
    today: date | None = None,
) -> list[ManifestValidationIssue]:
    """Validate manifest evidence and drift policy for CI/CLI use."""
    manifest_profiles = profiles if profiles is not None else load_capability_manifest()
    now = today or date.today()
    issues: list[ManifestValidationIssue] = []

    for profile in manifest_profiles:
        if not profile.evidence_source:
            issues.append(
                ManifestValidationIssue(
                    code="missing_evidence_source",
                    model_id=profile.model_id,
                    message="Manifest entry is missing evidence_source",
                )
            )
        if not profile.checked_at:
            issues.append(
                ManifestValidationIssue(
                    code="missing_checked_at",
                    model_id=profile.model_id,
                    message="Manifest entry is missing checked_at",
                )
            )
            continue
        try:
            checked_at = date.fromisoformat(profile.checked_at)
        except ValueError:
            issues.append(
                ManifestValidationIssue(
                    code="invalid_checked_at",
                    model_id=profile.model_id,
                    message=f"Invalid checked_at value: {profile.checked_at}",
                )
            )
            continue
        if (now - checked_at).days > max_age_days:
            issues.append(
                ManifestValidationIssue(
                    code="stale_entry",
                    model_id=profile.model_id,
                    message=f"Manifest entry is older than {max_age_days} days",
                )
            )
        if (
            profile.support_level == CapabilitySupportLevel.DOCUMENTED
            and profile.request_shape == RequestShape.NONE
        ):
            issues.append(
                ManifestValidationIssue(
                    code="documented_without_request_shape",
                    model_id=profile.model_id,
                    message="Documented structured-output support requires an explicit request shape",
                )
            )
        if profile.stability == CapabilityStability.PREVIEW and "preview" not in profile.model_id:
            issues.append(
                ManifestValidationIssue(
                    code="preview_stability_mismatch",
                    model_id=profile.model_id,
                    message="Preview entries must use preview model IDs",
                )
            )

    return issues


class CapabilityRegistry:
    """In-memory registry seeded from the pinned capability manifest."""

    def __init__(self) -> None:
        self._profiles: list[ProviderCapabilityProfile] = []
        self.reset()

    def register(self, profile: ProviderCapabilityProfile) -> None:
        self._profiles = [
            existing
            for existing in self._profiles
            if not (
                existing.provider_type == profile.provider_type
                and existing.model_id == profile.model_id
            )
        ]
        self._profiles.append(profile)

    def get_all_profiles(self, active_only: bool = True) -> list[ProviderCapabilityProfile]:
        if not active_only:
            return list(self._profiles)
        return [profile for profile in self._profiles if profile.is_active]

    def resolve(self, model: str, provider_name: str | None = None) -> ProviderCapabilityProfile | None:
        """Resolve a profile via exact ID or declared alias only."""
        for profile in self.get_all_profiles(active_only=False):
            if profile.matches(model, provider_name):
                return profile
        return None

    def clear(self) -> None:
        self._profiles.clear()

    def reset(self) -> None:
        self._profiles = load_capability_manifest()


_REGISTRY = CapabilityRegistry()


def get_capability_registry() -> CapabilityRegistry:
    """Return the process-local capability registry."""
    return _REGISTRY


def reset_capability_registry() -> None:
    """Reset the process-local capability registry to the pinned manifest."""
    _REGISTRY.reset()


__all__ = [
    "CapabilityLevel",
    "CapabilityRegistry",
    "CapabilityStability",
    "CapabilitySupportLevel",
    "ManifestValidationIssue",
    "ProviderCapabilityProfile",
    "RequestShape",
    "get_manifest_path",
    "get_capability_registry",
    "load_capability_manifest",
    "reset_capability_registry",
    "validate_capability_manifest",
]
