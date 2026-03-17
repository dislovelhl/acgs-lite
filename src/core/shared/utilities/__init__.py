"""
ACGS-2 Shared Utilities
Constitutional Hash: cdd01ef066bc6cf2

Centralized utility classes to reduce code duplication across the codebase.
This module provides common functionality that was previously duplicated.
"""

from .config_merger import ConfigMerger
from .dependency_registry import DependencyRegistry, FeatureFlag
from .tenant_normalizer import TenantNormalizer

__all__ = [
    "ConfigMerger",
    "DependencyRegistry",
    "FeatureFlag",
    "TenantNormalizer",
]
