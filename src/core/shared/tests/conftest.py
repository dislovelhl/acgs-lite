"""Shared test fixtures for src.core.shared tests.

Constitutional Hash: 608508a9bd224290
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_auth_module_state():
    """Reset module-level mutable state on auth between tests."""
    import src.core.shared.security.auth as auth

    original_service = auth._revocation_service
    original_initialized = auth._revocation_service_initialized
    yield
    auth._revocation_service = original_service
    auth._revocation_service_initialized = original_initialized


@pytest.fixture(autouse=True)
def _clear_eab_environment_override():
    """Remove ENVIRONMENT=test set by the EAB test conftest for each test."""
    original = os.environ.get("ENVIRONMENT")
    os.environ.pop("ENVIRONMENT", None)
    yield
    if original is None:
        os.environ.pop("ENVIRONMENT", None)
    else:
        os.environ["ENVIRONMENT"] = original
