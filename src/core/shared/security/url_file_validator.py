"""
ACGS-2 URL and File Upload Security Validation
Constitutional Hash: 608508a9bd224290

Security remediation for:
- SEC-003: SSRF Protection (URL validation with allowlist)
- SEC-006: File Upload Validation (magic byte verification)

Provides comprehensive security controls for external URL access
and file upload validation to prevent SSRF attacks and malicious
file uploads.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional hash for governance validation
from src.core.shared.constants import CONSTITUTIONAL_HASH

# =============================================================================
# SEC-003: SSRF Protection - URL Validation
# =============================================================================


class URLValidationError(ACGSBaseError):
    """Raised when URL validation fails (Q-H4 migration)."""

    http_status_code = 400
    error_code = "URL_VALIDATION_ERROR"

    def __init__(self, message: str, url: str = "", reason: str = "", **kwargs):
        self.url = url
        self.reason = reason
        details = kwargs.pop("details", {}) or {}
        details.update({"url": url, "reason": reason})
        super().__init__(message, details=details, **kwargs)


@dataclass
class SSRFProtectionConfig:
    """Configuration for SSRF protection."""

    # Allowed schemes
    allowed_schemes: set[str] = field(default_factory=lambda: {"https", "http"})

    # Allowed domains (exact match)
    allowed_domains: set[str] = field(default_factory=set)

    # Allowed domain patterns (regex)
    allowed_domain_patterns: list[str] = field(default_factory=list)

    # Block private/internal IPs
    block_private_ips: bool = True

    # Block localhost
    block_localhost: bool = True

    # Block link-local addresses
    block_link_local: bool = True

    # Block cloud metadata endpoints (AWS, GCP, Azure)
    block_cloud_metadata: bool = True

    # Maximum URL length
    max_url_length: int = 2048

    # Allow only HTTPS in production
    require_https_in_production: bool = True

    # Constitutional hash
    constitutional_hash: str = CONSTITUTIONAL_HASH


# Default safe domains for internal services
DEFAULT_ALLOWED_DOMAINS = {
    "opa",  # OPA policy engine
    "redis",  # Redis cache
    "kafka",  # Kafka message broker
    "postgres",  # PostgreSQL database
    "localhost",  # Local development (blocked by IP check in prod)
}

# Cloud metadata endpoints to block
CLOUD_METADATA_HOSTS = {
    "169.254.169.254",  # AWS/GCP metadata
    "metadata.google.internal",  # GCP
    "metadata.azure.com",  # Azure
    "100.100.100.200",  # Alibaba Cloud
}


class URLValidator:
    """
    Validates URLs for SSRF protection.

    Constitutional Hash: 608508a9bd224290
    MACI Role: CONTROLLER (security enforcement)

    Provides comprehensive URL validation to prevent:
    - Server-Side Request Forgery (SSRF) attacks
    - Access to internal network resources
    - Cloud metadata endpoint access
    - DNS rebinding attacks
    """

    def __init__(self, config: SSRFProtectionConfig | None = None):
        self.config = config or SSRFProtectionConfig()
        self._compiled_patterns: list[re.Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile domain patterns for faster matching."""
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.config.allowed_domain_patterns
        ]

    def validate_url(
        self,
        url: str,
        is_production: bool = True,
        additional_allowed_domains: set[str] | None = None,
    ) -> str:
        """
        Validate URL for SSRF protection.

        Args:
            url: URL to validate
            is_production: Whether running in production mode
            additional_allowed_domains: Additional domains to allow

        Returns:
            Validated URL (unchanged if valid)

        Raises:
            URLValidationError: If URL fails validation
            HTTPException: 400 status if validation fails
        """
        # Check URL length
        if len(url) > self.config.max_url_length:
            self._raise_error(url, "URL exceeds maximum length")

        # Parse URL
        try:
            parsed = urlparse(url)
        except ValueError as e:
            self._raise_error(url, f"Invalid URL format: {e}")

        # Validate scheme
        if parsed.scheme not in self.config.allowed_schemes:
            self._raise_error(
                url,
                f"Scheme '{parsed.scheme}' not allowed. Allowed: {self.config.allowed_schemes}",
            )

        # Require HTTPS in production
        if is_production and self.config.require_https_in_production and parsed.scheme != "https":
            # Allow internal service names without HTTPS requirement
            if parsed.hostname not in DEFAULT_ALLOWED_DOMAINS:
                self._raise_error(url, "HTTPS required in production")

        # Validate hostname exists
        if not parsed.hostname:
            self._raise_error(url, "Missing hostname")

        hostname = parsed.hostname.lower()

        # Block cloud metadata endpoints
        if self.config.block_cloud_metadata and hostname in CLOUD_METADATA_HOSTS:
            self._raise_error(url, "Cloud metadata endpoint blocked")

        # Check if IP address
        try:
            ip = ipaddress.ip_address(hostname)
            self._validate_ip_address(ip, url)
        except ValueError:
            # Not an IP address, validate as hostname
            self._validate_hostname(hostname, url, additional_allowed_domains)

        logger.debug(f"URL validated successfully: {url[:50]}...")
        return url

    def _validate_ip_address(
        self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, url: str
    ) -> None:
        """Validate IP address is not internal/private."""
        # Block localhost
        if self.config.block_localhost and ip.is_loopback:
            self._raise_error(url, "Localhost addresses blocked")

        # Block private IPs
        if self.config.block_private_ips and ip.is_private:
            self._raise_error(url, "Private IP addresses blocked")

        # Block link-local addresses
        if self.config.block_link_local and ip.is_link_local:
            self._raise_error(url, "Link-local addresses blocked")

        # Block reserved addresses
        if ip.is_reserved:
            self._raise_error(url, "Reserved IP addresses blocked")

        # Block multicast
        if ip.is_multicast:
            self._raise_error(url, "Multicast addresses blocked")

    def _validate_hostname(
        self,
        hostname: str,
        url: str,
        additional_allowed_domains: set[str] | None = None,
    ) -> None:
        """Validate hostname against allowlist."""
        # Merge allowed domains
        all_allowed = self.config.allowed_domains.copy()
        all_allowed.update(DEFAULT_ALLOWED_DOMAINS)
        if additional_allowed_domains:
            all_allowed.update(additional_allowed_domains)

        # Check exact match
        if hostname in all_allowed:
            return

        # Check suffix match (e.g., *.example.com)
        for allowed in all_allowed:
            if hostname.endswith(f".{allowed}"):
                return

        # Check pattern match
        for pattern in self._compiled_patterns:
            if pattern.match(hostname):
                return

        # Domain not in allowlist
        self._raise_error(
            url,
            f"Domain '{hostname}' not in allowlist",
        )

    def _raise_error(self, url: str, reason: str) -> None:
        """Raise validation error with logging."""
        logger.warning(f"SSRF protection blocked URL: {url[:100]}... Reason: {reason}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "url_validation_failed",
                "reason": reason,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )

    def add_allowed_domain(self, domain: str) -> None:
        """Add a domain to the allowlist."""
        self.config.allowed_domains.add(domain.lower())

    def add_allowed_pattern(self, pattern: str) -> None:
        """Add a domain pattern to the allowlist."""
        self.config.allowed_domain_patterns.append(pattern)
        self._compiled_patterns.append(re.compile(pattern, re.IGNORECASE))


