"""
ACGS-2 SAML Types and Exceptions
Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from datetime import datetime

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)
# Constants for common NameID formats
NAMEID_FORMAT_EMAILADDRESS = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
NAMEID_FORMAT_PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"


class SAMLError(ACGSBaseError):
    """Base exception for SAML-related errors (Q-H4 migration)."""

    http_status_code = 401
    error_code = "SAML_ERROR"


class SAMLValidationError(SAMLError):
    """SAML signature or assertion validation failed (Q-H4 migration)."""

    http_status_code = 401
    error_code = "SAML_VALIDATION_ERROR"


class SAMLAuthenticationError(SAMLError):
    """SAML authentication failed (Q-H4 migration)."""

    http_status_code = 401
    error_code = "SAML_AUTHENTICATION_ERROR"


class SAMLProviderError(SAMLError):
    """Error communicating with SAML IdP (Q-H4 migration)."""

    http_status_code = 502
    error_code = "SAML_PROVIDER_ERROR"


class SAMLReplayError(SAMLError):
    """Replay attack detected - response already processed (Q-H4 migration)."""

    http_status_code = 401
    error_code = "SAML_REPLAY_ERROR"


@dataclass
class SAMLUserInfo:
    """User information extracted from SAML assertion.

    Attributes:
        name_id: SAML NameID (unique user identifier from IdP)
        name_id_format: Format of the NameID
        session_index: Session index for logout
        email: User's email address
        name: Full name
        given_name: First name
        family_name: Last name
        groups: Group memberships from IdP
        attributes: All SAML attributes as dict
        issuer: IdP entity ID that issued the assertion
        authn_instant: When authentication occurred
        session_not_on_or_after: When session expires
    """

    name_id: str
    name_id_format: str = NAMEID_FORMAT_EMAILADDRESS
    session_index: str | None = None
    email: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    groups: list[str] = field(default_factory=list)
    attributes: JSONDict = field(default_factory=dict)
    issuer: str | None = None
    authn_instant: datetime | None = None
    session_not_on_or_after: datetime | None = None

    @classmethod
    def from_response(cls, response: object, has_pysaml2: bool = True) -> "SAMLUserInfo":
        """Create SAMLUserInfo from PySAML2 AuthnResponse.

        Args:
            response: PySAML2 AuthnResponse object
            has_pysaml2: Whether PySAML2 is available

        Returns:
            SAMLUserInfo instance
        """
        if not has_pysaml2:
            raise SAMLError("PySAML2 is required for SAML operations")

        # Extract NameID
        name_id = response.name_id
        name_id_value = str(name_id) if name_id else ""
        name_id_format = getattr(name_id, "format", NAMEID_FORMAT_EMAILADDRESS)

        # Extract session info
        session_info = response.session_info()
        session_index = session_info.get("session_index")

        # Extract attributes
        ava = response.ava  # Attribute Value Assertion

        # Common attribute mappings
        email = None
        name = None
        given_name = None
        family_name = None
        groups = []

        # Email attribute names
        for attr in [
            "email",
            "emailAddress",
            "mail",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        ]:
            if attr in ava:
                email = ava[attr][0] if ava[attr] else None
                break

        # Name attributes
        for attr in [
            "name",
            "displayName",
            "cn",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        ]:
            if attr in ava:
                name = ava[attr][0] if ava[attr] else None
                break

        # Given name
        for attr in [
            "givenName",
            "firstName",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        ]:
            if attr in ava:
                given_name = ava[attr][0] if ava[attr] else None
                break

        # Family name
        for attr in [
            "surname",
            "sn",
            "lastName",
            "familyName",
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        ]:
            if attr in ava:
                family_name = ava[attr][0] if ava[attr] else None
                break

        # Groups
        for attr in [
            "groups",
            "memberOf",
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        ]:
            if attr in ava:
                groups = list(ava[attr]) if ava[attr] else []
                break

        # Parse timestamps
        authn_instant = None
        session_not_on_or_after = None

        # Get issuer
        issuer = response.issuer() if hasattr(response, "issuer") else None

        return cls(
            name_id=name_id_value,
            name_id_format=str(name_id_format) if name_id_format else NAMEID_FORMAT_EMAILADDRESS,
            session_index=session_index,
            email=email or name_id_value,  # Fall back to NameID if no email
            name=name,
            given_name=given_name,
            family_name=family_name,
            groups=groups,
            attributes=dict(ava),
            issuer=issuer,
            authn_instant=authn_instant,
            session_not_on_or_after=session_not_on_or_after,
        )
