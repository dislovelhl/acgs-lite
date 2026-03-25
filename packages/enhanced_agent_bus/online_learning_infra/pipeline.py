"""
Online learning pipeline shim for ACGS-2.
Re-exports implementation from .trainer for backward compatibility.

Constitutional Hash: 608508a9bd224290
"""

from .trainer import OnlineLearningPipeline

__all__ = ["OnlineLearningPipeline"]
