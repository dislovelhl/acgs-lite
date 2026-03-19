"""
Tests for Unified PSV-Verus Policy Generator

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio

from src.core.shared.policy.models import PolicySpecification
from src.core.shared.policy.unified_generator import (
    UnifiedVerifiedPolicyGenerator,
    VerificationStatus,
)


async def test_policy_generation_and_verification():
    generator = UnifiedVerifiedPolicyGenerator(max_iterations=3)

    spec = PolicySpecification(
        spec_id="test_spec_001",
        natural_language="Admins can read and write, but users can only read.",
        domain="access_control",
        criticality="high",
    )

    policy = await generator.generate_verified_policy(spec)

    assert policy.specification.spec_id == "test_spec_001"
    assert policy.verification_status in (VerificationStatus.VERIFIED, VerificationStatus.PROVEN)
    assert "package constitutional.test_spe" in policy.rego_policy
    assert "z3-python" in policy.generation_metadata["backend"]
    assert policy.confidence_score > 0.0


async def test_critical_path_annotation():
    generator = UnifiedVerifiedPolicyGenerator()
    spec = PolicySpecification(
        spec_id="test_critical",
        natural_language="Emergency governance breach protocol.",
        domain="emergency",
    )

    policy = await generator.generate_verified_policy(spec)
    assert "[CRITICAL] High-impact governance path" in policy.dafny_spec


async def test_resource_permission_verification():
    generator = UnifiedVerifiedPolicyGenerator()
    spec = PolicySpecification(
        spec_id="test_resource",
        natural_language="Allow owners to delete their resources, and admins can do everything.",
        domain="resource_management",
    )

    policy = await generator.generate_verified_policy(spec)
    assert "[RESOURCE] Fine-grained resource permission model" in policy.dafny_spec
    assert "predicate IsOwner" in policy.dafny_spec
    assert "is_owner" in policy.smt_formulation.lower()


if __name__ == "__main__":
    asyncio.run(test_policy_generation_and_verification())
    asyncio.run(test_critical_path_annotation())
    asyncio.run(test_resource_permission_verification())
