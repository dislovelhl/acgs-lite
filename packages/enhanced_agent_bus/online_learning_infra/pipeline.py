"""
Online learning pipeline shim for ACGS-2.
Re-exports implementation from .trainer for backward compatibility.

Constitutional Hash: cdd01ef066bc6cf2
"""

from .trainer import OnlineLearningPipeline

__all__ = ["OnlineLearningPipeline"]
