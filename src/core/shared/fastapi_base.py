from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from src.core.shared.security.cors_config import get_cors_config
from src.core.shared.structured_logging import get_logger


def create_acgs_app(service_name: str, **config: object) -> FastAPI:
    environment = (
        str(
            config.get("environment")
            or os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or "production"
        )
        .strip()
        .lower()
    )
    is_development = environment in {"development", "dev", "test", "testing", "ci"}
    docs_enabled = bool(config.get("docs_enabled", is_development))

    app_kwargs: dict[str, object] = {
        "title": config.get("title", f"ACGS-2 {service_name}"),
        "description": config.get("description", f"{service_name} service"),
        "version": config.get("version", "1.0.0"),
        "docs_url": config.get("docs_url", "/docs" if docs_enabled else None),
        "redoc_url": config.get("redoc_url", "/redoc" if docs_enabled else None),
        "openapi_url": config.get("openapi_url", "/openapi.json" if docs_enabled else None),
    }
    if config.get("lifespan") is not None:
        app_kwargs["lifespan"] = config["lifespan"]
    if config.get("default_response_class") is not None:
        app_kwargs["default_response_class"] = config["default_response_class"]

    app = FastAPI(**app_kwargs)
    logger = config.get("logger") or get_logger(__name__)

    if config.get("enable_request_logging", True):

        @app.middleware("http")
        async def request_logging_middleware(request: Request, call_next):
            start_time = time.perf_counter()
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "request_completed",
                extra={
                    "service": service_name,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response

    trusted_hosts = config.get("trusted_hosts")
    if trusted_hosts:
        hosts = list(trusted_hosts) if not isinstance(trusted_hosts, list) else trusted_hosts
        if is_development and "testserver" not in hosts:
            hosts = [*hosts, "testserver"]
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    if config.get("enable_cors", True):
        app.add_middleware(CORSMiddleware, **config.get("cors_config", get_cors_config()))

    if config.get("enable_rate_limiting", False):
        try:
            from src.core.shared.security.rate_limiter import RateLimitConfig, RateLimitMiddleware

            rate_limit_config = config.get("rate_limit_config") or RateLimitConfig.from_env()
            if rate_limit_config.enabled:
                app.add_middleware(RateLimitMiddleware, config=rate_limit_config)
                logger.info(
                    "rate_limiting_enabled",
                    extra={
                        "service": service_name,
                        "rules_count": len(rate_limit_config.rules),
                    },
                )
        except Exception as exc:
            logger.warning(
                "rate_limiting_unavailable",
                extra={"service": service_name, "error": str(exc)},
            )

    if config.get("enable_common_exception_handlers", True):

        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(
            request: Request, exc: RequestValidationError
        ) -> JSONResponse:
            body = exc.body
            if body is not None and not isinstance(body, (dict, list, str, int, float, bool)):
                if hasattr(body, "items"):
                    try:
                        body = dict(body.items())
                    except (AttributeError, TypeError, ValueError):
                        body = str(body)
                else:
                    body = str(body)

            logger.error(
                "validation_error",
                extra={
                    "service": service_name,
                    "path": request.url.path,
                    "detail": exc.errors(),
                },
            )
            return JSONResponse(status_code=422, content={"detail": exc.errors()})

        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
            logger.error(
                "unhandled_exception",
                extra={
                    "service": service_name,
                    "path": request.url.path,
                    "method": request.method,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    if config.get("include_default_health_routes", True):
        health_path = str(config.get("health_path", "/health"))
        ready_path = str(config.get("ready_path", "/ready"))

        @app.get(health_path)
        async def health_check() -> dict[str, str]:
            return {
                "status": "healthy",
                "service": service_name,
            }

        @app.get(ready_path)
        async def readiness_check() -> dict[str, str]:
            return {
                "status": "ready",
                "service": service_name,
            }

    return app
