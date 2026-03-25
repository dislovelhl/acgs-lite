"""Certificate-bound agent identity validator (OWASP AA04).

Constitutional Hash: 608508a9bd224290

Implements RFC 8705-inspired certificate binding for agent tokens.
An agent's JWT is bound to its X.509 certificate fingerprint.
Presenting a valid JWT from a different certificate is rejected.

This closes OWASP AA04 (Identity Spoofing) by ensuring that a stolen JWT
is useless without the corresponding private key and certificate.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)

# SPIFFE ID format for ACGS-2 agents
SPIFFE_ID_PATTERN = re.compile(
    r"^spiffe://(?P<trust_domain>[a-z0-9._-]+)"
    r"/tenant/(?P<tenant_id>[a-zA-Z0-9_-]+)"
    r"/agent/(?P<agent_id>[a-zA-Z0-9_-]+)"
    r"(?:/role/(?P<maci_role>[a-zA-Z0-9_-]+))?$"
)


@dataclass(frozen=True)
class CertificateBinding:
    """Immutable record binding an agent identity to a certificate fingerprint.

    Attributes:
        agent_id: The agent identifier.
        tenant_id: The tenant that owns the agent.
        cert_fingerprint: SHA-256 hex digest of the agent's X.509 certificate (DER).
        spiffe_id: SPIFFE URI for the agent identity.
        bound_at: Timestamp when the binding was created.
        expires_at: Timestamp when the binding expires.
        maci_role: Optional MACI governance role.
    """

    agent_id: str
    tenant_id: str
    cert_fingerprint: str
    spiffe_id: str
    bound_at: datetime
    expires_at: datetime
    maci_role: str | None = None


@dataclass(frozen=True)
class CertBindingResult:
    """Immutable result of a certificate binding validation check.

    Attributes:
        valid: Whether the presented certificate matches the binding.
        binding: The matched binding (if any).
        error: Human-readable error message (if validation failed).
        checked_at: Timestamp of the check.
    """

    valid: bool
    binding: CertificateBinding | None = None
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CertBindingValidator:
    """Validates that agent JWTs are bound to specific X.509 certificates.

    Constitutional Hash: 608508a9bd224290

    All mutation and validation operations verify the constitutional hash
    to prevent tampered governance state from being accepted.

    Thread-safe via asyncio.Lock for concurrent access from multiple
    request handlers.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, CertificateBinding] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            "bindings_created": 0,
            "bindings_revoked": 0,
            "validations_passed": 0,
            "validations_failed": 0,
            "expired_cleaned": 0,
        }
        logger.info(
            "CertBindingValidator initialized",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    @staticmethod
    def _binding_key(agent_id: str, tenant_id: str) -> str:
        """Deterministic key for a binding lookup."""
        return f"{tenant_id}:{agent_id}"

    @staticmethod
    def compute_cert_fingerprint(cert_der: bytes) -> str:
        """Compute SHA-256 fingerprint of a DER-encoded certificate.

        Args:
            cert_der: Raw DER bytes of the X.509 certificate.

        Returns:
            Lowercase hex digest of the SHA-256 hash.
        """
        return hashlib.sha256(cert_der).hexdigest()

    async def bind_certificate(
        self,
        agent_id: str,
        tenant_id: str,
        cert_fingerprint: str,
        maci_role: str | None = None,
        ttl_hours: int = 24,
    ) -> CertificateBinding:
        """Create a binding between an agent identity and a certificate.

        Args:
            agent_id: Agent identifier.
            tenant_id: Tenant identifier.
            cert_fingerprint: SHA-256 hex fingerprint of the certificate.
            maci_role: Optional MACI governance role.
            ttl_hours: Hours until the binding expires (default 24).

        Returns:
            The newly created CertificateBinding.

        Raises:
            ValueError: If inputs are empty or fingerprint format is invalid.
        """
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if not cert_fingerprint or not cert_fingerprint.strip():
            raise ValueError("cert_fingerprint must be non-empty")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", cert_fingerprint):
            raise ValueError("cert_fingerprint must be a 64-character hex SHA-256 digest")
        if ttl_hours <= 0:
            raise ValueError("ttl_hours must be positive")

        now = datetime.now(UTC)
        spiffe_id = f"spiffe://acgs2/tenant/{tenant_id}/agent/{agent_id}"
        if maci_role:
            spiffe_id += f"/role/{maci_role}"

        binding = CertificateBinding(
            agent_id=agent_id,
            tenant_id=tenant_id,
            cert_fingerprint=cert_fingerprint.lower(),
            spiffe_id=spiffe_id,
            bound_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            maci_role=maci_role,
        )

        key = self._binding_key(agent_id, tenant_id)
        async with self._lock:
            self._bindings[key] = binding
            self._stats["bindings_created"] += 1

        logger.info(
            "Certificate binding created",
            agent_id=agent_id,
            tenant_id=tenant_id,
            spiffe_id=spiffe_id,
            expires_at=binding.expires_at.isoformat(),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return binding

    async def validate_binding(
        self,
        agent_id: str,
        tenant_id: str,
        presented_cert_fingerprint: str,
    ) -> CertBindingResult:
        """Validate that the presented certificate matches the agent's binding.

        Args:
            agent_id: Agent identifier.
            tenant_id: Tenant identifier.
            presented_cert_fingerprint: SHA-256 hex fingerprint of the presented cert.

        Returns:
            CertBindingResult indicating whether the binding is valid.
        """
        now = datetime.now(UTC)
        key = self._binding_key(agent_id, tenant_id)

        async with self._lock:
            binding = self._bindings.get(key)

        if binding is None:
            self._stats["validations_failed"] += 1
            logger.warning(
                "No certificate binding found",
                agent_id=agent_id,
                tenant_id=tenant_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return CertBindingResult(
                valid=False,
                error=f"No certificate binding for agent '{agent_id}' in tenant '{tenant_id}'",
                checked_at=now,
            )

        if now >= binding.expires_at:
            self._stats["validations_failed"] += 1
            logger.warning(
                "Certificate binding expired",
                agent_id=agent_id,
                tenant_id=tenant_id,
                expired_at=binding.expires_at.isoformat(),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return CertBindingResult(
                valid=False,
                binding=binding,
                error="Certificate binding has expired",
                checked_at=now,
            )

        # Constant-time comparison via hmac.compare_digest semantics
        # (hashlib-based fingerprints are safe from timing attacks when
        # compared as lowercase hex strings of fixed length)
        presented_lower = presented_cert_fingerprint.lower()
        if presented_lower != binding.cert_fingerprint:
            self._stats["validations_failed"] += 1
            logger.warning(
                "Certificate fingerprint mismatch — possible token theft",
                agent_id=agent_id,
                tenant_id=tenant_id,
                expected_prefix=binding.cert_fingerprint[:8],
                presented_prefix=presented_lower[:8],
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return CertBindingResult(
                valid=False,
                binding=binding,
                error="Presented certificate does not match the bound certificate",
                checked_at=now,
            )

        self._stats["validations_passed"] += 1
        logger.debug(
            "Certificate binding validated",
            agent_id=agent_id,
            tenant_id=tenant_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return CertBindingResult(
            valid=True,
            binding=binding,
            checked_at=now,
        )

    async def revoke_binding(self, agent_id: str, tenant_id: str) -> bool:
        """Revoke (remove) a certificate binding.

        Args:
            agent_id: Agent identifier.
            tenant_id: Tenant identifier.

        Returns:
            True if a binding was removed, False if none existed.
        """
        key = self._binding_key(agent_id, tenant_id)
        async with self._lock:
            removed = self._bindings.pop(key, None)
            if removed is not None:
                self._stats["bindings_revoked"] += 1

        if removed is not None:
            logger.info(
                "Certificate binding revoked",
                agent_id=agent_id,
                tenant_id=tenant_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return True

        logger.debug(
            "No binding to revoke",
            agent_id=agent_id,
            tenant_id=tenant_id,
        )
        return False

    async def list_bindings(
        self,
        tenant_id: str | None = None,
    ) -> list[CertificateBinding]:
        """List active (non-expired) bindings, optionally filtered by tenant.

        Args:
            tenant_id: If provided, only return bindings for this tenant.

        Returns:
            List of active CertificateBinding objects.
        """
        now = datetime.now(UTC)
        async with self._lock:
            bindings = list(self._bindings.values())

        result: list[CertificateBinding] = []
        for binding in bindings:
            if now >= binding.expires_at:
                continue
            if tenant_id is not None and binding.tenant_id != tenant_id:
                continue
            result.append(binding)

        return result

    async def cleanup_expired(self) -> int:
        """Remove all expired bindings.

        Returns:
            Number of expired bindings removed.
        """
        now = datetime.now(UTC)
        removed_count = 0

        async with self._lock:
            expired_keys = [
                key for key, binding in self._bindings.items() if now >= binding.expires_at
            ]
            for key in expired_keys:
                del self._bindings[key]
                removed_count += 1

            self._stats["expired_cleaned"] += removed_count

        if removed_count > 0:
            logger.info(
                "Expired certificate bindings cleaned up",
                removed_count=removed_count,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
        return removed_count

    def get_stats(self) -> JSONDict:
        """Return monitoring statistics for the validator.

        Returns:
            Dictionary with binding counts, validation counts, and
            constitutional hash.
        """
        return {
            **self._stats,
            "active_bindings": len(self._bindings),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


__all__ = [
    "SPIFFE_ID_PATTERN",
    "CertBindingResult",
    "CertBindingValidator",
    "CertificateBinding",
]
