"""SPIFFE SAN extraction from X.509 certificates.

Constitutional Hash: cdd01ef066bc6cf2

Extracts spiffe:// URIs from certificate Subject Alternative Names
and validates them against ACGS-2's trust domain.

SPIFFE (Secure Production Identity Framework For Everyone) identities
are encoded as URI-type SANs in X.509 certificates.  ACGS-2 uses the
path convention::

    spiffe://<trust_domain>/tenant/<tenant_id>/agent/<agent_id>[/role/<maci_role>]
"""

import re
from dataclasses import dataclass

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.x509.oid import ExtensionOID

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Matches ACGS-2 SPIFFE paths:
#   /tenant/<tenant_id>/agent/<agent_id>[/role/<maci_role>]
_ACGS2_PATH_PATTERN = re.compile(
    r"^/tenant/(?P<tenant_id>[a-zA-Z0-9_-]+)"
    r"/agent/(?P<agent_id>[a-zA-Z0-9_-]+)"
    r"(?:/role/(?P<maci_role>[a-zA-Z0-9_-]+))?$"
)

# Default trust domains accepted by ACGS-2
DEFAULT_TRUST_DOMAINS: list[str] = ["acgs2.io", "acgs2"]


@dataclass(frozen=True)
class SpiffeId:
    """Parsed SPIFFE identity.

    Attributes:
        raw: The original ``spiffe://`` URI string.
        trust_domain: The trust domain portion (e.g. ``acgs2``).
        path: The workload path (e.g. ``/tenant/t1/agent/a1``).
        tenant_id: Extracted tenant ID (None if path does not match ACGS-2 convention).
        agent_id: Extracted agent ID (None if path does not match ACGS-2 convention).
        maci_role: Extracted MACI role (None if not present).
    """

    raw: str
    trust_domain: str
    path: str
    tenant_id: str | None = None
    agent_id: str | None = None
    maci_role: str | None = None


def parse_spiffe_id(uri: str) -> SpiffeId:
    """Parse a SPIFFE URI string into a SpiffeId.

    Args:
        uri: A URI starting with ``spiffe://``.

    Returns:
        Parsed SpiffeId with extracted components.

    Raises:
        ValueError: If the URI is not a valid SPIFFE ID.
    """
    if not uri or not uri.startswith("spiffe://"):
        raise ValueError(f"Invalid SPIFFE URI (must start with spiffe://): {uri!r}")

    # Strip the scheme
    remainder = uri[len("spiffe://") :]

    # Split trust domain and path
    slash_idx = remainder.find("/")
    if slash_idx == -1:
        trust_domain = remainder
        path = ""
    else:
        trust_domain = remainder[:slash_idx]
        path = remainder[slash_idx:]

    if not trust_domain:
        raise ValueError(f"SPIFFE URI has empty trust domain: {uri!r}")

    # Validate trust domain characters (RFC: lowercase letters, digits, dots, hyphens)
    if not re.fullmatch(r"[a-z0-9._-]+", trust_domain):
        raise ValueError(f"SPIFFE trust domain contains invalid characters: {trust_domain!r}")

    # Try to extract ACGS-2 path components
    tenant_id: str | None = None
    agent_id: str | None = None
    maci_role: str | None = None

    if path:
        match = _ACGS2_PATH_PATTERN.match(path)
        if match:
            tenant_id = match.group("tenant_id")
            agent_id = match.group("agent_id")
            maci_role = match.group("maci_role")

    return SpiffeId(
        raw=uri,
        trust_domain=trust_domain,
        path=path,
        tenant_id=tenant_id,
        agent_id=agent_id,
        maci_role=maci_role,
    )


def extract_spiffe_ids_from_cert(cert_pem: str | bytes) -> list[SpiffeId]:
    """Extract all SPIFFE IDs from a PEM-encoded X.509 certificate's SANs.

    Looks for URI-type Subject Alternative Names that start with ``spiffe://``
    and parses each into a SpiffeId.

    Args:
        cert_pem: PEM-encoded certificate (str or bytes).

    Returns:
        List of parsed SpiffeId objects found in the certificate.
        Empty list if no SPIFFE SANs are present or the cert has no SANs.

    Raises:
        ValueError: If the certificate cannot be parsed.
    """
    if isinstance(cert_pem, str):
        cert_pem = cert_pem.encode("utf-8")

    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
    except (ValueError, UnsupportedAlgorithm) as exc:
        # Also try DER format
        try:
            cert = x509.load_der_x509_certificate(cert_pem)
        except (ValueError, UnsupportedAlgorithm):
            raise ValueError(f"Failed to parse certificate (tried PEM and DER): {exc}") from exc

    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except x509.ExtensionNotFound:
        logger.debug(
            "Certificate has no Subject Alternative Name extension",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return []

    san_value = san_ext.value
    spiffe_ids: list[SpiffeId] = []

    for general_name in san_value:
        if isinstance(general_name, x509.UniformResourceIdentifier):
            uri = general_name.value
            if uri.startswith("spiffe://"):
                try:
                    spiffe_id = parse_spiffe_id(uri)
                    spiffe_ids.append(spiffe_id)
                    logger.debug(
                        "Extracted SPIFFE ID from certificate SAN",
                        spiffe_id=uri,
                        trust_domain=spiffe_id.trust_domain,
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )
                except ValueError as exc:
                    logger.warning(
                        "Skipping malformed SPIFFE URI in certificate SAN",
                        uri=uri,
                        error=str(exc),
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )

    return spiffe_ids


def validate_spiffe_trust_domain(
    spiffe_id: SpiffeId,
    allowed_domains: list[str] | None = None,
) -> bool:
    """Check whether a SPIFFE ID belongs to an allowed trust domain.

    Args:
        spiffe_id: The parsed SPIFFE identity.
        allowed_domains: Trust domains to accept.  Defaults to
            ``["acgs2.io", "acgs2"]``.

    Returns:
        True if the SPIFFE ID's trust domain is in the allowed list.
    """
    domains = allowed_domains if allowed_domains is not None else DEFAULT_TRUST_DOMAINS
    is_valid = spiffe_id.trust_domain in domains

    if not is_valid:
        logger.warning(
            "SPIFFE trust domain not in allowed list",
            trust_domain=spiffe_id.trust_domain,
            allowed_domains=domains,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    return is_valid


__all__ = [
    "DEFAULT_TRUST_DOMAINS",
    "SpiffeId",
    "extract_spiffe_ids_from_cert",
    "parse_spiffe_id",
    "validate_spiffe_trust_domain",
]
