# Constitutional Hash: 608508a9bd224290
# Sprint 55 — api/routes/signup.py coverage
"""Comprehensive coverage tests for api/routes/signup.py.

Targets ≥95% line coverage of
src/core/enhanced_agent_bus/api/routes/signup.py.

Covers:
- Module-level constants and model definitions
- AccountRecord TypedDict shape
- _check_production_guard (dev env allowed, production blocked, unset blocked)
- SignupRequest / SignupResponse Pydantic models
- _generate_api_key prefix format
- _email_already_registered (found / not-found)
- _build_account_record fields
- _build_quickstart snippet content
- signup endpoint: success, duplicate email, production guard
- get_account: found and not found
- get_accounts_store
"""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from enhanced_agent_bus.api.routes.signup import (
    FREE_TIER_LIMIT,
    AccountRecord,
    SignupRequest,
    SignupResponse,
    _accounts,
    _accounts_lock,
    _build_account_record,
    _build_quickstart,
    _check_production_guard,
    _email_already_registered,
    _generate_api_key,
    get_account,
    get_accounts_store,
    router,
)

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD_PATH = "enhanced_agent_bus.api.routes.signup"


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the signup router and limiter state."""
    from enhanced_agent_bus.api.rate_limiting import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    return app


def _clear_accounts() -> None:
    """Remove all entries from the in-memory accounts store."""
    with _accounts_lock:
        _accounts.clear()


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_free_tier_limit_value(self):
        assert FREE_TIER_LIMIT == 1000

    def test_router_prefix(self):
        assert router.prefix == "/v1"

    def test_router_tags(self):
        assert "signup" in router.tags


# ---------------------------------------------------------------------------
# _check_production_guard
# ---------------------------------------------------------------------------


class TestCheckProductionGuard:
    def test_allows_development(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            _check_production_guard()  # must not raise

    def test_allows_dev(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
            _check_production_guard()

    def test_allows_test(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            _check_production_guard()

    def test_allows_testing(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "testing"}):
            _check_production_guard()

    def test_allows_ci(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "ci"}):
            _check_production_guard()

    def test_blocks_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(HTTPException) as exc_info:
                _check_production_guard()
        assert exc_info.value.status_code == 503
        assert "persistent storage" in exc_info.value.detail

    def test_blocks_staging(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "staging"}):
            with pytest.raises(HTTPException) as exc_info:
                _check_production_guard()
        assert exc_info.value.status_code == 503

    def test_blocks_unset_environment(self):
        """Fail-closed: empty ENVIRONMENT string is not in DEV_ENVIRONMENTS."""
        env = {k: v for k, v in os.environ.items() if k != "ENVIRONMENT"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                _check_production_guard()
        assert exc_info.value.status_code == 503

    def test_blocks_empty_string(self):
        with patch.dict(os.environ, {"ENVIRONMENT": ""}):
            with pytest.raises(HTTPException) as exc_info:
                _check_production_guard()
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestSignupRequest:
    def test_valid_email(self):
        req = SignupRequest(email="dev@example.com")
        assert req.email == "dev@example.com"

    def test_invalid_email_raises(self):
        with pytest.raises((TypeError, ValueError)):
            SignupRequest(email="not-an-email")


class TestSignupResponse:
    def test_defaults(self):
        resp = SignupResponse(
            api_key="acgs_live_abc123",
            email="user@example.com",
            quickstart="pip install acgs",
        )
        assert resp.plan == "free"
        assert resp.monthly_limit == FREE_TIER_LIMIT

    def test_custom_values(self):
        resp = SignupResponse(
            api_key="key",
            email="x@y.com",
            plan="pro",
            monthly_limit=9999,
            quickstart="...",
        )
        assert resp.plan == "pro"
        assert resp.monthly_limit == 9999


# ---------------------------------------------------------------------------
# _generate_api_key
# ---------------------------------------------------------------------------


class TestGenerateApiKey:
    def test_prefix(self):
        key = _generate_api_key()
        assert key.startswith("acgs_live_")

    def test_uniqueness(self):
        keys = {_generate_api_key() for _ in range(20)}
        assert len(keys) == 20

    def test_length(self):
        key = _generate_api_key()
        # "acgs_live_" (10) + 32 hex chars from token_hex(16)
        assert len(key) == 10 + 32


# ---------------------------------------------------------------------------
# _email_already_registered
# ---------------------------------------------------------------------------


class TestEmailAlreadyRegistered:
    def setup_method(self):
        _clear_accounts()

    def teardown_method(self):
        _clear_accounts()

    def test_not_registered_when_empty(self):
        assert _email_already_registered("new@example.com") is False

    def test_registered_after_insert(self):
        record: AccountRecord = {
            "email": "existing@example.com",
            "plan": "free",
            "monthly_limit": FREE_TIER_LIMIT,
            "used_this_month": 0,
            "created_at": time.time(),
        }
        with _accounts_lock:
            _accounts["test-key-001"] = record
        assert _email_already_registered("existing@example.com") is True

    def test_case_sensitive_match(self):
        record: AccountRecord = {
            "email": "user@example.com",
            "plan": "free",
            "monthly_limit": FREE_TIER_LIMIT,
            "used_this_month": 0,
            "created_at": time.time(),
        }
        with _accounts_lock:
            _accounts["test-key-002"] = record
        # Different case should not match (emails stored lower-cased by endpoint)
        assert _email_already_registered("USER@EXAMPLE.COM") is False


# ---------------------------------------------------------------------------
# _build_account_record
# ---------------------------------------------------------------------------


class TestBuildAccountRecord:
    def test_fields(self):
        before = time.time()
        record = _build_account_record("dev@acme.com")
        after = time.time()

        assert record["email"] == "dev@acme.com"
        assert record["plan"] == "free"
        assert record["monthly_limit"] == FREE_TIER_LIMIT
        assert record["used_this_month"] == 0
        assert before <= record["created_at"] <= after


# ---------------------------------------------------------------------------
# _build_quickstart
# ---------------------------------------------------------------------------


class TestBuildQuickstart:
    def test_contains_pip_install(self):
        qs = _build_quickstart("acgs_live_testkey")
        assert "pip install acgs" in qs

    def test_contains_api_key(self):
        key = "acgs_live_deadbeef0123456789"
        qs = _build_quickstart(key)
        assert key in qs

    def test_contains_await_validate(self):
        qs = _build_quickstart("k")
        assert "await client.validate" in qs

    def test_contains_compliant_print(self):
        qs = _build_quickstart("k")
        assert "Compliant" in qs


# ---------------------------------------------------------------------------
# signup endpoint — via TestClient
# ---------------------------------------------------------------------------


class TestSignupEndpoint:
    def setup_method(self):
        _clear_accounts()

    def teardown_method(self):
        _clear_accounts()

    def _client(self) -> TestClient:
        return TestClient(_make_app(), raise_server_exceptions=False)

    # --- success path ---

    def test_successful_signup_returns_200(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "newdev@example.com"})
        assert resp.status_code == 200

    def test_successful_signup_response_shape(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "shape@example.com"})
        data = resp.json()
        assert "api_key" in data
        assert data["api_key"].startswith("acgs_live_")
        assert data["email"] == "shape@example.com"
        assert data["plan"] == "free"
        assert data["monthly_limit"] == FREE_TIER_LIMIT
        assert "quickstart" in data
        assert "pip install acgs" in data["quickstart"]

    def test_email_lowercased_in_response(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "Mixed@Example.COM"})
        assert resp.json()["email"] == "mixed@example.com"

    def test_account_stored_after_signup(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "stored@example.com"})
        api_key = resp.json()["api_key"]
        account = get_account(api_key)
        assert account is not None
        assert account["email"] == "stored@example.com"

    # --- duplicate email ---

    def test_duplicate_email_returns_409(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            client.post("/v1/signup", json={"email": "dupe@example.com"})
            resp = client.post("/v1/signup", json={"email": "dupe@example.com"})
        assert resp.status_code == 409

    def test_duplicate_email_error_message(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            client.post("/v1/signup", json={"email": "dupe2@example.com"})
            resp = client.post("/v1/signup", json={"email": "dupe2@example.com"})
        assert "already exists" in resp.json()["detail"]

    # --- production guard in endpoint ---

    def test_production_environment_returns_503(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "blocked@example.com"})
        assert resp.status_code == 503

    def test_unset_environment_returns_503(self):
        env = {k: v for k, v in os.environ.items() if k != "ENVIRONMENT"}
        with patch.dict(os.environ, env, clear=True):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "no-env@example.com"})
        assert resp.status_code == 503

    # --- invalid request body ---

    def test_invalid_email_returns_422(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={"email": "not-valid"})
        assert resp.status_code == 422

    def test_missing_email_returns_422(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            client = self._client()
            resp = client.post("/v1/signup", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------


class TestGetAccount:
    def setup_method(self):
        _clear_accounts()

    def teardown_method(self):
        _clear_accounts()

    def test_returns_none_for_unknown_key(self):
        assert get_account("nonexistent-key") is None

    def test_returns_record_for_known_key(self):
        record: AccountRecord = {
            "email": "found@example.com",
            "plan": "free",
            "monthly_limit": FREE_TIER_LIMIT,
            "used_this_month": 0,
            "created_at": time.time(),
        }
        with _accounts_lock:
            _accounts["known-key"] = record
        result = get_account("known-key")
        assert result is not None
        assert result["email"] == "found@example.com"


# ---------------------------------------------------------------------------
# get_accounts_store
# ---------------------------------------------------------------------------


class TestGetAccountsStore:
    def setup_method(self):
        _clear_accounts()

    def teardown_method(self):
        _clear_accounts()

    def test_returns_dict(self):
        store = get_accounts_store()
        assert isinstance(store, dict)

    def test_reflects_current_state(self):
        record: AccountRecord = {
            "email": "store@example.com",
            "plan": "free",
            "monthly_limit": FREE_TIER_LIMIT,
            "used_this_month": 0,
            "created_at": time.time(),
        }
        with _accounts_lock:
            _accounts["store-key"] = record
        store = get_accounts_store()
        assert "store-key" in store
        assert store["store-key"]["email"] == "store@example.com"

    def test_is_same_object_as_internal_store(self):
        """get_accounts_store returns the actual dict, not a copy."""
        store = get_accounts_store()
        assert store is _accounts


# ---------------------------------------------------------------------------
# Thread-safety smoke test
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def setup_method(self):
        _clear_accounts()

    def teardown_method(self):
        _clear_accounts()

    def test_concurrent_signups_unique_keys(self):
        """Multiple threads signing up concurrently should each get unique keys.

        The global slowapi limiter may return 429 when the in-process rate
        limit window is already close to exhaustion from previous tests.  We
        accept 200 or 429 as valid responses — the important invariant is that
        no two successful signups produce the same API key and no 5xx errors
        occur (which would indicate a threading bug).
        """
        results: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def do_signup(idx: int) -> None:
            # ENVIRONMENT is set by the outer patch.dict; don't nest
            # patch.dict per-thread — concurrent patching of os.environ is not
            # thread-safe and can cause race-condition 503s.
            app = _make_app()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/v1/signup", json={"email": f"thread{idx}@example.com"})
            with lock:
                if resp.status_code == 200:
                    results.append(resp.json()["api_key"])
                elif resp.status_code == 429:
                    # Rate-limited — not a threading error, skip
                    pass
                else:
                    errors.append(Exception(f"unexpected status {resp.status_code}"))

        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            threads = [threading.Thread(target=do_signup, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        # All successful signups must have unique API keys
        assert len(set(results)) == len(results), "Duplicate API keys detected"
