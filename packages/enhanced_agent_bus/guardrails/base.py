"""
Guardrail Base Classes and Constants.

Provides the abstract base class for guardrail components and shared constants
including PII detection patterns used across multiple layers.

Constitutional Hash: 608508a9bd224290
"""

from abc import ABC, abstractmethod

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .enums import GuardrailLayer
from .models import GuardrailResult

# Type alias for guardrail input data - accepts any serializable value
# Used throughout the guardrail pipeline for flexible input handling
GuardrailInput = str | JSONDict | list | bytes | int | float | bool | None

# Centralized PII patterns for synchronization across layers
PII_PATTERNS = [
    # Social Security Numbers (US)
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b\d{9}\b",  # SSN without dashes
    # Credit/Debit Card Numbers
    r"\b\d{13,19}\b",  # General card number length
    r"\b\d{4}\s\d{4}\s\d{4}\s\d{4}\b",  # Card with spaces
    r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",  # Card with dashes
    # Email Addresses
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    # Phone Numbers (various formats)
    r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # US phone
    r"\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b",  # US phone with parens
    r"\b\+?\d{1,3}[-.\s]?\d{1,14}\b",  # International phone
    # IP Addresses
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    # MAC Addresses
    r"\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b",
    # Bank Account Numbers (US routing + account)
    r"\b\d{9}\s+\d{6,17}\b",
    # Driver's License Numbers (various states)
    r"\b[A-Z]\d{7}\b",  # California format
    r"\b\d{2}\s\d{3}\s\d{4}\b",  # New York format
    # Passport Numbers
    r"\b[A-Z]{1,2}\d{6,9}\b",
    # Tax ID Numbers
    r"\b\d{2}-\d{7}\b",  # EIN format
    # Health Insurance Numbers
    r"\b[A-Z]{2}\d{8}\b",  # Sample health ID format
    # API Keys/Tokens (more specific patterns to reduce false positives)
    r"\b[a-f0-9]{32}\b",  # MD5-like or 32-char hex API key
    r"\b[a-zA-Z0-9]{40}\b",  # 40-char token (GitHub, etc.)
    r"sk-[a-zA-Z0-9]{48}",  # OpenAI API key pattern
    r"xox[bapz]-\d+-\d+-[a-zA-Z0-9]{24}",  # Slack tokens (improved)
    # Cryptocurrency Addresses
    r"\b(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,62}\b",  # Bitcoin (Base58/Bech32)
    r"\b0x[a-fA-F0-9]{40}\b",  # Ethereum
    # URLs with sensitive parameters
    r"https?://[^\s]*?(?:password|token|key|secret|credential)=[^\s&]+",
]


class GuardrailComponent(ABC):
    """Abstract base class for guardrail components.

    All guardrail layers must implement this interface to ensure
    consistent processing and metrics collection across the pipeline.
    """

    # Config attribute - all subclasses have a config with at minimum an 'enabled' flag
    config: object  # Subclass-specific config type

    @abstractmethod
    async def process(self, data: GuardrailInput, context: JSONDict) -> GuardrailResult:
        """Process data through this guardrail component.

        Args:
            data: The input data to process
            context: Additional context information including trace_id

        Returns:
            GuardrailResult containing the action taken and any violations
        """
        pass

    @abstractmethod
    def get_layer(self) -> GuardrailLayer:
        """Return the guardrail layer this component implements."""
        pass

    async def get_metrics(self) -> JSONDict:
        """Get metrics for this component.

        Override in subclasses to provide layer-specific metrics.
        """
        return {}
