from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Constitution.to_response_schema() not yet implemented")

from acgs_lite import GovernedAgent
from acgs_lite.constitution import Constitution, Rule, Severity
from enhanced_agent_bus.llm_adapters.capability_matrix import (
    CapabilityLevel,
    ProviderCapabilityProfile,
)


class RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, input: str, **kwargs: object) -> str:
        self.calls.append({"input": input, "kwargs": dict(kwargs)})
        return "ok"


def _constitution() -> Constitution:
    return Constitution.from_rules(
        [
            Rule(
                id="STATE",
                text="State must be approved or rejected.",
                severity=Severity.HIGH,
                keywords=["approved", "rejected"],
            )
        ]
    )


def _profile(*, structured_output: CapabilityLevel = CapabilityLevel.FULL) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id="openai-test",
        model_id="gpt-4o",
        display_name="GPT-4o",
        provider_type="openai",
        structured_output=structured_output,
    )


def test_governed_agent_injects_response_format_for_structured_output() -> None:
    agent = RecordingAgent()
    governed = GovernedAgent(agent, constitution=_constitution(), strict=False, validate_output=True)

    governed.run("safe input", capability_profile=_profile())

    response_format = agent.calls[0]["kwargs"]["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"


def test_governed_agent_skips_response_format_when_capability_is_missing() -> None:
    agent = RecordingAgent()
    governed = GovernedAgent(agent, constitution=_constitution(), strict=False, validate_output=True)

    governed.run(
        "safe input",
        capability_profile=_profile(structured_output=CapabilityLevel.NONE),
    )

    assert "response_format" not in agent.calls[0]["kwargs"]
