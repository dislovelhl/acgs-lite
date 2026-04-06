from __future__ import annotations

import pytest
from acgs_lite.constitution import Constitution, Rule, Severity

pytestmark = pytest.mark.skip(reason="Constitution.to_response_schema() not yet implemented")

from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityLevel,
    ProviderCapabilityProfile,
)
from enhanced_agent_bus.llm_adapters.constrained_output import attach_response_format


def _constitution() -> Constitution:
    return Constitution.from_rules(
        [
            Rule(
                id="STATE",
                text="State must be approved or rejected.",
                severity=Severity.HIGH,
                keywords=["approved", "rejected"],
                patterns=[r"^(approved|rejected)$"],
            )
        ],
        name="integration-constitution",
    )


def _profile(
    *,
    provider_type: str = "openai",
    structured_output: CapabilityLevel = CapabilityLevel.FULL,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=f"{provider_type}-test",
        model_id="model-test",
        display_name="Test Model",
        provider_type=provider_type,
        structured_output=structured_output,
    )


def test_attach_response_format_for_openai_profiles() -> None:
    result = attach_response_format({}, _constitution(), _profile())

    assert result["response_format"]["type"] == "json_schema"
    assert result["response_format"]["json_schema"]["name"] == "integration_constitution"
    assert result["response_format"]["json_schema"]["strict"] is True
    assert result["response_format"]["json_schema"]["schema"]["properties"]["STATE"]["enum"] == [
        "approved",
        "rejected",
    ]


def test_attach_response_format_skips_unsupported_capability() -> None:
    result = attach_response_format(
        {},
        _constitution(),
        _profile(structured_output=CapabilityLevel.NONE),
    )

    assert result == {}


def test_attach_response_format_skips_unknown_provider_mapping() -> None:
    result = attach_response_format({}, _constitution(), _profile(provider_type="anthropic"))

    assert result == {}
