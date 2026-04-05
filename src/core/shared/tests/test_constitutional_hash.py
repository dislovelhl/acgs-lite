"""
Tests for Constitutional Hash Registry and Algorithm Agility Framework.

Constitutional Hash: 608508a9bd224290

Covers:
- HashVersion dataclass (to_canonical, is_valid, from_canonical)
- ConstitutionalHashRegistry (register, deprecate, retire, set_active, validate,
  matches_active, normalize, migrate, compute_hash)
- ValidationResult.to_dict
- Error classes (ConstitutionalHashError, HashVersionMismatchError,
  HashVersionDeprecatedError, HashVersionRetiredError)
- Module-level helpers (get_hash_registry, validate_constitutional_hash, etc.)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.core.shared.constitutional_hash import (
    LEGACY_CONSTITUTIONAL_HASH,
    ConstitutionalHashError,
    ConstitutionalHashRegistry,
    HashAlgorithm,
    HashStatus,
    HashVersion,
    HashVersionDeprecatedError,
    HashVersionMismatchError,
    HashVersionRetiredError,
    ValidationResult,
    get_active_constitutional_hash,
    get_active_hash_value,
    get_hash_registry,
    matches_active_constitutional_hash,
    normalize_constitutional_hash,
    validate_constitutional_hash,
)
from src.core.shared.errors.exceptions import (
    ConstitutionalViolationError,
    ResourceNotFoundError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)

# ---------------------------------------------------------------------------
# HashVersion tests
# ---------------------------------------------------------------------------


class TestHashVersion:
    """Tests for the HashVersion dataclass."""

    def test_to_canonical(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
        )
        assert hv.to_canonical() == "sha256:v1:abcd1234abcd1234"

    def test_is_valid_active(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
            status=HashStatus.ACTIVE,
        )
        assert hv.is_valid() is True

    def test_is_valid_deprecated_no_sunset(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
            status=HashStatus.DEPRECATED,
        )
        assert hv.is_valid() is True

    def test_is_valid_retired(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
            status=HashStatus.RETIRED,
        )
        assert hv.is_valid() is False

    def test_is_valid_sunset_future(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
            status=HashStatus.SUNSET,
            sunset_date=datetime.now(UTC) + timedelta(days=30),
        )
        assert hv.is_valid() is True

    def test_is_valid_sunset_past(self):
        hv = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd1234abcd1234",
            status=HashStatus.SUNSET,
            sunset_date=datetime.now(UTC) - timedelta(days=1),
        )
        assert hv.is_valid() is False

    def test_from_canonical_valid(self):
        hv = HashVersion.from_canonical("sha256:v1:abcd1234abcd1234")
        assert hv.algorithm == HashAlgorithm.SHA256
        assert hv.version == "v1"
        assert hv.hash_value == "abcd1234abcd1234"

    def test_from_canonical_invalid_format(self):
        with pytest.raises(ACGSValidationError):
            HashVersion.from_canonical("invalid")

    def test_from_canonical_too_many_parts(self):
        with pytest.raises(ACGSValidationError):
            HashVersion.from_canonical("a:b:c:d")

    def test_from_canonical_unknown_algorithm(self):
        with pytest.raises(ACGSValidationError):
            HashVersion.from_canonical("unknown_algo:v1:abcd1234")


# ---------------------------------------------------------------------------
# ConstitutionalHashRegistry tests
# ---------------------------------------------------------------------------


class TestConstitutionalHashRegistry:
    """Tests for the ConstitutionalHashRegistry."""

    def _fresh_registry(self) -> ConstitutionalHashRegistry:
        return ConstitutionalHashRegistry()

    def test_initial_version_registered(self):
        reg = self._fresh_registry()
        assert reg.active_version is not None
        assert reg.active_version.hash_value == LEGACY_CONSTITUTIONAL_HASH

    def test_active_hash_canonical(self):
        reg = self._fresh_registry()
        assert reg.active_hash == f"sha256:v1:{LEGACY_CONSTITUTIONAL_HASH}"

    def test_active_hash_value(self):
        reg = self._fresh_registry()
        assert reg.active_hash_value == LEGACY_CONSTITUTIONAL_HASH

    def test_register_version(self):
        reg = self._fresh_registry()
        hv = reg.register_version(
            algorithm=HashAlgorithm.SHA512,
            version="v2",
            hash_value="deadbeefdeadbeef",
            notes="test",
        )
        assert hv.algorithm == HashAlgorithm.SHA512
        assert hv.version == "v2"
        all_versions = reg.get_all_versions()
        assert len(all_versions) == 2

    def test_register_duplicate_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ACGSValidationError):
            reg.register_version(
                algorithm=HashAlgorithm.SHA256,
                version="v1",
                hash_value=LEGACY_CONSTITUTIONAL_HASH,
            )

    def test_deprecate_version(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        sunset = datetime.now(UTC) + timedelta(days=90)
        reg.deprecate_version(canonical, sunset_date=sunset, successor="sha512:v2:abc")
        version = reg._versions[canonical]
        assert version.status == HashStatus.DEPRECATED
        assert version.sunset_date == sunset
        assert version.successor_version == "sha512:v2:abc"

    def test_deprecate_unknown_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ResourceNotFoundError):
            reg.deprecate_version("sha256:v99:nonexistent")

    def test_deprecate_calls_hooks(self):
        reg = self._fresh_registry()
        hook = MagicMock()
        reg.register_deprecation_hook(hook)
        canonical = reg.active_hash
        reg.deprecate_version(canonical)
        hook.assert_called_once()
        assert hook.call_args[0][0].status == HashStatus.DEPRECATED

    def test_deprecate_hook_error_does_not_raise(self):
        reg = self._fresh_registry()
        hook = MagicMock(side_effect=RuntimeError("hook boom"))
        reg.register_deprecation_hook(hook)
        canonical = reg.active_hash
        # Should not raise
        reg.deprecate_version(canonical)

    def test_retire_version(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        reg.retire_version(canonical)
        assert reg._versions[canonical].status == HashStatus.RETIRED

    def test_retire_unknown_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ResourceNotFoundError):
            reg.retire_version("sha256:v99:nonexistent")

    def test_set_active_version(self):
        reg = self._fresh_registry()
        hv = reg.register_version(
            algorithm=HashAlgorithm.SHA512,
            version="v2",
            hash_value="deadbeefdeadbeef",
        )
        reg.set_active_version(hv.to_canonical())
        assert reg.active_hash_value == "deadbeefdeadbeef"

    def test_set_active_unknown_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ResourceNotFoundError):
            reg.set_active_version("sha256:v99:nonexistent")

    def test_set_active_invalid_raises(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        reg.retire_version(canonical)
        with pytest.raises(ConstitutionalViolationError):
            reg.set_active_version(canonical)

    # --- validate_hash ---

    def test_validate_canonical_active(self):
        reg = self._fresh_registry()
        result = reg.validate_hash(reg.active_hash)
        assert result.valid is True
        assert result.version is not None

    def test_validate_canonical_unknown(self):
        reg = self._fresh_registry()
        result = reg.validate_hash("sha256:v99:0000000000000000")
        assert result.valid is False
        assert "Unknown hash version" in result.error

    def test_validate_canonical_retired(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        reg.retire_version(canonical)
        result = reg.validate_hash(canonical)
        assert result.valid is False

    def test_validate_strict_deprecated(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        reg.deprecate_version(canonical)
        result = reg.validate_hash(canonical, strict=True)
        assert result.valid is False
        assert "deprecated" in result.error.lower()
        assert len(result.warnings) > 0

    def test_validate_deprecated_non_strict_warns(self):
        reg = self._fresh_registry()
        canonical = reg.active_hash
        sunset = datetime.now(UTC) + timedelta(days=30)
        reg.deprecate_version(canonical, sunset_date=sunset)
        result = reg.validate_hash(canonical, strict=False)
        assert result.valid is True
        assert len(result.warnings) > 0

    def test_validate_legacy_hash(self):
        reg = self._fresh_registry()
        result = reg.validate_hash(LEGACY_CONSTITUTIONAL_HASH, allow_legacy=True)
        assert result.valid is True
        assert len(result.warnings) > 0

    def test_validate_legacy_disallowed(self):
        reg = self._fresh_registry()
        result = reg.validate_hash(LEGACY_CONSTITUTIONAL_HASH, allow_legacy=False)
        assert result.valid is False

    def test_validate_unknown_legacy(self):
        reg = self._fresh_registry()
        result = reg.validate_hash("aaaaaaaaaaaaaaaa", allow_legacy=True)
        assert result.valid is False

    def test_validate_invalid_format(self):
        reg = self._fresh_registry()
        result = reg.validate_hash("not-a-hash!")
        assert result.valid is False
        assert "Invalid hash format" in result.error

    # --- matches_active ---

    def test_matches_active_canonical(self):
        reg = self._fresh_registry()
        assert reg.matches_active(reg.active_hash) is True

    def test_matches_active_legacy(self):
        reg = self._fresh_registry()
        assert reg.matches_active(LEGACY_CONSTITUTIONAL_HASH) is True

    def test_matches_active_wrong(self):
        reg = self._fresh_registry()
        assert reg.matches_active("aaaaaaaaaaaaaaaa") is False

    # --- normalize_hash ---

    def test_normalize_canonical(self):
        reg = self._fresh_registry()
        normalized = reg.normalize_hash(reg.active_hash)
        assert normalized == reg.active_hash

    def test_normalize_legacy(self):
        reg = self._fresh_registry()
        normalized = reg.normalize_hash(LEGACY_CONSTITUTIONAL_HASH)
        assert normalized == f"sha256:v1:{LEGACY_CONSTITUTIONAL_HASH}"

    def test_normalize_invalid_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ConstitutionalViolationError):
            reg.normalize_hash("bad-format!")

    # --- migrate_hash ---

    def test_migrate_hash(self):
        reg = self._fresh_registry()
        new_hv = reg.register_version(
            algorithm=HashAlgorithm.SHA3_256,
            version="v2",
            hash_value="deadbeefdeadbeef",
        )
        result = reg.migrate_hash(reg.active_hash, new_hv.to_canonical())
        assert result == "sha3-256:v2:deadbeefdeadbeef"

    def test_migrate_invalid_old_hash_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ConstitutionalViolationError):
            reg.migrate_hash("bad!", "sha256:v1:x")

    def test_migrate_unknown_target_raises(self):
        reg = self._fresh_registry()
        with pytest.raises(ResourceNotFoundError):
            reg.migrate_hash(reg.active_hash, "sha512:v99:nonexistent")

    def test_migrate_invalid_target_raises(self):
        reg = self._fresh_registry()
        new_hv = reg.register_version(
            algorithm=HashAlgorithm.SHA512,
            version="v2",
            hash_value="deadbeefdeadbeef",
        )
        reg.retire_version(new_hv.to_canonical())
        with pytest.raises(ConstitutionalViolationError):
            reg.migrate_hash(reg.active_hash, new_hv.to_canonical())

    # --- get_valid_versions ---

    def test_get_valid_versions(self):
        reg = self._fresh_registry()
        valid = reg.get_valid_versions()
        assert len(valid) >= 1
        assert all(v.is_valid() for v in valid)

    # --- compute_hash ---

    def test_compute_hash_sha256(self):
        reg = self._fresh_registry()
        result = reg.compute_hash(b"hello", HashAlgorithm.SHA256)
        assert len(result) == 64  # sha256 hex length

    def test_compute_hash_sha3_256(self):
        reg = self._fresh_registry()
        result = reg.compute_hash(b"hello", HashAlgorithm.SHA3_256)
        assert len(result) == 64

    def test_compute_hash_blake2b(self):
        reg = self._fresh_registry()
        result = reg.compute_hash(b"hello", HashAlgorithm.BLAKE2B)
        assert len(result) > 0

    def test_compute_hash_blake2s(self):
        reg = self._fresh_registry()
        result = reg.compute_hash(b"hello", HashAlgorithm.BLAKE2S)
        assert len(result) > 0

    def test_compute_hash_unsupported_algorithm(self):
        reg = self._fresh_registry()
        with pytest.raises(ACGSValidationError):
            reg.compute_hash(b"hello", HashAlgorithm.SPHINCS_256)


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_to_dict_valid(self):
        vr = ValidationResult()
        vr.valid = True
        vr.version = HashVersion(
            algorithm=HashAlgorithm.SHA256,
            version="v1",
            hash_value="abcd",
        )
        d = vr.to_dict()
        assert d["valid"] is True
        assert d["version"] == "sha256:v1:abcd"
        assert d["error"] is None
        assert d["warnings"] == []

    def test_to_dict_invalid(self):
        vr = ValidationResult()
        vr.valid = False
        vr.error = "something wrong"
        d = vr.to_dict()
        assert d["valid"] is False
        assert d["version"] is None
        assert d["error"] == "something wrong"


# ---------------------------------------------------------------------------
# Error classes tests
# ---------------------------------------------------------------------------


class TestConstitutionalHashError:
    def test_basic_error(self):
        err = ConstitutionalHashError("test message", code="test_code", hash_value="abc")
        assert err.code == "test_code"
        assert err.hash_value == "abc"
        d = err.to_dict()
        assert d["hash_value"] == "abc"

    def test_error_without_hash(self):
        err = ConstitutionalHashError("msg")
        assert err.hash_value is None


class TestHashVersionMismatchError:
    def test_mismatch_error(self):
        err = HashVersionMismatchError(expected="v1", actual="v2")
        assert err.expected == "v1"
        assert err.actual == "v2"
        assert "mismatch" in str(err).lower()


class TestHashVersionDeprecatedError:
    def test_deprecated_with_sunset(self):
        sunset = datetime.now(UTC) + timedelta(days=30)
        err = HashVersionDeprecatedError(version="v1", sunset_date=sunset)
        assert err.sunset_date == sunset
        assert "deprecated" in str(err).lower()
        assert sunset.isoformat() in str(err)

    def test_deprecated_without_sunset(self):
        err = HashVersionDeprecatedError(version="v1")
        assert "deprecated" in str(err).lower()


class TestHashVersionRetiredError:
    def test_retired_error(self):
        err = HashVersionRetiredError(version="v1")
        assert "retired" in str(err).lower()


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    """Test the module-level convenience functions."""

    def test_get_hash_registry_returns_singleton(self):
        r1 = get_hash_registry()
        r2 = get_hash_registry()
        assert r1 is r2

    def test_validate_constitutional_hash(self):
        result = validate_constitutional_hash(LEGACY_CONSTITUTIONAL_HASH)
        assert result.valid is True

    def test_get_active_constitutional_hash(self):
        h = get_active_constitutional_hash()
        assert LEGACY_CONSTITUTIONAL_HASH in h

    def test_get_active_hash_value(self):
        v = get_active_hash_value()
        assert v == LEGACY_CONSTITUTIONAL_HASH

    def test_normalize_constitutional_hash(self):
        n = normalize_constitutional_hash(LEGACY_CONSTITUTIONAL_HASH)
        assert n == f"sha256:v1:{LEGACY_CONSTITUTIONAL_HASH}"

    def test_matches_active_constitutional_hash(self):
        assert matches_active_constitutional_hash(LEGACY_CONSTITUTIONAL_HASH) is True
        assert matches_active_constitutional_hash("aaaaaaaaaaaaaaaa") is False
