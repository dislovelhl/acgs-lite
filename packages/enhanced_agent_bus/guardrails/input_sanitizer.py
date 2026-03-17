"""
Input Sanitizer Guardrail Component.

Layer 1 of OWASP guardrails: cleans, validates, and sanitizes incoming
requests before they reach the agent engine. Includes HTML sanitization,
injection detection, and PII detection.

Constitutional Hash: cdd01ef066bc6cf2
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import PII_PATTERNS, GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .models import GuardrailResult, Violation

logger = get_logger(__name__)


@dataclass
class InputSanitizerConfig:
    """Configuration for input sanitizer."""

    enabled: bool = True
    max_input_length: int = 1000000  # 1MB
    allowed_content_types: list[str] = field(
        default_factory=lambda: ["text/plain", "application/json"]
    )
    sanitize_html: bool = True
    detect_injection: bool = True
    pii_detection: bool = True
    timeout_ms: int = 1000


class InputSanitizer(GuardrailComponent):
    """Input Sanitizer: Layer 1 of OWASP guardrails.

    Cleans, validates, and sanitizes incoming requests before they reach
    the agent engine. Provides comprehensive protection against:
    - XSS (Cross-Site Scripting)
    - SQL Injection
    - Command Injection
    - Path Traversal
    - LDAP/NoSQL/Template Injection
    - XXE (XML External Entity)
    - PII exposure
    """

    def __init__(self, config: InputSanitizerConfig | None = None):
        self.config = config or InputSanitizerConfig()
        self._pii_patterns = self._compile_pii_patterns()
        self._injection_patterns = self._compile_injection_patterns()

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.INPUT_SANITIZER

    def _compile_pii_patterns(self) -> list[re.Pattern]:
        """Compile comprehensive PII detection patterns (GDPR/HIPAA compliant)."""
        return [re.compile(p, re.IGNORECASE) for p in PII_PATTERNS]

    def _compile_injection_patterns(self) -> list[re.Pattern]:
        """Compile comprehensive injection attack patterns (OWASP compliant)."""
        patterns = [
            # XSS (Cross-Site Scripting)
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"data:text/html",
            r"on\w+\s*=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
            # SQL Injection
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b.*\b(FROM|INTO|TABLE|DATABASE)\b)",
            r"(\bUNION\b.*\bSELECT\b)",
            r"(\bOR\b.*\d+\s*=\s*\d+)",
            r"(\bAND\b.*\d+\s*=\s*\d+)",
            # Command Injection
            r"[;&|`$()<>]",
            r"\\\$\{.*\}",
            r"\$\(.*\)",
            r"`.*`",
            r"eval\s*\(",
            r"exec\s*\(",
            r"system\s*\(",
            r"popen\s*\(",
            r"import\s+os",
            r"import\s+subprocess",
            r"os\.",
            r"subprocess\.",
            r"shutil\.",
            r"commands\.",
            # Path Traversal
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"%2e%2e/",
            r"~/\.",  # Home-dir traversal (e.g. ~/.ssh, ~/.bashrc)
            r"(?<!\w)etc/(?:passwd|shadow|hosts|group|sudoers)",  # /etc/ sensitive files only
            # LDAP Injection
            r"(\*\)|\(\*\))",
            r"(\|\|)",
            r"(&&)",
            # NoSQL Injection
            r"\$ne|\$gt|\$lt|\$gte|\$lte|\$regex|\$where",
            r"db\.\w+\.",
            r"collection\.\w+\.",
            # Template Injection
            r"\{\{.*\}\}",
            r"\{\%.*\%\}",
            r"\$\{.*\}",
            # XML External Entity (XXE)
            r"<!ENTITY",
            r"<!DOCTYPE.*SYSTEM",
            r"file://",
            r"<!DOCTYPE[^>]*http://",  # XXE-specific HTTP reference only
        ]
        return [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Sanitize input data."""
        start_time = time.monotonic()
        violations: list[str] = []
        trace_id = context.get("trace_id", self._generate_trace_id())

        try:
            # Perform all validation steps
            self._validate_input_size(data, violations, trace_id)
            self._validate_content_type(context, violations, trace_id)

            # Normalize input for processing
            input_text, original_text = self._normalize_input(data)

            # Perform sanitization if enabled
            if self.config.sanitize_html:
                input_text = self._sanitize_html(input_text)

            # Perform security checks
            self._perform_security_checks(original_text, input_text, violations, trace_id)

            # Determine final action and apply sanitization if needed
            action, allowed, input_text = self._determine_action(violations, input_text)

        except (json.JSONDecodeError, TypeError, ValueError, re.error) as e:
            action, allowed, input_text = self._handle_processing_error(e, violations, trace_id)

        processing_time = (time.monotonic() - start_time) * 1000

        return GuardrailResult(
            action=action,
            allowed=allowed,
            violations=violations,
            modified_data=input_text if input_text != str(data) else None,
            metadata={"original_length": len(str(data))},
            processing_time_ms=processing_time,
            trace_id=trace_id,
        )

    def _validate_input_size(
        self, data: GuardrailInput, violations: list[Violation], trace_id: str
    ) -> None:
        """Validate input size constraints."""
        if isinstance(data, str) and len(data) > self.config.max_input_length:
            violations.append(
                Violation(
                    layer=self.get_layer(),
                    violation_type="input_too_large",
                    severity=ViolationSeverity.HIGH,
                    message=f"Input size {len(data)} exceeds maximum {self.config.max_input_length}",  # noqa: E501
                    trace_id=trace_id,
                )
            )

    def _validate_content_type(
        self, context: JSONDict, violations: list[Violation], trace_id: str
    ) -> None:
        """Validate content type constraints."""
        content_type = context.get("content_type", "text/plain")
        if content_type not in self.config.allowed_content_types:
            violations.append(
                Violation(
                    layer=self.get_layer(),
                    violation_type="invalid_content_type",
                    severity=ViolationSeverity.MEDIUM,
                    message=f"Content type {content_type} not allowed",
                    trace_id=trace_id,
                )
            )

    def _normalize_input(self, data: GuardrailInput) -> tuple[str, str]:
        """Convert input data to string format for processing."""
        if isinstance(data, dict):
            input_text = json.dumps(data)
        elif isinstance(data, str):
            input_text = data
        else:
            input_text = str(data)

        # Store original text for injection detection before sanitization
        original_text = input_text
        return input_text, original_text

    def _perform_security_checks(
        self, original_text: str, input_text: str, violations: list[Violation], trace_id: str
    ) -> None:
        """Perform injection and PII detection checks."""
        # Injection detection (on original text)
        if self.config.detect_injection:
            injection_violations = self._detect_injection(original_text, trace_id)
            violations.extend(injection_violations)

        # PII detection (on potentially sanitized text)
        if self.config.pii_detection:
            pii_violations = self._detect_pii(input_text, trace_id)
            violations.extend(pii_violations)

    def _determine_action(
        self, violations: list[Violation], input_text: str
    ) -> tuple[SafetyAction, bool, str]:
        """Determine final action based on violations (fail-closed semantics)."""
        if not violations:
            return SafetyAction.ALLOW, True, input_text

        # Check if any violations are critical - BLOCK immediately (fail-closed)
        critical_violations = [v for v in violations if v.severity == ViolationSeverity.CRITICAL]
        if critical_violations:
            return SafetyAction.BLOCK, False, input_text

        # PII detection should result in AUDIT (flag but allow)
        pii_violations = [v for v in violations if v.violation_type == "pii_detected"]
        if pii_violations:
            return SafetyAction.AUDIT, True, input_text

        # Other non-critical violations
        action = SafetyAction.MODIFY if self.config.sanitize_html else SafetyAction.AUDIT
        allowed = True

        # Apply additional sanitization if needed
        if action == SafetyAction.MODIFY:
            input_text = self._apply_sanitization(input_text, violations)

        return action, allowed, input_text

    def _handle_processing_error(
        self, error: Exception, violations: list[Violation], trace_id: str
    ) -> tuple[SafetyAction, bool, str]:
        """Handle processing errors with fail-closed semantics."""
        logger.error(f"Input sanitizer error: {error}")
        violations.append(
            Violation(
                layer=self.get_layer(),
                violation_type="processing_error",
                severity=ViolationSeverity.HIGH,
                message=f"Input processing failed: {error!s}",
                trace_id=trace_id,
            )
        )
        # Fail-closed: block on any processing error
        return SafetyAction.BLOCK, False, ""

    def _sanitize_html(self, text: str) -> str:
        """Basic HTML sanitization."""
        # Remove script tags and their contents
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
        # Remove other dangerous tags
        dangerous_tags = ["iframe", "object", "embed", "form", "input", "button"]
        for tag in dangerous_tags:
            text = re.sub(f"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.IGNORECASE | re.DOTALL)
        return text

    def _detect_injection(self, text: str, trace_id: str = "") -> list[Violation]:
        """Detect injection attacks."""
        violations = []
        for pattern in self._injection_patterns:
            if pattern.search(text):
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="injection_attack",
                        severity=ViolationSeverity.CRITICAL,
                        message="Input rejected: potential injection pattern detected",
                        details={},
                        trace_id=trace_id,
                    )
                )
        return violations

    def _detect_pii(self, text: str, trace_id: str = "") -> list[Violation]:
        """Detect personally identifiable information."""
        violations = []
        for pattern in self._pii_patterns:
            matches = pattern.findall(text)
            if matches:
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="pii_detected",
                        severity=ViolationSeverity.HIGH,
                        message=f"PII detected: {len(matches)} potential matches",
                        details={"match_count": len(matches)},
                        trace_id=trace_id,
                    )
                )
        return violations

    def _apply_sanitization(self, text: str, violations: list[Violation]) -> str:
        """Apply sanitization based on detected violations."""
        sanitized = text
        # Redact PII
        for pattern in self._pii_patterns:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized

    def _generate_trace_id(self) -> str:
        """Generate a trace ID."""
        timestamp = datetime.now(UTC).isoformat()
        data = f"{timestamp}-{CONSTITUTIONAL_HASH}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
