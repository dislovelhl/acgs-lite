from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.services.api_gateway.routes import admin_sso


@pytest.mark.asyncio
async def test_dev_bypass_rejects_environment_only_production(monkeypatch):
    monkeypatch.setenv("ACGS_DEV_ADMIN_BYPASS", "true")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(admin_sso.settings, "env", "development")
    monkeypatch.setattr(admin_sso.settings.sso, "enabled", False, raising=False)

    request = SimpleNamespace(session={})

    with pytest.raises(HTTPException) as exc_info:
        await admin_sso.get_current_admin(request=request, credentials=None)

    assert exc_info.value.status_code == 401