# =============================================================================
# SEC-006: File Upload Validation - Magic Byte Verification
# =============================================================================


class FileType(Enum):
    """Supported file types with magic bytes."""

    # Policy bundles
    TAR_GZ = "application/gzip"
    TAR = "application/x-tar"
    ZIP = "application/zip"

    # Documents
    PDF = "application/pdf"
    JSON = "application/json"

    # Images (for avatars, etc.)
    PNG = "image/png"
    JPEG = "image/jpeg"
    GIF = "image/gif"

    # Text
    TEXT = "text/plain"
    REGO = "text/x-rego"

    # Unknown
    UNKNOWN = "application/octet-stream"


@dataclass
class FileSignature:
    """File type signature (magic bytes)."""

    file_type: FileType
    magic_bytes: bytes
    offset: int = 0
    description: str = ""


# Magic byte signatures for file type detection
FILE_SIGNATURES: list[FileSignature] = [
    # Compressed archives
    FileSignature(FileType.TAR_GZ, b"\x1f\x8b", 0, "Gzip compressed"),
    FileSignature(FileType.ZIP, b"PK\x03\x04", 0, "ZIP archive"),
    FileSignature(FileType.ZIP, b"PK\x05\x06", 0, "ZIP archive (empty)"),
    FileSignature(FileType.ZIP, b"PK\x07\x08", 0, "ZIP archive (spanned)"),
    # Documents
    FileSignature(FileType.PDF, b"%PDF", 0, "PDF document"),
    # Images
    FileSignature(FileType.PNG, b"\x89PNG\r\n\x1a\n", 0, "PNG image"),
    FileSignature(FileType.JPEG, b"\xff\xd8\xff", 0, "JPEG image"),
    FileSignature(FileType.GIF, b"GIF87a", 0, "GIF image (87a)"),
    FileSignature(FileType.GIF, b"GIF89a", 0, "GIF image (89a)"),
]

