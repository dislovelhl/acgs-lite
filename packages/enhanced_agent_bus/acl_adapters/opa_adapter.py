from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from enhanced_agent_bus._compat.json_utils import dumps as json_dumps

from .base import CONSTITUTIONAL_HASH, ACLAdapter, AdapterConfig, AdapterResult

_UNINITIALIZED = object()


@dataclass(slots=True)
class OPARequest:
    input: dict[str, Any]
    policy_path: str | None = None
    explain: bool = False
    pretty: bool = False
    metrics: bool = True
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if self.trace_id is None:
            self.trace_id = hashlib.sha256(
                json_dumps(self.input, sort_keys=True).encode()
            ).hexdigest()[:16]


@dataclass(slots=True)
class OPAResponse:
    allow: bool
    result: Any = None
    decision_id: str | None = None
    explanation: list[str] | None = None
    metrics: dict[str, Any] | None = None
    trace_id: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "result": self.result,
            "decision_id": self.decision_id,
            "explanation": self.explanation,
            "metrics": self.metrics,
            "constitutional_hash": self.constitutional_hash,
            "trace_id": self.trace_id,
        }


@dataclass(slots=True)
class OPAAdapterConfig(AdapterConfig):
    opa_url: str = "http://localhost:8181"
    opa_bundle_path: str = "/v1/data"
    fail_closed: bool = True
    default_policy_path: str = "acgs2/constitutional"
    cache_enabled: bool = True
    cache_ttl_s: int = 60
    timeout_ms: int = 1000
    max_retries: int = 2
    circuit_failure_threshold: int = 3


