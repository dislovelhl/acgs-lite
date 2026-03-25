"""
Online Learning Submodule for ACGS-2 Enhanced Agent Bus
Constitutional Hash: 608508a9bd224290

Re-exports online learning components for backwards compatibility.
"""

import sys

from .config import LearningStatus, ModelType
from .models import (
    ConsumerStats,
    LearningResult,
    LearningStats,
    PipelineStats,
    PredictionResult,
)

_MODULE = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.online_learning_infra", _MODULE)
sys.modules.setdefault("packages.enhanced_agent_bus.online_learning_infra", _MODULE)

__all__ = [
    "ConsumerStats",
    "LearningResult",
    "LearningStats",
    "LearningStatus",
    "ModelType",
    "PipelineStats",
    "PredictionResult",
]
