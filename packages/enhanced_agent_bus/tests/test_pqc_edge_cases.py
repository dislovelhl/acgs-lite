"""
ACGS-2 Enhanced Agent Bus - PQC Enforcement Edge Case Tests
Constitutional Hash: 608508a9bd224290

Tests for race conditions, config unavailability, delete/recreate,
and migration context bypass scenarios.
"""

from __future__ import annotations

import pytest

pytest.importorskip("src.core.services.policy_registry")

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
        UnsupportedPQCAlgorithmError,
    )
except ImportError:
    pytest.skip("PQC error classes not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _config_mock(mode: str = "strict") -> AsyncMock:
    svc = AsyncMock()
    svc.get_mode.return_value = mode
    return svc


# ---------------------------------------------------------------------------
# Config unavailability → defaults to strict (fail-safe)
# ---------------------------------------------------------------------------


async def test_config_failure_defaults_to_strict_rejects_classical():
    """When get_mode() raises, enforcement defaults to strict and rejects classical key."""
    config = AsyncMock()
    config.get_mode.side_effect = OSError("Redis/PG both down")

    with pytest.raises(ClassicalKeyRejectedError):
        await check_enforcement_for_create(
            key_type="classical",
            key_algorithm="RSA-2048",
            enforcement_config=config,
        )


# ---------------------------------------------------------------------------
# Mode change mid-operation — uses mode at processing time
# ---------------------------------------------------------------------------


async def test_mode_change_uses_value_at_processing_time():
    """Enforcement uses the mode value returned at the time of the check,
    not a cached value. Simulated by returning 'permissive' from get_mode()."""
    config = _config_mock("permissive")

    # Classical key should be accepted under permissive
    await check_enforcement_for_create(
        key_type="classical",
        key_algorithm="RSA-2048",
        enforcement_config=config,
    )
    config.get_mode.assert_awaited_once()


# ---------------------------------------------------------------------------
# DELETE operations — key-type agnostic
# ---------------------------------------------------------------------------


async def test_delete_classical_key_strict_succeeds():
    """DELETE operations do not enforce key-type checks.

    This is verified at the route level (T011). Here we verify that
    check_enforcement_for_update with a 'delete' context hint still works
    or that no special delete enforcement function exists.
    """
    # No enforcement function for delete exists — design decision verified
    try:
        from enhanced_agent_bus.pqc_validators import check_enforcement_for_delete
    except ImportError:
        try:
            from pqc_validators import check_enforcement_for_delete  # type: ignore[no-redef]
        except ImportError:
            check_enforcement_for_delete = None  # type: ignore[assignment]

    assert check_enforcement_for_delete is None, (
        "No delete enforcement should exist — deletes are key-type agnostic"
    )


# ---------------------------------------------------------------------------
# Recreate after delete — requires PQC key under strict
# ---------------------------------------------------------------------------


async def test_recreate_after_delete_requires_pqc_key():
    """Recreating a deleted record under strict mode requires PQC key (uses create path)."""
    config = _config_mock("strict")
    with pytest.raises(ClassicalKeyRejectedError):
        await check_enforcement_for_create(
            key_type="classical",
            key_algorithm="RSA-2048",
            enforcement_config=config,
        )


# ---------------------------------------------------------------------------
# Batch migration context — bypasses strict gate for create
# ---------------------------------------------------------------------------


async def test_batch_migration_context_bypasses_create_strict():
    """migration_context=True on create bypasses strict gate."""
    config = _config_mock("strict")
    await check_enforcement_for_create(
        key_type="classical",
        key_algorithm="RSA-2048",
        enforcement_config=config,
        migration_context=True,
    )


# ---------------------------------------------------------------------------
# Unsupported PQC algorithm returns supported_algorithms list
# ---------------------------------------------------------------------------


async def test_unsupported_pqc_returns_supported_algorithms_list():
    """UnsupportedPQCAlgorithmError carries the supported_algorithms list."""
    config = _config_mock("strict")
    with pytest.raises(UnsupportedPQCAlgorithmError) as exc_info:
        await check_enforcement_for_create(
            key_type="pqc",
            key_algorithm="SPHINCS+-SHA2-128f",
            enforcement_config=config,
        )
    assert isinstance(exc_info.value.supported_algorithms, list)
    assert len(exc_info.value.supported_algorithms) > 0
    # Must include at least one ML-DSA and one ML-KEM algorithm
    all_algs = exc_info.value.supported_algorithms
    assert any("ML-DSA" in a for a in all_algs)
    assert any("ML-KEM" in a for a in all_algs)
