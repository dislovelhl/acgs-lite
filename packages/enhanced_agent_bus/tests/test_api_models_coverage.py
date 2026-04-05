# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/api_models.py
Target: ≥95% line coverage
"""

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus.api_models import (
    ErrorResponse,
    HealthResponse,
    # Dataclasses / classes
    LatencyMetrics,
    LatencyTracker,
    # Pydantic models
    MessageRequest,
    MessageResponse,
    MessageStatusEnum,
    # Enums
    MessageTypeEnum,
    PolicyOverrideRequest,
    PriorityEnum,
    ServiceUnavailableResponse,
    SessionOverridesRequest,
    StabilityMetricsResponse,
    ValidationErrorResponse,
    ValidationFinding,
    ValidationResponse,
)

# =============================================================================
# MessageTypeEnum Tests
# =============================================================================


class TestMessageTypeEnum:
    def test_all_values_exist(self):
        expected = [
            "command",
            "query",
            "response",
            "event",
            "notification",
            "heartbeat",
            "governance_request",
            "governance_response",
            "constitutional_validation",
            "task_request",
            "task_response",
            "audit_log",
            "chat",
            "message",
            "user_request",
            "governance",
            "constitutional",
            "info",
            "security_alert",
            "agent_command",
            "constitutional_update",
        ]
        actual_values = [e.value for e in MessageTypeEnum]
        for v in expected:
            assert v in actual_values

    def test_is_str_enum(self):
        assert isinstance(MessageTypeEnum.COMMAND, str)
        assert MessageTypeEnum.COMMAND == "command"

    def test_command(self):
        assert MessageTypeEnum.COMMAND.value == "command"

    def test_query(self):
        assert MessageTypeEnum.QUERY.value == "query"

    def test_response(self):
        assert MessageTypeEnum.RESPONSE.value == "response"

    def test_event(self):
        assert MessageTypeEnum.EVENT.value == "event"

    def test_notification(self):
        assert MessageTypeEnum.NOTIFICATION.value == "notification"

    def test_heartbeat(self):
        assert MessageTypeEnum.HEARTBEAT.value == "heartbeat"

    def test_governance_request(self):
        assert MessageTypeEnum.GOVERNANCE_REQUEST.value == "governance_request"

    def test_governance_response(self):
        assert MessageTypeEnum.GOVERNANCE_RESPONSE.value == "governance_response"

    def test_constitutional_validation(self):
        assert MessageTypeEnum.CONSTITUTIONAL_VALIDATION.value == "constitutional_validation"

    def test_task_request(self):
        assert MessageTypeEnum.TASK_REQUEST.value == "task_request"

    def test_task_response(self):
        assert MessageTypeEnum.TASK_RESPONSE.value == "task_response"

    def test_audit_log(self):
        assert MessageTypeEnum.AUDIT_LOG.value == "audit_log"

    def test_chat(self):
        assert MessageTypeEnum.CHAT.value == "chat"

    def test_message(self):
        assert MessageTypeEnum.MESSAGE.value == "message"

    def test_user_request(self):
        assert MessageTypeEnum.USER_REQUEST.value == "user_request"

    def test_governance(self):
        assert MessageTypeEnum.GOVERNANCE.value == "governance"

    def test_constitutional(self):
        assert MessageTypeEnum.CONSTITUTIONAL.value == "constitutional"

    def test_info(self):
        assert MessageTypeEnum.INFO.value == "info"

    def test_security_alert(self):
        assert MessageTypeEnum.SECURITY_ALERT.value == "security_alert"

    def test_agent_command(self):
        assert MessageTypeEnum.AGENT_COMMAND.value == "agent_command"

    def test_constitutional_update(self):
        assert MessageTypeEnum.CONSTITUTIONAL_UPDATE.value == "constitutional_update"

    def test_enum_from_string(self):
        assert MessageTypeEnum("command") == MessageTypeEnum.COMMAND
        assert MessageTypeEnum("query") == MessageTypeEnum.QUERY

    def test_enum_count(self):
        # 21 values total
        assert len(MessageTypeEnum) == 21


# =============================================================================
# PriorityEnum Tests
# =============================================================================


class TestPriorityEnum:
    def test_low(self):
        assert PriorityEnum.LOW.value == "low"

    def test_normal(self):
        assert PriorityEnum.NORMAL.value == "normal"

    def test_medium(self):
        assert PriorityEnum.MEDIUM.value == "medium"

    def test_high(self):
        assert PriorityEnum.HIGH.value == "high"

    def test_critical(self):
        assert PriorityEnum.CRITICAL.value == "critical"

    def test_is_str_enum(self):
        assert isinstance(PriorityEnum.HIGH, str)
        assert PriorityEnum.HIGH == "high"

    def test_from_string(self):
        assert PriorityEnum("low") == PriorityEnum.LOW
        assert PriorityEnum("critical") == PriorityEnum.CRITICAL

    def test_all_values(self):
        values = {e.value for e in PriorityEnum}
        assert values == {"low", "normal", "medium", "high", "critical"}


# =============================================================================
# MessageStatusEnum Tests
# =============================================================================


class TestMessageStatusEnum:
    def test_pending(self):
        assert MessageStatusEnum.PENDING.value == "pending"

    def test_accepted(self):
        assert MessageStatusEnum.ACCEPTED.value == "accepted"

    def test_processing(self):
        assert MessageStatusEnum.PROCESSING.value == "processing"

    def test_completed(self):
        assert MessageStatusEnum.COMPLETED.value == "completed"

    def test_failed(self):
        assert MessageStatusEnum.FAILED.value == "failed"

    def test_rejected(self):
        assert MessageStatusEnum.REJECTED.value == "rejected"

    def test_is_str_enum(self):
        assert isinstance(MessageStatusEnum.PENDING, str)
        assert MessageStatusEnum.PENDING == "pending"

    def test_from_string(self):
        assert MessageStatusEnum("pending") == MessageStatusEnum.PENDING
        assert MessageStatusEnum("failed") == MessageStatusEnum.FAILED

    def test_all_values(self):
        values = {e.value for e in MessageStatusEnum}
        assert values == {"pending", "accepted", "processing", "completed", "failed", "rejected"}


# =============================================================================
# MessageRequest Tests
# =============================================================================


class TestMessageRequest:
    def _make(self, **kwargs):
        defaults = {"content": "Hello world", "sender": "agent-01"}
        defaults.update(kwargs)
        return MessageRequest(**defaults)

    def test_minimal_valid(self):
        req = self._make()
        assert req.content == "Hello world"
        assert req.sender == "agent-01"

    def test_default_message_type(self):
        req = self._make()
        assert req.message_type == MessageTypeEnum.COMMAND

    def test_default_priority(self):
        req = self._make()
        assert req.priority == PriorityEnum.NORMAL

    def test_default_optional_fields_none(self):
        req = self._make()
        assert req.recipient is None
        assert req.tenant_id is None
        assert req.metadata is None
        assert req.session_id is None
        assert req.idempotency_key is None

    def test_set_all_fields(self):
        req = self._make(
            message_type=MessageTypeEnum.QUERY,
            priority=PriorityEnum.HIGH,
            recipient="agent-02",
            tenant_id="tenant-abc",
            metadata={"key": "value"},
            session_id="sess-001",
            idempotency_key="idem-001",
        )
        assert req.message_type == MessageTypeEnum.QUERY
        assert req.priority == PriorityEnum.HIGH
        assert req.recipient == "agent-02"
        assert req.tenant_id == "tenant-abc"
        assert req.metadata == {"key": "value"}
        assert req.session_id == "sess-001"
        assert req.idempotency_key == "idem-001"

    def test_content_whitespace_only_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            self._make(content="   ")
        assert "whitespace" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    def test_content_empty_raises(self):
        with pytest.raises(ValidationError):
            self._make(content="")

    def test_content_tab_only_raises(self):
        with pytest.raises(ValidationError):
            self._make(content="\t\n ")

    def test_content_max_length(self):
        # 1MB = 1048576 chars
        req = self._make(content="a" * 1048576)
        assert len(req.content) == 1048576

    def test_content_too_long_raises(self):
        with pytest.raises(ValidationError):
            self._make(content="a" * 1048577)

    def test_sender_empty_raises(self):
        with pytest.raises(ValidationError):
            self._make(sender="")

    def test_sender_max_length(self):
        req = self._make(sender="s" * 255)
        assert len(req.sender) == 255

    def test_sender_too_long_raises(self):
        with pytest.raises(ValidationError):
            self._make(sender="s" * 256)

    def test_recipient_max_length(self):
        req = self._make(recipient="r" * 255)
        assert len(req.recipient) == 255

    def test_recipient_too_long_raises(self):
        with pytest.raises(ValidationError):
            self._make(recipient="r" * 256)

    def test_tenant_id_max_length(self):
        req = self._make(tenant_id="t" * 100)
        assert len(req.tenant_id) == 100

    def test_tenant_id_too_long_raises(self):
        with pytest.raises(ValidationError):
            self._make(tenant_id="t" * 101)

    def test_message_type_string_coercion(self):
        req = self._make(message_type="query")
        assert req.message_type == MessageTypeEnum.QUERY

    def test_priority_string_coercion(self):
        req = self._make(priority="high")
        assert req.priority == PriorityEnum.HIGH

    def test_invalid_message_type_raises(self):
        with pytest.raises(ValidationError):
            self._make(message_type="invalid_type")

    def test_invalid_priority_raises(self):
        with pytest.raises(ValidationError):
            self._make(priority="ultra")

    def test_metadata_nested(self):
        req = self._make(metadata={"nested": {"a": 1}})
        assert req.metadata["nested"]["a"] == 1

    def test_model_serialization(self):
        req = self._make(recipient="r-01")
        data = req.model_dump()
        assert "content" in data
        assert "sender" in data
        assert "recipient" in data

    def test_json_schema_extra_exists(self):
        schema = MessageRequest.model_config.get("json_schema_extra")
        assert schema is not None
        assert "example" in schema

    def test_content_with_leading_trailing_spaces_valid(self):
        # Has non-whitespace chars, so valid
        req = self._make(content="  hello  ")
        assert req.content == "  hello  "

    def test_model_rebuild_called(self):
        # model_rebuild is called at module level; test that model still works
        req = self._make()
        assert req is not None

    def test_all_message_types_accepted(self):
        for mt in MessageTypeEnum:
            req = self._make(message_type=mt)
            assert req.message_type == mt

    def test_all_priorities_accepted(self):
        for p in PriorityEnum:
            req = self._make(priority=p)
            assert req.priority == p


# =============================================================================
# MessageResponse Tests
# =============================================================================


class TestMessageResponse:
    def _make(self, **kwargs):
        defaults = {
            "message_id": "msg-001",
            "status": MessageStatusEnum.ACCEPTED,
            "timestamp": "2024-01-15T10:30:00Z",
        }
        defaults.update(kwargs)
        return MessageResponse(**defaults)

    def test_minimal_valid(self):
        resp = self._make()
        assert resp.message_id == "msg-001"
        assert resp.status == MessageStatusEnum.ACCEPTED
        assert resp.timestamp == "2024-01-15T10:30:00Z"

    def test_optional_fields_default_none(self):
        resp = self._make()
        assert resp.details is None
        assert resp.correlation_id is None

    def test_with_details(self):
        resp = self._make(details={"key": "val"})
        assert resp.details["key"] == "val"

    def test_with_correlation_id(self):
        resp = self._make(correlation_id="corr-123")
        assert resp.correlation_id == "corr-123"

    def test_status_string_coercion(self):
        resp = self._make(status="completed")
        assert resp.status == MessageStatusEnum.COMPLETED

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            self._make(status="unknown_status")

    def test_all_statuses(self):
        for s in MessageStatusEnum:
            resp = self._make(status=s)
            assert resp.status == s

    def test_serialization(self):
        resp = self._make(correlation_id="c-001", details={"info": "data"})
        data = resp.model_dump()
        assert data["message_id"] == "msg-001"
        assert data["correlation_id"] == "c-001"

    def test_json_schema_extra_exists(self):
        schema = MessageResponse.model_config.get("json_schema_extra")
        assert schema is not None
        assert "example" in schema

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            MessageResponse(status=MessageStatusEnum.ACCEPTED, timestamp="2024-01-01T00:00:00Z")

    def test_json_round_trip(self):
        resp = self._make(correlation_id="c-rt")
        json_str = resp.model_dump_json()
        restored = MessageResponse.model_validate_json(json_str)
        assert restored.message_id == resp.message_id
        assert restored.status == resp.status


# =============================================================================
# ValidationFinding Tests
# =============================================================================


class TestValidationFinding:
    def _make(self, **kwargs):
        defaults = {
            "severity": "critical",
            "code": "ERR_001",
            "message": "Something went wrong",
        }
        defaults.update(kwargs)
        return ValidationFinding(**defaults)

    def test_minimal_valid(self):
        f = self._make()
        assert f.severity == "critical"
        assert f.code == "ERR_001"
        assert f.message == "Something went wrong"
        assert f.field is None

    def test_with_field(self):
        f = self._make(field="content")
        assert f.field == "content"

    def test_severity_warning(self):
        f = self._make(severity="warning")
        assert f.severity == "warning"

    def test_severity_recommendation(self):
        f = self._make(severity="recommendation")
        assert f.severity == "recommendation"

    def test_missing_severity_raises(self):
        with pytest.raises(ValidationError):
            ValidationFinding(code="ERR_001", message="msg")

    def test_missing_code_raises(self):
        with pytest.raises(ValidationError):
            ValidationFinding(severity="critical", message="msg")

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ValidationFinding(severity="critical", code="ERR_001")

    def test_serialization(self):
        f = self._make(field="sender")
        data = f.model_dump()
        assert data["field"] == "sender"
        assert data["severity"] == "critical"


# =============================================================================
# ValidationResponse Tests
# =============================================================================


class TestValidationResponse:
    def test_valid_true(self):
        vr = ValidationResponse(valid=True)
        assert vr.valid is True

    def test_valid_false(self):
        vr = ValidationResponse(valid=False)
        assert vr.valid is False

    def test_default_findings(self):
        vr = ValidationResponse(valid=True)
        assert "critical" in vr.findings
        assert "warnings" in vr.findings
        assert "recommendations" in vr.findings
        assert vr.findings["critical"] == []
        assert vr.findings["warnings"] == []
        assert vr.findings["recommendations"] == []

    def test_custom_findings(self):
        f = ValidationFinding(severity="critical", code="E001", message="fail")
        vr = ValidationResponse(
            valid=False, findings={"critical": [f], "warnings": [], "recommendations": []}
        )
        assert len(vr.findings["critical"]) == 1

    def test_missing_valid_raises(self):
        with pytest.raises(ValidationError):
            ValidationResponse()

    def test_findings_default_factory_gives_new_instance(self):
        v1 = ValidationResponse(valid=True)
        v2 = ValidationResponse(valid=True)
        # Mutate one — should not affect the other
        v1.findings["critical"].append("x")
        assert v2.findings["critical"] == []

    def test_serialization(self):
        vr = ValidationResponse(valid=True)
        data = vr.model_dump()
        assert data["valid"] is True
        assert isinstance(data["findings"], dict)


# =============================================================================
# PolicyOverrideRequest Tests
# =============================================================================


class TestPolicyOverrideRequest:
    def _make(self, **kwargs):
        defaults = {
            "policy_id": "pol-001",
            "variables": {"x": "int"},
            "constraints": ["x > 0"],
        }
        defaults.update(kwargs)
        return PolicyOverrideRequest(**defaults)

    def test_minimal_valid(self):
        pol = self._make()
        assert pol.policy_id == "pol-001"
        assert pol.variables == {"x": "int"}
        assert pol.constraints == ["x > 0"]
        assert pol.name is None
        assert pol.description is None

    def test_with_name_and_description(self):
        pol = self._make(name="My Policy", description="Does stuff")
        assert pol.name == "My Policy"
        assert pol.description == "Does stuff"

    def test_empty_variables(self):
        pol = self._make(variables={})
        assert pol.variables == {}

    def test_empty_constraints(self):
        pol = self._make(constraints=[])
        assert pol.constraints == []

    def test_multiple_constraints(self):
        pol = self._make(constraints=["x > 0", "y < 10", "x + y == 5"])
        assert len(pol.constraints) == 3

    def test_missing_policy_id_raises(self):
        with pytest.raises(ValidationError):
            PolicyOverrideRequest(variables={"x": "int"}, constraints=[])

    def test_missing_variables_raises(self):
        with pytest.raises(ValidationError):
            PolicyOverrideRequest(policy_id="pol-001", constraints=[])

    def test_missing_constraints_raises(self):
        with pytest.raises(ValidationError):
            PolicyOverrideRequest(policy_id="pol-001", variables={"x": "int"})

    def test_serialization(self):
        pol = self._make(name="Test")
        data = pol.model_dump()
        assert data["policy_id"] == "pol-001"
        assert data["name"] == "Test"

    def test_model_rebuild(self):
        pol = self._make()
        assert pol is not None


# =============================================================================
# SessionOverridesRequest Tests
# =============================================================================


class TestSessionOverridesRequest:
    def _make_override(self, policy_id="pol-001"):
        return PolicyOverrideRequest(
            policy_id=policy_id,
            variables={"x": "int"},
            constraints=["x > 0"],
        )

    def test_empty_overrides(self):
        sor = SessionOverridesRequest(overrides=[])
        assert sor.overrides == []

    def test_single_override(self):
        sor = SessionOverridesRequest(overrides=[self._make_override()])
        assert len(sor.overrides) == 1

    def test_multiple_overrides(self):
        sor = SessionOverridesRequest(
            overrides=[
                self._make_override("pol-001"),
                self._make_override("pol-002"),
            ]
        )
        assert len(sor.overrides) == 2
        assert sor.overrides[0].policy_id == "pol-001"
        assert sor.overrides[1].policy_id == "pol-002"

    def test_missing_overrides_raises(self):
        with pytest.raises(ValidationError):
            SessionOverridesRequest()

    def test_serialization(self):
        sor = SessionOverridesRequest(overrides=[self._make_override()])
        data = sor.model_dump()
        assert "overrides" in data
        assert len(data["overrides"]) == 1


# =============================================================================
# HealthResponse Tests
# =============================================================================


class TestHealthResponse:
    def _make(self, **kwargs):
        defaults = {
            "status": "healthy",
            "service": "enhanced-agent-bus",
            "version": "1.0.0",
            "agent_bus_status": "running",
        }
        defaults.update(kwargs)
        return HealthResponse(**defaults)

    def test_minimal_valid(self):
        hr = self._make()
        assert hr.status == "healthy"
        assert hr.service == "enhanced-agent-bus"
        assert hr.version == "1.0.0"
        assert hr.agent_bus_status == "running"

    def test_defaults_false(self):
        hr = self._make()
        assert hr.rate_limiting_enabled is False
        assert hr.circuit_breaker_enabled is False

    def test_rate_limiting_enabled(self):
        hr = self._make(rate_limiting_enabled=True)
        assert hr.rate_limiting_enabled is True

    def test_circuit_breaker_enabled(self):
        hr = self._make(circuit_breaker_enabled=True)
        assert hr.circuit_breaker_enabled is True

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            HealthResponse(status="healthy")

    def test_serialization(self):
        hr = self._make(rate_limiting_enabled=True)
        data = hr.model_dump()
        assert data["rate_limiting_enabled"] is True
        assert data["status"] == "healthy"


# =============================================================================
# ErrorResponse Tests
# =============================================================================


class TestErrorResponse:
    def _make(self, **kwargs):
        defaults = {
            "error": "NotFound",
            "message": "Resource not found",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        defaults.update(kwargs)
        return ErrorResponse(**defaults)

    def test_minimal_valid(self):
        er = self._make()
        assert er.error == "NotFound"
        assert er.message == "Resource not found"
        assert er.timestamp == "2024-01-15T10:30:00Z"
        assert er.details is None
        assert er.correlation_id is None

    def test_with_details(self):
        er = self._make(details={"field": "content", "issue": "too long"})
        assert er.details["field"] == "content"

    def test_with_correlation_id(self):
        er = self._make(correlation_id="corr-abc")
        assert er.correlation_id == "corr-abc"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            ErrorResponse(message="msg", timestamp="2024-01-01T00:00:00Z")

    def test_serialization(self):
        er = self._make(correlation_id="c-x")
        data = er.model_dump()
        assert data["error"] == "NotFound"
        assert data["correlation_id"] == "c-x"


# =============================================================================
# ServiceUnavailableResponse Tests
# =============================================================================


class TestServiceUnavailableResponse:
    def test_valid(self):
        sur = ServiceUnavailableResponse(status="unavailable", message="Maintenance in progress")
        assert sur.status == "unavailable"
        assert sur.message == "Maintenance in progress"

    def test_missing_status_raises(self):
        with pytest.raises(ValidationError):
            ServiceUnavailableResponse(message="msg")

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ServiceUnavailableResponse(status="unavailable")

    def test_serialization(self):
        sur = ServiceUnavailableResponse(status="down", message="Circuit open")
        data = sur.model_dump()
        assert data["status"] == "down"
        assert data["message"] == "Circuit open"


# =============================================================================
# ValidationErrorResponse Tests
# =============================================================================


class TestValidationErrorResponse:
    def test_minimal_valid(self):
        ver = ValidationErrorResponse(message="Validation failed")
        assert ver.message == "Validation failed"
        assert ver.valid is False
        assert ver.findings == {}

    def test_default_valid_false(self):
        ver = ValidationErrorResponse(message="err")
        assert ver.valid is False

    def test_with_findings(self):
        ver = ValidationErrorResponse(
            message="err",
            findings={"critical": [{"code": "E001", "message": "bad"}]},
        )
        assert len(ver.findings["critical"]) == 1

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ValidationErrorResponse()

    def test_serialization(self):
        ver = ValidationErrorResponse(message="fail")
        data = ver.model_dump()
        assert data["valid"] is False
        assert data["message"] == "fail"
        assert data["findings"] == {}


# =============================================================================
# StabilityMetricsResponse Tests
# =============================================================================


class TestStabilityMetricsResponse:
    def _make(self, **kwargs):
        defaults = {
            "spectral_radius_bound": 0.95,
            "divergence": 0.01,
            "max_weight": 0.5,
            "stability_hash": "abc123def456",
            "input_norm": 1.0,
            "output_norm": 0.99,
        }
        defaults.update(kwargs)
        return StabilityMetricsResponse(**defaults)

    def test_minimal_valid(self):
        smr = self._make()
        assert smr.spectral_radius_bound == 0.95
        assert smr.divergence == 0.01
        assert smr.max_weight == 0.5
        assert smr.stability_hash == "abc123def456"
        assert smr.input_norm == 1.0
        assert smr.output_norm == 0.99

    def test_timestamp_auto_generated(self):
        smr = self._make()
        # Should be a non-empty ISO 8601 string
        assert smr.timestamp
        # Should parse as datetime
        dt = datetime.fromisoformat(smr.timestamp)
        assert dt is not None

    def test_timestamp_default_factory_is_utc(self):
        before = datetime.now(UTC)
        smr = self._make()
        after = datetime.now(UTC)
        ts = datetime.fromisoformat(smr.timestamp)
        assert before <= ts <= after

    def test_custom_timestamp(self):
        ts = "2024-06-01T12:00:00+00:00"
        smr = self._make(timestamp=ts)
        assert smr.timestamp == ts

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            StabilityMetricsResponse(
                divergence=0.01,
                max_weight=0.5,
                stability_hash="abc",
                input_norm=1.0,
                output_norm=0.99,
            )

    def test_serialization(self):
        smr = self._make()
        data = smr.model_dump()
        assert "spectral_radius_bound" in data
        assert "stability_hash" in data
        assert "timestamp" in data

    def test_zero_values(self):
        smr = self._make(
            spectral_radius_bound=0.0,
            divergence=0.0,
            max_weight=0.0,
            input_norm=0.0,
            output_norm=0.0,
        )
        assert smr.spectral_radius_bound == 0.0

    def test_large_values(self):
        smr = self._make(spectral_radius_bound=1e10, divergence=1e8, input_norm=999.9)
        assert smr.spectral_radius_bound == 1e10


# =============================================================================
# LatencyMetrics Tests
# =============================================================================


class TestLatencyMetrics:
    def test_default_values(self):
        lm = LatencyMetrics()
        assert lm.p50_ms == 0.0
        assert lm.p95_ms == 0.0
        assert lm.p99_ms == 0.0
        assert lm.min_ms == 0.0
        assert lm.max_ms == 0.0
        assert lm.mean_ms == 0.0
        assert lm.sample_count == 0
        assert lm.window_size == 1000

    def test_custom_values(self):
        lm = LatencyMetrics(
            p50_ms=1.5,
            p95_ms=3.0,
            p99_ms=4.5,
            min_ms=0.1,
            max_ms=10.0,
            mean_ms=2.0,
            sample_count=500,
            window_size=2000,
        )
        assert lm.p50_ms == 1.5
        assert lm.p95_ms == 3.0
        assert lm.p99_ms == 4.5
        assert lm.min_ms == 0.1
        assert lm.max_ms == 10.0
        assert lm.mean_ms == 2.0
        assert lm.sample_count == 500
        assert lm.window_size == 2000

    def test_is_dataclass(self):
        import dataclasses

        assert dataclasses.is_dataclass(LatencyMetrics)

    def test_partial_override(self):
        lm = LatencyMetrics(p50_ms=2.0, sample_count=100)
        assert lm.p50_ms == 2.0
        assert lm.sample_count == 100
        assert lm.p95_ms == 0.0


# =============================================================================
# LatencyTracker Tests
# =============================================================================


class TestLatencyTracker:
    async def test_get_metrics_returns_latency_metrics(self):
        tracker = LatencyTracker()
        metrics = await tracker.get_metrics()
        assert isinstance(metrics, LatencyMetrics)

    async def test_get_metrics_default_values(self):
        tracker = LatencyTracker()
        metrics = await tracker.get_metrics()
        assert metrics.p50_ms == 0.0
        assert metrics.sample_count == 0

    async def test_get_total_messages_returns_zero(self):
        tracker = LatencyTracker()
        total = await tracker.get_total_messages()
        assert total == 0

    async def test_multiple_calls_independent(self):
        tracker = LatencyTracker()
        m1 = await tracker.get_metrics()
        m2 = await tracker.get_metrics()
        assert m1.p50_ms == m2.p50_ms

    def test_instantiation(self):
        tracker = LatencyTracker()
        assert tracker is not None


# =============================================================================
# Module-level model_rebuild verification
# =============================================================================


class TestModelRebuild:
    """Verify all models were successfully rebuilt (called at module level)."""

    def test_message_request_schema(self):
        schema = MessageRequest.model_json_schema()
        assert "content" in schema.get("properties", {})

    def test_message_response_schema(self):
        schema = MessageResponse.model_json_schema()
        assert "message_id" in schema.get("properties", {})

    def test_validation_finding_schema(self):
        schema = ValidationFinding.model_json_schema()
        assert "severity" in schema.get("properties", {})

    def test_validation_response_schema(self):
        schema = ValidationResponse.model_json_schema()
        assert "valid" in schema.get("properties", {})

    def test_health_response_schema(self):
        schema = HealthResponse.model_json_schema()
        assert "status" in schema.get("properties", {})

    def test_error_response_schema(self):
        schema = ErrorResponse.model_json_schema()
        assert "error" in schema.get("properties", {})

    def test_service_unavailable_schema(self):
        schema = ServiceUnavailableResponse.model_json_schema()
        assert "status" in schema.get("properties", {})

    def test_validation_error_response_schema(self):
        schema = ValidationErrorResponse.model_json_schema()
        assert "message" in schema.get("properties", {})

    def test_stability_metrics_response_schema(self):
        schema = StabilityMetricsResponse.model_json_schema()
        assert "spectral_radius_bound" in schema.get("properties", {})

    def test_policy_override_schema(self):
        schema = PolicyOverrideRequest.model_json_schema()
        assert "policy_id" in schema.get("properties", {})

    def test_session_overrides_schema(self):
        schema = SessionOverridesRequest.model_json_schema()
        assert "overrides" in schema.get("properties", {})
