"""Exceptions for ACGS-Auth0 constitutional token governance.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations


class TokenVaultGovernanceError(Exception):
    """Base class for all ACGS-Auth0 governance errors."""


class ConstitutionalScopeViolation(TokenVaultGovernanceError):
    """Raised when a requested OAuth scope violates the constitutional policy.

    This is the primary error surface when an agent requests a scope that the
    constitution does not permit for its MACI role.

    Attributes:
        agent_id: Identifier of the agent making the request.
        role: MACI role of the agent.
        connection: External provider connection (e.g. "github", "google-oauth2").
        requested_scopes: The scopes the agent attempted to request.
        permitted_scopes: The scopes the constitution allows for this role/connection.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        role: str,
        connection: str,
        requested_scopes: list[str],
        permitted_scopes: list[str],
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.connection = connection
        self.requested_scopes = requested_scopes
        self.permitted_scopes = permitted_scopes
        denied = set(requested_scopes) - set(permitted_scopes)
        super().__init__(
            f"Constitutional scope violation: agent '{agent_id}' (role={role}) "
            f"requested denied scopes for '{connection}': {sorted(denied)}. "
            f"Permitted: {sorted(permitted_scopes)}"
        )


class MACIRoleNotPermittedError(TokenVaultGovernanceError):
    """Raised when the agent's MACI role has no permission to use a connection at all.

    This is stricter than ConstitutionalScopeViolation — the role is simply not
    listed in the policy for the requested connection.
    """

    def __init__(self, *, agent_id: str, role: str, connection: str) -> None:
        self.agent_id = agent_id
        self.role = role
        self.connection = connection
        super().__init__(
            f"MACI role '{role}' (agent '{agent_id}') is not permitted to access "
            f"connection '{connection}' under the current constitutional policy."
        )


class StepUpAuthRequiredError(TokenVaultGovernanceError):
    """Raised when a high-risk scope requires CIBA step-up authentication.

    This error is intentionally non-fatal in governed tool execution:
    the CIBA handler catches it and initiates the CIBA flow before retrying.

    Attributes:
        connection: External provider connection.
        high_risk_scopes: Subset of requested scopes classified as high-risk.
        binding_message: Human-readable message shown to the user during CIBA approval.
    """

    def __init__(
        self,
        *,
        connection: str,
        high_risk_scopes: list[str],
        binding_message: str,
    ) -> None:
        self.connection = connection
        self.high_risk_scopes = high_risk_scopes
        self.binding_message = binding_message
        super().__init__(
            f"Step-up authentication required for connection '{connection}': "
            f"high-risk scopes {high_risk_scopes}. "
            f"Binding message: '{binding_message}'"
        )