class OPAAdapter(ACLAdapter[OPARequest, OPAResponse]):
    def __init__(self, name: str = "opa", config: OPAAdapterConfig | None = None) -> None:
        self.opa_config = config or OPAAdapterConfig()
        super().__init__(name=name, config=self.opa_config)
        self._http_client: Any = _UNINITIALIZED

    async def _get_http_client(self) -> Any:
        if self._http_client is not _UNINITIALIZED and self._http_client is not None:
            start = getattr(self._http_client, "start", None)
            if callable(start):
                await start()
            return self._http_client
        try:
            import aiohttp
        except ImportError:
            self._http_client = None
            return None
        self._http_client = aiohttp.ClientSession()
        return self._http_client

    def _simulate_opa_response(self, request: OPARequest) -> OPAResponse:
        if self.opa_config.fail_closed:
            return OPAResponse(
                allow=False,
                result={"simulated": True, "reason": "opa_unavailable"},
                trace_id=request.trace_id,
            )
        return OPAResponse(
            allow=True,
            result={"simulated": True, "reason": "opa_unavailable_failopen"},
            trace_id=request.trace_id,
        )

    def _parse_opa_response(self, data: dict[str, Any], request: OPARequest) -> OPAResponse:
        result = data.get("result", {})
        if isinstance(result, bool):
            allow = result
        elif isinstance(result, dict):
            if "allow" in result:
                allow = bool(result.get("allow"))
            elif "allowed" in result:
                allow = bool(result.get("allowed"))
            else:
                allow = bool(result)
        else:
            allow = bool(result)
        decision_id = hashlib.sha256(f"{request.trace_id}:{result}".encode()).hexdigest()[:16]
        return OPAResponse(
            allow=allow,
            result=result,
            decision_id=decision_id,
            explanation=data.get("explanation"),
            metrics=data.get("metrics"),
            trace_id=request.trace_id,
        )

    def _validate_response(self, response: OPAResponse) -> bool:
        return isinstance(response.allow, bool)

    def _get_cache_key(self, request: OPARequest) -> str:
        policy_path = request.policy_path or self.opa_config.default_policy_path
        payload = f"{policy_path}|{json_dumps(request.input, sort_keys=True)}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_fallback_response(self, request: OPARequest) -> OPAResponse | None:
        if not self.opa_config.fail_closed:
            return None
        return OPAResponse(
            allow=False,
            result={"fallback": True, "reason": "circuit_open"},
            trace_id=request.trace_id,
        )

    async def _execute(self, request: OPARequest) -> OPAResponse:
        client = await self._get_http_client()
        if client is None:
            return self._simulate_opa_response(request)

        policy_path = request.policy_path or self.opa_config.default_policy_path
        params: dict[str, str] = {}
        if request.explain:
            params["explain"] = "full"
        if request.pretty:
            params["pretty"] = "true"
        if request.metrics:
            params["metrics"] = "true"
        url = f"{self.opa_config.opa_url}{self.opa_config.opa_bundle_path}/{policy_path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        payload = {"input": request.input}

        try:
            post_result = client.post(url, json=payload)
            if hasattr(post_result, "__aenter__"):
                async with post_result as response:
                    status = getattr(response, "status", getattr(response, "status_code", 500))
                    if status != 200:
                        return OPAResponse(
                            allow=not self.opa_config.fail_closed,
                            result={"error": f"OPA returned status {status}"},
                            trace_id=request.trace_id,
                        )
                    return self._parse_opa_response(await response.json(), request)
            response = await post_result
            status = getattr(response, "status_code", None)
            if status is None or not isinstance(status, int):
                status = getattr(response, "status", 500)
            if status != 200:
                return OPAResponse(
                    allow=not self.opa_config.fail_closed,
                    result={"error": f"OPA returned status {status}"},
                    trace_id=request.trace_id,
                )
            if hasattr(response, "json"):
                data = await response.json() if callable(response.json) else response.json
            else:
                data = {}
            return self._parse_opa_response(data, request)
        except TimeoutError:
            return OPAResponse(
                allow=not self.opa_config.fail_closed,
                result={"error": "timeout"},
                trace_id=request.trace_id,
            )
        except Exception as exc:
            if self.opa_config.fail_closed:
                return OPAResponse(
                    allow=False, result={"error": str(exc)}, trace_id=request.trace_id
                )
            return self._simulate_opa_response(request)

    async def close(self) -> None:
        if self._http_client is None or self._http_client is _UNINITIALIZED:
            self._http_client = None
            return
        close = getattr(self._http_client, "close", None)
        if callable(close):
            result = close()
            if hasattr(result, "__await__"):
                await result
        self._http_client = None


async def check_constitutional_compliance(
    action: str,
    resource: str,
    context: dict[str, Any] | None = None,
    adapter: OPAAdapter | None = None,
) -> AdapterResult[OPAResponse]:
    opa = adapter or OPAAdapter()
    payload = {"action": action, "resource": resource, "constitutional_hash": CONSTITUTIONAL_HASH}
    if context:
        payload.update(context)
    request = OPARequest(input=payload)
    return await opa.call(request)


async def check_agent_permission(
    agent_id: str,
    permission: str,
    target: str | None = None,
    adapter: OPAAdapter | None = None,
) -> AdapterResult[OPAResponse]:
    opa = adapter or OPAAdapter()
    request = OPARequest(
        input={"agent_id": agent_id, "permission": permission, "target": target},
        policy_path="acgs2/agent/permissions",
    )
    return await opa.call(request)


async def evaluate_maci_role(
    agent_role: str,
    action: str,
    target_role: str | None = None,
    adapter: OPAAdapter | None = None,
) -> AdapterResult[OPAResponse]:
    opa = adapter or OPAAdapter()
    request = OPARequest(
        input={"agent_role": agent_role, "action": action, "target_role": target_role},
        policy_path="acgs2/maci/role_separation",
        explain=True,
    )
    return await opa.call(request)


__all__ = [
    "CONSTITUTIONAL_HASH",
    "OPAAdapter",
    "OPAAdapterConfig",
    "OPARequest",
    "OPAResponse",
    "check_agent_permission",
    "check_constitutional_compliance",
    "evaluate_maci_role",
]
