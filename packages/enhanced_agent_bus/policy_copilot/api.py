from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ValidationError
from src.core.shared.security.auth import UserClaims, get_current_user

from .models import (
    CopilotRequest,
    CopilotResponse,
    ExplainRequest,
    ExplainResponse,
    ImproveRequest,
    ImproveResponse,
    PolicyResult,
    PolicyTemplate,
    RiskAssessment,
    TestRequest,
    TestResult,
    ValidationResult,
)

router = APIRouter(
    prefix="/api/v1/policy-copilot",
    tags=["policy-copilot"],
    dependencies=[Depends(get_current_user)],
)

_nlp_engine: Any | None = None
_rego_generator: Any | None = None
_policy_validator: Any | None = None


class HealthResponse(ValidationResult):
    status: str = "healthy"
    constitutional_hash: str = CONSTITUTIONAL_HASH


class FeedbackRequest(ValidationResult):
    policy_id: str
    feedback: str
    comment: str | None = None


class FeedbackResponse(ValidationResult):
    received: bool = True
    policy_id: str


class TemplateListResponse(ValidationResult):
    templates: list[PolicyTemplate] = []
    total: int = 0


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

            def get_templates(self, category: str | None = None) -> list[PolicyTemplate]:
                values = list(self.TEMPLATES.values())
                if category is None:
                    return values
                return [template for template in values if template.category == category]

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


def _assert_tenant_scope(user: UserClaims, tenant_id: str | None) -> str:
    if tenant_id is None:
        return user.tenant_id
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross-tenant denied")
    return tenant_id


@router.get("/health")
async def health_check() -> HealthResponse:
    return HealthResponse(valid=True)


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
    result = generator.generate(request.description, tenant_id=tenant_id, entities=entities)
    suggestions: list[str] = []
    risks: list[str] = []
    if result.confidence < 0.7:
        suggestions.append("Confidence is low; review the generated policy before use.")
    if "default allow = true" in result.rego_code:
        risks.append("Default allow detected; deny-by-default is safer.")
    return CopilotResponse(result=result, suggestions=suggestions, risks=risks)


@router.post("/explain")
async def explain_policy(
    request: ExplainRequest,
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> ExplainResponse:
    response = generator.explain(request.policy, detail_level=request.detail_level)
    risks = [RiskAssessment(**risk) for risk in response.get("risks", [])]
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
    improved_policy, changes = generator.improve(
        request.policy, feedback=request.feedback, instruction=request.instruction
    )
    return ImproveResponse(improved_policy=improved_policy, changes_made=changes)


@router.post("/validate")
async def validate_policy(
    policy: str,
    validator: Annotated[Any, Depends(get_policy_validator)],
) -> ValidationResult:
    return validator.validate_syntax(policy)


@router.post("/test")
async def test_policy(
    request: TestRequest,
    validator: Annotated[Any, Depends(get_policy_validator)],
) -> TestResult:
    return validator.test_policy(request.policy, request.test_input)


@router.get("/templates")
async def get_templates(
    category: str | None = Query(default=None),
    generator: Annotated[Any, Depends(get_rego_generator)] = None,
) -> TemplateListResponse:
    templates = generator.get_templates(category)
    return TemplateListResponse(valid=True, templates=templates, total=len(templates))


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    generator: Annotated[Any, Depends(get_rego_generator)],
) -> PolicyTemplate:
    templates = getattr(generator, "TEMPLATES", {})
    template = templates.get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    return template


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    return FeedbackResponse(valid=True, policy_id=request.policy_id)
