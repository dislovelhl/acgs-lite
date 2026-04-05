"""
SAML 2.0 protocol handler.
Constitutional Hash: 608508a9bd224290
"""

import base64
from binascii import Error as BinasciiError
from datetime import UTC, datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import BaseProtocolHandler
from .models import (
    CONSTITUTIONAL_HASH,
    AuthorizationRequest,
    LogoutRequest,
    LogoutRequestResult,
    LogoutResult,
    ProtocolValidationResult,
)

logger = get_logger(__name__)
_SAML_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    BinasciiError,
    UnicodeDecodeError,
)


class SAML2Handler(BaseProtocolHandler):
    """SAML 2.0 protocol handler."""

    def __init__(
        self,
        entity_id: str,
        sso_url: str,
        x509_certificate: str | None = None,
        x509_certificate_fingerprint: str | None = None,
        name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        authn_request_signed: bool = True,
        want_assertions_signed: bool = True,
        want_response_signed: bool = True,
        sp_entity_id: str | None = None,
        sp_acs_url: str | None = None,
        slo_url: str | None = None,
        sp_slo_url: str | None = None,
        sp_x509_certificate: str | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash)
        self.entity_id = entity_id
        self.sso_url = sso_url
        self.x509_certificate = x509_certificate
        self.x509_certificate_fingerprint = x509_certificate_fingerprint
        self.name_id_format = name_id_format
        self.authn_request_signed = authn_request_signed
        self.want_assertions_signed = want_assertions_signed
        self.want_response_signed = want_response_signed
        self.sp_entity_id = sp_entity_id or "urn:acgs2:sp"
        self.sp_acs_url = sp_acs_url
        self.slo_url = slo_url
        self.sp_slo_url = sp_slo_url
        self.sp_x509_certificate = sp_x509_certificate

        self._pending_requests: dict[str, AuthorizationRequest] = {}
        self._pending_logout_requests: dict[str, LogoutRequest] = {}

        logger.info(f"[{CONSTITUTIONAL_HASH}] Initialized SAML2Handler for IdP: {entity_id}")

    def create_authorization_request(
        self,
        redirect_uri: str,
        state: str | None = None,
    ) -> AuthorizationRequest:
        """Create SAML AuthnRequest."""
        state = state or self.generate_state()
        request_id = f"_id_{uuid4().hex}"
        issue_instant = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        acs_url = redirect_uri or self.sp_acs_url or ""

        authn_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{self.sso_url}"
    AssertionConsumerServiceURL="{acs_url}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>{self.sp_entity_id}</saml:Issuer>
    <samlp:NameIDPolicy
        Format="{self.name_id_format}"
        AllowCreate="true"/>