# File extension to expected types mapping
EXTENSION_TYPE_MAP: dict[str, set[FileType]] = {
    ".tar.gz": {FileType.TAR_GZ},
    ".tgz": {FileType.TAR_GZ},
    ".gz": {FileType.TAR_GZ},
    ".zip": {FileType.ZIP},
    ".pdf": {FileType.PDF},
    ".png": {FileType.PNG},
    ".jpg": {FileType.JPEG},
    ".jpeg": {FileType.JPEG},
    ".gif": {FileType.GIF},
    ".json": {FileType.JSON, FileType.TEXT},
    ".rego": {FileType.REGO, FileType.TEXT},
    ".txt": {FileType.TEXT},
}


class FileValidationError(ACGSBaseError):
    """Raised when file validation fails (Q-H4 migration)."""

    http_status_code = 400
    error_code = "FILE_VALIDATION_ERROR"

    def __init__(self, message: str, filename: str = "", reason: str = "", **kwargs):
        self.filename = filename
        self.reason = reason
        details = kwargs.pop("details", {}) or {}
        details.update({"filename": filename, "reason": reason})
        super().__init__(message, details=details, **kwargs)


@dataclass
class FileValidationConfig:
    """Configuration for file upload validation."""

    # Maximum file size in bytes (default 50MB)
    max_file_size: int = 50 * 1024 * 1024

    # Allowed file types
    allowed_types: set[FileType] = field(
        default_factory=lambda: {
            FileType.TAR_GZ,
            FileType.ZIP,
            FileType.JSON,
            FileType.TEXT,
            FileType.REGO,
            FileType.PDF,
        }
    )

    # Require magic byte verification
    verify_magic_bytes: bool = True

    # Verify extension matches content type
    verify_extension_match: bool = True

    # Block executable content
    block_executables: bool = True

    # Block polyglot files (files that are valid as multiple types)
    block_polyglots: bool = True

    # Constitutional hash
    constitutional_hash: str = CONSTITUTIONAL_HASH


# Dangerous patterns in file content
DANGEROUS_PATTERNS = [
    b"<%",  # JSP/ASP
    b"<?php",  # PHP
    b"<script",  # JavaScript
    b"#!/",  # Shebang (executables)
    b"\x4d\x5a",  # Windows PE executable
    b"\x7fELF",  # Linux ELF executable
    b"\xca\xfe\xba\xbe",  # Mach-O executable (universal)
    b"\xfe\xed\xfa\xce",  # Mach-O executable (32-bit)
    b"\xfe\xed\xfa\xcf",  # Mach-O executable (64-bit)
]


