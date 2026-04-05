"""
OpenID Connect (OIDC) protocol handler.
Constitutional Hash: 608508a9bd224290
"""

import hashlib
import json
import time
from urllib.parse import urlencode

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .base import BaseProtocolHandler
from .models import (
    CONSTITUTIONAL_HASH,
    AuthorizationRequest,
    ProtocolValidationResult,
)

logger = get_logger(__name__)
_OIDC_HANDLER_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
    json.JSONDecodeError,
)


class OIDCHandler(BaseProtocolHandler):
    """OpenID Connect (OIDC) protocol handler."""

    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str | None = None,
        authorization_endpoint: str | None = None,
        token_endpoint: str | None = None,
        userinfo_endpoint: str | None = None,
        jwks_uri: str | None = None,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        super().__init__(constitutional_hash)
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or ["openid", "profile", "email"]
        self.use_pkce = use_pkce

        self.authorization_endpoint = authorization_endpoint or f"{self.issuer}/authorize"
        self.token_endpoint = token_endpoint or f"{self.issuer}/oauth/token"
        self.userinfo_endpoint = userinfo_endpoint or f"{self.issuer}/userinfo"
        self.jwks_uri = jwks_uri or f"{self.issuer}/.well-known/jwks.json"

        self._pending_requests: dict[str, AuthorizationRequest] = {}

        logger.info(f"[{CONSTITUTIONAL_HASH}] Initialized OIDCHandler for issuer: {issuer}")

    def create_authorization_request(
        self,
        redirect_uri: str,
        state: str | None = None,
    ) -> AuthorizationRequest:
        """Create OIDC authorization request."""
        state = state or self.generate_state()
        nonce = self.generate_nonce()
        code_verifier = None
        code_challenge = None

        if self.use_pkce:
            code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(code_verifier)

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "nonce": nonce,
        }

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        authorization_url = f"{self.authorization_endpoint}?{urlencode(params)}"
        auth_request = AuthorizationRequest(
            authorization_url=authorization_url,
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            code_challenge=code_challenge,
        )

        self._pending_requests[state] = auth_request
        logger.debug(
            f"[{CONSTITUTIONAL_HASH}] Created OIDC authorization request: state={state[:12]}..."
        )
        return auth_request

    async def validate_response(
        self,
        response_data: JSONDict,
        expected_state: str | None = None,
    ) -> ProtocolValidationResult:
        """Validate OIDC callback response."""
        try:
            if "error" in response_data:
                return ProtocolValidationResult(
                    success=False,
                    error=response_data.get("error_description", response_data["error"]),
                    error_code=response_data["error"],
                )

            code = response_data.get("code")
            state = response_data.get("state")

            if not code:
                return ProtocolValidationResult(
                    success=False, error="Missing authorization code", error_code="MISSING_CODE"
                )

            if expected_state and state != expected_state:
                return ProtocolValidationResult(
                    success=False, error="State mismatch", error_code="STATE_MISMATCH"
                )

            pending = None
            if state and state in self._pending_requests:
                pending = self._pending_requests.pop(state)
                if pending.is_expired():
                    return ProtocolValidationResult(
                        success=False,
                        error="Authorization request expired",
                        error_code="REQUEST_EXPIRED",
                    )

            redirect_uri = response_data.get("redirect_uri", "")
            tokens = await self._exchange_code(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=pending.code_verifier if pending else None,
            )

            if "error" in tokens:
                return ProtocolValidationResult(
                    success=False,
                    error=tokens.get("error_description", tokens["error"]),
                    error_code=tokens["error"],
                )

            id_token = tokens.get("id_token")
            if id_token:
                expected_nonce = pending.nonce if pending else None
                result = self._parse_id_token(id_token, expected_nonce=expected_nonce)
                result.raw_response = {"tokens": {k: "..." for k in tokens.keys()}}
                return result

            access_token = tokens.get("access_token")
            if access_token:
                return await self._get_userinfo(access_token)

            return ProtocolValidationResult(
                success=False, error="No ID token or access token received", error_code="NO_TOKEN"
            )

        except _OIDC_HANDLER_OPERATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] OIDC validation error")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] OIDC validation error detail: {e}")
            return ProtocolValidationResult(
                success=False, error="OIDC validation failed", error_code="VALIDATION_ERROR"
            )

    async def _exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> JSONDict:
        """Exchange authorization code for tokens."""
        from enhanced_agent_bus._compat.http_client import HttpClient

        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            async with HttpClient() as client:
                response = await client.post(
                    self.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                return response.json()
        except _OIDC_HANDLER_OPERATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] Token exchange failed")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] Token exchange error detail: {e}")
            return {"error": "token_exchange_failed", "error_description": "Token exchange failed"}

    def _parse_id_token(
        self, id_token: str, expected_nonce: str | None = None
    ) -> ProtocolValidationResult:
        """Parse and validate ID token (JWT)."""
        import base64

        try:
            parts = id_token.split(".")
            if len(parts) != 3:
                return ProtocolValidationResult(
                    success=False,
                    error="Invalid ID token format",
                    error_code="INVALID_TOKEN",
                )

            payload = parts[1]
            payload += "=" * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded)

            now = time.time()
            if claims.get("exp", 0) < now:
                return ProtocolValidationResult(
                    success=False,
                    error="ID token expired",
                    error_code="TOKEN_EXPIRED",
                )

            if claims.get("aud") != self.client_id:
                return ProtocolValidationResult(
                    success=False,
                    error="ID token audience mismatch",
                    error_code="AUDIENCE_MISMATCH",
                )

            # SECURITY: Verify nonce to prevent replay attacks.
            # If the IdP returns a nonce in the token, it MUST match the
            # one we sent in the authorization request.
            token_nonce = claims.get("nonce")
            if expected_nonce and token_nonce is not None:
                if token_nonce != expected_nonce:
                    return ProtocolValidationResult(
                        success=False,
                        error="ID token nonce mismatch - possible replay attack",
                        error_code="NONCE_MISMATCH",
                    )
            elif expected_nonce and token_nonce is None:
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] ID token missing nonce claim - "
                    "IdP should return the nonce sent in the authorization request"
                )

            user_id = claims.get("sub")
            if not user_id:
                return ProtocolValidationResult(
                    success=False,
                    error="No subject claim in ID token",
                    error_code="NO_SUBJECT",
                )

            groups = claims.get("groups", [])
            return ProtocolValidationResult(
                success=True,
                user_id=user_id,
                email=claims.get("email"),
                display_name=claims.get("name"),
                first_name=claims.get("given_name"),
                last_name=claims.get("family_name"),
                groups=groups if isinstance(groups, list) else [groups],
                attributes=claims,
            )
        except _OIDC_HANDLER_OPERATION_ERRORS as e:
            return ProtocolValidationResult(
                success=False,
                error=f"Failed to parse ID token: {e}",
                error_code="PARSE_ERROR",
            )

    async def _get_userinfo(self, access_token: str) -> ProtocolValidationResult:
        """Get user information from userinfo endpoint."""
        from enhanced_agent_bus._compat.http_client import HttpClient

        try:
            async with HttpClient() as client:
                response = await client.get(
                    self.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code != 200:
                    return ProtocolValidationResult(
                        success=False,
                        error=f"Userinfo request failed: {response.status_code}",
                        error_code="USERINFO_FAILED",
                    )
                userinfo = response.json()
                return ProtocolValidationResult(
                    success=True,
                    user_id=userinfo.get("sub"),
                    email=userinfo.get("email"),
                    display_name=userinfo.get("name"),
                    first_name=userinfo.get("given_name"),
                    last_name=userinfo.get("family_name"),
                    groups=userinfo.get("groups", []),
                    attributes=userinfo,
                )
        except _OIDC_HANDLER_OPERATION_ERRORS as e:
            return ProtocolValidationResult(
                success=False,
                error=f"Failed to get userinfo: {e}",
                error_code="USERINFO_ERROR",
            )

    @staticmethod
    def _generate_code_verifier() -> str:
        """Generate PKCE code verifier."""
        import secrets

        return secrets.token_urlsafe(64)[:128]

    @staticmethod
    def _generate_code_challenge(code_verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        import base64

        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
