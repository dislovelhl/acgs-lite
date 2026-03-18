"""
Information Flow Control helpers for Enhanced Agent Bus.

Constitutional Hash: cdd01ef066bc6cf2
"""

from .labels import Confidentiality, IFCLabel, IFCViolation, Integrity, taint_merge

__all__ = [
    "Confidentiality",
    "IFCLabel",
    "IFCViolation",
    "Integrity",
    "taint_merge",
]
