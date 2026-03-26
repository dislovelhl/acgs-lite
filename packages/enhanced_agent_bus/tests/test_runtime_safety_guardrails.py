"""
Tests for Runtime Safety Guardrails.

Tests the OWASP-compliant 5-layer guardrail system:
1. Input Sanitizer
2. Agent Engine
3. Tool Runner Sandbox
4. Output Verifier
5. Audit Log

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock

import pytest

from ..runtime_safety_guardrails import (
    AgentEngine,
    AuditLog,
    GuardrailLayer,
    InputSanitizer,
    InputSanitizerConfig,
    OutputVerifier,
    RuntimeSafetyGuardrails,
    RuntimeSafetyGuardrailsConfig,
    SafetyAction,
    ToolRunnerSandbox,
    Violation,
    ViolationSeverity,
)


class TestInputSanitizer:
    """Tests for Input Sanitizer component."""

    @pytest.fixture
    def sanitizer(self):
        """Create input sanitizer instance."""
        return InputSanitizer()

    async def test_sanitize_normal_input(self, sanitizer):
        """Test sanitizing normal input."""
        data = "Hello, this is normal input."
        context = {"trace_id": "test-trace"}

        result = await sanitizer.process(data, context)

        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert len(result.violations) == 0

    async def test_detect_pii_email(self, sanitizer):
        """Test PII detection for email addresses."""
        data = "Contact me at user@example.com for details."
        context = {"trace_id": "test-trace"}

        result = await sanitizer.process(data, context)

        assert result.allowed is True  # Allow but flag
        assert result.action == SafetyAction.AUDIT
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "pii_detected"

    async def test_detect_injection_attack(self, sanitizer):
        """Test injection attack detection."""
        data = "Normal text <script>alert('xss')</script> more text"
        context = {"trace_id": "test-trace"}

        result = await sanitizer.process(data, context)

        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert len(result.violations) >= 1  # May match multiple injection patterns
        assert result.violations[0].violation_type == "injection_attack"
        assert result.violations[0].severity == ViolationSeverity.CRITICAL

    async def test_html_sanitization(self, sanitizer):
        """Test HTML sanitization."""
        # Create sanitizer with injection detection disabled to test pure HTML sanitization
        config = InputSanitizerConfig(detect_injection=False, sanitize_html=True)
        html_sanitizer = InputSanitizer(config=config)

        data = "Normal text <script>evil()</script> and <iframe>bad</iframe>"
        context = {"trace_id": "test-trace"}

        result = await html_sanitizer.process(data, context)

        assert result.allowed is True
        assert result.modified_data is not None
        assert "<script>" not in result.modified_data
        assert "<iframe>" not in result.modified_data


class TestAgentEngine:
    """Tests for Agent Engine component."""

    @pytest.fixture
    def engine(self):
        """Create agent engine instance."""
        return AgentEngine()

    async def test_normal_request_processing(self, engine):
        """Test normal request processing."""
        data = {"action": "read_data", "resource": "public_info"}
        context = {"trace_id": "test-trace"}

        result = await engine.process(data, context)

        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert len(result.violations) == 0

    async def test_constitutional_validation_failure(self, engine):
        """Test constitutional validation failure."""
        # Mock the constitutional validation to fail
        engine._validate_constitutional = AsyncMock(
            return_value={
                "compliant": False,
                "confidence": 0.9,
                "reason": "Violates privacy principles",
            }
        )

        data = {"action": "access_private_data"}
        context = {"trace_id": "test-trace"}

        result = await engine.process(data, context)

        assert result.allowed is False
        assert result.action == SafetyAction.ESCALATE
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "constitutional_violation"


class TestToolRunnerSandbox:
    """Tests for Tool Runner Sandbox component."""

    @pytest.fixture
    def sandbox(self):
        """Create sandbox instance."""
        return ToolRunnerSandbox()

    async def test_sandbox_execution_success(self, sandbox):
        """Test successful sandbox execution."""
        # Mock sandbox execution to succeed
        sandbox._execute_in_sandbox = AsyncMock(return_value={"success": True, "output": "hello\n"})

        data = {"tool": "echo", "args": ["hello"]}
        context = {"trace_id": "test-trace"}

        result = await sandbox.process(data, context)

        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert len(result.violations) == 0

    async def test_sandbox_execution_failure(self, sandbox):
        """Test sandbox execution failure."""
        # Mock sandbox execution to fail
        sandbox._execute_in_sandbox = AsyncMock(
            return_value={"success": False, "error": "Command not allowed"}
        )

        data = {"command": "dangerous_command"}
        context = {"trace_id": "test-trace", "should_sandbox": True}

        result = await sandbox.process(data, context)

        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert len(result.violations) == 1
        assert "sandbox_execution_failed" in result.violations[0].violation_type


class TestOutputVerifier:
    """Tests for Output Verifier component."""

    @pytest.fixture
    def verifier(self):
        """Create output verifier instance."""
        return OutputVerifier()

    async def test_verify_safe_output(self, verifier):
        """Test verifying safe output."""
        data = "This is safe output content."
        context = {"trace_id": "test-trace"}

        result = await verifier.process(data, context)

        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert len(result.violations) == 0

    async def test_detect_harmful_content(self, verifier):
        """Test detection of harmful content."""
        data = "Here are instructions for how to hack a website."
        context = {"trace_id": "test-trace"}

        result = await verifier.process(data, context)

        assert result.allowed is False
        assert result.action == SafetyAction.BLOCK
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == "harmful_content"

    async def test_pii_redaction(self, verifier):
        """Test PII redaction in output."""
        data = "Contact support@example.com for help."
        context = {"trace_id": "test-trace"}

        result = await verifier.process(data, context)

        assert result.allowed is True
        assert result.action == SafetyAction.MODIFY
        assert result.modified_data is not None
        assert "support@example.com" not in result.modified_data
        assert "[REDACTED]" in result.modified_data


class TestAuditLog:
    """Tests for Audit Log component."""

    @pytest.fixture
    def audit_log(self):
        """Create audit log instance."""
        return AuditLog()

    async def test_audit_logging(self, audit_log):
        """Test audit logging functionality."""
        context = {
            "trace_id": "test-trace",
            "current_layer": GuardrailLayer.INPUT_SANITIZER,
            "action": SafetyAction.ALLOW,
            "allowed": True,
            "violations": [],
            "processing_time_ms": 50.0,
            "metadata": {"test": "data"},
        }

        result = await audit_log.process(None, context)

        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW

        # Check that entry was logged
        entries = audit_log.get_entries("test-trace")
        assert len(entries) == 1
        assert entries[0]["trace_id"] == "test-trace"
        assert entries[0]["allowed"] is True

    async def test_audit_metrics(self, audit_log):
        """Test audit log metrics."""
        # Add some test entries
        await audit_log.process(
            None,
            {
                "trace_id": "trace1",
                "action": SafetyAction.ALLOW,
                "allowed": True,
                "violations": [],
                "processing_time_ms": 10.0,
            },
        )

        await audit_log.process(
            None,
            {
                "trace_id": "trace2",
                "action": SafetyAction.BLOCK,
                "allowed": False,
                "violations": [
                    Violation(
                        layer=GuardrailLayer.INPUT_SANITIZER,
                        violation_type="test",
                        severity=ViolationSeverity.LOW,
                        message="test violation",
                    )
                ],
                "processing_time_ms": 20.0,
            },
        )

        metrics = await audit_log.get_metrics()

        assert metrics["total_entries"] == 2
        assert metrics["allowed_rate"] == 0.5  # 1 allowed out of 2
        assert metrics["violation_rate"] == 0.5  # 1 violation total


class TestRuntimeSafetyGuardrails:
    """Tests for the complete Runtime Safety Guardrails system."""

    @pytest.fixture
    def guardrails(self):
        """Create runtime safety guardrails instance."""
        config = RuntimeSafetyGuardrailsConfig()
        # Disable some layers for faster testing
        config.sandbox.enabled = False
        return RuntimeSafetyGuardrails(config)

    async def test_full_pipeline_success(self, guardrails):
        """Test successful processing through all layers."""
        request_data = {"action": "safe_action", "data": "safe content"}
        context = {"content_type": "application/json"}

        result = await guardrails.process_request(request_data, context)

        assert result["allowed"] is True
        assert result["trace_id"] is not None
        assert len(result["layer_results"]) > 0
        assert "input_sanitizer" in result["layer_results"]
        assert "agent_engine" in result["layer_results"]
        assert "output_verifier" in result["layer_results"]

    async def test_pipeline_with_violation(self, guardrails):
        """Test processing with a violation that gets blocked."""
        # Inject a violation in the input sanitizer by using XSS
        request_data = "Safe text <script>alert('xss')</script>"
        context = {"content_type": "text/plain"}

        result = await guardrails.process_request(request_data, context)

        assert result["allowed"] is False
        assert len(result["violations"]) > 0
        assert any(v["violation_type"] == "injection_attack" for v in result["violations"])

    async def test_metrics_collection(self, guardrails):
        """Test metrics collection across layers."""
        # Process a few requests
        await guardrails.process_request("safe request 1")
        await guardrails.process_request("safe request 2")

        metrics = await guardrails.get_metrics()

        assert "system" in metrics
        assert "constitutional_hash" in metrics["system"]
        assert "input_sanitizer" in metrics
        assert "agent_engine" in metrics
        assert "output_verifier" in metrics
        assert "audit_log" in metrics

    async def test_trace_id_generation(self, guardrails):
        """Test that trace IDs are generated and consistent."""
        result1 = await guardrails.process_request("request 1")
        result2 = await guardrails.process_request("request 2")

        assert result1["trace_id"] is not None
        assert result2["trace_id"] is not None
        assert result1["trace_id"] != result2["trace_id"]

    async def test_custom_trace_id(self, guardrails):
        """Test using custom trace ID."""
        custom_trace_id = "custom-trace-123"
        context = {"trace_id": custom_trace_id}

        result = await guardrails.process_request("test request", context)

        assert result["trace_id"] == custom_trace_id


class TestGuardrailConfiguration:
    """Tests for guardrail configuration."""

    def test_default_configuration(self):
        """Test default configuration values."""
        config = RuntimeSafetyGuardrailsConfig()

        assert config.input_sanitizer.enabled is True
        assert config.agent_engine.enabled is True
        assert config.sandbox.enabled is True
        assert config.output_verifier.enabled is True
        assert config.audit_log.enabled is True
        assert config.strict_mode is False
        assert config.fail_closed is True

    def test_custom_configuration(self):
        """Test custom configuration."""
        from ..runtime_safety_guardrails import AgentEngineConfig, InputSanitizerConfig

        config = RuntimeSafetyGuardrailsConfig(
            input_sanitizer=InputSanitizerConfig(max_input_length=500),
            agent_engine=AgentEngineConfig(constitutional_validation=False),
            strict_mode=True,
            timeout_ms=10000,
        )

        assert config.input_sanitizer.max_input_length == 500
        assert config.agent_engine.constitutional_validation is False
        assert config.strict_mode is True
        assert config.timeout_ms == 10000
