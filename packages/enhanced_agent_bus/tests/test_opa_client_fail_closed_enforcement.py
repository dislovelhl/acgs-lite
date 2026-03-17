"""Tests for environment-aware fail-closed enforcement in get_opa_client.

Constitutional Hash: cdd01ef066bc6cf2
"""

import packages.enhanced_agent_bus.opa_client as opa_client_module
import pytest


@pytest.fixture(autouse=True)
def _reset_global_client() -> None:
    opa_client_module._opa_client = None
    yield
    opa_client_module._opa_client = None


@pytest.mark.constitutional
def test_get_opa_client_respects_fail_closed_flag_outside_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")

    client = opa_client_module.get_opa_client(fail_closed=False)

    assert client.fail_closed is False


@pytest.mark.constitutional
def test_get_opa_client_forces_fail_closed_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    client = opa_client_module.get_opa_client(fail_closed=False)

    assert client.fail_closed is True
