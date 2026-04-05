"""Constitutional Hash: 608508a9bd224290
ACGS-2 Runtime Security - Permission Scoper
Facilitates dynamic, task-specific token generation for autonomous agents.
Enforces the principle of least privilege.
"""

import os
from dataclasses import dataclass

from enhanced_agent_bus._compat.crypto import CryptoService

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class ScopedPermission:
    resource: str
    action: str
    constraints: JSONDict | None = None


class PermissionScoper:
    """
    Manages dynamic scoping of agent permissions based on task context.
    Generates short-lived, task-specific tokens (SVIDs).
    """

    def __init__(self, private_key: str | None = None):
        self._private_key = private_key or os.environ.get("JWT_PRIVATE_KEY")
        if not self._private_key:
            logger.warning(
                "PermissionScoper initialized without private key. Token generation will fail."
            )

    def generate_task_token(
        self,
        agent_id: str,
        tenant_id: str,
        task_id: str,
        permissions: list[ScopedPermission],
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generates a task-scoped JWT token.
        """
        if not self._private_key:
            raise ValueError("Private key not configured for PermissionScoper")

        # Prepare extra claims for permissions and task context
        extra_claims = {
            "task_id": task_id,
            "permissions": [
                {"resource": p.resource, "action": p.action, "constraints": p.constraints}
                for p in permissions
            ],
        }

        # Use CryptoService with extra claims support
        return str(
            CryptoService.issue_agent_token(
                agent_id=agent_id,
                tenant_id=tenant_id,
                capabilities=[],  # Capabilities handled via permissions now
                private_key_b64=self._private_key,
                ttl_hours=max(
                    1, round(expires_in_seconds / 3600)
                ),  # Convert to hours, minimum 1 hour
                extra_claims=extra_claims,
            )
        )

    def scope_permissions_for_task(
        self, agent_capabilities: list[str], task_requirements: list[str]
    ) -> list[ScopedPermission]:
        """
        Reduces broad agent capabilities to a minimal set required for a specific task.
        """
        scoped = []
        for req in task_requirements:
            # Simple intersection for now
            if req in agent_capabilities:
                scoped.append(ScopedPermission(resource="general", action=req))
            else:
                logger.warning(
                    f"Agent requested task requiring {req} which exceeds its capabilities."
                )

        return scoped
