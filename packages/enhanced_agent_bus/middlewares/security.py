"""
Security Middleware for ACGS-2 Pipeline.

Provides prompt injection detection using:
1. Fast regex-based scanning (legacy)
2. AI-powered guardrails (new, more thorough)

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import re
import time
from dataclasses import dataclass

from ..pipeline.context import PipelineContext
from ..pipeline.exceptions import SecurityException
from ..pipeline.middleware import BaseMiddleware, MiddlewareConfig

# Legacy regex patterns for fast path detection
PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"system prompt (leak|override|manipulation)",
    r"do anything now",
    r"jailbreak",
    r"persona (adoption|override)",
    r"\(note to self: .*\)",
    r"\[INST\].*\[/INST\]",
    r"<s>.*ignore.*</s>",
    r"<<SYS>>.*<<SYS>>",
]
_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)
AI_GUARDRAILS_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


@dataclass
class AIGuardrailsConfig:
    """Configuration for AI-powered guardrails.

    Attributes:
        model: Model identifier for prompt classification
        threshold: Classification threshold (0.0-1.0)
        max_tokens: Maximum tokens to classify
        timeout_ms: Timeout for AI inference
        fallback_to_regex: Whether to fallback to regex on AI failure
    """

    model: str = "acgs-prompt-guard-v1"
    threshold: float = 0.85
    max_tokens: int = 512
    timeout_ms: int = 50
    fallback_to_regex: bool = True


class AIGuardrailsClient:
    """Client for AI-powered prompt injection detection.

    PLACEHOLDER: This is a stub implementation. In production, this would
    call an actual ML model service (e.g., via gRPC or HTTP).

    Example:
        client = AIGuardrailsClient(AIGuardrailsConfig())
        result = await client.classify("message content")
        if result.is_injection:
            # Handle injection
    """

    def __init__(self, config: AIGuardrailsConfig):
        self.config = config
        self._available = False  # PLACEHOLDER: Check if service available

    async def classify(self, content: str) -> "GuardrailsResult":
        """Classify content for prompt injection.

        Args:
            content: Text content to classify

        Returns:
            Classification result
        """
        # PLACEHOLDER: Call actual ML model service
        # This stub simulates detection of Base64 and Unicode obfuscation

        # Simple heuristic: detect Base64-like strings
        if self._looks_like_base64(content):
            return GuardrailsResult(
                is_injection=True,
                score=0.92,
                detection_method="base64_heuristic",
            )

        # Simple heuristic: detect Unicode homoglyphs
        if self._has_unicode_homoglyphs(content):
            return GuardrailsResult(
                is_injection=True,
                score=0.88,
                detection_method="unicode_homoglyph",
            )

        return GuardrailsResult(is_injection=False, score=0.1)

    def _looks_like_base64(self, content: str) -> bool:
        """Check if content looks like Base64 encoded."""
        # Simple check: starts with common Base64 prefixes and length
        if len(content) < 8:
            return False

        # Check for Base64 character set
        base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        content_chars = set(content.replace(" ", ""))

        # If >95% of chars are Base64 charset and has padding, likely encoded
        if content_chars.issubset(base64_chars):
            # Additional heuristics: has padding or looks like encoded data
            has_padding = "=" in content
            reasonable_length = len(content) >= 8 and len(content) % 4 == 0
            if (has_padding or reasonable_length) and len(content) >= 8:
                return True

        return False

    def _has_unicode_homoglyphs(self, content: str) -> bool:
        """Check for Unicode homoglyphs (e.g., Cyrillic 'i' vs Latin 'i')."""
        # Common homoglyph Unicode ranges
        suspicious_ranges = [
            (0x0400, 0x04FF),  # Cyrillic
            (0x0370, 0x03FF),  # Greek
        ]

        for char in content:
            code = ord(char)
            for start, end in suspicious_ranges:
                if start <= code <= end:
                    return True

        return False

    @property
    def available(self) -> bool:
        """Whether the AI guardrails service is available."""
        return self._available


@dataclass
class GuardrailsResult:
    """Result of AI guardrails classification."""

    is_injection: bool
    score: float
    detection_method: str | None = None


@dataclass
class SecurityThreat:
    """Security threat detection result."""

    threat_type: str
    confidence: float
    description: str
    metadata: dict | None = None


class AIGuardrails:
    """AI-powered guardrails for prompt injection detection.

    Standalone wrapper for AI-based content scanning with
    Base64/Unicode normalization support.

    Example:
        guardrails = AIGuardrails()
        threat = await guardrails.scan("suspicious content")
        if threat:
            # Handle threat
    """

    def __init__(self, config: AIGuardrailsConfig | None = None):
        self.config = config or AIGuardrailsConfig()
        self._client = AIGuardrailsClient(self.config)

    async def scan(self, content: str) -> SecurityThreat | None:
        """Scan content for security threats.

        Args:
            content: Text content to scan

        Returns:
            SecurityThreat if threat detected, None otherwise
        """
        result = await self._client.classify(content)

        if result.is_injection:
            return SecurityThreat(
                threat_type="prompt_injection",
                confidence=result.score,
                description=f"Detected via {result.detection_method}",
                metadata={"score": result.score, "method": result.detection_method},
            )
        return None


class RegexGuardrails:
    """Regex-based guardrails for fast prompt injection detection.

    Lightweight scanner using compiled regex patterns.

    Example:
        guardrails = RegexGuardrails()
        threat = await guardrails.scan("IGNORE PREVIOUS INSTRUCTIONS")
        if threat:
            # Handle threat
    """

    def __init__(self):
        self._pattern = _INJECTION_RE

    async def scan(self, content: str) -> SecurityThreat | None:
        """Scan content using regex patterns.

        Args:
            content: Text content to scan

        Returns:
            SecurityThreat if threat detected, None otherwise
        """
        if self._pattern.search(content):
            return SecurityThreat(
                threat_type="prompt_injection",
                confidence=0.85,
                description="Detected via regex pattern matching",
                metadata={"patterns": PROMPT_INJECTION_PATTERNS},
            )
        return None


class SecurityMiddleware(BaseMiddleware):
    """Security scanning middleware for prompt injection detection.

    Uses a two-tier approach:
    1. Fast regex scan (always runs)
    2. AI guardrails (optional, more thorough)

    Example:
        # Regex only (fast)
        middleware = SecurityMiddleware()

        # With AI guardrails (more secure)
        middleware = SecurityMiddleware(
            guardrails_config=AIGuardrailsConfig(threshold=0.85)
        )
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        guardrails_config: AIGuardrailsConfig | None = None,
    ):
        super().__init__(config)
        self._guardrails_config = guardrails_config
        self._ai_client = AIGuardrailsClient(guardrails_config) if guardrails_config else None

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Scan message for security issues.

        Args:
            context: Pipeline context containing the message

        Returns:
            Context with security scan results

        Raises:
            SecurityException: If injection detected and fail_closed is True
        """
        start_time = time.perf_counter()
        content = str(context.message.content)
        injection_detected = False

        # Tier 1: Fast regex scan
        if self._regex_scan(content):
            injection_detected = True
            context.security_passed = False
            context.security_result = {
                "blocked": True,
                "detection_method": "regex",
            }

            if self.config.fail_closed:
                raise SecurityException(
                    message="Prompt injection detected",
                    detection_method="regex",
                    details={"matched_pattern": "injection_pattern"},
                )

        # Tier 2: AI guardrails (if enabled)
        elif self._ai_client and self._guardrails_config:
            try:
                ai_result = await self._ai_client.classify(content)

                if ai_result.is_injection and ai_result.score > self._guardrails_config.threshold:
                    injection_detected = True
                    context.security_passed = False
                    context.security_result = {
                        "blocked": True,
                        "detection_method": ai_result.detection_method or "ai_guardrails",
                        "score": ai_result.score,
                    }

                    if self.config.fail_closed:
                        raise SecurityException(
                            message="Prompt injection detected by AI guardrails",
                            detection_method=ai_result.detection_method,
                            details={"score": ai_result.score},
                        )
            except AI_GUARDRAILS_ERRORS as e:
                # AI failure - fallback to regex if configured, but log for debugging
                if hasattr(self, "_logger"):
                    self._logger.warning("AI guardrails classification failed", error=str(e))
                if not self._guardrails_config.fallback_to_regex:
                    raise

        # Only mark as passed if no injection detected
        if not injection_detected:
            context.security_passed = True
            context.security_result = {"blocked": False}

        duration_ms = (time.perf_counter() - start_time) * 1000
        context.metrics.record_security_scan(duration_ms)

        return await self._call_next(context)

    def _regex_scan(self, content: str) -> bool:
        """Perform regex-based injection detection.

        Args:
            content: Text content to scan

        Returns:
            True if injection detected, False otherwise
        """
        return bool(_INJECTION_RE.search(content))
