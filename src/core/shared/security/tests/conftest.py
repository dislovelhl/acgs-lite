"""Shared test fixtures for src.core.shared.security tests.

Constitutional Hash: 608508a9bd224290
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_auth_module_state():
    """Reset module-level mutable state on auth between tests.

    auth._revocation_service and auth._revocation_service_initialized are
    module-level singletons. Without reset they leak between tests when the
    full suite runs in a single process.
    """
    import src.core.shared.security.auth as auth

    original_service = auth._revocation_service
    original_initialized = auth._revocation_service_initialized
    yield
    auth._revocation_service = original_service
    auth._revocation_service_initialized = original_initialized


@pytest.fixture(autouse=True)
def _clear_eab_environment_override():
    """Remove ENVIRONMENT=test set by the EAB test conftest.

    The enhanced_agent_bus test conftest calls ``os.environ.setdefault("ENVIRONMENT", "test")``
    to satisfy the sandbox guard.  When the full suite runs in one process, that
    value bleeds into security tests that patch ``settings.env`` and expect
    ``_detect_environment()`` / ``_runtime_environment()`` to respect the patched
    value.  We restore the original value after each test.
    """
    original = os.environ.get("ENVIRONMENT")
    # Remove the EAB-injected value; individual tests that want it use monkeypatch.setenv
    os.environ.pop("ENVIRONMENT", None)
    yield
    if original is None:
        os.environ.pop("ENVIRONMENT", None)
    else:
        os.environ["ENVIRONMENT"] = original
