"""
ACGS-2 Enhanced Agent Bus - Security Helpers
Constitutional Hash: cdd01ef066bc6cf2
"""

import re

from .security.tenant_validator import TenantValidator


def normalize_tenant_id(tenant_id: str | None) -> str | None:
    """Normalize tenant identifiers to a canonical optional value."""
    return TenantValidator.normalize(tenant_id)


def format_tenant_id(tenant_id: str | None) -> str:
    """Format tenant identifiers for logging and validation messages."""
    return tenant_id if tenant_id else "none"


def validate_tenant_consistency(
    agents_registry: dict, from_agent: str, to_agent: str | None, message_tenant: str | None
) -> list[str]:
    """Validate tenant_id consistency for sender/recipient."""
    errors: list[str] = []
    norm_msg_tenant = normalize_tenant_id(message_tenant)

    if from_agent in agents_registry:
        sender_tenant = normalize_tenant_id(agents_registry[from_agent].get("tenant_id"))
        if sender_tenant != norm_msg_tenant:
            errors.append(
                f"Tenant mismatch: message tenant_id '{format_tenant_id(norm_msg_tenant)}' "
                f"does not match sender tenant_id '{format_tenant_id(sender_tenant)}'"
            )

    if to_agent and to_agent in agents_registry:
        recipient_tenant = normalize_tenant_id(agents_registry[to_agent].get("tenant_id"))
        if recipient_tenant != norm_msg_tenant:
            errors.append(
                f"Tenant mismatch: message tenant_id '{format_tenant_id(norm_msg_tenant)}' "
                f"does not match recipient tenant_id '{format_tenant_id(recipient_tenant)}'"
            )

    return errors


PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"system prompt (leak|override)",
    r"do anything now",
    r"jailbreak",
    r"persona (adoption|override)",
    r"\(note to self: .*\)",
    r"\[INST\].*\[/INST\]",
]
_INJECTION_RE = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(content: object) -> bool:
    """Detect potential prompt injection attacks."""
    content_str = content if isinstance(content, str) else str(content)
    return bool(_INJECTION_RE.search(content_str))
