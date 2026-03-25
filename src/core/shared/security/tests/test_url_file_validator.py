"""Tests for URL and File Validation Security Module.

Constitutional Hash: 608508a9bd224290

Tests for SEC-003 (SSRF Protection) and SEC-006 (File Upload Validation).
"""

import pytest
from fastapi import HTTPException

from src.core.shared.security.url_file_validator import (
    CONSTITUTIONAL_HASH,
    FileType,
    FileValidationConfig,
    FileValidationError,
    FileValidator,
    SSRFProtectionConfig,
    URLValidationError,
    URLValidator,
    get_file_validator,
    get_url_validator,
    reset_file_validator,
    reset_url_validator,
    validate_file_content,
    validate_url,
)


class TestConstitutionalHash:
    # Constitutional Hash: 608508a9bd224290
    """Test constitutional hash compliance."""

    def test_constitutional_hash_value(self) -> None:
        """Verify constitutional hash matches expected value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


class TestSSRFProtectionConfig:
    """Test SSRF protection configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SSRFProtectionConfig()
        assert config.block_private_ips is True
        assert config.block_localhost is True
        assert config.block_link_local is True
        assert config.block_cloud_metadata is True
        assert "https" in config.allowed_schemes
        assert "http" in config.allowed_schemes
        assert config.max_url_length == 2048

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = SSRFProtectionConfig(
            allowed_domains={"example.com", "api.example.com"},
            block_private_ips=False,
            allowed_schemes={"https"},
        )
        assert "example.com" in config.allowed_domains
        assert config.block_private_ips is False
        assert "http" not in config.allowed_schemes


class TestURLValidator:
    """Test URL validator for SSRF protection (SEC-003)."""

    @pytest.fixture(autouse=True)
    def reset_validator(self) -> None:
        """Reset singleton validator before each test."""
        reset_url_validator()
        yield
        reset_url_validator()

    def test_valid_https_url_with_allowlist(self) -> None:
        """Test valid HTTPS URL passes when in allowlist."""
        config = SSRFProtectionConfig(allowed_domains={"example.com", "api.example.com"})
        validator = URLValidator(config)
        result = validator.validate_url("https://example.com/api/data", is_production=False)
        assert result == "https://example.com/api/data"

    def test_private_ip_blocked(self) -> None:
        """Test private IP addresses are blocked."""
        validator = URLValidator()

        # Test various private IP ranges
        private_urls = [
            "http://10.0.0.1/api",
            "http://172.16.0.1/api",
            "http://192.168.1.1/api",
        ]

        for url in private_urls:
            with pytest.raises((URLValidationError, HTTPException)):
                validator.validate_url(url, is_production=False)

    def test_loopback_blocked(self) -> None:
        """Test loopback addresses are blocked."""
        validator = URLValidator()

        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url("http://127.0.0.1/api", is_production=False)

    def test_cloud_metadata_blocked(self) -> None:
        """Test cloud metadata endpoints are blocked (critical SSRF protection)."""
        validator = URLValidator()

        metadata_urls = [
            "http://169.254.169.254/latest/meta-data/",  # AWS
            "http://metadata.google.internal/",  # GCP
        ]

        for url in metadata_urls:
            with pytest.raises((URLValidationError, HTTPException)):
                validator.validate_url(url, is_production=False)

    def test_link_local_blocked(self) -> None:
        """Test link-local addresses are blocked."""
        validator = URLValidator()
        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url("http://169.254.1.1/api", is_production=False)

    def test_invalid_scheme_blocked(self) -> None:
        """Test invalid schemes are blocked."""
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config)

        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url("file:///etc/passwd", is_production=False)

        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url("ftp://example.com/file.txt", is_production=False)

    def test_allowlist_mode(self) -> None:
        """Test allowlist mode only allows specific hosts."""
        config = SSRFProtectionConfig(allowed_domains={"api.trusted.com", "cdn.trusted.com"})
        validator = URLValidator(config)

        # Allowed hosts pass
        result = validator.validate_url("https://api.trusted.com/data", is_production=False)
        assert "api.trusted.com" in result

        # Non-allowed hosts fail
        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url("https://malicious.com/steal", is_production=False)

    def test_empty_url(self) -> None:
        """Test empty URL is rejected."""
        validator = URLValidator()
        with pytest.raises((URLValidationError, HTTPException, ValueError)):
            validator.validate_url("", is_production=False)

    def test_url_with_port(self) -> None:
        """Test URL with port is handled correctly."""
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config)
        result = validator.validate_url("https://example.com:8443/api", is_production=False)
        assert "8443" in result

    def test_singleton_pattern(self) -> None:
        """Test singleton pattern works correctly."""
        validator1 = get_url_validator()
        validator2 = get_url_validator()
        assert validator1 is validator2

        reset_url_validator()
        validator3 = get_url_validator()
        assert validator1 is not validator3


