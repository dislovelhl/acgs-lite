"""
ACGS-2 Enhanced Agent Bus - Deterministic Chaos Profiles
Constitutional Hash: 608508a9bd224290

Deterministic chaos testing profiles for controlled failure injection:
- Governance-only chaos: Target constitutional validation paths
- Audit-path chaos: Target audit and logging paths
- Timing chaos: Target latency-sensitive operations

These profiles enable reproducible chaos testing without random behavior.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Optional

# Constitutional Hash - Required for all governance operations
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class ChaosType(Enum):
    """Types of chaos that can be injected."""

    GOVERNANCE = "governance"
    AUDIT = "audit"
    TIMING = "timing"
    NETWORK = "network"
    RESOURCE = "resource"


class ChaosTarget(Enum):
    """Specific targets for chaos injection."""

    # Governance targets
    CONSTITUTIONAL_HASH = "constitutional_hash"
    MACI_ROLES = "maci_roles"
    OPA_POLICY = "opa_policy"
    VOTING_SERVICE = "voting_service"

    # Audit targets
    AUDIT_LOGGING = "audit_logging"
    INTEGRITY_CHECK = "integrity_check"
    DECISION_LOG = "decision_log"

    # Timing targets
    VALIDATION_LATENCY = "validation_latency"
    MESSAGE_PROCESSING = "message_processing"
    CACHE_OPERATIONS = "cache_operations"


@dataclass
class ChaosInjection:
    """A single chaos injection specification."""

    target: ChaosTarget
    chaos_type: ChaosType
    duration_ms: int
    intensity: float  # 0.0 to 1.0
    deterministic_seed: int

    def __post_init__(self):
        if not 0.0 <= self.intensity <= 1.0:
            raise ValueError(f"Intensity must be 0.0-1.0, got {self.intensity}")
        if self.duration_ms < 0:
            raise ValueError(f"Duration must be non-negative, got {self.duration_ms}")


@dataclass
class ChaosProfile:
    """A complete chaos testing profile."""

    name: str
    description: str
    injections: list[ChaosInjection] = field(default_factory=list)
    enabled: bool = True
    fail_closed_expected: bool = True  # Whether system should fail-closed
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def add_injection(self, injection: ChaosInjection) -> None:
        """Add an injection to the profile."""
        self.injections.append(injection)

    def get_targets(self) -> set[ChaosTarget]:
        """Get all unique targets in this profile."""
        return {inj.target for inj in self.injections}


# =============================================================================
# Pre-defined Chaos Profiles
# =============================================================================


def create_governance_chaos_profile() -> ChaosProfile:
    """
    Governance-Only Chaos Profile

    Targets constitutional validation paths:
    - Hash validation failures
    - MACI role desynchronization
    - OPA policy evaluation failures
    - Voting service conflicts

    Expected behavior: System fails-closed on all governance failures
    """
    profile = ChaosProfile(
        name="governance-only",
        description="Target constitutional governance paths to verify fail-closed behavior",
        fail_closed_expected=True,
    )

    # Constitutional hash corruption
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.CONSTITUTIONAL_HASH,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=5000,
            intensity=0.8,
            deterministic_seed=42,
        )
    )

    # MACI role confusion
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.MACI_ROLES,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=3000,
            intensity=0.6,
            deterministic_seed=43,
        )
    )

    # OPA policy failures
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.OPA_POLICY,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=4000,
            intensity=0.7,
            deterministic_seed=44,
        )
    )

    # Voting service conflicts
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.VOTING_SERVICE,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=2000,
            intensity=0.5,
            deterministic_seed=45,
        )
    )

    return profile


def create_audit_path_chaos_profile() -> ChaosProfile:
    """
    Audit-Path Chaos Profile

    Targets audit and logging paths:
    - Audit logging failures
    - Integrity check failures
    - Decision log corruption

    Expected behavior: Operations proceed but with degraded auditing
    """
    profile = ChaosProfile(
        name="audit-path",
        description="Target audit and logging paths to verify graceful degradation",
        fail_closed_expected=False,  # Audit failures shouldn't block operations
    )

    # Audit logging failure
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.AUDIT_LOGGING,
            chaos_type=ChaosType.AUDIT,
            duration_ms=5000,
            intensity=0.9,
            deterministic_seed=100,
        )
    )

    # Integrity check failure
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.INTEGRITY_CHECK,
            chaos_type=ChaosType.AUDIT,
            duration_ms=3000,
            intensity=0.7,
            deterministic_seed=101,
        )
    )

    # Decision log corruption
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.DECISION_LOG,
            chaos_type=ChaosType.AUDIT,
            duration_ms=4000,
            intensity=0.8,
            deterministic_seed=102,
        )
    )

    return profile


def create_timing_chaos_profile() -> ChaosProfile:
    """
    Timing Chaos Profile

    Targets latency-sensitive operations:
    - Validation latency spikes
    - Message processing delays
    - Cache operation timeouts

    Expected behavior: System handles delays gracefully within SLA
    """
    profile = ChaosProfile(
        name="timing",
        description="Target latency-sensitive paths to verify timeout handling",
        fail_closed_expected=False,  # Timeouts should be handled gracefully
    )

    # Validation latency spikes
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.VALIDATION_LATENCY,
            chaos_type=ChaosType.TIMING,
            duration_ms=10000,
            intensity=0.5,  # 50% chance of latency spike
            deterministic_seed=200,
        )
    )

    # Message processing delays
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.MESSAGE_PROCESSING,
            chaos_type=ChaosType.TIMING,
            duration_ms=8000,
            intensity=0.4,
            deterministic_seed=201,
        )
    )

    # Cache operation timeouts
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.CACHE_OPERATIONS,
            chaos_type=ChaosType.TIMING,
            duration_ms=5000,
            intensity=0.6,
            deterministic_seed=202,
        )
    )

    return profile


def create_combined_chaos_profile() -> ChaosProfile:
    """
    Combined Chaos Profile

    Combines governance, audit, and timing chaos for comprehensive testing.
    Used for stress testing and integration validation.
    """
    profile = ChaosProfile(
        name="combined",
        description="Combined chaos for comprehensive stress testing",
        fail_closed_expected=True,  # Governance failures should still fail-closed
    )

    # Add governance chaos
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.CONSTITUTIONAL_HASH,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=3000,
            intensity=0.5,
            deterministic_seed=300,
        )
    )

    # Add audit chaos
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.AUDIT_LOGGING,
            chaos_type=ChaosType.AUDIT,
            duration_ms=3000,
            intensity=0.5,
            deterministic_seed=301,
        )
    )

    # Add timing chaos
    profile.add_injection(
        ChaosInjection(
            target=ChaosTarget.VALIDATION_LATENCY,
            chaos_type=ChaosType.TIMING,
            duration_ms=3000,
            intensity=0.3,
            deterministic_seed=302,
        )
    )

    return profile


# =============================================================================
# Chaos Profile Registry
# =============================================================================


class ChaosProfileRegistry:
    """Registry for chaos testing profiles."""

    _profiles: ClassVar[dict[str, ChaosProfile]] = {}

    @classmethod
    def register(cls, profile: ChaosProfile) -> None:
        """Register a chaos profile."""
        cls._profiles[profile.name] = profile
        logger.info(f"Registered chaos profile: {profile.name}")

    @classmethod
    def get(cls, name: str) -> ChaosProfile | None:
        """Get a chaos profile by name."""
        return cls._profiles.get(name)

    @classmethod
    def list_profiles(cls) -> list[str]:
        """list all registered profile names."""
        return list(cls._profiles.keys())

    @classmethod
    def get_all(cls) -> dict[str, ChaosProfile]:
        """Get all registered profiles."""
        return cls._profiles.copy()


# Register default profiles
def _register_default_profiles():
    """Register default chaos profiles."""
    ChaosProfileRegistry.register(create_governance_chaos_profile())
    ChaosProfileRegistry.register(create_audit_path_chaos_profile())
    ChaosProfileRegistry.register(create_timing_chaos_profile())
    ChaosProfileRegistry.register(create_combined_chaos_profile())


_register_default_profiles()

# =============================================================================
# Chaos Executor
# =============================================================================


class DeterministicChaosExecutor:
    """
    Executes chaos injections in a deterministic manner.

    Uses deterministic seeds to ensure reproducible chaos testing.
    """

    def __init__(self, profile: ChaosProfile):
        self.profile = profile
        self.active_injections: dict[ChaosTarget, bool] = {}
        self._start_time: float | None = None
        self._injection_counts: dict[ChaosTarget, int] = {}

    def start(self) -> None:
        """Start the chaos executor."""
        self._start_time = time.time()
        for injection in self.profile.injections:
            self.active_injections[injection.target] = True
            self._injection_counts[injection.target] = 0
        logger.info(f"Started chaos profile: {self.profile.name}")

    def stop(self) -> None:
        """Stop the chaos executor."""
        for target in self.active_injections:
            self.active_injections[target] = False
        self._start_time = None
        logger.info(f"Stopped chaos profile: {self.profile.name}")

    def should_inject(self, target: ChaosTarget) -> bool:
        """
        Deterministically decide whether to inject chaos for a target.

        Uses the seed and call count for reproducibility.
        """
        if not self.active_injections.get(target, False):
            return False

        if self._start_time is None:
            return False

        # Find injection config for this target
        injection = next((i for i in self.profile.injections if i.target == target), None)
        if injection is None:
            return False

        # Check if within duration
        elapsed_ms = (time.time() - self._start_time) * 1000
        if elapsed_ms > injection.duration_ms:
            self.active_injections[target] = False
            return False

        # Deterministic decision based on seed and call count
        count = self._injection_counts.get(target, 0)
        self._injection_counts[target] = count + 1

        # Use seed + count to generate deterministic value
        deterministic_value = (injection.deterministic_seed + count) % 100 / 100.0

        return deterministic_value < injection.intensity

    def get_injection_stats(self) -> JSONDict:
        """Get statistics about injections."""
        return {
            "profile_name": self.profile.name,
            "active_targets": [t.value for t, active in self.active_injections.items() if active],
            "injection_counts": {t.value: c for t, c in self._injection_counts.items()},
            "elapsed_ms": (time.time() - self._start_time) * 1000 if self._start_time else 0,
        }


# =============================================================================
# Helper Functions
# =============================================================================


def get_profile(name: str) -> ChaosProfile:
    """Get a chaos profile by name."""
    profile = ChaosProfileRegistry.get(name)
    if profile is None:
        raise ValueError(f"Unknown chaos profile: {name}")
    return profile


def list_profiles() -> list[str]:
    """list all available chaos profile names."""
    return ChaosProfileRegistry.list_profiles()


def create_executor(profile_name: str) -> DeterministicChaosExecutor:
    """Create a chaos executor for a named profile."""
    profile = get_profile(profile_name)
    return DeterministicChaosExecutor(profile)
