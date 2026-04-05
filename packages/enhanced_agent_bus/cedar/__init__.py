"""Cedar policy engine for ACGS governance.

Constitutional Hash: 608508a9bd224290

Embedded Cedar (cedarpy) replaces the external OPA server for policy evaluation.
Cedar is 42-60x faster than Rego, runs in-process, and requires no external
infrastructure.

Usage::

    from enhanced_agent_bus.cedar import CedarPolicyEngine

    engine = CedarPolicyEngine.from_policy_dir("policies/cedar/")
    result = engine.authorize(principal="agent:alpha", action="propose", resource="draft:123")
"""

from .engine import CedarPolicyEngine

__all__ = ["CedarPolicyEngine"]