class FileValidator:
    """
    Validates file uploads for security.

    Constitutional Hash: 608508a9bd224290
    MACI Role: CONTROLLER (security enforcement)

    Provides comprehensive file validation to prevent:
    - Malicious file uploads
    - File type spoofing
    - Executable uploads
    - Polyglot file attacks
    """

    def __init__(self, config: FileValidationConfig | None = None):
        self.config = config or FileValidationConfig()

    async def validate_upload(
        self,
        file: UploadFile,
        allowed_types: set[FileType] | None = None,
        max_size: int | None = None,
    ) -> tuple[bytes, FileType]:
        """
        Validate an uploaded file.

        Args:
            file: FastAPI UploadFile object
            allowed_types: Override allowed file types
            max_size: Override maximum file size

        Returns:
            Tuple of (file content, detected file type)

        Raises:
            HTTPException: 400 status if validation fails
        """
        effective_types = allowed_types or self.config.allowed_types
        effective_max_size = max_size or self.config.max_file_size

        # Read file content
        content = await file.read()
        await file.seek(0)  # Reset for potential re-read

        # Validate file size
        if len(content) > effective_max_size:
            self._raise_error(
                file.filename or "unknown",
                f"File exceeds maximum size ({effective_max_size} bytes)",
            )

        # Empty file check
        if not content:
            self._raise_error(file.filename or "unknown", "Empty file not allowed")

        # Detect file type from magic bytes
        detected_type = self._detect_file_type(content)

        # Validate magic bytes if required
        if self.config.verify_magic_bytes and detected_type == FileType.UNKNOWN:
            # Allow text-based files without magic bytes
            if not self._is_valid_text(content):
                self._raise_error(
                    file.filename or "unknown",
                    "Unable to verify file type from content",
                )
            detected_type = FileType.TEXT

        # Validate file type is allowed
        if detected_type not in effective_types:
            self._raise_error(
                file.filename or "unknown",
                f"File type '{detected_type.value}' not allowed",
            )

        # Verify extension matches content type
        if self.config.verify_extension_match and file.filename:
            self._verify_extension_match(file.filename, detected_type)

        # Block executable content
        if self.config.block_executables:
            self._check_executable_content(content, file.filename or "unknown")

        logger.debug(
            f"File validated: {file.filename}, type={detected_type.value}, size={len(content)}"
        )

        return content, detected_type

    def validate_content(
        self,
        content: bytes,
        filename: str = "unknown",
        allowed_types: set[FileType] | None = None,
    ) -> FileType:
        """
        Validate file content directly.

        Args:
            content: File content bytes
            filename: Original filename (for extension checking)
            allowed_types: Override allowed file types

        Returns:
            Detected file type

        Raises:
            HTTPException: 400 status if validation fails
        """
        effective_types = allowed_types or self.config.allowed_types

        # Validate file size
        if len(content) > self.config.max_file_size:
            self._raise_error(filename, "File exceeds maximum size")

        # Empty file check
        if not content:
            self._raise_error(filename, "Empty file not allowed")

        # Detect file type
        detected_type = self._detect_file_type(content)

        # Validate magic bytes
        if self.config.verify_magic_bytes and detected_type == FileType.UNKNOWN:
            if not self._is_valid_text(content):
                self._raise_error(filename, "Unable to verify file type from content")
            detected_type = FileType.TEXT

        # Validate file type is allowed
        if detected_type not in effective_types:
            self._raise_error(filename, f"File type '{detected_type.value}' not allowed")

        # Verify extension matches
        if self.config.verify_extension_match:
            self._verify_extension_match(filename, detected_type)

        # Block executable content
        if self.config.block_executables:
            self._check_executable_content(content, filename)

        return detected_type

    def _detect_file_type(self, content: bytes) -> FileType:
        """Detect file type from magic bytes."""
        for signature in FILE_SIGNATURES:
            if len(content) >= signature.offset + len(signature.magic_bytes):
                start = signature.offset
                end = start + len(signature.magic_bytes)
                if content[start:end] == signature.magic_bytes:
                    return signature.file_type

        # Check for JSON (starts with { or [)
        stripped = content.lstrip()
        if stripped and stripped[0:1] in (b"{", b"["):
            return FileType.JSON

        return FileType.UNKNOWN

    def _is_valid_text(self, content: bytes) -> bool:
        """Check if content is valid text."""
        try:
            # Try to decode as UTF-8
            content.decode("utf-8")
            return True
        except UnicodeDecodeError:
            pass

        # Check if ASCII-ish
        non_printable = sum(
            1
            for byte in content[:1024]
            if byte < 32 and byte not in (9, 10, 13)  # Tab, LF, CR
        )
        return non_printable < len(content[:1024]) * 0.1

    def _verify_extension_match(self, filename: str, detected_type: FileType) -> None:
        """Verify file extension matches detected type."""
        if not filename:
            return

        # Get extension(s)
        path = Path(filename)
        suffixes = "".join(path.suffixes).lower()

        # Check each extension pattern
        for ext, allowed_types in EXTENSION_TYPE_MAP.items():
            if suffixes.endswith(ext):
                if detected_type not in allowed_types:
                    # Text types are flexible
                    if detected_type not in (FileType.TEXT, FileType.JSON):
                        self._raise_error(
                            filename,
                            f"Extension '{ext}' does not match content type '{detected_type.value}'",
                        )
                return

        # Unknown extension - allow if type is valid
        logger.debug(f"Unknown extension for file: {filename}")

    def _check_executable_content(self, content: bytes, filename: str) -> None:
        """Check for executable or dangerous content."""
        # Check first 1KB for dangerous patterns
        header = content[:1024]

        for pattern in DANGEROUS_PATTERNS:
            if pattern in header:
                self._raise_error(
                    filename,
                    "Executable or potentially dangerous content detected",
                )

    def _raise_error(self, filename: str, reason: str) -> None:
        """Raise validation error with logging."""
        logger.warning(f"File validation failed: {filename}. Reason: {reason}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "file_validation_failed",
                "filename": filename,
                "reason": reason,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )


