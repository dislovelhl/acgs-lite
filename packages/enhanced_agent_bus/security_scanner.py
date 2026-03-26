"""
ACGS-2 Enhanced Agent Bus - Message Security Scanner
Constitutional Hash: 608508a9bd224290

Security scanning and prompt injection detection for agent messages.
Wraps the runtime security scanner and provides a regex-based
fallback for prompt injection detection.
"""

import re

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import AgentMessage
from .runtime_security import get_runtime_security_scanner
from .validators import ValidationResult

logger = get_logger(__name__)
# Prompt injection detection patterns
PROMPT_INJECTION_PATTERNS: list[str] = [
    r"ignore (all )?previous instructions",
    r"system prompt (leak|override|manipulation)",
    r"do anything now",
    r"jailbreak",
    r"persona (adoption|override)",
    r"\(note to self: .*\)",
    r"\[INST\].*\[/INST\]",
]
_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)


class MessageSecurityScanner:
    """Security scanning with prompt injection detection fallback.

    Performs two layers of security validation:
    1. **Runtime scanner** — external, configurable scanner with
       tenant validation, anomaly detection, rate limiting, etc.
    2. **Prompt injection regex** — fast regex-based fallback that
       catches common injection patterns even when the runtime
       scanner is unavailable.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        pass  # stateless — scanner obtained per-call

    async def scan(self, msg: AgentMessage) -> ValidationResult | None:
        """Run full security scan on *msg*.

        Args:
            msg: The agent message to scan.

        Returns:
            ``ValidationResult(is_valid=False)`` if the message is
            blocked, ``None`` if the scan passed.
        """
        scanner = get_runtime_security_scanner()
        security_res = await scanner.scan(
            content=msg.content,
            tenant_id=msg.tenant_id,
            agent_id=msg.from_agent,
            constitutional_hash=msg.constitutional_hash,
            context={
                "priority": msg.priority.value,
                "message_type": msg.message_type.value,
            },
        )

        if security_res.blocked:
            return ValidationResult(
                is_valid=False,
                errors=[security_res.block_reason],
                metadata={
                    "rejection_reason": "security_block",
                    "security_events": [e.to_dict() for e in security_res.events],
                },
            )
        return None

    def detect_prompt_injection(self, msg: AgentMessage) -> ValidationResult | None:
        """Check *msg* content against known injection patterns.

        This is a fast, regex-based check that can run independently
        of the full runtime security scanner.

        Args:
            msg: The agent message to check.

        Returns:
            ``ValidationResult(is_valid=False)`` if an injection
            pattern is detected, ``None`` if content is clean.
        """
        content = msg.content
        content_str = content if isinstance(content, str) else str(content)
        if _INJECTION_RE.search(content_str):
            return ValidationResult(
                is_valid=False,
                errors=["Prompt injection detected"],
                metadata={
                    "rejection_reason": "prompt_injection",
                },
            )
        return None
