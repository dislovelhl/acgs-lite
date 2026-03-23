"""Pytest configuration with pydantic/litellm compatibility fix.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import concurrent.futures
import contextlib
import os
import queue
import sys
import threading
from typing import Any

import httpx

_project_root = os.path.dirname(os.path.abspath(__file__))

def _prepend_sys_path(path: str) -> None:
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


# Prefer the checked-in package sources over stale root/src shims or globally
# installed distributions during pytest collection.
_prepend_sys_path(os.path.join(_project_root, "packages", "acgs-deliberation", "src"))
_prepend_sys_path(os.path.join(_project_root, "packages", "acgs-lite", "src"))

# Ensure project-local package roots win over similarly named packages from
# other workspaces on the user-level sys.path.
_prepend_sys_path(os.path.join(_project_root, "packages"))

# Ensure project root is on sys.path so `tests.*` shim imports resolve
# (e.g. src/core/shared/tests/ shims that import tests.core.* or tests.unit.*)
_prepend_sys_path(_project_root)

from src.core.shared.constants import CONSTITUTIONAL_HASH

# Pre-cache the project-level `tests` package in sys.modules so that sub-directory
# conftest files (e.g. enhanced_agent_bus/tests/conftest.py) cannot shadow it by
# inserting their own `tests/` directory at the front of sys.path.
with contextlib.suppress(ImportError):
    pass


# Preload pydantic modules to fix litellm compatibility

# Now safe to import litellm
# litellm optional

# Avoid import-time service_auth configuration errors during tests.
os.environ.setdefault(
    "ACGS2_SERVICE_SECRET",
    "test-service-secret-key-that-is-at-least-32-characters-long",
)
os.environ.setdefault("SERVICE_JWT_ALGORITHM", "HS256")

# Constitutional hash verification
CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH


class _WorkerThreadRunner:
    """Run async callables on a dedicated thread without AnyIO's portal bridge."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[Any, concurrent.futures.Future[Any]] | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._worker,
            name="pytest-testclient-worker",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()

    def _worker(self) -> None:
        with asyncio.Runner() as runner:
            self._ready.set()
            while True:
                item = self._queue.get()
                if item is None:
                    return

                factory, future = item
                try:
                    result = runner.run(factory())
                except Exception as exc:  # noqa: BLE001 pragma: no cover - surfaced to caller
                    future.set_exception(exc)
                else:
                    future.set_result(result)

    def run(self, factory: Any) -> Any:
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        self._queue.put((factory, future))
        return future.result()

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)


class CompatTestClient:
    """Pytest-only fallback TestClient for Python 3.14 sandbox runs.

    Starlette/FastAPI's stock TestClient relies on AnyIO's blocking portal, which
    hangs in this environment before requests reach the ASGI app. This shim keeps
    the subset of the API the repository test suite uses.
    """

    __test__ = False

    def __init__(
        self,
        app: Any,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
        root_path: str = "",
        backend: str = "asyncio",
        backend_options: dict[str, Any] | None = None,
        cookies: httpx._types.CookieTypes | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        client: tuple[str, int] = ("testclient", 50000),
    ) -> None:
        if backend != "asyncio":
            raise RuntimeError(f"Unsupported test backend: {backend}")
        if backend_options:
            raise RuntimeError("CompatTestClient does not support backend_options")

        self.app = app
        self.app_state: dict[str, Any] = {}
        self.base_url = base_url
        self.raise_server_exceptions = raise_server_exceptions
        self.root_path = root_path
        self.follow_redirects = follow_redirects
        self.client = client
        self.headers = httpx.Headers(headers or {})
        self.headers.setdefault("user-agent", "testclient")
        self.cookies = httpx.Cookies(cookies)
        self._context_worker: _WorkerThreadRunner | None = None
        self._lifespan_cm: Any = None

    def __enter__(self) -> "CompatTestClient":
        if self._context_worker is None:
            self._context_worker = _WorkerThreadRunner()

        lifespan_context = getattr(getattr(self.app, "router", None), "lifespan_context", None)
        if lifespan_context is not None:
            self._lifespan_cm = lifespan_context(self.app)
            self._context_worker.run(self._lifespan_cm.__aenter__)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._lifespan_cm is not None and self._context_worker is not None:
                self._context_worker.run(lambda: self._lifespan_cm.__aexit__(exc_type, exc, tb))
        finally:
            self._lifespan_cm = None
            self.close()

    def close(self) -> None:
        if self._context_worker is not None:
            self._context_worker.close()
            self._context_worker = None

    def _run_async(self, factory: Any) -> Any:
        if self._context_worker is not None:
            return self._context_worker.run(factory)

        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}

        def invoke() -> None:
            try:
                result_box["value"] = asyncio.run(factory())
            except Exception as exc:  # noqa: BLE001 pragma: no cover - surfaced to caller
                error_box["error"] = exc

        thread = threading.Thread(target=invoke, name="pytest-testclient-call", daemon=True)
        thread.start()
        thread.join()

        if "error" in error_box:
            raise error_box["error"]
        return result_box["value"]

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        request_kwargs = dict(kwargs)
        request_headers = httpx.Headers(self.headers)
        if "headers" in request_kwargs and request_kwargs["headers"] is not None:
            request_headers.update(request_kwargs.pop("headers"))

        follow_redirects = request_kwargs.pop("follow_redirects", self.follow_redirects)

        async def do_request() -> tuple[httpx.Response, httpx.Cookies]:
            transport = httpx.ASGITransport(
                app=self.app,
                raise_app_exceptions=self.raise_server_exceptions,
                root_path=self.root_path,
                client=self.client,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                headers=request_headers,
                cookies=self.cookies,
                follow_redirects=follow_redirects,
            ) as client:
                response = await client.request(method, url, **request_kwargs)
                return response, httpx.Cookies(client.cookies)

        response, updated_cookies = self._run_async(do_request)
        self.cookies = updated_cookies
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("OPTIONS", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)


import fastapi.testclient as fastapi_testclient
import starlette.testclient as starlette_testclient

fastapi_testclient.TestClient = CompatTestClient
starlette_testclient.TestClient = CompatTestClient
