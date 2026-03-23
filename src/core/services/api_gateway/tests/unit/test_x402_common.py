from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

from src.core.services.api_gateway.routes._x402_common import (
    configure_x402_payment_middleware,
)


class _FakeResourceServer:
    def __init__(self, clients):
        self.clients = clients
        self.registrations: list[tuple[str, object]] = []

    def register(self, network: str, scheme: object) -> None:
        self.registrations.append((network, scheme))


def _build_fake_importer() -> tuple[dict[str, object], callable]:
    route_config_calls: list[dict[str, object]] = []
    payment_option_calls: list[dict[str, object]] = []
    middleware_cls = type("PaymentMiddlewareASGI", (), {})
    resource_servers: list[_FakeResourceServer] = []

    class _RouteConfig:
        def __init__(self, **kwargs):
            route_config_calls.append(kwargs)
            self.kwargs = kwargs

    class _PaymentOption:
        def __init__(self, **kwargs):
            payment_option_calls.append(kwargs)
            self.kwargs = kwargs

    class _FacilitatorConfig:
        def __init__(self, url: str):
            self.url = url

    class _HTTPFacilitatorClient:
        def __init__(self, config: _FacilitatorConfig):
            self.config = config

    class _ExactEvmServerScheme:
        pass

    def _resource_server_factory(clients):
        server = _FakeResourceServer(clients)
        resource_servers.append(server)
        return server

    module_map: dict[str, object] = {
        "x402": SimpleNamespace(FacilitatorConfig=_FacilitatorConfig),
        "x402.http": SimpleNamespace(HTTPFacilitatorClient=_HTTPFacilitatorClient),
        "x402.http.middleware.fastapi": SimpleNamespace(PaymentMiddlewareASGI=middleware_cls),
        "x402.http.types": SimpleNamespace(RouteConfig=_RouteConfig, PaymentOption=_PaymentOption),
        "x402.mechanisms.evm.exact": SimpleNamespace(ExactEvmServerScheme=_ExactEvmServerScheme),
        "x402.server": SimpleNamespace(x402ResourceServer=_resource_server_factory),
    }

    def _importer(name: str):
        if name not in module_map:
            raise ImportError(name)
        return module_map[name]

    state = {
        "route_config_calls": route_config_calls,
        "payment_option_calls": payment_option_calls,
        "middleware_cls": middleware_cls,
        "resource_servers": resource_servers,
    }
    return state, _importer


def test_configure_x402_payment_middleware_disabled_when_pay_to_missing():
    app = FastAPI()

    result = configure_x402_payment_middleware(app, environ={})

    assert result is False


def test_configure_x402_payment_middleware_fails_closed_without_dependency(monkeypatch):
    app = FastAPI()

    def _raise_import_error(name: str):
        raise ImportError(name)

    monkeypatch.setattr("src.core.services.api_gateway.routes._x402_common.importlib.import_module", _raise_import_error)

    with pytest.raises(RuntimeError, match="x402\\[evm\\]"):
        configure_x402_payment_middleware(app, environ={"EVM_ADDRESS": "0xabc123"})


def test_configure_x402_payment_middleware_registers_routes(monkeypatch):
    app = FastAPI()
    add_middleware = MagicMock()
    app.add_middleware = add_middleware  # type: ignore[method-assign]
    state, importer = _build_fake_importer()
    monkeypatch.setattr(
        "src.core.services.api_gateway.routes._x402_common.importlib.import_module",
        importer,
    )

    result = configure_x402_payment_middleware(
        app,
        environ={
            "EVM_ADDRESS": "0xabc123",
            "X402_NETWORK": "eip155:1",
            "FACILITATOR_URL": "https://facilitator.example.com",
        },
    )

    assert result is True
    add_middleware.assert_called_once()
    _, kwargs = add_middleware.call_args
    assert kwargs["server"] is state["resource_servers"][0]
    assert "POST /x402/validate" in kwargs["routes"]
    assert len(state["payment_option_calls"]) >= 5
    assert len(state["route_config_calls"]) >= 5
    assert state["resource_servers"][0].registrations[0][0] == "eip155:1"