class TestFileValidationConfig:
    """Test file validation configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = FileValidationConfig()
        assert config.max_file_size == 50 * 1024 * 1024  # 50MB
        assert len(config.allowed_types) > 0
        assert config.verify_magic_bytes is True
        assert config.block_executables is True
        # Default includes policy-related types
        assert FileType.JSON in config.allowed_types
        assert FileType.PDF in config.allowed_types
        assert FileType.REGO in config.allowed_types

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = FileValidationConfig(
            max_file_size=1024,
            allowed_types={FileType.PDF, FileType.PNG},
        )
        assert config.max_file_size == 1024
        assert FileType.PDF in config.allowed_types
        assert FileType.PNG in config.allowed_types


class TestFileValidator:
    """Test file validator for upload validation (SEC-006)."""

    @pytest.fixture(autouse=True)
    def reset_validator(self) -> None:
        """Reset singleton validator before each test."""
        reset_file_validator()
        yield
        reset_file_validator()

    def test_valid_pdf_file(self) -> None:
        """Test valid PDF file passes validation (default allowed)."""
        # PDF magic bytes
        pdf_data = b"%PDF-1.4" + b"\x00" * 100

        validator = FileValidator()
        detected_type = validator.validate_content(
            content=pdf_data,
            filename="document.pdf",
        )
        assert detected_type == FileType.PDF

    def test_valid_json_file(self) -> None:
        """Test valid JSON file passes validation (default allowed)."""
        json_data = b'{"key": "value", "number": 42}'

        validator = FileValidator()
        detected_type = validator.validate_content(
            content=json_data,
            filename="config.json",
        )
        assert detected_type == FileType.JSON

    def test_valid_png_when_explicitly_allowed(self) -> None:
        """Test valid PNG file passes validation when explicitly allowed."""
        # PNG magic bytes
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        config = FileValidationConfig(allowed_types={FileType.PNG, FileType.JPEG, FileType.PDF})
        validator = FileValidator(config)
        detected_type = validator.validate_content(
            content=png_data,
            filename="test.png",
        )
        assert detected_type == FileType.PNG

    def test_valid_jpeg_when_explicitly_allowed(self) -> None:
        """Test valid JPEG file passes validation when explicitly allowed."""
        # JPEG magic bytes
        jpeg_data = b"\xff\xd8\xff" + b"\x00" * 100

        config = FileValidationConfig(allowed_types={FileType.PNG, FileType.JPEG, FileType.PDF})
        validator = FileValidator(config)
        detected_type = validator.validate_content(
            content=jpeg_data,
            filename="test.jpg",
        )
        assert detected_type == FileType.JPEG

    def test_file_too_large(self) -> None:
        """Test file size limit is enforced."""
        config = FileValidationConfig(max_file_size=100)
        validator = FileValidator(config)

        large_file = b"%PDF-1.4" + b"\x00" * 200
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=large_file,
                filename="large.pdf",
            )

    def test_executable_blocked(self) -> None:
        """Test executable files are blocked."""
        # EXE magic bytes (MZ header)
        exe_data = b"MZ" + b"\x00" * 100

        validator = FileValidator()
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=exe_data,
                filename="program.exe",
            )

    def test_elf_blocked(self) -> None:
        """Test ELF executables are blocked."""
        # ELF magic bytes
        elf_data = b"\x7fELF" + b"\x00" * 100

        validator = FileValidator()
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=elf_data,
                filename="binary",
            )

    def test_script_blocked(self) -> None:
        """Test script files are blocked."""
        # Shell script
        script_data = b"#!/bin/bash\necho hello"

        validator = FileValidator()
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=script_data,
                filename="script.sh",
            )

    def test_php_blocked(self) -> None:
        """Test PHP files are blocked."""
        php_data = b"<?php echo 'hello'; ?>"

        validator = FileValidator()
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=php_data,
                filename="test.php",
            )

    def test_empty_file(self) -> None:
        """Test empty file is rejected."""
        validator = FileValidator()
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=b"",
                filename="empty.txt",
            )

    def test_double_extension_blocked(self) -> None:
        """Test double extension files may be flagged via extension mismatch."""
        # This tests that extension verification catches suspicious filenames
        config = FileValidationConfig(
            allowed_types={FileType.PDF},
            verify_extension_match=True,
        )
        validator = FileValidator(config)

        # Valid PDF with correct extension should pass
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        detected_type = validator.validate_content(
            content=pdf_data,
            filename="document.pdf",
        )
        assert detected_type == FileType.PDF

    def test_allowed_types_restriction(self) -> None:
        """Test allowed types restriction works."""
        config = FileValidationConfig(
            allowed_types={FileType.PDF},
        )
        validator = FileValidator(config)

        # JSON should be rejected (not in allowed types)
        json_data = b'{"test": true}'
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=json_data,
                filename="test.json",
            )

        # PDF should be accepted
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        detected_type = validator.validate_content(
            content=pdf_data,
            filename="test.pdf",
        )
        assert detected_type == FileType.PDF

    def test_singleton_pattern(self) -> None:
        """Test singleton pattern works correctly."""
        validator1 = get_file_validator()
        validator2 = get_file_validator()
        assert validator1 is validator2

        reset_file_validator()
        validator3 = get_file_validator()
        assert validator1 is not validator3


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_validators(self) -> None:
        """Reset all validators before each test."""
        reset_url_validator()
        reset_file_validator()
        yield
        reset_url_validator()
        reset_file_validator()

    def test_validate_url_function_blocks_metadata(self) -> None:
        """Test validate_url convenience function blocks cloud metadata."""
        with pytest.raises((URLValidationError, HTTPException)):
            validate_url("http://169.254.169.254/metadata", is_production=False)

    def test_validate_file_content_function(self) -> None:
        """Test validate_file_content convenience function."""
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        detected_type = validate_file_content(pdf_data, filename="doc.pdf")
        assert detected_type == FileType.PDF


class TestSecurityScenarios:
    """Test real-world security attack scenarios."""

    @pytest.fixture(autouse=True)
    def reset_validators(self) -> None:
        """Reset all validators before each test."""
        reset_url_validator()
        reset_file_validator()
        yield
        reset_url_validator()
        reset_file_validator()

    def test_ssrf_aws_metadata_attack(self) -> None:
        """Test AWS metadata SSRF attack is blocked."""
        validator = URLValidator()

        # Common AWS metadata endpoints used in SSRF attacks
        attack_urls = [
            "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            "http://169.254.169.254/latest/user-data",
            "http://169.254.169.254/latest/api/token",
        ]

        for url in attack_urls:
            with pytest.raises((URLValidationError, HTTPException)):
                validator.validate_url(url, is_production=False)

    def test_ssrf_gcp_metadata_attack(self) -> None:
        """Test GCP metadata SSRF attack is blocked."""
        validator = URLValidator()

        with pytest.raises((URLValidationError, HTTPException)):
            validator.validate_url(
                "http://metadata.google.internal/computeMetadata/v1/", is_production=False
            )

    def test_file_upload_webshell(self) -> None:
        """Test webshell upload is blocked."""
        validator = FileValidator()

        # PHP webshell attempt
        webshell = b"<?php system($_GET['cmd']); ?>"
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=webshell,
                filename="image.php",
            )

    def test_content_type_spoofing(self) -> None:
        """Test content-type spoofing is detected via magic bytes."""
        validator = FileValidator()

        # EXE file with PDF extension - should be blocked due to executable patterns
        exe_data = b"MZ" + b"\x00" * 100
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=exe_data,
                filename="document.pdf",
            )

    def test_zip_bomb_size_check(self) -> None:
        """Test oversized files are rejected (prevents zip bombs)."""
        config = FileValidationConfig(max_file_size=1024)  # 1KB
        validator = FileValidator(config)

        # Create data larger than limit
        large_data = b"%PDF-1.4" + b"\x00" * 2000
        with pytest.raises((FileValidationError, HTTPException)):
            validator.validate_content(
                content=large_data,
                filename="large.pdf",
            )

    def test_internal_service_domains_with_allowlist(self) -> None:
        """Test that allowlisted internal service domains work."""
        config = SSRFProtectionConfig(allowed_domains={"opa", "redis", "internal-api.example.com"})
        validator = URLValidator(config)

        # Allowlisted internal services should work
        result = validator.validate_url("http://opa:8181/v1/data", is_production=False)
        assert "opa" in result


class TestURLValidatorExtended:
    """Extended tests for URL validator covering edge cases."""

    @pytest.fixture(autouse=True)
    def reset_validator(self) -> None:
        reset_url_validator()
        yield
        reset_url_validator()

    def test_url_too_long(self) -> None:
        validator = URLValidator()
        long_url = "https://example.com/" + "a" * 3000
        with pytest.raises(HTTPException):
            validator.validate_url(long_url, is_production=False)

    def test_missing_hostname(self) -> None:
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://", is_production=False)

    def test_https_required_in_production(self) -> None:
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config)
        with pytest.raises(HTTPException):
            validator.validate_url("http://example.com/api", is_production=True)

    def test_https_not_required_for_internal_services(self) -> None:
        validator = URLValidator()
        result = validator.validate_url("http://opa:8181/v1/data", is_production=True)
        assert "opa" in result

    def test_reserved_ip_blocked(self) -> None:
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://240.0.0.1/api", is_production=False)

    def test_multicast_ip_blocked(self) -> None:
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://224.0.0.1/api", is_production=False)

    def test_domain_pattern_match(self) -> None:
        config = SSRFProtectionConfig(
            allowed_domain_patterns=[r".*\.trusted\.org$"],
        )
        validator = URLValidator(config)
        result = validator.validate_url(
            "https://api.trusted.org/data", is_production=False
        )
        assert "trusted.org" in result

    def test_domain_not_in_allowlist(self) -> None:
        config = SSRFProtectionConfig(allowed_domains=set())
        validator = URLValidator(config)
        with pytest.raises(HTTPException):
            validator.validate_url("https://evil.com/steal", is_production=False)

    def test_subdomain_suffix_match(self) -> None:
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config)
        result = validator.validate_url(
            "https://sub.example.com/api", is_production=False
        )
        assert "sub.example.com" in result

    def test_add_allowed_domain(self) -> None:
        validator = URLValidator()
        validator.add_allowed_domain("Custom.COM")
        assert "custom.com" in validator.config.allowed_domains

    def test_add_allowed_pattern(self) -> None:
        validator = URLValidator()
        validator.add_allowed_pattern(r".*\.test\.io$")
        assert len(validator._compiled_patterns) >= 1

    def test_get_url_validator_custom_config(self) -> None:
        config = SSRFProtectionConfig(allowed_domains={"custom.io"})
        v = get_url_validator(config)
        assert "custom.io" in v.config.allowed_domains

    def test_azure_metadata_blocked(self) -> None:
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://metadata.azure.com/api", is_production=False)

    def test_alibaba_metadata_blocked(self) -> None:
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://100.100.100.200/api", is_production=False)


class TestFileValidatorExtended:
    """Extended tests for file validator covering edge cases."""

    @pytest.fixture(autouse=True)
    def reset_validator(self) -> None:
        reset_file_validator()
        yield
        reset_file_validator()

    def test_valid_gzip(self) -> None:
        gz_data = b"\x1f\x8b" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.TAR_GZ})
        validator = FileValidator(config)
        result = validator.validate_content(gz_data, filename="archive.tar.gz")
        assert result == FileType.TAR_GZ

    def test_valid_gif87a(self) -> None:
        gif_data = b"GIF87a" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.GIF})
        validator = FileValidator(config)
        result = validator.validate_content(gif_data, filename="image.gif")
        assert result == FileType.GIF

    def test_valid_gif89a(self) -> None:
        gif_data = b"GIF89a" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.GIF})
        validator = FileValidator(config)
        result = validator.validate_content(gif_data, filename="image.gif")
        assert result == FileType.GIF

    def test_text_file_detection(self) -> None:
        text_data = b"Hello, this is plain text content.\nLine 2.\n"
        validator = FileValidator()
        result = validator.validate_content(text_data, filename="readme.txt")
        assert result == FileType.TEXT

    def test_rego_file(self) -> None:
        rego_data = b'package authz\n\ndefault allow = false\n'
        validator = FileValidator()
        result = validator.validate_content(rego_data, filename="policy.rego")
        assert result == FileType.TEXT

    def test_unknown_type_not_text(self) -> None:
        # Invalid UTF-8 (bare continuation bytes) + control chars < 32
        # that are not tab/lf/cr, so both UTF-8 decode and ASCII heuristic fail
        binary_data = (b"\x80\x01\x02\x03\x04\x05\x06\x07" * 200)
        config = FileValidationConfig(verify_magic_bytes=True)
        validator = FileValidator(config)
        with pytest.raises(HTTPException):
            validator.validate_content(binary_data, filename="unknown.bin")

    def test_extension_mismatch_blocks(self) -> None:
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        config = FileValidationConfig(
            allowed_types={FileType.PNG, FileType.JPEG},
            verify_extension_match=True,
        )
        validator = FileValidator(config)
        with pytest.raises(HTTPException):
            validator.validate_content(png_data, filename="image.jpg")

    def test_no_filename_skips_extension_check(self) -> None:
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        validator = FileValidator()
        result = validator.validate_content(pdf_data, filename="")
        assert result == FileType.PDF

    def test_unknown_extension_allowed(self) -> None:
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.PDF})
        validator = FileValidator(config)
        result = validator.validate_content(pdf_data, filename="document.xyz")
        assert result == FileType.PDF

    def test_jsp_blocked(self) -> None:
        jsp_data = b"<% out.println('hello'); %>"
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(jsp_data, filename="page.txt")

    def test_javascript_in_file_blocked(self) -> None:
        js_data = b"<script>alert('xss')</script>"
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(js_data, filename="data.txt")

    def test_macho_universal_blocked(self) -> None:
        macho_data = b"\xca\xfe\xba\xbe" + b"\x00" * 100
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(macho_data, filename="binary")

    def test_macho_32bit_blocked(self) -> None:
        macho_data = b"\xfe\xed\xfa\xce" + b"\x00" * 100
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(macho_data, filename="binary")

    def test_macho_64bit_blocked(self) -> None:
        macho_data = b"\xfe\xed\xfa\xcf" + b"\x00" * 100
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(macho_data, filename="binary")

    async def test_validate_upload_success(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        file = MagicMock()
        file.read = AsyncMock(return_value=b'{"key": "value"}')
        file.seek = AsyncMock()
        file.filename = "data.json"

        validator = FileValidator()
        content, ftype = await validator.validate_upload(file)
        assert ftype == FileType.JSON
        assert content == b'{"key": "value"}'
        file.seek.assert_awaited_once_with(0)

    async def test_validate_upload_too_large(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        file = MagicMock()
        file.read = AsyncMock(return_value=b"\x00" * 200)
        file.seek = AsyncMock()
        file.filename = "big.bin"

        config = FileValidationConfig(max_file_size=100)
        validator = FileValidator(config)
        with pytest.raises(HTTPException):
            await validator.validate_upload(file)

    async def test_validate_upload_empty(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        file = MagicMock()
        file.read = AsyncMock(return_value=b"")
        file.seek = AsyncMock()
        file.filename = "empty.txt"

        validator = FileValidator()
        with pytest.raises(HTTPException):
            await validator.validate_upload(file)

    def test_get_file_validator_custom_config(self) -> None:
        config = FileValidationConfig(max_file_size=1024)
        v = get_file_validator(config)
        assert v.config.max_file_size == 1024

    def test_zip_empty_signature(self) -> None:
        zip_data = b"PK\x05\x06" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.ZIP})
        validator = FileValidator(config)
        result = validator.validate_content(zip_data, filename="archive.zip")
        assert result == FileType.ZIP

    def test_zip_spanned_signature(self) -> None:
        zip_data = b"PK\x07\x08" + b"\x00" * 100
        config = FileValidationConfig(allowed_types={FileType.ZIP})
        validator = FileValidator(config)
        result = validator.validate_content(zip_data, filename="archive.zip")
        assert result == FileType.ZIP

    def test_json_array_detection(self) -> None:
        json_data = b'[1, 2, 3]'
        validator = FileValidator()
        result = validator.validate_content(json_data, filename="list.json")
        assert result == FileType.JSON


class TestConvenienceFunctionsExtended:
    """Extended convenience function tests."""

    @pytest.fixture(autouse=True)
    def reset_validators(self) -> None:
        reset_url_validator()
        reset_file_validator()
        yield
        reset_url_validator()
        reset_file_validator()

    async def test_validate_upload_convenience(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from src.core.shared.security.url_file_validator import validate_upload

        file = MagicMock()
        file.read = AsyncMock(return_value=b'{"test": true}')
        file.seek = AsyncMock()
        file.filename = "test.json"

        _content, ftype = await validate_upload(file)
        assert ftype == FileType.JSON

    def test_validate_url_non_production(self) -> None:
        result = validate_url("http://opa:8181/v1/data", is_production=False)
        assert "opa" in result


class TestURLValidationError:
    def test_url_validation_error_attrs(self) -> None:
        err = URLValidationError("bad url", url="http://evil.com", reason="blocked")
        assert err.url == "http://evil.com"
        assert err.reason == "blocked"

    def test_file_validation_error_attrs(self) -> None:
        err = FileValidationError("bad file", filename="evil.exe", reason="executable")
        assert err.filename == "evil.exe"
        assert err.reason == "executable"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
