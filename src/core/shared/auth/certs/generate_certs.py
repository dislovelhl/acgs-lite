#!/usr/bin/env python3
"""
Constitutional Hash: 608508a9bd224290

Generate SAML SP certificate and private key for ACGS-2.

This script generates a self-signed X.509 certificate and RSA private key
for use as a SAML Service Provider (SP) certificate.

Usage:
    python generate_certs.py

Output:
    - sp.crt: Self-signed X.509 certificate (PEM format)
    - sp.key: RSA private key (PEM format, unencrypted)

Security Notes:
    - These certificates are for development/testing only
    - For production, use certificates from a trusted CA or proper PKI
    - Never commit sp.key to version control in production
    - The private key is unencrypted for ease of use with PySAML2
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    sys.exit(1)


def generate_saml_sp_certificate(
    common_name: str = "acgs2-saml-sp",
    key_size: int = 2048,
    validity_days: int = 3650,
    output_dir: str | None = None,
) -> tuple[bytes, bytes]:
    """
    Generate a self-signed certificate and private key for SAML SP.

    Args:
        common_name: The CN (Common Name) for the certificate
        key_size: RSA key size in bits (minimum 2048 as per spec)
        validity_days: Certificate validity period in days
        output_dir: Directory to write files (None = current directory)

    Returns:
        Tuple of (certificate_pem, private_key_pem)
    """
    # Generate RSA private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    # Build certificate subject and issuer (self-signed)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    # Build the certificate
    now = datetime.now(UTC)
    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=validity_days))
    )

    # Add extensions for SAML SP use
    cert_builder = cert_builder.add_extension(
        x509.BasicConstraints(ca=False, path_length=None),
        critical=True,
    )

    cert_builder = cert_builder.add_extension(
        x509.KeyUsage(
            digital_signature=True,
            key_encipherment=True,
            content_commitment=True,  # For XML signing
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )

    # Sign the certificate with its own private key (self-signed)
    certificate = cert_builder.sign(private_key, hashes.SHA256())

    # Serialize to PEM format
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)

    # Write to files if output_dir specified
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        key_file = output_path / "sp.key"
        cert_file = output_path / "sp.crt"

        # Write private key with restricted permissions
        key_file.write_bytes(private_key_pem)
        os.chmod(key_file, 0o600)  # Owner read/write only

        # Write certificate
        cert_file.write_bytes(certificate_pem)
        os.chmod(cert_file, 0o644)  # Owner read/write, others read

    return certificate_pem, private_key_pem


if __name__ == "__main__":
    # Generate certificates in the same directory as this script
    script_dir = Path(__file__).parent
    generate_saml_sp_certificate(output_dir=script_dir)
