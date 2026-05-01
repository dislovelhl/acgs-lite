from __future__ import annotations

from datetime import date
from pathlib import Path

from acgs_lite.provider_capabilities import (
    CapabilityStability,
    CapabilitySupportLevel,
    ManifestValidationIssue,
    ProviderCapabilityProfile,
    RequestShape,
    load_capability_manifest,
    validate_capability_manifest,
)


def _source_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_manifest_documented_entries_have_request_shape() -> None:
    for profile in load_capability_manifest():
        if profile.support_level == CapabilitySupportLevel.DOCUMENTED:
            assert profile.request_shape != RequestShape.NONE


def test_manifest_preview_entries_are_explicitly_marked() -> None:
    preview_profiles = [
        profile
        for profile in load_capability_manifest()
        if profile.stability == CapabilityStability.PREVIEW
    ]
    assert preview_profiles
    assert all("preview" in profile.model_id for profile in preview_profiles)


def test_runtime_source_defaults_exist_in_manifest() -> None:
    manifest_models = {profile.model_id for profile in load_capability_manifest()}
    source_defaults = {
        "gpt-5.5",
        "claude-sonnet-4-6",
        "gemini-3-flash-preview",
    }
    assert source_defaults <= manifest_models


def test_source_examples_reference_current_provider_defaults() -> None:
    _src_root = Path(__file__).resolve().parents[1] / "src" / "acgs_lite" / "integrations"
    assert 'model="gpt-5.5"' in _source_text(str(_src_root / "openai.py"))
    assert 'model="claude-sonnet-4-6"' in _source_text(str(_src_root / "anthropic.py"))
    assert 'model="gemini-3-flash-preview"' in _source_text(str(_src_root / "google_genai.py"))


def test_validate_manifest_reports_stale_entries() -> None:
    issues = validate_capability_manifest(
        [
            ProviderCapabilityProfile(
                provider_id="p",
                model_id="m",
                display_name="m",
                provider_type="openai",
                support_level=CapabilitySupportLevel.DOCUMENTED,
                request_shape=RequestShape.OPENAI_RESPONSE_FORMAT_JSON_SCHEMA,
                evidence_source="https://example.com",
                checked_at="2025-01-01",
            )
        ],
        max_age_days=30,
        today=date(2026, 4, 8),
    )
    assert any(issue.code == "stale_entry" for issue in issues)


def test_validate_manifest_reports_missing_request_shape_for_documented_support() -> None:
    issues = validate_capability_manifest(
        [
            ProviderCapabilityProfile(
                provider_id="p",
                model_id="m",
                display_name="m",
                provider_type="anthropic",
                support_level=CapabilitySupportLevel.DOCUMENTED,
                request_shape=RequestShape.NONE,
                evidence_source="https://example.com",
                checked_at="2026-04-08",
            )
        ],
        today=date(2026, 4, 8),
    )
    assert any(issue.code == "documented_without_request_shape" for issue in issues)


def test_validate_manifest_reports_preview_stability_mismatch() -> None:
    issues = validate_capability_manifest(
        [
            ProviderCapabilityProfile(
                provider_id="p",
                model_id="gemini-2.5-flash",
                display_name="m",
                provider_type="google",
                support_level=CapabilitySupportLevel.DOCUMENTED,
                request_shape=RequestShape.GOOGLE_CONFIG_JSON_SCHEMA,
                evidence_source="https://example.com",
                checked_at="2026-04-08",
                stability=CapabilityStability.PREVIEW,
            )
        ],
        today=date(2026, 4, 8),
    )
    assert issues == [
        ManifestValidationIssue(
            code="preview_stability_mismatch",
            model_id="gemini-2.5-flash",
            message="Preview entries must use preview model IDs",
        )
    ]
