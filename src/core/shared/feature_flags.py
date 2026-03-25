"""
Feature Flags for ACGS-2 Meta-Orchestrator
==========================================

Explicit feature flag management replacing silent try/except import failures.
All flags are loaded from environment variables with ACGS_FEATURE_ prefix.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T")


def _get_bool_env(key: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class FeatureFlags:
    """
    Immutable feature flags for ACGS-2 components.

    All flags default to True (enabled) to maintain backward compatibility.
    Set ACGS_FEATURE_<NAME>=false to disable specific features.

    Environment Variables:
        ACGS_FEATURE_MAMBA: Enable Mamba-2 hybrid processor (100K context)
        ACGS_FEATURE_MACI: Enable MACI role enforcement (Gödel bypass prevention)
        ACGS_FEATURE_LANGGRAPH: Enable LangGraph workflow orchestration
        ACGS_FEATURE_SAFLA: Enable SAFLA v3 neural memory (4-tier persistence)
        ACGS_FEATURE_SWARM: Enable swarm intelligence (dynamic agent spawning)
        ACGS_FEATURE_WORKFLOW_EVOLUTION: Enable workflow evolution engine
        ACGS_FEATURE_RESEARCH: Enable research integration (web/arxiv)
        ACGS_FEATURE_OPTIMIZATION: Enable optimization toolkit
        ACGS_FEATURE_CACHE_WARMING: Enable cache warming
    """

    mamba_enabled: bool = True
    maci_enabled: bool = True
    langgraph_enabled: bool = True
    safla_enabled: bool = True
    swarm_enabled: bool = True
    workflow_evolution_enabled: bool = True
    research_enabled: bool = True
    optimization_enabled: bool = True
    cache_warming_enabled: bool = True

    def log_status(self) -> None:
        """Log the status of all feature flags."""
        features = [
            ("Mamba-2 Hybrid Processor", self.mamba_enabled),
            ("MACI Role Enforcement", self.maci_enabled),
            ("LangGraph Orchestration", self.langgraph_enabled),
            ("SAFLA Neural Memory v3", self.safla_enabled),
            ("Swarm Intelligence", self.swarm_enabled),
            ("Workflow Evolution", self.workflow_evolution_enabled),
            ("Research Integration", self.research_enabled),
            ("Optimization Toolkit", self.optimization_enabled),
            ("Cache Warming", self.cache_warming_enabled),
        ]

        enabled_count = sum(1 for _, enabled in features if enabled)
        logger.info(f"Feature flags loaded: {enabled_count}/{len(features)} features enabled")

        for name, enabled in features:
            status = "enabled" if enabled else "DISABLED"
            log_fn = logger.debug if enabled else logger.warning
            log_fn(f"  {name}: {status}")


@lru_cache(maxsize=1)
def get_feature_flags() -> FeatureFlags:
    """
    Get feature flags from environment variables.

    Uses lru_cache to ensure flags are loaded once at startup.
    To reload flags, call get_feature_flags.cache_clear() first.
    """
    flags = FeatureFlags(
        mamba_enabled=_get_bool_env("ACGS_FEATURE_MAMBA", default=True),
        maci_enabled=_get_bool_env("ACGS_FEATURE_MACI", default=True),
        langgraph_enabled=_get_bool_env("ACGS_FEATURE_LANGGRAPH", default=True),
        safla_enabled=_get_bool_env("ACGS_FEATURE_SAFLA", default=True),
        swarm_enabled=_get_bool_env("ACGS_FEATURE_SWARM", default=True),
        workflow_evolution_enabled=_get_bool_env("ACGS_FEATURE_WORKFLOW_EVOLUTION", default=True),
        research_enabled=_get_bool_env("ACGS_FEATURE_RESEARCH", default=True),
        optimization_enabled=_get_bool_env("ACGS_FEATURE_OPTIMIZATION", default=True),
        cache_warming_enabled=_get_bool_env("ACGS_FEATURE_CACHE_WARMING", default=True),
    )
    flags.log_status()
    return flags


def guarded_import(
    flag_name: str,
    import_fn: Callable[[], T],
    feature_name: str,
) -> tuple[T | None, bool]:
    """
    Import a module only if the feature flag is enabled AND the import succeeds.

    Args:
        flag_name: Attribute name on FeatureFlags (e.g., 'mamba_enabled')
        import_fn: Callable that performs the import and returns the module/objects
        feature_name: Human-readable feature name for logging

    Returns:
        Tuple of (imported_value_or_None, is_available)

    Example:
        mamba_module, MAMBA_AVAILABLE = guarded_import(
            'mamba_enabled',
            lambda: __import__('mamba2_hybrid_processor'),
            'Mamba-2 Hybrid Processor'
        )
    """
    flags = get_feature_flags()
    is_enabled = getattr(flags, flag_name, False)

    if not is_enabled:
        logger.info(
            f"{feature_name} disabled by feature flag ACGS_FEATURE_{flag_name.upper().replace('_ENABLED', '')}"
        )
        return None, False

    try:
        result = import_fn()
        logger.debug(f"{feature_name} loaded successfully")
        return result, True
    except ImportError as e:
        logger.warning(f"{feature_name} import failed: {e}")
        return None, False


FEATURES = get_feature_flags()
