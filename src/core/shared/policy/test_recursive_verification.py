"""
Module.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio

import pytest

from src.core.shared.policy.models import PolicySpecification, VerificationStatus
from src.core.shared.policy.unified_generator import UnifiedVerifiedPolicyGenerator


@pytest.mark.asyncio
async def test_recursive_policy_generation():
    """
    Verifies that for a recursive/hierarchical spec, the generator
    produces a co-inductive Dafny specification and verifies it.
    """
    generator = UnifiedVerifiedPolicyGenerator()

    # Spec that triggers recursive template
    spec = PolicySpecification(
        spec_id="recursive_spec_001",
        natural_language="The swarm must recursively adhere to the constitutional hash.",
        domain="swarm_governance",
        criticality="high",
    )

    policy = await generator.generate_verified_policy(spec)

    assert policy.specification.spec_id == "recursive_spec_001"
    # It should be PROVEN if Dafny CLI verifies the recursive contract
    assert policy.verification_status in (VerificationStatus.VERIFIED, VerificationStatus.PROVEN)

    # Check for recursive patterns in the generated Dafny
    assert "codatatype AgentSwarm" in policy.dafny_spec
    assert "copredicate ValidSwarm" in policy.dafny_spec
    assert "[RECURSIVE]" in policy.dafny_spec


if __name__ == "__main__":
    asyncio.run(test_recursive_policy_generation())
