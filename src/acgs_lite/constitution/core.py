"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: 608508a9bd224290
"""

from .constitution import Constitution
from .rule import AcknowledgedTension, Rule, RuleSynthesisProvider, Severity

__all__ = [
    "AcknowledgedTension",
    "Constitution",
    "Rule",
    "RuleSynthesisProvider",
    "Severity",
]
