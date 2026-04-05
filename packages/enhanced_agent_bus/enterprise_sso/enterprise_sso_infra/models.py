"""
SSO Protocol data models and constants.
Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


@dataclass
class ProtocolValidationResult:
    """Result of validating an SSO protocol response."""

    success: bool
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    groups: list[str] = field(default_factory=list)
    attributes: JSONDict = field(default_factory=dict)
    raw_response: JSONDict | None = None
    error: str | None = None
    error_code: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "success": self.success,
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
            "groups": self.groups,
            "error": self.error,
            "error_code": self.error_code,
        }


@dataclass
class AuthorizationRequest:
    """Authorization request for initiating SSO flow."""

    authorization_url: str
    state: str
    nonce: str | None = None
    code_verifier: str | None = None
    code_challenge: str | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


@dataclass
class LogoutRequest:
    """Logout request for SAML Single Logout (SLO)."""

    logout_url: str
    request_id: str
    name_id: str
    session_index: str | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at


@dataclass
class LogoutRequestResult:
    """Result of processing an IdP-initiated logout request."""

    success: bool
    name_id: str | None = None
    session_index: str | None = None
    in_response_to: str | None = None
    error: str | None = None


@dataclass
class LogoutResult:
    """Result of validating a logout response."""

    success: bool
    error: str | None = None
    error_code: str | None = None
