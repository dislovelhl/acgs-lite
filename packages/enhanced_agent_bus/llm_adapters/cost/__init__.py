"""
ACGS-2 Enhanced Agent Bus - Cost-Aware LLM Provider Selection
Constitutional Hash: 608508a9bd224290

Implements cost-aware routing for LLM providers with quality constraints, budget
management, anomaly detection, and batch optimization for non-urgent operations.

Features:
- Cost model per provider with input/output pricing
- Cost-based routing with quality constraints
- Budget limits per tenant and operation
- Cost anomaly detection
- Batch optimization for non-urgent operations
- Cost reporting and analytics

This module provides a modular structure for cost optimization:
- enums.py: Cost tier, quality level, and urgency level enumerations
- models.py: Data models for costs, budgets, anomalies, and batches
- budget.py: Budget management for tenants and operations
- anomaly.py: Cost anomaly detection using statistical methods
- batch.py: Batch optimization for non-urgent requests
- optimizer.py: Main cost optimizer integrating all components
"""

from .anomaly import CostAnomalyDetector
from .batch import BatchOptimizer
from .budget import BudgetManager
from .enums import CostTier, QualityLevel, UrgencyLevel
from .models import (
    BatchRequest,
    BatchResult,
    BudgetLimit,
    CostAnomaly,
    CostEstimate,
    CostModel,
)
from .optimizer import CostOptimizer, get_cost_optimizer, initialize_cost_optimizer

__all__ = [
    "BatchOptimizer",
    "BatchRequest",
    "BatchResult",
    "BudgetLimit",
    # Classes
    "BudgetManager",
    "CostAnomaly",
    "CostAnomalyDetector",
    "CostEstimate",
    # Data classes
    "CostModel",
    "CostOptimizer",
    # Enums
    "CostTier",
    "QualityLevel",
    "UrgencyLevel",
    # Global accessors
    "get_cost_optimizer",
    "initialize_cost_optimizer",
]
