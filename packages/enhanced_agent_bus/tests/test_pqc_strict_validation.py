"""
ACGS-2 Enhanced Agent Bus - PQC Strict Validation Tests
Constitutional Hash: 608508a9bd224290

Tests for check_enforcement_for_create() and check_enforcement_for_update()
enforcement gates in pqc_validators.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("src.core.services.policy_registry.app.services.pqc_algorithm_registry")

from unittest.mock import AsyncMock

import pytest

try:
    from enhanced_agent_bus.pqc_validators import (
        SUPPORTED_PQC_ALGORITHMS,
        check_enforcement_for_create,
        check_enforcement_for_update,
    )
except ImportError:
    from pqc_validators import (  # type: ignore[no-redef]
        SUPPORTED_PQC_ALGORITHMS,
        check_enforcement_for_create,
        check_enforcement_for_update,
    )

try:
    from enhanced_agent_bus._compat.security.pqc import (
        ClassicalKeyRejectedError,
        MigrationRequiredError,
        PQCKeyRequiredError,
        UnsupportedPQCAlgorithmError,
    )
except ImportError:
    pytest.skip("PQC error classes not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _config_mock(mode: str = "strict") -> AsyncMock:
    """Return a mock EnforcementModeConfigService with configurable mode."""
    svc = AsyncMock()
    svc.get_mode.return_value = mode
    return svc


# ---------------------------------------------------------------------------
# check_enforcement_for_create() — strict mode
# ---------------------------------------------------------------------------


async def test_create_classical_key_strict_raises_classical_key_rejected():
    """Classical key under strict mode raises ClassicalKeyRejectedError."""
    config = _config_mock("strict")
    with pytest.raises(ClassicalKeyRejectedError):
        await check_enforcement_for_create(
            key_type="classical",
            key_algorithm="RSA-2048",
            enforcement_config=config,
        )


async def test_create_no_key_strict_raises_pqc_key_required():
    """No key provided under strict mode raises PQCKeyRequiredError."""
    config = _config_mock("strict")
    with pytest.raises(PQCKeyRequiredError):
        await check_enforcement_for_create(
            key_type=None,
            key_algorithm=None,
            enforcement_config=config,
        )


async def test_create_unsupported_pqc_algorithm_raises():
    """Unsupported PQC algorithm raises UnsupportedPQCAlgorithmError."""
    config = _config_mock("strict")
    with pytest.raises(UnsupportedPQCAlgorithmError) as exc_info:
        await check_enforcement_for_create(
            key_type="pqc",
            key_algorithm="SPHINCS+-SHA2-128f",
            enforcement_config=config,
        )
    assert exc_info.value.supported_algorithms


async def test_create_valid_ml_dsa_65_strict_succeeds():
    """Valid ML-DSA-65 key under strict mode succeeds (no exception)."""
    config = _config_mock("strict")
    # Should not raise
    await check_enforcement_for_create(
        key_type="pqc",
        key_algorithm="ML-DSA-65",
        enforcement_config=config,
    )
    config.get_mode.assert_awaited_once()


async def test_create_valid_ml_kem_768_strict_succeeds():
    """Valid ML-KEM-768 key under strict mode succeeds."""
    config = _config_mock("strict")
    await check_enforcement_for_create(
        key_type="pqc",
        key_algorithm="ML-KEM-768",
        enforcement_config=config,
    )


# ---------------------------------------------------------------------------
# check_enforcement_for_create() — permissive mode
# ---------------------------------------------------------------------------


async def test_create_classical_key_permissive_succeeds():
    """Classical key under permissive mode succeeds."""
    config = _config_mock("permissive")
    await check_enforcement_for_create(
        key_type="classical",
        key_algorithm="RSA-2048",
        enforcement_config=config,
    )


async def test_create_no_key_permissive_succeeds():
    """No key under permissive mode succeeds."""
    config = _config_mock("permissive")
    await check_enforcement_for_create(
        key_type=None,
        key_algorithm=None,
        enforcement_config=config,
    )


# ---------------------------------------------------------------------------
# check_enforcement_for_update() — strict mode
# ---------------------------------------------------------------------------


async def test_update_classical_key_strict_raises_migration_required():
    """Updating existing classical-key record under strict mode raises MigrationRequiredError."""
    config = _config_mock("strict")
    with pytest.raises(MigrationRequiredError):
        await check_enforcement_for_update(
            existing_key_type="classical",
            enforcement_config=config,
        )


async def test_update_classical_key_strict_migration_context_bypasses():
    """migration_context=True bypasses strict gate for update operations."""
    config = _config_mock("strict")
    await check_enforcement_for_update(
        existing_key_type="classical",
        enforcement_config=config,
        migration_context=True,
    )


async def test_update_pqc_key_strict_succeeds():
    """Updating PQC-key record under strict mode succeeds."""
    config = _config_mock("strict")
    await check_enforcement_for_update(
        existing_key_type="pqc",
        enforcement_config=config,
    )


# ---------------------------------------------------------------------------
# Read path — no enforcement check needed
# ---------------------------------------------------------------------------


async def test_read_path_no_enforcement_check():
    """Read/verify path does not call enforcement. This is a design-level test:
    the absence of check_enforcement_for_read() in the module API is the assertion."""
    try:
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_read
    except ImportError:
        try:
            from pqc_validators import check_enforcement_for_read  # type: ignore[no-redef]
        except ImportError:
            check_enforcement_for_read = None  # type: ignore[assignment]

    assert check_enforcement_for_read is None, (
        "check_enforcement_for_read should NOT exist — reads are always allowed"
    )


# ---------------------------------------------------------------------------
# SUPPORTED_PQC_ALGORITHMS constant
# ---------------------------------------------------------------------------


def test_supported_pqc_algorithms_includes_nist_families():
    """SUPPORTED_PQC_ALGORITHMS includes ML-DSA and ML-KEM families."""
    assert any("ML-DSA" in alg for alg in SUPPORTED_PQC_ALGORITHMS)
    assert any("ML-KEM" in alg for alg in SUPPORTED_PQC_ALGORITHMS)
