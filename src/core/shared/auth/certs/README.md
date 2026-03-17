# SAML SP Certificates

This directory contains the SAML Service Provider (SP) certificate and private key
used for signing SAML requests and decrypting SAML assertions.

## Files

- `sp.crt` - X.509 certificate (PEM format) - **DO NOT COMMIT (NOT IN REPO)**
- `sp.key` - RSA private key (PEM format, unencrypted) - **DO NOT COMMIT (NOT IN REPO)**
- `generate_certs.py` - Script to generate new certificates

## Generating Certificates

### Option 1: Using the Python script (Recommended)

```bash
# From repository root
cd src/core/shared/auth/certs
python generate_certs.py
```

### Option 2: Using OpenSSL

```bash
# From repository root
cd src/core/shared/auth/certs
openssl req -x509 -newkey rsa:2048 -keyout sp.key -out sp.crt \
    -days 3650 -nodes -subj '/CN=acgs2-saml-sp'
```

## Verification

Verify the certificate was generated correctly:

```bash
openssl x509 -in sp.crt -text -noout | grep 'Subject:'
# Expected output: Subject: CN = acgs2-saml-sp
```

## Security Notes

⚠️ **IMPORTANT**:

- **Never commit `sp.key` to version control**
- The files `sp.key` and `sp.crt` are **NOT included in this repository** and must be generated locally for development/testing.
- For production deployments:
  - Generate new certificates on deployment
  - Use certificates from your organization's PKI or a trusted CA
  - Store private keys in a secrets management system (Vault, AWS Secrets Manager, etc.)
  - Set `SAML_SP_KEY_FILE` and `SAML_SP_CERT_FILE` environment variables

## Certificate Requirements

Per the ACGS-2 specification:

- Minimum 2048-bit RSA key
- SHA-256 signature algorithm
- KeyUsage: digitalSignature, keyEncipherment, contentCommitment
- Valid for SAML request signing and assertion decryption

## IdP Configuration

When configuring your Identity Provider (Okta, Azure AD, etc.), you'll need to:

1. Upload `sp.crt` as the SP signing/encryption certificate
2. Configure the SP Entity ID (default: from `settings.sso.saml_entity_id`)
3. Set the Assertion Consumer Service URL: `https://your-domain/sso/saml/acs`
4. Set the Single Logout Service URL: `https://your-domain/sso/saml/sls`
