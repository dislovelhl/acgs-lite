"""Cedar policy backend for ACGS.

Constitutional Hash: 608508a9bd224290

Embedded Cedar (cedarpy) policy evaluation — 42-60x faster than Rego,
runs in-process, no external server required.

Usage::

    from acgs.cedar import CedarBackend

    backend = CedarBackend.from_policy_dir("policies/")
    decision = backend.evaluate("propose a change", agent_id="agent-1")
"""

from .backend import CedarBackend

__all__ = ["CedarBackend"]
