"""Tests for fail-closed enforcement in OPAClient.

Constitutional Hash: 608508a9bd224290

VULN-002: OPAClient always forces fail_closed=True regardless of environment.
The constructor no longer accepts a fail_closed parameter.
"""

import pytest

import enhanced_agent_bus.opa_client as opa_client_module


@pytest.mark.constitutional
def test_opa_client_forces_fail_closed_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even in development, fail_closed is always True (VULN-002)."""
    monkeypatch.setenv("ENVIRONMENT", "development")

    client = opa_client_module.OPAClient()

    assert client.fail_closed is True


@pytest.mark.constitutional
def test_opa_client_forces_fail_closed_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In production, fail_closed is always True (VULN-002)."""
    monkeypatch.setenv("ENVIRONMENT", "production")

    client = opa_client_module.OPAClient()

    assert client.fail_closed is True