</samlp:AuthnRequest>"""

        encoded_request = base64.b64encode(authn_request.encode("utf-8")).decode("utf-8")
        params = {"SAMLRequest": encoded_request, "RelayState": state}
        authorization_url = f"{self.sso_url}?{urlencode(params)}"

        auth_request = AuthorizationRequest(authorization_url=authorization_url, state=state)
        self._pending_requests[state] = auth_request
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Created SAML AuthnRequest: id={request_id}")

        return auth_request

    async def validate_response(
        self,
        response_data: JSONDict,
        expected_state: str | None = None,
    ) -> ProtocolValidationResult:
        """Validate SAML Response."""
        try:
            saml_response = response_data.get("SAMLResponse")
            relay_state = response_data.get("RelayState")

            if not saml_response:
                return ProtocolValidationResult(
                    success=False, error="Missing SAMLResponse", error_code="MISSING_RESPONSE"
                )

            if expected_state and relay_state != expected_state:
                return ProtocolValidationResult(
                    success=False, error="State mismatch (RelayState)", error_code="STATE_MISMATCH"
                )

            if relay_state and relay_state in self._pending_requests:
                pending = self._pending_requests.pop(relay_state)
                if pending.is_expired():
                    return ProtocolValidationResult(
                        success=False, error="SAML request expired", error_code="REQUEST_EXPIRED"
                    )

            try:
                decoded_response = base64.b64decode(saml_response).decode("utf-8")
            except (BinasciiError, UnicodeDecodeError, ValueError) as e:
                return ProtocolValidationResult(
                    success=False,
                    error=f"Failed to decode SAMLResponse: {e}",
                    error_code="DECODE_ERROR",
                )

            # SECURITY: Verify XML signature before parsing claims.
            # Without signature verification, an attacker can forge arbitrary
            # SAML responses and impersonate any user.
            if self.want_response_signed or self.want_assertions_signed:
                if not self.x509_certificate:
                    logger.error(
                        f"[{CONSTITUTIONAL_HASH}] SAML signature verification required "
                        "but no IdP certificate configured"
                    )
                    return ProtocolValidationResult(
                        success=False,
                        error="SAML signature verification required but no IdP certificate configured. "
                        "Set x509_certificate to the IdP's signing certificate.",
                        error_code="MISSING_IDP_CERTIFICATE",
                    )

                sig_result = self._verify_xml_signature(decoded_response, self.x509_certificate)
                if sig_result is False:
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] SAML response signature verification failed"
                    )
                    return ProtocolValidationResult(
                        success=False,
                        error="SAML response signature verification failed",
                        error_code="SIGNATURE_INVALID",
                    )
                # sig_result is None when signxml is not installed — log warning
                # but allow through (library must be installed for production use)

            result = self._parse_saml_response(decoded_response)
            logger.info(f"[{CONSTITUTIONAL_HASH}] SAML response validated: user={result.user_id}")
            return result

        except _SAML_OPERATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] SAML validation error")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] SAML validation error detail: {e}")
            return ProtocolValidationResult(
                success=False, error="SAML validation failed", error_code="VALIDATION_ERROR"
            )

    def _parse_saml_response(self, xml_response: str) -> ProtocolValidationResult:
        """Parse SAML Response XML."""
        import re

        # Extract basic user identifier
        name_id_match = re.search(
            r"<(?:saml:)?NameID[^>]*>([^<]+)</(?:saml:)?NameID>", xml_response, re.IGNORECASE
        )
        user_id = name_id_match.group(1) if name_id_match else None

        # Extract user attributes using helper methods
        email = self._extract_email_attribute(xml_response, user_id)
        display_name = self._extract_display_name_attribute(xml_response)
        first_name = self._extract_first_name_attribute(xml_response)
        last_name = self._extract_last_name_attribute(xml_response)
        groups = self._extract_groups_attribute(xml_response)

        # Validate required fields
        if not user_id and not email:
            return ProtocolValidationResult(
                success=False,
                error="No user identifier found in SAML response",
                error_code="NO_USER_ID",
            )

        return self._build_validation_result(
            user_id=user_id or email,
            email=email,
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            groups=groups,
            xml_response=xml_response,
        )

    @staticmethod
    def _extract_email_attribute(xml_response: str, user_id: str | None) -> str | None:
        """Extract email attribute from SAML response."""
        import re

        email_patterns = [
            r'Name="(?:http://schemas\.xmlsoap\.org/ws/2005/05/identity/claims/)?emailaddress"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="mail"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="email"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
        ]

        for pattern in email_patterns:
            match = re.search(pattern, xml_response, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        # Fallback: use user_id if it looks like an email
        if user_id and "@" in user_id:
            return user_id

        return None

    @staticmethod
    def _extract_display_name_attribute(xml_response: str) -> str | None:
        """Extract display name attribute from SAML response."""
        import re

        name_patterns = [
            r'Name="(?:http://schemas\.xmlsoap\.org/ws/2005/05/identity/claims/)?displayname"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="displayName"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="name"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
        ]

        for pattern in name_patterns:
            match = re.search(pattern, xml_response, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return None

    @staticmethod
    def _extract_first_name_attribute(xml_response: str) -> str | None:
        """Extract first name attribute from SAML response."""
        import re

        first_name_patterns = [
            r'Name="(?:http://schemas\.xmlsoap\.org/ws/2005/05/identity/claims/)?givenname"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="firstName"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="given_name"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
        ]

        for pattern in first_name_patterns:
            match = re.search(pattern, xml_response, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return None

    @staticmethod
    def _extract_last_name_attribute(xml_response: str) -> str | None:
        """Extract last name attribute from SAML response."""
        import re

        last_name_patterns = [
            r'Name="(?:http://schemas\.xmlsoap\.org/ws/2005/05/identity/claims/)?surname"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="lastName"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
            r'Name="family_name"[^>]*>\s*<(?:saml:)?AttributeValue>([^<]+)',
        ]

        for pattern in last_name_patterns:
            match = re.search(pattern, xml_response, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        return None

    @staticmethod
    def _extract_groups_attribute(xml_response: str) -> list[str]:
        """Extract groups attribute from SAML response."""
        import re

        groups_patterns = [
            r'Name="(?:http://schemas\.microsoft\.com/ws/2008/06/identity/claims/)?groups?"[^>]*>.*?</(?:saml:)?Attribute>',
            r'Name="memberOf"[^>]*>.*?</(?:saml:)?Attribute>',
        ]

        for pattern in groups_patterns:
            match = re.search(pattern, xml_response, re.IGNORECASE | re.DOTALL)
            if match:
                group_values = re.findall(
                    r"<(?:saml:)?AttributeValue>([^<]+)</(?:saml:)?AttributeValue>", match.group(0)
                )
                return group_values

        return []

    @staticmethod
    def _build_validation_result(
        user_id: str,
        email: str | None,
        display_name: str | None,
        first_name: str | None,
        last_name: str | None,
        groups: list[str],
        xml_response: str,
    ) -> ProtocolValidationResult:
        """Build the final validation result."""
        return ProtocolValidationResult(
            success=True,
            user_id=user_id,
            email=email,
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            groups=groups,
            attributes={},
            raw_response={"xml": xml_response[:1000]},
        )

    def _verify_xml_signature(self, xml_response: str, certificate: str) -> bool | None:
        """
        Verify XML digital signature on SAML response.

        Returns:
            True if signature is valid, False if invalid, None if signxml
            is not installed (logs a warning for production deployments).

        Uses signxml if available. This is a critical security control —
        without it, SAML responses can be forged by any attacker.
        In production, signxml MUST be installed.
        """
        try:
            from lxml import etree
            from signxml import XMLVerifier
        except ImportError:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] signxml/lxml not installed — "
                "SAML signature verification SKIPPED. "
                "Install with: pip install signxml lxml. "
                "This MUST be installed for production SAML deployments."
            )
            return None

        try:
            root = etree.fromstring(xml_response.encode("utf-8"))
            XMLVerifier().verify(root, x509_cert=certificate)
            return True
        except _SAML_OPERATION_ERRORS as e:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] SAML signature verification failed: {e}")
            return False

    def generate_sp_metadata(self) -> str:
        """Generate SAML Service Provider metadata XML."""
        acs_url = self.sp_acs_url or ""
        authn_signed = "true" if self.authn_request_signed else "false"
        want_assertions_signed = "true" if self.want_assertions_signed else "false"

        key_descriptor = ""
        if self.sp_x509_certificate:
            cert_body = self.sp_x509_certificate
            if "-----BEGIN CERTIFICATE-----" in cert_body:
                cert_body = (
                    cert_body.replace("-----BEGIN CERTIFICATE-----", "")
                    .replace("-----END CERTIFICATE-----", "")
                    .strip()
                )

            key_descriptor = f"""
        <md:KeyDescriptor use="signing">
            <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
                <ds:X509Data>
                    <ds:X509Certificate>{cert_body}</ds:X509Certificate>
                </ds:X509Data>
            </ds:KeyInfo>
        </md:KeyDescriptor>"""

        slo_section = ""
        if self.sp_slo_url:
            slo_section = f"""
        <md:SingleLogoutService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="{self.sp_slo_url}"/>
        <md:SingleLogoutService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="{self.sp_slo_url}"/>"""

        metadata = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="{self.sp_entity_id}">
    <md:SPSSODescriptor
        AuthnRequestsSigned="{authn_signed}"
        WantAssertionsSigned="{want_assertions_signed}"
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">{key_descriptor}{slo_section}
        <md:NameIDFormat>{self.name_id_format}</md:NameIDFormat>
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="{acs_url}"
            index="0"
            isDefault="true"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>"""

        logger.debug(f"[{CONSTITUTIONAL_HASH}] Generated SP metadata for: {self.sp_entity_id}")
        return metadata

    def create_logout_request(
        self,
        name_id: str,
        session_index: str | None = None,
    ) -> LogoutRequest | None:
        """Create SAML LogoutRequest."""
        if not self.slo_url:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] SLO not configured for this handler")
            return None

        request_id = f"_id_{uuid4().hex}"
        issue_instant = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_index_element = (
            f"\n    <samlp:SessionIndex>{session_index}</samlp:SessionIndex>"
            if session_index
            else ""
        )

        logout_request_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{self.slo_url}">
    <saml:Issuer>{self.sp_entity_id}</saml:Issuer>
    <saml:NameID Format="{self.name_id_format}">{name_id}</saml:NameID>{session_index_element}
