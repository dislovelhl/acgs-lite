"""Direct invocation tests for Policy Copilot API handlers (no HTTP transport)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ValidationError
from enhanced_agent_bus._compat.security.auth import UserClaims
from enhanced_agent_bus.policy_copilot.api import (
    FeedbackRequest,
    ValidateRequest,
    explain_policy,
    generate_policy,
    get_template,
    get_templates,
    health_check,
    improve_policy,
    submit_feedback,
    validate_policy,
)
from enhanced_agent_bus.policy_copilot.api import (
    test_policy as api_test_policy,
)
from enhanced_agent_bus.policy_copilot.models import (
    CopilotRequest,
    ExplainRequest,
    ImproveRequest,
    PolicyEntity,
    PolicyEntityType,
    PolicyResult,
    PolicyTemplate,
    PolicyTemplateCategory,
    ValidationResult,
)
from enhanced_agent_bus.policy_copilot.models import (
    TestRequest as CopilotTestRequest,
)
from enhanced_agent_bus.policy_copilot.models import (
    TestResult as CopilotTestResult,
)


def _user(tenant_id: str = "tenant-a") -> UserClaims:
    return UserClaims(
        sub="user-1",
        tenant_id=tenant_id,
        roles=["agent"],
        permissions=["read", "write"],
        exp=9999999999,
        iat=1000000000,
        iss="acgs2",
        constitutional_hash=CONSTITUTIONAL_HASH,  # pragma: allowlist secret
    )


def _result(
    confidence: float = 0.9, rego_code: str = "package authz\ndefault allow = false"
) -> PolicyResult:
    return PolicyResult(
        rego_code=rego_code,
        explanation="explanation",
        test_cases=[],
        confidence=confidence,
        entities=[PolicyEntity(type=PolicyEntityType.ROLE, value="admin", confidence=0.95)],
    )


async def test_health_check_success() -> None:
    nlp = MagicMock()
    gen = MagicMock()
    val = MagicMock()
    result = await health_check(nlp=nlp, generator=gen, validator=val)
    assert result.status == "healthy"
    assert result.constitutional_hash == CONSTITUTIONAL_HASH


async def test_generate_policy_success() -> None:
    nlp = MagicMock()
    nlp.extract_entities.return_value = [PolicyEntity(type=PolicyEntityType.ROLE, value="admin")]
    nlp.detect_policy_type.return_value = "role_based"

    gen = MagicMock()
    gen.TEMPLATES = {}
    gen.generate.return_value = _result()

    req = CopilotRequest(description="Only admins can delete resources", tenant_id="tenant-a")
    resp = await generate_policy(req, user=_user("tenant-a"), nlp=nlp, generator=gen)
    assert resp.confidence == 0.9
    assert resp.constitutional_hash == CONSTITUTIONAL_HASH


async def test_generate_policy_low_confidence_adds_suggestion() -> None:
    nlp = MagicMock()
    nlp.extract_entities.return_value = []
    nlp.detect_policy_type.return_value = "role_based"

    gen = MagicMock()
    gen.TEMPLATES = {}
    gen.generate.return_value = _result(confidence=0.5)

    req = CopilotRequest(description="Policy text", tenant_id="tenant-a")
    resp = await generate_policy(req, user=_user("tenant-a"), nlp=nlp, generator=gen)
    assert any("confidence" in s.lower() for s in resp.suggestions)


async def test_generate_policy_default_allow_adds_risk() -> None:
    nlp = MagicMock()
    nlp.extract_entities.return_value = []
    nlp.detect_policy_type.return_value = "role_based"

    gen = MagicMock()
    gen.TEMPLATES = {}
    gen.generate.return_value = _result(rego_code="package authz\ndefault allow = true")

    req = CopilotRequest(description="Policy text", tenant_id="tenant-a")
    resp = await generate_policy(req, user=_user("tenant-a"), nlp=nlp, generator=gen)
    assert any("default allow" in r.lower() for r in resp.risks)


async def test_generate_policy_cross_tenant_forbidden() -> None:
    nlp = MagicMock()
    nlp.extract_entities.return_value = []
    nlp.detect_policy_type.return_value = "role_based"

    gen = MagicMock()
    gen.TEMPLATES = {}
    gen.generate.return_value = _result()

    req = CopilotRequest(description="Policy text", tenant_id="tenant-b")
    with pytest.raises(HTTPException) as exc:
        await generate_policy(req, user=_user("tenant-a"), nlp=nlp, generator=gen)
    assert exc.value.status_code == 403


async def test_generate_policy_validation_error_maps_400() -> None:
    nlp = MagicMock()
    nlp.extract_entities.side_effect = ValidationError("bad input")

    gen = MagicMock()
    gen.TEMPLATES = {}

    req = CopilotRequest(description="Policy text", tenant_id="tenant-a")
    with pytest.raises(HTTPException) as exc:
        await generate_policy(req, user=_user("tenant-a"), nlp=nlp, generator=gen)
    assert exc.value.status_code == 400


async def test_explain_policy_success() -> None:
    gen = MagicMock()
    gen.explain.return_value = {
        "explanation": "ok",
        "risks": [{"severity": "high", "category": "security", "description": "d"}],
        "suggestions": ["s1"],
        "complexity_score": 0.2,
    }

    resp = await explain_policy(ExplainRequest(policy="package x"), generator=gen)
    assert resp.explanation == "ok"
    assert len(resp.risks) == 1


async def test_improve_policy_success() -> None:
    gen = MagicMock()
    gen.improve.return_value = ("package x", ["change-1"])

    req = ImproveRequest(policy="package x", feedback="make stricter", instruction="stricter")
    resp = await improve_policy(req, generator=gen)
    assert resp.improved_policy == "package x"
    assert resp.changes_made == ["change-1"]


async def test_validate_policy_success() -> None:
    validator = MagicMock()
    validator.validate_syntax.return_value = ValidationResult(valid=True, syntax_check=True)

    resp = await validate_policy(ValidateRequest(policy="package x"), validator=validator)
    assert resp.valid is True


async def test_test_policy_success() -> None:
    validator = MagicMock()
    validator.test_policy.return_value = CopilotTestResult(allowed=True)

    req = CopilotTestRequest(policy="package x", test_input={"k": "v"})
    resp = await api_test_policy(req, validator=validator)
    assert resp.allowed is True


async def test_get_templates_success() -> None:
    gen = MagicMock()
    gen.get_templates.return_value = [
        PolicyTemplate(
            id="t1",
            name="Template 1",
            description="d",
            category=PolicyTemplateCategory.SECURITY,
            rego_template="package x",
            placeholders=[],
            example_usage="u",
            tags=[],
        )
    ]

    resp = await get_templates(category=None, generator=gen)
    assert resp.total == 1


async def test_get_template_not_found_raises_404() -> None:
    gen = MagicMock()
    gen.TEMPLATES = {}

    with pytest.raises(HTTPException) as exc:
        await get_template("missing", generator=gen)
    assert exc.value.status_code == 404


async def test_submit_feedback_success() -> None:
    req = FeedbackRequest(policy_id="p1", feedback="thumbs_up", comment="ok")
    resp = await submit_feedback(req)
    assert resp.received is True
    assert resp.policy_id == "p1"
