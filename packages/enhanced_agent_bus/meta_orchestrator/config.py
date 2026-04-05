"""
Meta-Orchestrator Configuration Module
=======================================

Configuration classes and constants for the Meta-Orchestrator system.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
__all__ = [
    "CONSTITUTIONAL_HASH",
    "OrchestratorConfig",
]


@dataclass
class OrchestratorConfig:
    """Configuration for the Meta-Orchestrator."""

    constitutional_hash: str = CONSTITUTIONAL_HASH
    max_swarm_agents: int = 8
    mamba_context_size: int = 100_000
    enable_maci: bool = True
    enable_research: bool = True
    enable_neural_memory: bool = True
    auto_evolution_limit: int = 5  # per day
    confidence_threshold: float = 0.8
    p99_latency_target_ms: float = 5.0
    throughput_target_rps: float = 100.0
    cache_hit_rate_target: float = 0.85

    def validate(self) -> bool:
        """Validate configuration against constitutional requirements."""
        if self.constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(f"Invalid constitutional hash. Expected: {CONSTITUTIONAL_HASH}")
        if self.max_swarm_agents > 8:
            logger.warning("Swarm agents capped at 8 for stability")
            self.max_swarm_agents = 8
        return True