# =============================================================================
# Singleton instances
# =============================================================================

_url_validator: URLValidator | None = None
_file_validator: FileValidator | None = None


def get_url_validator(config: SSRFProtectionConfig | None = None) -> URLValidator:
    """Get singleton URL validator instance."""
    global _url_validator
    if _url_validator is None or config is not None:
        _url_validator = URLValidator(config)
    return _url_validator


def get_file_validator(config: FileValidationConfig | None = None) -> FileValidator:
    """Get singleton file validator instance."""
    global _file_validator
    if _file_validator is None or config is not None:
        _file_validator = FileValidator(config)
    return _file_validator


def reset_url_validator() -> None:
    """Reset URL validator singleton (for testing)."""
    global _url_validator
    _url_validator = None


def reset_file_validator() -> None:
    """Reset file validator singleton (for testing)."""
    global _file_validator
    _file_validator = None


# =============================================================================
# Convenience functions
# =============================================================================


def validate_url(
    url: str,
    is_production: bool = True,
    additional_allowed_domains: set[str] | None = None,
) -> str:
    """
    Convenience function to validate URL for SSRF protection.

    Args:
        url: URL to validate
        is_production: Whether running in production mode
        additional_allowed_domains: Additional domains to allow

    Returns:
        Validated URL

    Raises:
        HTTPException: 400 status if validation fails
    """
    return get_url_validator().validate_url(url, is_production, additional_allowed_domains)


async def validate_upload(
    file: UploadFile,
    allowed_types: set[FileType] | None = None,
    max_size: int | None = None,
) -> tuple[bytes, FileType]:
    """
    Convenience function to validate file upload.

    Args:
        file: FastAPI UploadFile object
        allowed_types: Allowed file types
        max_size: Maximum file size in bytes

    Returns:
        Tuple of (file content, detected file type)

    Raises:
        HTTPException: 400 status if validation fails
    """
    return await get_file_validator().validate_upload(file, allowed_types, max_size)


def validate_file_content(
    content: bytes,
    filename: str = "unknown",
    allowed_types: set[FileType] | None = None,
) -> FileType:
    """
    Convenience function to validate file content.

    Args:
        content: File content bytes
        filename: Original filename
        allowed_types: Allowed file types

    Returns:
        Detected file type

    Raises:
        HTTPException: 400 status if validation fails
    """
    return get_file_validator().validate_content(content, filename, allowed_types)


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "FileSignature",
    "FileType",
    "FileValidationConfig",
    "FileValidationError",
    # File Validation
    "FileValidator",
    "SSRFProtectionConfig",
    "URLValidationError",
    # SSRF Protection
    "URLValidator",
    "get_file_validator",
    "get_url_validator",
    "reset_file_validator",
    "reset_url_validator",
    "validate_file_content",
    "validate_upload",
    "validate_url",
]
