"""
Output Verifier Guardrail Component.

Layer 4 of OWASP guardrails: validates and sanitizes output before it reaches
users, including content safety checks, toxicity filtering, and PII redaction.

Constitutional Hash: cdd01ef066bc6cf2
"""

import json
import re
import time
from dataclasses import dataclass

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import PII_PATTERNS, GuardrailComponent, GuardrailInput
from .enums import GuardrailLayer, SafetyAction, ViolationSeverity
from .models import GuardrailResult, Violation

logger = get_logger(__name__)


@dataclass
class OutputVerifierConfig:
    """Configuration for output verifier."""

    enabled: bool = True
    content_safety_check: bool = True
    pii_redaction: bool = True
    hallucination_detection: bool = False  # Future feature
    toxicity_filter: bool = True
    timeout_ms: int = 2000


class OutputVerifier(GuardrailComponent):
    """Output Verifier: Layer 4 of OWASP guardrails.

    Validates and sanitizes output before it reaches users.
    Provides protection against:
    - Harmful instruction generation
    - Toxic content
    - PII leakage
    """

    def __init__(self, config: OutputVerifierConfig | None = None):
        self.config = config or OutputVerifierConfig()
        self._toxicity_patterns = self._compile_toxicity_patterns()
        self._pii_patterns = [re.compile(p, re.IGNORECASE) for p in PII_PATTERNS]

    def get_layer(self) -> GuardrailLayer:
        return GuardrailLayer.OUTPUT_VERIFIER

    def _compile_toxicity_patterns(self) -> list[re.Pattern]:
        """Compile toxicity detection patterns."""
        patterns = [
            r"\b(hate|racist|sexist|violent)\b",
            r"\b(kill|murder|attack|harm)\s+(yourself|others|people)\b",
            r"\b(suicide|self-harm)\b",
        ]
        return [re.compile(p, re.IGNORECASE) for p in patterns]

    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Verify and sanitize output."""
        start_time = time.monotonic()
        violations = []
        trace_id = context.get("trace_id", "")
        modified_output = None

        try:
            # Convert to string for processing
            if isinstance(data, dict):
                output_text = json.dumps(data)
            elif isinstance(data, str):
                output_text = data
            else:
                output_text = str(data)

            # Content safety check
            if self.config.content_safety_check:
                safety_violations = self._check_content_safety(output_text, trace_id)
                violations.extend(safety_violations)

            # Toxicity filter
            if self.config.toxicity_filter:
                toxicity_violations = self._check_toxicity(output_text, trace_id)
                violations.extend(toxicity_violations)

            # PII redaction
            if self.config.pii_redaction:
                output_text, pii_violations = self._redact_pii(output_text, trace_id)
                violations.extend(pii_violations)
                if pii_violations:
                    modified_output = output_text

            # Determine action
            if violations:
                # Check for critical violations
                critical_violations = [
                    v for v in violations if v.severity == ViolationSeverity.CRITICAL
                ]
                if critical_violations:
                    action = SafetyAction.BLOCK
                    allowed = False
                else:
                    action = SafetyAction.MODIFY
                    allowed = True
            else:
                action = SafetyAction.ALLOW
                allowed = True

        except (json.JSONDecodeError, TypeError, ValueError, re.error) as e:
            logger.error(f"Output verifier error: {e}")
            violations.append(
                Violation(
                    layer=self.get_layer(),
                    violation_type="processing_error",
                    severity=ViolationSeverity.HIGH,
                    message=f"Output verification failed: {e!s}",
                    trace_id=trace_id,
                )
            )
            action = SafetyAction.BLOCK
            allowed = False

        processing_time = (time.monotonic() - start_time) * 1000

        return GuardrailResult(
            action=action,
            allowed=allowed,
            violations=violations,
            modified_data=modified_output,
            processing_time_ms=processing_time,
            trace_id=trace_id,
        )

    def _check_content_safety(self, text: str, trace_id: str = "") -> list[Violation]:
        """Check content for safety violations."""
        violations = []

        # Check for harmful instructions
        harmful_patterns = [
            r"\b(how\s+to|instructions?\s+for|steps?\s+to)\s+(hack|exploit|attack|build.*bomb)\b",
            r"\b(to|how\s+to|instructions?\s+for)\s+(hack|exploit|bypass|crack)\b",
            r"\b(create|make|build|generate)\s+(virus|malware|ransomware|trojan|rootkit)\b",
            r"\b(instructions?\s+to)\s+(harm|kill|murder|attack)\b",
        ]

        for pattern in harmful_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="harmful_content",
                        severity=ViolationSeverity.CRITICAL,
                        message="Output contains potentially harmful instructions",
                        trace_id=trace_id,
                    )
                )
                break  # Only report once

        return violations

    def _check_toxicity(self, text: str, trace_id: str = "") -> list[Violation]:
        """Check for toxic content."""
        violations = []

        for i, pattern in enumerate(self._toxicity_patterns):
            if pattern.search(text):
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="toxicity_detected",
                        severity=ViolationSeverity.HIGH,
                        message=f"Toxic content detected (pattern {i})",
                        details={"pattern_index": i},
                        trace_id=trace_id,
                    )
                )

        return violations

    def _redact_pii(self, text: str, trace_id: str = "") -> tuple[str, list[Violation]]:
        """Redact PII from output using synchronized patterns."""
        violations = []
        redacted = text

        for i, pattern in enumerate(self._pii_patterns):
            matches = pattern.findall(text)
            if matches:
                violations.append(
                    Violation(
                        layer=self.get_layer(),
                        violation_type="pii_leak",
                        severity=ViolationSeverity.HIGH,
                        message=f"PII detected in output: {len(matches)} instances (pattern {i})",
                        details={"match_count": len(matches), "pattern_index": i},
                        trace_id=trace_id,
                    )
                )
                redacted = pattern.sub("[REDACTED]", redacted)

        return redacted, violations
