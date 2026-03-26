"""SPIFFE SVID identity validation for ACGS-2 agent attestation.

Constitutional Hash: 608508a9bd224290

Provides X.509 SVID (SPIFFE Verifiable Identity Document) validation as an
alternative identity attestation mechanism alongside existing JWT auth.

SPIFFE identities use the URI SAN format::

    spiffe://<trust_domain>/tenant/<tenant_id>/agent/<agent_id>[/role/<maci_role>]

This module is fail-closed: any validation error results in a rejection.
Feature flag: ``ACGS_ENABLE_SPIFFE_ATTESTATION`` (default ``false``).

Usage::

    from src.core.shared.security.spiffe_identity import SpiffeIdentityValidator

    validator = SpiffeIdentityValidator()
    result = validator.validate_svid(cert_pem)
    if result.valid:
        agent_id = result.spiffe_id.agent_id
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.x509.oid import ExtensionOID

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.security.spiffe_san import (
    DEFAULT_TRUST_DOMAINS,
    SpiffeId,
    parse_spiffe_id,
)
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Environment variable controlling SPIFFE attestation visibility
_SPIFFE_FEATURE_FLAG = "ACGS_ENABLE_SPIFFE_ATTESTATION"


@dataclass(frozen=True)
class SpiffeValidationResult:
    """Immutable result of SPIFFE SVID validation.

    Attributes:
        valid: Whether the certificate passed all validation checks.
        spiffe_id: Parsed SPIFFE identity (None if validation failed).
        error: Human-readable error message (None if validation succeeded).
        checked_at: Timestamp when the validation was performed.
    """

    valid: bool
    spiffe_id: SpiffeId | None = None
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SpiffeIdentityValidator:
    """Validates X.509 SVID certificates for SPIFFE-based agent identity.

    Constitutional Hash: 608508a9bd224290

    The validator extracts SPIFFE URIs from certificate SANs, validates the
    trust domain against an allow-list, and checks certificate expiry.

    All validation failures result in ``SpiffeValidationResult(valid=False)``
    (fail-closed posture).

    Args:
        allowed_trust_domains: Trust domains to accept.  Defaults to
            ``DEFAULT_TRUST_DOMAINS`` from ``spiffe_san.py``.
    """

    def __init__(
        self,
        allowed_trust_domains: list[str] | None = None,
    ) -> None:
        self._allowed_domains: list[str] = (
            allowed_trust_domains
            if allowed_trust_domains is not None
            else list(DEFAULT_TRUST_DOMAINS)
        )
        self._stats = {
            "validations_attempted": 0,
            "validations_passed": 0,
            "validations_failed": 0,
        }

        feature_enabled = os.environ.get(_SPIFFE_FEATURE_FLAG, "false").lower() == "true"
        if not feature_enabled:
            logger.warning(
                "SPIFFE attestation feature flag is disabled; "
                "validator is operational but attestation is not enforced",
                feature_flag=_SPIFFE_FEATURE_FLAG,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        logger.info(
            "SpiffeIdentityValidator initialized",
            allowed_trust_domains=self._allowed_domains,
            feature_enabled=feature_enabled,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    def _fail(self, error: str) -> SpiffeValidationResult:
        """Create a failed validation result and update stats."""
        self._stats["validations_failed"] += 1
        logger.warning(
            "SPIFFE SVID validation failed",
            error=error,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return SpiffeValidationResult(valid=False, error=error)

    def validate_svid(self, cert_pem: bytes | str) -> SpiffeValidationResult:
        """Validate an X.509 SVID certificate and extract the SPIFFE identity.

        Performs the following checks in order:
        1. Parse the certificate (PEM or DER).
        2. Check certificate expiry (not-before / not-after).
        3. Extract SPIFFE URI from Subject Alternative Name.
        4. Parse and validate the SPIFFE URI.
        5. Verify the trust domain is in the allow-list.

        Args:
            cert_pem: PEM-encoded (or DER-encoded) X.509 certificate.

        Returns:
            SpiffeValidationResult indicating success or failure.
        """
        self._stats["validations_attempted"] += 1

        # Step 1: Parse certificate
        cert = self._load_certificate(cert_pem)
        if cert is None:
            return self._fail("Failed to parse certificate (tried PEM and DER)")

        # Step 2: Check expiry
        now = datetime.now(UTC)
        not_valid_before = cert.not_valid_before_utc
        not_valid_after = cert.not_valid_after_utc

        if now < not_valid_before:
            return self._fail(
                f"Certificate is not yet valid (not-before: {not_valid_before.isoformat()})"
            )
        if now > not_valid_after:
            return self._fail(f"Certificate has expired (not-after: {not_valid_after.isoformat()})")

        # Step 3: Extract SPIFFE URI from SAN
        spiffe_uri = self._extract_spiffe_uri(cert)
        if spiffe_uri is None:
            return self._fail("No spiffe:// URI found in certificate Subject Alternative Name")

        # Step 4: Parse SPIFFE URI
        try:
            spiffe_id = parse_spiffe_id(spiffe_uri)
        except ValueError as exc:
            return self._fail(f"Invalid SPIFFE URI in certificate SAN: {exc}")

        # Step 5: Validate trust domain
        if spiffe_id.trust_domain not in self._allowed_domains:
            return self._fail(
                f"Trust domain '{spiffe_id.trust_domain}' is not in the allowed list: "
                f"{self._allowed_domains}"
            )

        # All checks passed
        self._stats["validations_passed"] += 1
        logger.info(
            "SPIFFE SVID validated successfully",
            spiffe_id=spiffe_id.raw,
            trust_domain=spiffe_id.trust_domain,
            agent_id=spiffe_id.agent_id,
            tenant_id=spiffe_id.tenant_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return SpiffeValidationResult(valid=True, spiffe_id=spiffe_id)

    def parse_spiffe_id(self, uri: str) -> SpiffeId:
        """Parse a SPIFFE URI string into a SpiffeId.

        Convenience wrapper around :func:`spiffe_san.parse_spiffe_id`.

        Args:
            uri: A URI starting with ``spiffe://``.

        Returns:
            Parsed SpiffeId with extracted components.

        Raises:
            ValueError: If the URI is not a valid SPIFFE ID.
        """
        return parse_spiffe_id(uri)

    def get_stats(self) -> dict[str, int]:
        """Return validation statistics.

        Returns:
            Dictionary with attempt, pass, and fail counts.
        """
        return dict(self._stats)

    @staticmethod
    def _load_certificate(cert_data: bytes | str) -> x509.Certificate | None:
        """Attempt to load a certificate from PEM or DER format.

        Args:
            cert_data: Certificate bytes or string.

        Returns:
            Parsed Certificate, or None if parsing failed.
        """
        if isinstance(cert_data, str):
            cert_data = cert_data.encode("utf-8")

        # Try PEM first
        try:
            return x509.load_pem_x509_certificate(cert_data)
        except (ValueError, UnsupportedAlgorithm):
            pass

        # Fall back to DER
        try:
            return x509.load_der_x509_certificate(cert_data)
        except (ValueError, UnsupportedAlgorithm):
            return None

    @staticmethod
    def _extract_spiffe_uri(cert: x509.Certificate) -> str | None:
        """Extract the first spiffe:// URI from certificate SANs.

        Args:
            cert: Parsed X.509 certificate.

        Returns:
            The first spiffe:// URI found, or None.
        """
        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        except x509.ExtensionNotFound:
            return None

        for general_name in san_ext.value:
            if isinstance(general_name, x509.UniformResourceIdentifier):
                uri: str = general_name.value
                if uri.startswith("spiffe://"):
                    return uri

        return None


__all__ = [
    "SpiffeIdentityValidator",
    "SpiffeValidationResult",
]
