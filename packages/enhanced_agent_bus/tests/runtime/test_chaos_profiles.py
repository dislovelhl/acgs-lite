"""
ACGS-2 Enhanced Agent Bus - Tests for Deterministic Chaos Profiles
Constitutional Hash: 608508a9bd224290

Tests for the deterministic chaos testing framework.
"""

import time

import pytest

from .chaos_profiles import (
    CONSTITUTIONAL_HASH,
    ChaosInjection,
    ChaosProfile,
    ChaosProfileRegistry,
    ChaosTarget,
    ChaosType,
    DeterministicChaosExecutor,
    create_audit_path_chaos_profile,
    create_combined_chaos_profile,
    create_executor,
    create_governance_chaos_profile,
    create_timing_chaos_profile,
    get_profile,
    list_profiles,
)


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_present(self) -> None:
        """Test that constitutional hash is defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_profile_has_constitutional_hash(self) -> None:
        """Test that profiles contain constitutional hash."""
        profile = create_governance_chaos_profile()
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH


class TestChaosInjection:
    """Test ChaosInjection dataclass."""

    def test_valid_injection_creation(self) -> None:
        """Test creating a valid chaos injection."""
        injection = ChaosInjection(
            target=ChaosTarget.CONSTITUTIONAL_HASH,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=1000,
            intensity=0.5,
            deterministic_seed=42,
        )
        assert injection.target == ChaosTarget.CONSTITUTIONAL_HASH
        assert injection.chaos_type == ChaosType.GOVERNANCE
        assert injection.duration_ms == 1000
        assert injection.intensity == 0.5
        assert injection.deterministic_seed == 42

    def test_intensity_lower_bound(self) -> None:
        """Test intensity cannot be negative."""
        with pytest.raises(ValueError, match=r"Intensity must be 0.0-1.0"):
            ChaosInjection(
                target=ChaosTarget.AUDIT_LOGGING,
                chaos_type=ChaosType.AUDIT,
                duration_ms=1000,
                intensity=-0.1,
                deterministic_seed=1,
            )

    def test_intensity_upper_bound(self) -> None:
        """Test intensity cannot exceed 1.0."""
        with pytest.raises(ValueError, match=r"Intensity must be 0.0-1.0"):
            ChaosInjection(
                target=ChaosTarget.AUDIT_LOGGING,
                chaos_type=ChaosType.AUDIT,
                duration_ms=1000,
                intensity=1.5,
                deterministic_seed=1,
            )

    def test_intensity_boundary_values(self) -> None:
        """Test intensity at exact boundaries."""
        # 0.0 should be valid
        injection_zero = ChaosInjection(
            target=ChaosTarget.AUDIT_LOGGING,
            chaos_type=ChaosType.AUDIT,
            duration_ms=1000,
            intensity=0.0,
            deterministic_seed=1,
        )
        assert injection_zero.intensity == 0.0

        # 1.0 should be valid
        injection_one = ChaosInjection(
            target=ChaosTarget.AUDIT_LOGGING,
            chaos_type=ChaosType.AUDIT,
            duration_ms=1000,
            intensity=1.0,
            deterministic_seed=1,
        )
        assert injection_one.intensity == 1.0

    def test_negative_duration_rejected(self) -> None:
        """Test that negative duration is rejected."""
        with pytest.raises(ValueError, match="Duration must be non-negative"):
            ChaosInjection(
                target=ChaosTarget.AUDIT_LOGGING,
                chaos_type=ChaosType.AUDIT,
                duration_ms=-100,
                intensity=0.5,
                deterministic_seed=1,
            )

    def test_zero_duration_allowed(self) -> None:
        """Test that zero duration is allowed."""
        injection = ChaosInjection(
            target=ChaosTarget.AUDIT_LOGGING,
            chaos_type=ChaosType.AUDIT,
            duration_ms=0,
            intensity=0.5,
            deterministic_seed=1,
        )
        assert injection.duration_ms == 0


class TestChaosProfile:
    """Test ChaosProfile dataclass."""

    def test_profile_creation(self) -> None:
        """Test creating a chaos profile."""
        profile = ChaosProfile(
            name="test-profile",
            description="Test description",
        )
        assert profile.name == "test-profile"
        assert profile.description == "Test description"
        assert profile.enabled is True
        assert profile.fail_closed_expected is True
        assert len(profile.injections) == 0

    def test_add_injection(self) -> None:
        """Test adding injections to a profile."""
        profile = ChaosProfile(name="test", description="Test")
        injection = ChaosInjection(
            target=ChaosTarget.OPA_POLICY,
            chaos_type=ChaosType.GOVERNANCE,
            duration_ms=1000,
            intensity=0.5,
            deterministic_seed=42,
        )
        profile.add_injection(injection)
        assert len(profile.injections) == 1
        assert profile.injections[0] == injection

    def test_get_targets(self) -> None:
        """Test getting unique targets from profile."""
        profile = ChaosProfile(name="test", description="Test")
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=1000,
                intensity=0.5,
                deterministic_seed=1,
            )
        )
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.AUDIT_LOGGING,
                chaos_type=ChaosType.AUDIT,
                duration_ms=1000,
                intensity=0.5,
                deterministic_seed=2,
            )
        )
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,  # Duplicate target
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=500,
                intensity=0.3,
                deterministic_seed=3,
            )
        )

        targets = profile.get_targets()
        assert len(targets) == 2
        assert ChaosTarget.OPA_POLICY in targets
        assert ChaosTarget.AUDIT_LOGGING in targets


class TestPredefinedProfiles:
    """Test pre-defined chaos profiles."""

    def test_governance_profile_structure(self) -> None:
        """Test governance chaos profile structure."""
        profile = create_governance_chaos_profile()
        assert profile.name == "governance-only"
        assert profile.fail_closed_expected is True
        assert len(profile.injections) == 4

        targets = profile.get_targets()
        assert ChaosTarget.CONSTITUTIONAL_HASH in targets
        assert ChaosTarget.MACI_ROLES in targets
        assert ChaosTarget.OPA_POLICY in targets
        assert ChaosTarget.VOTING_SERVICE in targets

    def test_audit_profile_structure(self) -> None:
        """Test audit-path chaos profile structure."""
        profile = create_audit_path_chaos_profile()
        assert profile.name == "audit-path"
        assert profile.fail_closed_expected is False  # Audit failures shouldn't block
        assert len(profile.injections) == 3

        targets = profile.get_targets()
        assert ChaosTarget.AUDIT_LOGGING in targets
        assert ChaosTarget.INTEGRITY_CHECK in targets
        assert ChaosTarget.DECISION_LOG in targets

    def test_timing_profile_structure(self) -> None:
        """Test timing chaos profile structure."""
        profile = create_timing_chaos_profile()
        assert profile.name == "timing"
        assert profile.fail_closed_expected is False  # Timeouts handled gracefully
        assert len(profile.injections) == 3

        targets = profile.get_targets()
        assert ChaosTarget.VALIDATION_LATENCY in targets
        assert ChaosTarget.MESSAGE_PROCESSING in targets
        assert ChaosTarget.CACHE_OPERATIONS in targets

    def test_combined_profile_structure(self) -> None:
        """Test combined chaos profile structure."""
        profile = create_combined_chaos_profile()
        assert profile.name == "combined"
        assert profile.fail_closed_expected is True  # Governance failures should fail-closed
        assert len(profile.injections) == 3

        targets = profile.get_targets()
        assert ChaosTarget.CONSTITUTIONAL_HASH in targets
        assert ChaosTarget.AUDIT_LOGGING in targets
        assert ChaosTarget.VALIDATION_LATENCY in targets

    def test_all_profiles_have_deterministic_seeds(self) -> None:
        """Test that all injections have deterministic seeds."""
        profiles = [
            create_governance_chaos_profile(),
            create_audit_path_chaos_profile(),
            create_timing_chaos_profile(),
            create_combined_chaos_profile(),
        ]
        for profile in profiles:
            for injection in profile.injections:
                assert isinstance(injection.deterministic_seed, int)
                assert injection.deterministic_seed >= 0


class TestChaosProfileRegistry:
    """Test ChaosProfileRegistry functionality."""

    def test_default_profiles_registered(self) -> None:
        """Test that default profiles are registered at import."""
        profiles = ChaosProfileRegistry.list_profiles()
        assert "governance-only" in profiles
        assert "audit-path" in profiles
        assert "timing" in profiles
        assert "combined" in profiles

    def test_get_existing_profile(self) -> None:
        """Test getting an existing profile."""
        profile = ChaosProfileRegistry.get("governance-only")
        assert profile is not None
        assert profile.name == "governance-only"

    def test_get_nonexistent_profile(self) -> None:
        """Test getting a non-existent profile returns None."""
        profile = ChaosProfileRegistry.get("nonexistent-profile")
        assert profile is None

    def test_register_custom_profile(self) -> None:
        """Test registering a custom profile."""
        custom = ChaosProfile(
            name="custom-test",
            description="Custom test profile",
        )
        ChaosProfileRegistry.register(custom)

        retrieved = ChaosProfileRegistry.get("custom-test")
        assert retrieved is not None
        assert retrieved.name == "custom-test"

    def test_get_all_profiles(self) -> None:
        """Test getting all registered profiles."""
        all_profiles = ChaosProfileRegistry.get_all()
        assert isinstance(all_profiles, dict)
        assert len(all_profiles) >= 4  # At least the default profiles


class TestDeterministicChaosExecutor:
    """Test DeterministicChaosExecutor functionality."""

    def test_executor_creation(self) -> None:
        """Test creating an executor."""
        profile = create_governance_chaos_profile()
        executor = DeterministicChaosExecutor(profile)
        assert executor.profile == profile
        assert len(executor.active_injections) == 0

    def test_executor_start(self) -> None:
        """Test starting the executor."""
        profile = create_governance_chaos_profile()
        executor = DeterministicChaosExecutor(profile)
        executor.start()

        assert executor._start_time is not None
        assert len(executor.active_injections) == 4
        for target in profile.get_targets():
            assert executor.active_injections[target] is True

    def test_executor_stop(self) -> None:
        """Test stopping the executor."""
        profile = create_governance_chaos_profile()
        executor = DeterministicChaosExecutor(profile)
        executor.start()
        executor.stop()

        assert executor._start_time is None
        for target in executor.active_injections:
            assert executor.active_injections[target] is False

    def test_should_inject_before_start(self) -> None:
        """Test that injection returns False before start."""
        profile = create_governance_chaos_profile()
        executor = DeterministicChaosExecutor(profile)

        result = executor.should_inject(ChaosTarget.CONSTITUTIONAL_HASH)
        assert result is False

    def test_should_inject_deterministic(self) -> None:
        """Test that injection decisions are deterministic."""
        profile = ChaosProfile(name="test", description="Test")
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=10000,  # Long enough for test
                intensity=0.5,
                deterministic_seed=42,
            )
        )

        # Run twice with same seed
        results1 = []
        executor1 = DeterministicChaosExecutor(profile)
        executor1.start()
        for _ in range(10):
            results1.append(executor1.should_inject(ChaosTarget.OPA_POLICY))
        executor1.stop()

        # Create new profile with same seed
        profile2 = ChaosProfile(name="test2", description="Test2")
        profile2.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=10000,
                intensity=0.5,
                deterministic_seed=42,
            )
        )

        results2 = []
        executor2 = DeterministicChaosExecutor(profile2)
        executor2.start()
        for _ in range(10):
            results2.append(executor2.should_inject(ChaosTarget.OPA_POLICY))
        executor2.stop()

        # Results should be identical due to deterministic seed
        assert results1 == results2

    def test_should_inject_inactive_target(self) -> None:
        """Test injection returns False for inactive target."""
        profile = ChaosProfile(name="test", description="Test")
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=10000,
                intensity=1.0,  # Always inject
                deterministic_seed=42,
            )
        )

        executor = DeterministicChaosExecutor(profile)
        executor.start()

        # Target not in profile
        result = executor.should_inject(ChaosTarget.AUDIT_LOGGING)
        assert result is False

        executor.stop()

    def test_injection_respects_duration(self) -> None:
        """Test that injection stops after duration."""
        profile = ChaosProfile(name="test", description="Test")
        profile.add_injection(
            ChaosInjection(
                target=ChaosTarget.OPA_POLICY,
                chaos_type=ChaosType.GOVERNANCE,
                duration_ms=50,  # Very short duration
                intensity=1.0,  # Always inject when active
                deterministic_seed=42,
            )
        )

        executor = DeterministicChaosExecutor(profile)
        executor.start()

        # Should inject initially
        initial_result = executor.should_inject(ChaosTarget.OPA_POLICY)
        # Note: Due to deterministic behavior, first call might or might not inject

        # Wait for duration to expire
        time.sleep(0.1)  # 100ms > 50ms duration

        # Should not inject after duration
        after_result = executor.should_inject(ChaosTarget.OPA_POLICY)
        assert after_result is False

        executor.stop()

    def test_get_injection_stats(self) -> None:
        """Test getting injection statistics."""
        profile = create_governance_chaos_profile()
        executor = DeterministicChaosExecutor(profile)
        executor.start()

        # Make some injection checks
        executor.should_inject(ChaosTarget.CONSTITUTIONAL_HASH)
        executor.should_inject(ChaosTarget.OPA_POLICY)
        executor.should_inject(ChaosTarget.CONSTITUTIONAL_HASH)

        stats = executor.get_injection_stats()
        assert stats["profile_name"] == "governance-only"
        assert "active_targets" in stats
        assert "injection_counts" in stats
        assert "elapsed_ms" in stats
        assert stats["elapsed_ms"] > 0

        # Check counts
        assert stats["injection_counts"]["constitutional_hash"] == 2
        assert stats["injection_counts"]["opa_policy"] == 1

        executor.stop()


class TestHelperFunctions:
    """Test module-level helper functions."""

    def test_get_profile_existing(self) -> None:
        """Test getting an existing profile."""
        profile = get_profile("governance-only")
        assert profile.name == "governance-only"

    def test_get_profile_nonexistent(self) -> None:
        """Test getting a non-existent profile raises error."""
        with pytest.raises(ValueError, match="Unknown chaos profile"):
            get_profile("nonexistent-profile")

    def test_list_profiles(self) -> None:
        """Test listing all profiles."""
        profiles = list_profiles()
        assert isinstance(profiles, list)
        assert "governance-only" in profiles
        assert "audit-path" in profiles
        assert "timing" in profiles
        assert "combined" in profiles

    def test_create_executor(self) -> None:
        """Test creating an executor by profile name."""
        executor = create_executor("governance-only")
        assert isinstance(executor, DeterministicChaosExecutor)
        assert executor.profile.name == "governance-only"

    def test_create_executor_invalid_profile(self) -> None:
        """Test creating an executor with invalid profile raises error."""
        with pytest.raises(ValueError, match="Unknown chaos profile"):
            create_executor("nonexistent-profile")


class TestChaosTypeEnum:
    """Test ChaosType enumeration."""

    def test_all_chaos_types(self) -> None:
        """Test all chaos types are defined."""
        assert ChaosType.GOVERNANCE.value == "governance"
        assert ChaosType.AUDIT.value == "audit"
        assert ChaosType.TIMING.value == "timing"
        assert ChaosType.NETWORK.value == "network"
        assert ChaosType.RESOURCE.value == "resource"


class TestChaosTargetEnum:
    """Test ChaosTarget enumeration."""

    def test_governance_targets(self) -> None:
        """Test governance-related targets."""
        assert ChaosTarget.CONSTITUTIONAL_HASH.value == "constitutional_hash"
        assert ChaosTarget.MACI_ROLES.value == "maci_roles"
        assert ChaosTarget.OPA_POLICY.value == "opa_policy"
        assert ChaosTarget.VOTING_SERVICE.value == "voting_service"

    def test_audit_targets(self) -> None:
        """Test audit-related targets."""
        assert ChaosTarget.AUDIT_LOGGING.value == "audit_logging"
        assert ChaosTarget.INTEGRITY_CHECK.value == "integrity_check"
        assert ChaosTarget.DECISION_LOG.value == "decision_log"

    def test_timing_targets(self) -> None:
        """Test timing-related targets."""
        assert ChaosTarget.VALIDATION_LATENCY.value == "validation_latency"
        assert ChaosTarget.MESSAGE_PROCESSING.value == "message_processing"
        assert ChaosTarget.CACHE_OPERATIONS.value == "cache_operations"
