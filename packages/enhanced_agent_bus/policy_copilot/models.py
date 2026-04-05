from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.policy_copilot.models", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.policy_copilot.models", _module)

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class PolicyEntityType(StrEnum):
    SUBJECT = "subject"
    ACTION = "action"
    RESOURCE = "resource"
    CONDITION = "condition"
    ROLE = "role"
    TIME = "time"
    LOCATION = "location"


class LogicalOperator(StrEnum):
    AND = "and"
    OR = "or"
    NOT = "not"


class PolicyTemplateCategory(StrEnum):
    COMPLIANCE = "compliance"
    SECURITY = "security"
    ACCESS_CONTROL = "access_control"
    DATA_PROTECTION = "data_protection"
    CUSTOM = "custom"


class PolicyEntity(BaseModel):
    type: PolicyEntityType
    value: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    modifiers: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    __test__ = False
    name: str = Field(min_length=1)
    input_data: dict = Field(default_factory=dict)
    expected_result: bool
    description: str | None = None


class PolicyResult(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rego_code: str = Field(min_length=1)
    explanation: str
    test_cases: list[TestCase] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: list[PolicyEntity] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


class PolicyTemplate(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: PolicyTemplateCategory
    rego_template: str = Field(min_length=1)
    placeholders: list[str] = Field(default_factory=list)
    example_usage: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class CopilotRequest(BaseModel):
    description: str = Field(min_length=3, max_length=5000)
    context: str | None = Field(default=None, max_length=1000)
    template_id: str | None = None
    tenant_id: str | None = None

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("description too short")
        return value


class CopilotResponse(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy: str = ""
    explanation: str = ""
    test_cases: list[TestCase] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: list[PolicyEntity] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


class ExplainRequest(BaseModel):
    policy: str = Field(min_length=1)
    detail_level: str = "detailed"

    @field_validator("detail_level")
    @classmethod
    def _validate_detail_level(cls, value: str) -> str:
        if value not in {"simple", "detailed", "technical"}:
            raise ValueError("invalid detail level")
        return value


class RiskAssessment(BaseModel):
    severity: str
    category: str
    description: str
    mitigation: str | None = None

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, value: str) -> str:
        if value not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid severity")
        return value


class ExplainResponse(BaseModel):
    explanation: str
    risks: list[RiskAssessment] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    complexity_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ImproveRequest(BaseModel):
    policy: str = Field(min_length=1)
    feedback: str = Field(min_length=1, max_length=2000)
    instruction: str = "custom"

    @field_validator("instruction")
    @classmethod
    def _validate_instruction(cls, value: str) -> str:
        if value not in {"stricter", "permissive", "custom"}:
            raise ValueError("invalid instruction")
        return value


class ImproveResponse(BaseModel):
    improved_policy: str
    explanation: str = ""
    changes_made: list[str] = Field(default_factory=list)


class TestRequest(BaseModel):
    __test__ = False

    policy: str = Field(min_length=1)
    test_input: dict
    tenant_id: str | None = None


class TestResult(BaseModel):
    __test__ = False

    allowed: bool
    decision_path: list[str] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    execution_time_ms: float = 0.0


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    syntax_check: bool = False
    best_practices: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in {"user", "assistant", "system"}:
            raise ValueError("invalid role")
        return value


class ChatHistory(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def add_message(self, role: str, content: str, metadata: dict | None = None) -> None:
        msg = ChatMessage(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = datetime.now(UTC)


__all__ = [
    "ChatHistory",
    "ChatMessage",
    "CopilotRequest",
    "CopilotResponse",
    "ExplainRequest",
    "ExplainResponse",
    "ImproveRequest",
    "ImproveResponse",
    "LogicalOperator",
    "PolicyEntity",
    "PolicyEntityType",
    "PolicyResult",
    "PolicyTemplate",
    "PolicyTemplateCategory",
    "RiskAssessment",
    "TestCase",
    "TestRequest",
    "TestResult",
    "ValidationResult",
]
