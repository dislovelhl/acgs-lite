"""Policy storage abstraction — Protocol plus in-memory implementation.

Constitutional Hash: 608508a9bd224290
ADR: docs/wiki/architecture/adr/021-policy-storage-abstraction.md

Pattern: mirrors BundleStore (constitution/bundle_store.py) with async methods
for Redis/DB forward-compatibility.

Usage::

    storage: PolicyStorage = InMemoryPolicyStorage()
    await storage.store(policy)
    loaded = await storage.load("policy-id")

    # Custom backend::
    class MyRedisStorage:
        async def load(self, policy_id: str, version: str | None = None) -> Policy: ...
        async def store(self, policy: Policy) -> None: ...
        async def delete(self, policy_id: str) -> None: ...
        async def list_versions(self, policy_id: str) -> list[str]: ...

    assert isinstance(MyRedisStorage(), PolicyStorage)  # runtime_checkable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class PolicyNotFoundError(Exception):
    """Raised by PolicyStorage.load() when *policy_id* is not present.

    Never returns None — callers get a descriptive exception so the root
    cause is clear rather than an AttributeError at the call site.
    """

    def __init__(self, policy_id: str, version: str | None = None) -> None:
        self.policy_id = policy_id
        self.version = version
        version_hint = f" (version={version!r})" if version else ""
        super().__init__(
            f"Policy not found: policy_id={policy_id!r}{version_hint}. "
            "Ensure the policy has been stored before accessing it."
        )


@dataclass
class Policy:
    """Minimal policy value object.

    Consumers may subclass or replace this with a richer domain model.
    The storage protocol only requires that policies are serialisable.
    """

    policy_id: str
    content: Any
    version: str = "latest"
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PolicyStorage(Protocol):
    """Protocol for pluggable policy storage backends.

    All methods are async for Redis/DB forward-compatibility.
    Implementations must raise PolicyNotFoundError (never return None)
    when a requested policy is absent.

    Constitutional Hash: 608508a9bd224290
    """

    async def load(self, policy_id: str, version: str | None = None) -> Policy:
        """Load a policy by ID and optional version.

        Raises:
            PolicyNotFoundError: if the policy does not exist.
        """
        ...

    async def store(self, policy: Policy) -> None:
        """Persist a policy.  Overwrites any existing version entry."""
        ...

    async def delete(self, policy_id: str) -> None:
        """Remove all versions of *policy_id*.  No-op if absent."""
        ...

    async def list_versions(self, policy_id: str) -> list[str]:
        """Return a list of stored version strings for *policy_id*.

        Returns an empty list (never raises) if *policy_id* is unknown.
        """
        ...


class InMemoryPolicyStorage:
    """In-process policy store for tests and single-process use.

    Each instance is isolated: two InMemoryPolicyStorage objects do not
    share state, making them safe for AgentScope isolation tests.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, scope_id: str = "default") -> None:
        self.scope_id = scope_id
        # policy_id → {version → Policy}
        self._store: dict[str, dict[str, Policy]] = {}

    async def load(self, policy_id: str, version: str | None = None) -> Policy:
        versions = self._store.get(policy_id)
        if not versions:
            raise PolicyNotFoundError(policy_id, version)
        target = version or "latest"
        if target not in versions:
            # Fall back to the most-recently stored entry when version is None
            # and "latest" tag is not explicitly stored.
            if version is None and versions:
                return next(reversed(versions.values()))
            raise PolicyNotFoundError(policy_id, version)
        return versions[target]

    async def store(self, policy: Policy) -> None:
        if policy.policy_id not in self._store:
            self._store[policy.policy_id] = {}
        self._store[policy.policy_id][policy.version] = policy

    async def delete(self, policy_id: str) -> None:
        self._store.pop(policy_id, None)

    async def list_versions(self, policy_id: str) -> list[str]:
        versions = self._store.get(policy_id)
        if not versions:
            return []
        return list(versions.keys())


__all__ = ["InMemoryPolicyStorage", "Policy", "PolicyNotFoundError", "PolicyStorage"]
