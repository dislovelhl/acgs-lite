from __future__ import annotations

import logging
import sys
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ValidationError
from enhanced_agent_bus._compat.security.auth import UserClaims, get_current_user

from .models import (
    CopilotRequest,
    CopilotResponse,
    ExplainRequest,
    ExplainResponse,
    ImproveRequest,
    ImproveResponse,
    PolicyResult,
    PolicyTemplate,
    PolicyTemplateCategory,
    RiskAssessment,
    TestRequest,
    TestResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.policy_copilot.api", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.policy_copilot.api", _module)

router = APIRouter(
    prefix="/api/v1/policy-copilot",
    tags=["policy-copilot"],
    dependencies=[Depends(get_current_user)],
)

_nlp_engine: Any | None = None
_rego_generator: Any | None = None
_policy_validator: Any | None = None

API_ERRORS = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)


# ---------------------------------------------------------------------------
# API-only models (not in models.py)
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    valid: bool = True
    status: str = "healthy"
    version: str = "1.0.0"
    constitutional_hash: str = CONSTITUTIONAL_HASH
    components: dict[str, bool] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    policy_id: str
    feedback: str
    comment: str | None = None

    @field_validator("feedback")
    @classmethod
    def _validate_feedback(cls, value: str) -> str:
        if value not in {"thumbs_up", "thumbs_down"}:
            raise ValueError("feedback must be thumbs_up or thumbs_down")
        return value


class FeedbackResponse(BaseModel):
    received: bool = True
    policy_id: str


class TemplateListResponse(BaseModel):
    valid: bool = True
    templates: list[PolicyTemplate] = Field(default_factory=list)
    total: int = 0


class ValidateRequest(BaseModel):
    policy: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Dependency providers (singleton factories)
# ---------------------------------------------------------------------------


def get_nlp_engine() -> Any:
    global _nlp_engine
    if _nlp_engine is None:

        class _Engine:
            def extract_entities(self, _description: str) -> list:
                return []

            def detect_policy_type(self, _description: str) -> str:
                return "role_based"

        _nlp_engine = _Engine()
    return _nlp_engine


def get_rego_generator() -> Any:
    global _rego_generator
    if _rego_generator is None:

        class _Generator:
            TEMPLATES: dict[str, PolicyTemplate] = {}

            def generate(self, *_args: Any, **_kwargs: Any) -> PolicyResult:
                return PolicyResult(
                    rego_code="package authz\ndefault allow = false",
                    explanation="Generated policy",
                )

            def explain(self, _policy: str, *_args: Any, **_kwargs: Any) -> dict:
                return {"explanation": "Generated explanation", "risks": [], "suggestions": []}

            def improve(self, policy: str, *_args: Any, **_kwargs: Any) -> tuple[str, list[str]]:
                return policy, []

            def get_templates(
                self, category: PolicyTemplateCategory | None = None
            ) -> list[PolicyTemplate]:
                values = list(self.TEMPLATES.values())
                if category is None:
                    return values
                return [t for t in values if t.category == category]

        _rego_generator = _Generator()
    return _rego_generator


def get_policy_validator() -> Any:
    global _policy_validator
    if _policy_validator is None:

        class _Validator:
            def validate_syntax(self, _policy: str) -> ValidationResult:
                return ValidationResult(valid=True, syntax_check=True)

            def test_policy(self, _policy: str, _input: dict) -> TestResult:
                return TestResult(allowed=True)

        _policy_validator = _Validator()
    return _policy_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_tenant_scope(user: UserClaims, tenant_id: str | None) -> str:
    if tenant_id is None:
        return user.tenant_id
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant denied")
    return tenant_id


def _safe_risk(raw: dict) -> RiskAssessment:
    """Build RiskAssessment with safe defaults for missing fields."""
    return RiskAssessment(
        severity=raw.get("severity", "low"),
        category=raw.get("category", "general"),
        description=raw.get("description", ""),
        mitigation=raw.get("mitigation"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/health")
async def health_check(
    nlp: Annotated[Any, Depends(get_nlp_engine)],
    generator: Annotated[Any, Depends(get_rego_generator)],
    validator: Annotated[Any, Depends(get_policy_validator)],
) -> HealthResponse:
    return HealthResponse(
        components={
            "nlp_engine": nlp is not None,
            "rego_generator": generator is not None,
            "policy_validator": validator is not None,
        },
    )


@router.post("/generate")
async def generate_policy(
    request: CopilotRequest,
    user: Annotated[UserClaims, Depends(get_current_user)],
    nlp: Annotated[Any, Depends(get_nlp_engine)],
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> CopilotResponse:
    tenant_id = _assert_tenant_scope(user, request.tenant_id)
    try:
        entities = nlp.extract_entities(request.description)
        _policy_type = nlp.detect_policy_type(request.description)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Use template if specified and available
    kwargs: dict[str, Any] = {"tenant_id": tenant_id, "entities": entities}
    if request.template_id:
        templates = getattr(generator, "TEMPLATES", {})
        if request.template_id in templates:
            kwargs["policy_type"] = request.template_id

    result = generator.generate(request.description, **kwargs)

    suggestions: list[str] = []
    risks: list[str] = []
    if result.confidence < 0.7:
        suggestions.append("Confidence is low; review the generated policy before use.")
    if "default allow = true" in result.rego_code:
        risks.append("Default allow detected; deny-by-default is safer.")

    return CopilotResponse(
        policy_id=result.policy_id,
        policy=result.rego_code,
        explanation=result.explanation,
        test_cases=result.test_cases,
        confidence=result.confidence,
        entities=result.entities,
        suggestions=suggestions,
        risks=risks,
        constitutional_hash=result.constitutional_hash,
    )


@router.post("/explain")
async def explain_policy(
    request: ExplainRequest,
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> ExplainResponse:
    try:
        response = generator.explain(request.policy, detail_level=request.detail_level)
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    risks = [_safe_risk(r) for r in response.get("risks", [])]
    return ExplainResponse(
        explanation=response.get("explanation", ""),
        risks=risks,
        suggestions=response.get("suggestions", []),
        complexity_score=response.get("complexity_score", 0.0),
    )


@router.post("/improve")
async def improve_policy(
    request: ImproveRequest,
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> ImproveResponse:
    try:
        improved_policy, changes = generator.improve(
            request.policy, feedback=request.feedback, instruction=request.instruction
        )
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ImproveResponse(
        improved_policy=improved_policy,
        explanation=f"Applied {len(changes)} changes to the policy.",
        changes_made=changes,
    )


@router.post("/validate")
async def validate_policy(
    request: ValidateRequest,
    validator: Annotated[Any, Depends(get_policy_validator)],
) -> ValidationResult:
    try:
        return validator.validate_syntax(request.policy)
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test")
async def test_policy(
    request: TestRequest,
    validator: Annotated[Any, Depends(get_policy_validator)],
) -> TestResult:
    try:
        return validator.test_policy(request.policy, request.test_input)
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/templates")
async def get_templates(
    category: PolicyTemplateCategory | None = Query(default=None),
    generator: Annotated[Any, Depends(get_rego_generator)] = None,
) -> TemplateListResponse:
    try:
        templates = generator.get_templates(category)
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TemplateListResponse(templates=templates, total=len(templates))


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> PolicyTemplate:
    templates = getattr(generator, "TEMPLATES", {})
    template = templates.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"template not found: {template_id}")
    return template


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    try:
        logger.info("Feedback received for policy %s: %s", request.policy_id, request.feedback)
    except API_ERRORS as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FeedbackResponse(policy_id=request.policy_id)
