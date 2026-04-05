"""
ACGS-2 SAML Request Tracker
Constitutional Hash: 608508a9bd224290
"""

import secrets
from datetime import UTC, datetime, timedelta

from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from .saml_config import CONSTITUTIONAL_HASH

logger = get_logger(__name__)


class SAMLRequestTracker:
    """Tracker for outstanding SAML requests to prevent replay attacks."""

    def __init__(self):
        self._requests: dict[str, JSONDict] = {}

    def _generate_request_id(self) -> str:
        """Generate a unique SAML request ID.

        Returns:
            Unique request ID string
        """
        return f"_saml_{secrets.token_hex(16)}"

    def store_request(
        self,
        request_id: str | None = None,
        idp_name: str | None = None,
        relay_state: str | None = None,
        expiry_minutes: int = 5,
    ) -> str:
        """Store an outstanding SAML request.

        Args:
            request_id: Request ID (generated if not provided)
            idp_name: Name of the IdP
            relay_state: Relay state for redirect after authentication
            expiry_minutes: Minutes until request expires

        Returns:
            The request ID
        """
        if request_id is None:
            request_id = self._generate_request_id()

        now = datetime.now(UTC)
        self._requests[request_id] = {
            "idp_name": idp_name,
            "relay_state": relay_state,
            "created_at": now,
            "expires_at": now + timedelta(minutes=expiry_minutes),
        }

        logger.debug(
            "SAML outstanding request stored",
            extra={
                "request_id": request_id[:16] + "...",
                "idp_name": idp_name,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

        return request_id

    def get_request(self, request_id: str) -> JSONDict | None:
        """Get information about an outstanding request.

        Args:
            request_id: Request ID to look up

        Returns:
            Request information or None if not found
        """
        return self._requests.get(request_id)

    def verify_and_remove(self, request_id: str) -> bool:
        """Verify an outstanding request exists and remove it.

        Args:
            request_id: Request ID to verify

        Returns:
            True if request was valid, False otherwise
        """
        if request_id not in self._requests:
            return False

        request = self._requests.pop(request_id)

        # Check expiration
        if datetime.now(UTC) > request["expires_at"]:
            logger.warning(
                "SAML request expired",
                extra={
                    "request_id": request_id[:16] + "...",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            return False

        return True

    def get_requests_as_dict(self) -> dict[str, str]:
        """Get all outstanding requests in a PySAML2 compatible format.

        Returns:
            Dictionary mapping request IDs to IdP names
        """
        # Clean expired requests
        self.clear_expired()

        return {rid: str(req["idp_name"] or "") for rid, req in self._requests.items()}

    def clear_expired(self) -> int:
        """Clear expired outstanding requests.

        Returns:
            Number of requests cleared
        """
        now = datetime.now(UTC)
        expired = [rid for rid, req in self._requests.items() if now > req["expires_at"]]

        for rid in expired:
            del self._requests[rid]

        if expired:
            logger.info(
                "Cleared expired SAML requests",
                extra={
                    "count": len(expired),
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return len(expired)