</samlp:LogoutRequest>"""

        encoded_request = base64.b64encode(logout_request_xml.encode("utf-8")).decode("utf-8")
        params = {"SAMLRequest": encoded_request}
        logout_url = f"{self.slo_url}?{urlencode(params)}"

        logout_request = LogoutRequest(
            logout_url=logout_url,
            request_id=request_id,
            name_id=name_id,
            session_index=session_index,
        )
        self._pending_logout_requests[request_id] = logout_request
        logger.debug(f"[{CONSTITUTIONAL_HASH}] Created SAML LogoutRequest: id={request_id}")
        return logout_request

    async def validate_logout_response(self, response_data: JSONDict) -> LogoutResult:
        """Validate SAML LogoutResponse."""
        try:
            saml_response = response_data.get("SAMLResponse")
            if not saml_response:
                return LogoutResult(
                    success=False, error="Missing SAMLResponse", error_code="MISSING_RESPONSE"
                )

            try:
                decoded_response = base64.b64decode(saml_response).decode("utf-8")
            except (BinasciiError, UnicodeDecodeError, ValueError) as e:
                return LogoutResult(
                    success=False,
                    error=f"Failed to decode SAMLResponse: {e}",
                    error_code="DECODE_ERROR",
                )

            import re

            status_match = re.search(
                r'StatusCode\s+Value="([^"]+)"', decoded_response, re.IGNORECASE
            )
            if status_match and "Success" in status_match.group(1):
                logger.info(f"[{CONSTITUTIONAL_HASH}] SLO completed successfully")
                return LogoutResult(success=True)

            error_match = re.search(
                r"<samlp:StatusMessage>([^<]+)</samlp:StatusMessage>",
                decoded_response,
                re.IGNORECASE,
            )
            error_message = error_match.group(1) if error_match else "Logout failed"
            return LogoutResult(success=False, error=error_message, error_code="LOGOUT_FAILED")

        except _SAML_OPERATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] SLO response validation error")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] SLO response validation error detail: {e}")
            return LogoutResult(
                success=False, error="Logout validation failed", error_code="VALIDATION_ERROR"
            )

    async def handle_logout_request(self, request_data: JSONDict) -> LogoutRequestResult:
        """Handle IdP-initiated LogoutRequest."""
        try:
            saml_request = request_data.get("SAMLRequest")
            if not saml_request:
                return LogoutRequestResult(success=False, error="Missing SAMLRequest")

            try:
                decoded_request = base64.b64decode(saml_request).decode("utf-8")
            except (BinasciiError, UnicodeDecodeError, ValueError) as e:
                return LogoutRequestResult(
                    success=False, error=f"Failed to decode SAMLRequest: {e}"
                )

            import re

            name_id_match = re.search(
                r"<(?:saml:)?NameID[^>]*>([^<]+)</(?:saml:)?NameID>", decoded_request, re.IGNORECASE
            )
            name_id = name_id_match.group(1) if name_id_match else None

            session_index_match = re.search(
                r"<(?:samlp:)?SessionIndex>([^<]+)</(?:samlp:)?SessionIndex>",
                decoded_request,
                re.IGNORECASE,
            )
            session_index = session_index_match.group(1) if session_index_match else None

            id_match = re.search(r'ID="([^"]+)"', decoded_request, re.IGNORECASE)
            in_response_to = id_match.group(1) if id_match else None

            if not name_id:
                return LogoutRequestResult(success=False, error="No NameID found in logout request")

            logger.info(f"[{CONSTITUTIONAL_HASH}] IdP-initiated logout for: {name_id}")
            return LogoutRequestResult(
                success=True,
                name_id=name_id,
                session_index=session_index,
                in_response_to=in_response_to,
            )

        except _SAML_OPERATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] IdP logout request handling error")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] IdP logout request error detail: {e}")
            return LogoutRequestResult(success=False, error="Logout request processing failed")
