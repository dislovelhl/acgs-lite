"""
Information Flow Control helpers for Enhanced Agent Bus.

Constitutional Hash: 608508a9bd224290
"""

from .labels import Confidentiality, IFCLabel, IFCViolation, Integrity, taint_merge

__all__ = [
    "Confidentiality",
    "IFCLabel",
    "IFCViolation",
    "Integrity",
    "taint_merge",
]
