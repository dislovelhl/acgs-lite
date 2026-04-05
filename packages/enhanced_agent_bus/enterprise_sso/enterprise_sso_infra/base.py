"""
Base interfaces for SSO protocol handlers.
Constitutional Hash: 608508a9bd224290
"""

import secrets
from abc import ABC, abstractmethod

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .models import CONSTITUTIONAL_HASH, AuthorizationRequest, ProtocolValidationResult


class BaseProtocolHandler(ABC):
    """Abstract base class for SSO protocol handlers."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {constitutional_hash}"
            )
        self.constitutional_hash = constitutional_hash

    @abstractmethod
    def create_authorization_request(
        self,
        redirect_uri: str,
        state: str | None = None,
    ) -> AuthorizationRequest:
        """Create an authorization request to initiate SSO flow."""
        pass

    @abstractmethod
    async def validate_response(
        self,
        response_data: JSONDict,
        expected_state: str | None = None,
    ) -> ProtocolValidationResult:
        """Validate SSO response from IdP."""
        pass

    @staticmethod
    def generate_state() -> str:
        """Generate cryptographically secure state parameter."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_nonce() -> str:
        """Generate cryptographically secure nonce."""
        return secrets.token_urlsafe(32)
