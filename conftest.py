"""Pytest configuration with pydantic/litellm compatibility fix.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import concurrent.futures
import contextlib
import io
import os
import queue
import sys
import threading
from types import GeneratorType
from typing import Any
from urllib.parse import unquote

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
                except Exception as exc:
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


class _CompatSyncTransport(httpx.BaseTransport):
    """Sync ASGI transport that avoids AnyIO's blocking portal."""

    def __init__(
        self,
        *,
        app: Any,
        app_state: dict[str, Any],
        raise_server_exceptions: bool,
        root_path: str,
        client: tuple[str, int],
        run_async: Any,
    ) -> None:
        self.app = app
        self.app_state = app_state
        self.raise_server_exceptions = raise_server_exceptions
        self.root_path = root_path
        self.client = client
        self.run_async = run_async

    async def _run_app_with_ticker(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        stop = asyncio.Event()
        ticker_task = asyncio.create_task(self._ticker(stop))
        try:
            await self.app(scope, receive, send)
        finally:
            stop.set()
            ticker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker_task

    async def _ticker(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await asyncio.sleep(0.05)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        scheme = request.url.scheme
        netloc = request.url.netloc.decode("ascii")
        path = request.url.path
        raw_path = request.url.raw_path
        query = request.url.query.decode("ascii")

        default_port = {"http": 80, "https": 443, "ws": 80, "wss": 443}[scheme]
        if ":" in netloc:
            host, port_string = netloc.split(":", 1)
            port = int(port_string)
        else:
            host = netloc
            port = default_port

        if "host" in request.headers:
            headers: list[tuple[bytes, bytes]] = []
        elif port == default_port:  # pragma: no cover
            headers = [(b"host", host.encode())]
        else:  # pragma: no cover
            headers = [(b"host", f"{host}:{port}".encode())]

        headers += [
            (key.lower().encode(), value.encode()) for key, value in request.headers.multi_items()
        ]

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": request.method,
            "path": unquote(path),
            "raw_path": raw_path.split(b"?", 1)[0],
            "root_path": self.root_path,
            "scheme": scheme,
            "query_string": query.encode(),
            "headers": headers,
            "client": self.client,
            "server": [host, port],
            "extensions": {"http.response.debug": {}},
            "state": self.app_state.copy(),
        }

        request_complete = False
        response_started = False
        response_complete = threading.Event()
        raw_kwargs: dict[str, Any] = {"stream": io.BytesIO()}

        async def receive() -> dict[str, Any]:
            nonlocal request_complete

            if request_complete:
                if not response_complete.is_set():
                    await asyncio.to_thread(response_complete.wait)
                return {"type": "http.disconnect"}

            body = request.read()
            if isinstance(body, str):
                body_bytes = body.encode("utf-8")  # pragma: no cover
            elif body is None:
                body_bytes = b""  # pragma: no cover
            elif isinstance(body, GeneratorType):
                try:  # pragma: no cover
                    chunk = body.send(None)
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    return {"type": "http.request", "body": chunk, "more_body": True}
                except StopIteration:
                    request_complete = True
                    return {"type": "http.request", "body": b""}
            else:
                body_bytes = body

            request_complete = True
            return {"type": "http.request", "body": body_bytes}

        async def send(message: dict[str, Any]) -> None:
            nonlocal raw_kwargs, response_started

            if message["type"] == "http.response.start":
                raw_kwargs["status_code"] = message["status"]
                raw_kwargs["headers"] = [
                    (key.decode(), value.decode()) for key, value in message.get("headers", [])
                ]
                response_started = True
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                more_body = message.get("more_body", False)
                if request.method != "HEAD":
                    raw_kwargs["stream"].write(body)
                if not more_body:
                    raw_kwargs["stream"].seek(0)
                    response_complete.set()

        try:
            self.run_async(lambda: self._run_app_with_ticker(scope, receive, send))
        except BaseException as exc:
            if self.raise_server_exceptions:
                raise exc

        if self.raise_server_exceptions:
            assert response_started, "TestClient did not receive any response."
        elif not response_started:
            raw_kwargs = {
                "status_code": 500,
                "headers": [],
                "stream": io.BytesIO(),
            }

        raw_kwargs["stream"] = httpx.ByteStream(raw_kwargs["stream"].read())
        return httpx.Response(**raw_kwargs, request=request)


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

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(factory())

        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}

        def invoke() -> None:
            try:
                result_box["value"] = asyncio.run(factory())
            except Exception as exc:
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
        transport = _CompatSyncTransport(
            app=self.app,
            app_state=self.app_state,
            raise_server_exceptions=self.raise_server_exceptions,
            root_path=self.root_path,
            client=self.client,
            run_async=self._run_async,
        )
        with httpx.Client(
            transport=transport,
            base_url=self.base_url,
            headers=request_headers,
            cookies=self.cookies,
            follow_redirects=follow_redirects,
        ) as client:
            response = client.request(method, url, **request_kwargs)
            self.cookies = httpx.Cookies(client.cookies)
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
