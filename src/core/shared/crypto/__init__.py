# Constitutional Hash: cdd01ef066bc6cf2

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import AuthenticationError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing side-channels."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=True):
        result |= ord(x) ^ ord(y)
    return result == 0


class CryptoService:
    """Ed25519 cryptographic service for policy signing and agent token management."""

    @staticmethod
    def generate_keypair() -> tuple[str, str]:
        """Generate a new Ed25519 keypair and return (public_key_b64, private_key_b64)."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        private_b64 = base64.b64encode(private_bytes).decode("utf-8")
        public_b64 = base64.b64encode(public_bytes).decode("utf-8")
        return public_b64, private_b64

    @staticmethod
    def sign_policy_content(content: JSONDict, private_key_b64: str) -> str:
        """Sign a policy content dict with an Ed25519 private key and return base64 signature."""
        content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        content_bytes = content_str.encode("utf-8")

        private_bytes = base64.b64decode(private_key_b64)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)

        signature = private_key.sign(content_bytes)
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def verify_policy_signature(content: JSONDict, signature_b64: str, public_key_b64: str) -> bool:
        """Verify an Ed25519 policy signature; return True if valid, False otherwise."""
        try:
            content_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
            content_bytes = content_str.encode("utf-8")

            public_bytes = base64.b64decode(public_key_b64)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)

            signature_bytes = base64.b64decode(signature_b64)
            public_key.verify(signature_bytes, content_bytes)
            return True
        except (InvalidSignature, ValueError, TypeError, UnicodeEncodeError) as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    @staticmethod
    def generate_public_key_fingerprint(public_key_b64: str) -> str:
        """Return the SHA-256 hex fingerprint of a base64-encoded Ed25519 public key."""
        public_bytes = base64.b64decode(public_key_b64)
        return hashlib.sha256(public_bytes).hexdigest()

    @staticmethod
    def generate_fingerprint(public_key_b64: str) -> str:
        """Alias for generate_public_key_fingerprint."""
        return CryptoService.generate_public_key_fingerprint(public_key_b64)

    @staticmethod
    def create_policy_signature(
        policy_id: str,
        version: str,
        content: JSONDict,
        private_key_b64: str,
        public_key_b64: str,
    ) -> JSONDict:
        """Create a signed policy signature record including fingerprint and metadata."""
        signature_b64 = CryptoService.sign_policy_content(content, private_key_b64)
        fingerprint = CryptoService.generate_public_key_fingerprint(public_key_b64)
        logger.info(f"Created policy signature with fingerprint: {fingerprint}")

        return {
            "policy_id": policy_id,
            "version": version,
            "public_key": public_key_b64,
            "signature": signature_b64,
            "key_fingerprint": fingerprint,
        }

    @staticmethod
    def validate_signature_integrity(signature: JSONDict) -> bool:
        """Validate that the key_fingerprint in a signature record matches the public_key."""
        public_key = signature.get("public_key")
        key_fingerprint = signature.get("key_fingerprint")

        if not isinstance(public_key, str) or not isinstance(key_fingerprint, str):
            return False

        expected_fingerprint = CryptoService.generate_public_key_fingerprint(public_key)
        logger.info(f"Validating signature integrity for public key: {public_key[:20]}...")
        return key_fingerprint == expected_fingerprint

    @staticmethod
    def generate_agent_token(
        agent_id: str,
        tenant_id: str,
        capabilities: list[str],
        private_key_b64: str,
        ttl_hours: int = 24,
        extra_claims: JSONDict | None = None,
        agent_checksum: str | None = None,
    ) -> str:
        """Generate a signed EdDSA JWT agent token with SPIFFE subject and capabilities.

        Args:
            agent_id: Agent identifier.
            tenant_id: Tenant identifier.
            capabilities: List of agent capabilities.
            private_key_b64: Base64-encoded Ed25519 private key.
            ttl_hours: Token time-to-live in hours.
            extra_claims: Additional JWT claims to include.
            agent_checksum: SHA-256 agent code checksum (ach claim) for
                binding the token to a specific agent code version.
        """
        private_bytes = base64.b64decode(private_key_b64)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)

        sub = f"spiffe://acgs2/tenant/{tenant_id}/agent/{agent_id}"
        now = datetime.now(UTC)
        payload: JSONDict = {
            "iss": "acgs2-identity-service",
            "sub": sub,
            "aud": ["acgs2-agent-bus", "acgs2-deliberation-layer"],
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "capabilities": capabilities,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        if agent_checksum:
            payload["ach"] = agent_checksum

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, private_key, algorithm="EdDSA")

    @staticmethod
    def issue_agent_token(
        agent_id: str,
        tenant_id: str,
        capabilities: list[str],
        private_key_b64: str,
        ttl_hours: int = 24,
        extra_claims: JSONDict | None = None,
        agent_checksum: str | None = None,
    ) -> str:
        """Alias for generate_agent_token."""
        return CryptoService.generate_agent_token(
            agent_id=agent_id,
            tenant_id=tenant_id,
            capabilities=capabilities,
            private_key_b64=private_key_b64,
            ttl_hours=ttl_hours,
            extra_claims=extra_claims,
            agent_checksum=agent_checksum,
        )

    @staticmethod
    def verify_agent_token(
        token: str,
        public_key_b64: str,
        expected_checksum: str | None = None,
    ) -> JSONDict:
        """Verify and decode an EdDSA agent JWT; raise AuthenticationError if invalid or expired.

        Args:
            token: The JWT token string.
            public_key_b64: Base64-encoded Ed25519 public key.
            expected_checksum: If provided, validates the ach (agent checksum hash)
                claim against this value. Raises AuthenticationError on mismatch.
        """
        public_bytes = base64.b64decode(public_key_b64)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["EdDSA"],
                audience=["acgs2-agent-bus", "acgs2-deliberation-layer"],
            )

            # Validate agent checksum if expected
            if expected_checksum:
                token_checksum = payload.get("ach")
                if not token_checksum:
                    raise AuthenticationError(
                        "Token missing agent checksum (ach) claim",
                        error_code="CHECKSUM_MISSING",
                    )
                # Constant-time comparison
                if not _constant_time_compare(token_checksum, expected_checksum):
                    raise AuthenticationError(
                        "Agent checksum mismatch — agent code may have been modified",
                        error_code="CHECKSUM_MISMATCH",
                    )

            return payload
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationError(
                "Token has expired",
                error_code="TOKEN_EXPIRED",
            ) from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(
                f"Invalid token: {e}",
                error_code="TOKEN_INVALID",
            ) from e
        except Exception as e:
            raise AuthenticationError(
                f"Token verification failed: {e}",
                error_code="TOKEN_VERIFICATION_FAILED",
            ) from e

    @staticmethod
    def hash_content(content: str) -> str:
        """Return the SHA-256 hex digest of a UTF-8 encoded string."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = ["CryptoService"]
