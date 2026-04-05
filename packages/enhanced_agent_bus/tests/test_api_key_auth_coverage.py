# Constitutional Hash: 608508a9bd224290
"""Extended coverage tests for api/api_key_auth.py.

Targets ≥90% coverage of src/core/enhanced_agent_bus/api/api_key_auth.py,
covering all auth paths, cache logic, revocation, and error handling.
"""

import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from enhanced_agent_bus.api import api_key_auth

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset all module-level mutable state before and after every test."""
    api_key_auth.reset_valid_keys()
    # Also reset the cached signup getter so tests don't bleed into each other
    api_key_auth._cached_get_account = None
    yield
    api_key_auth.reset_valid_keys()
    api_key_auth._cached_get_account = None


# ---------------------------------------------------------------------------
# _key_fingerprint
# ---------------------------------------------------------------------------


class TestKeyFingerprint:
    def test_returns_12_char_hex(self):
        fp = api_key_auth._key_fingerprint("some-key-test-value-32chars-xxxx")
        assert len(fp) == 12
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic(self):
        fp1 = api_key_auth._key_fingerprint("my-key-test-value-32chars-xxxxxx")
        fp2 = api_key_auth._key_fingerprint("my-key-test-value-32chars-xxxxxx")
        assert fp1 == fp2

    def test_different_keys_produce_different_fingerprints(self):
        fp1 = api_key_auth._key_fingerprint("key-a-test-value-32chars-xxxxxxx")
        fp2 = api_key_auth._key_fingerprint("key-b-test-value-32chars-xxxxxxx")
        assert fp1 != fp2

    def test_matches_sha256_prefix(self):
        raw = "check-key-test-value-32chars-xxx"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:12]
        assert api_key_auth._key_fingerprint(raw) == expected


# ---------------------------------------------------------------------------
# _is_test_context
# ---------------------------------------------------------------------------


class TestIsTestContext:
    def test_returns_true_when_pytest_var_set(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_file.py::test_x (call)")
        assert api_key_auth._is_test_context() is True

    def test_returns_false_when_var_absent(self, monkeypatch):
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert api_key_auth._is_test_context() is False

    def test_returns_false_when_var_empty(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "")
        assert api_key_auth._is_test_context() is False


# ---------------------------------------------------------------------------
# _is_production_environment
# ---------------------------------------------------------------------------


class TestIsProductionEnvironment:
    def test_production_env_returns_true(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is True

    def test_development_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_dev_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_test_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_testing_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_ci_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "ci")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_unset_env_treated_as_production(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is True

    def test_runtime_env_overrides_environment(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "production")
        assert api_key_auth._is_production_environment() is True

    def test_runtime_env_development_returns_false(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "development")
        assert api_key_auth._is_production_environment() is False

    def test_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "  CI  ")
        assert api_key_auth._is_production_environment() is False

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "TESTING")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is False

    def test_arbitrary_unknown_env_is_production(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        assert api_key_auth._is_production_environment() is True


# ---------------------------------------------------------------------------
# _is_test_key_explicitly_allowed
# ---------------------------------------------------------------------------


class TestIsTestKeyExplicitlyAllowed:
    def test_true_when_flag_set_lowercase(self, monkeypatch):
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "true")
        assert api_key_auth._is_test_key_explicitly_allowed() is True

    def test_true_when_flag_set_uppercase(self, monkeypatch):
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "TRUE")
        assert api_key_auth._is_test_key_explicitly_allowed() is True

    def test_false_when_flag_absent(self, monkeypatch):
        monkeypatch.delenv("ACGS_ALLOW_TEST_API_KEY", raising=False)
        assert api_key_auth._is_test_key_explicitly_allowed() is False

    def test_false_when_flag_is_false(self, monkeypatch):
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "false")
        assert api_key_auth._is_test_key_explicitly_allowed() is False

    def test_false_when_flag_is_empty(self, monkeypatch):
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "")
        assert api_key_auth._is_test_key_explicitly_allowed() is False


# ---------------------------------------------------------------------------
# _allow_test_api_key
# ---------------------------------------------------------------------------


class TestAllowTestApiKey:
    def test_blocked_in_production_regardless_of_pytest(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test.py::test (call)")
        assert api_key_auth._allow_test_api_key() is False

    def test_blocked_in_production_with_explicit_flag(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "true")
        assert api_key_auth._allow_test_api_key() is False

    def test_allowed_in_dev_with_pytest_context(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test.py::test (call)")
        assert api_key_auth._allow_test_api_key() is True

    def test_allowed_in_dev_with_explicit_flag(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ACGS_ALLOW_TEST_API_KEY", "true")
        assert api_key_auth._allow_test_api_key() is True

    def test_blocked_in_dev_without_pytest_or_flag(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.delenv("ACGS_ALLOW_TEST_API_KEY", raising=False)
        assert api_key_auth._allow_test_api_key() is False

    def test_allowed_in_ci_with_pytest_context(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "ci")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test.py::test (call)")
        assert api_key_auth._allow_test_api_key() is True


# ---------------------------------------------------------------------------
# _load_env_api_keys
# ---------------------------------------------------------------------------


class TestLoadEnvApiKeys:
    def test_empty_env_returns_empty_set(self, monkeypatch):
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        result = api_key_auth._load_env_api_keys()
        assert result == set()

    def test_single_key(self, monkeypatch):
        monkeypatch.setenv("ACGS_API_KEYS", "only-key-test-value-32chars-xxxx")
        result = api_key_auth._load_env_api_keys()
        assert result == {"only-key-test-value-32chars-xxxx"}

    def test_multiple_keys_split_by_comma(self, monkeypatch):
        monkeypatch.setenv(
            "ACGS_API_KEYS",
            "key-a-test-value-32chars-xxxxxxx,key-b-test-value-32chars-xxxxxxx,key-c-test-value-32chars-xxxxxxx",
        )
        result = api_key_auth._load_env_api_keys()
        assert result == {
            "key-a-test-value-32chars-xxxxxxx",
            "key-b-test-value-32chars-xxxxxxx",
            "key-c-test-value-32chars-xxxxxxx",
        }

    def test_whitespace_stripped(self, monkeypatch):
        monkeypatch.setenv(
            "ACGS_API_KEYS", " key-a-test-value-32chars-xxxxxxx , key-b-test-value-32chars-xxxxxxx "
        )
        result = api_key_auth._load_env_api_keys()
        assert result == {"key-a-test-value-32chars-xxxxxxx", "key-b-test-value-32chars-xxxxxxx"}

    def test_empty_segments_ignored(self, monkeypatch):
        monkeypatch.setenv(
            "ACGS_API_KEYS", "key-a-test-value-32chars-xxxxxxx,,key-b-test-value-32chars-xxxxxxx,"
        )
        result = api_key_auth._load_env_api_keys()
        assert result == {"key-a-test-value-32chars-xxxxxxx", "key-b-test-value-32chars-xxxxxxx"}


# ---------------------------------------------------------------------------
# _get_valid_keys — cache logic
# ---------------------------------------------------------------------------


class TestGetValidKeys:
    def test_returns_env_keys(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv(
            "ACGS_API_KEYS", "env-key-1-test-value-32chars-xxx,env-key-2-test-value-32chars-xxx"
        )
        keys = api_key_auth._get_valid_keys()
        assert "env-key-1-test-value-32chars-xxx" in keys
        assert "env-key-2-test-value-32chars-xxx" in keys

    def test_cache_hit_reuses_previous_result(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "first-key-test-value-32chars-xxx")
        # First call populates cache
        first = api_key_auth._get_valid_keys()
        assert "first-key-test-value-32chars-xxx" in first
        # Change env but cache is still valid (time hasn't advanced)
        monkeypatch.setenv("ACGS_API_KEYS", "second-key-test-value-32chars-xx")
        second = api_key_auth._get_valid_keys()
        assert "first-key-test-value-32chars-xxx" in second
        assert "second-key-test-value-32chars-xx" not in second

    def test_cache_miss_after_ttl_reloads_keys(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "old-key-test-value-32chars-xxxxx")
        call_count = {"n": 0}
        times = [0.0, 200.0]  # second call is after 60s TTL

        def mock_monotonic():
            idx = min(call_count["n"], len(times) - 1)
            call_count["n"] += 1
            return times[idx]

        monkeypatch.setattr(api_key_auth.time, "monotonic", mock_monotonic)
        first = api_key_auth._get_valid_keys()
        assert "old-key-test-value-32chars-xxxxx" in first

        monkeypatch.setenv("ACGS_API_KEYS", "new-key-test-value-32chars-xxxxx")
        second = api_key_auth._get_valid_keys()
        assert "new-key-test-value-32chars-xxxxx" in second
        assert "old-key-test-value-32chars-xxxxx" not in second

    def test_test_key_not_in_valid_keys_after_removal(self, monkeypatch, test_api_key):
        """Test key should not be in valid keys (moved to fixtures)."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("AGENT_RUNTIME_ENVIRONMENT", raising=False)
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test.py::test (call)")
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        keys = api_key_auth._get_valid_keys()
        # Test key should NOT be in valid keys (it's now in fixtures only)
        assert test_api_key not in keys

    def test_revoked_keys_filtered_from_result(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv(
            "ACGS_API_KEYS", "good-key-test-value-32chars-xxxx,bad-key-test-value-32chars-xxxxx"
        )
        # Revoke before loading so it gets filtered during _get_valid_keys
        api_key_auth._revoked_keys.add("bad-key-test-value-32chars-xxxxx")
        keys = api_key_auth._get_valid_keys()
        assert "good-key-test-value-32chars-xxxx" in keys
        assert "bad-key-test-value-32chars-xxxxx" not in keys

    def test_empty_cache_triggers_reload(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "reload-key-test-value-32chars-xx")
        # Force empty cache with recent timestamp to trigger reload via empty check
        api_key_auth._cached_keys = frozenset()
        api_key_auth._cache_timestamp = 999999999.0  # far future — but cache empty
        keys = api_key_auth._get_valid_keys()
        assert "reload-key-test-value-32chars-xx" in keys


# ---------------------------------------------------------------------------
# reset_valid_keys
# ---------------------------------------------------------------------------


class TestResetValidKeys:
    def test_clears_cache_and_revocation(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "key-x-test-value-32chars-xxxxxxx")
        api_key_auth._get_valid_keys()
        api_key_auth._revoked_keys.add("key-x-test-value-32chars-xxxxxxx")
        api_key_auth.reset_valid_keys()
        assert api_key_auth._cached_keys == frozenset()
        assert api_key_auth._cache_timestamp == 0.0
        assert len(api_key_auth._revoked_keys) == 0

    def test_after_reset_cache_reloads_on_next_call(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "before-reset-test-value-32chars-x")
        api_key_auth._get_valid_keys()
        api_key_auth.reset_valid_keys()
        monkeypatch.setenv("ACGS_API_KEYS", "after-reset-test-value-32chars-xx")
        keys = api_key_auth._get_valid_keys()
        assert "after-reset-test-value-32chars-xx" in keys
        assert "before-reset-test-value-32chars-x" not in keys


# ---------------------------------------------------------------------------
# revoke_api_key
# ---------------------------------------------------------------------------


class TestRevokeApiKey:
    def test_revoke_empty_string_is_no_op(self):
        original_count = len(api_key_auth._revoked_keys)
        api_key_auth.revoke_api_key("")
        assert len(api_key_auth._revoked_keys) == original_count

    def test_revoke_adds_key_to_revoked_set(self):
        api_key_auth.revoke_api_key("to-revoke-test-value-32chars-xxx")
        assert "to-revoke-test-value-32chars-xxx" in api_key_auth._revoked_keys

    def test_revoke_removes_from_cached_keys(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv(
            "ACGS_API_KEYS", "keep-key-test-value-32chars-xxxx,remove-key-test-value-32chars-xxx"
        )
        api_key_auth._get_valid_keys()
        assert "remove-key-test-value-32chars-xxx" in api_key_auth._cached_keys
        api_key_auth.revoke_api_key("remove-key-test-value-32chars-xxx")
        assert "remove-key-test-value-32chars-xxx" not in api_key_auth._cached_keys
        assert "keep-key-test-value-32chars-xxxx" in api_key_auth._cached_keys

    def test_revoke_when_cache_empty_does_not_error(self):
        api_key_auth._cached_keys = frozenset()
        api_key_auth.revoke_api_key("some-key-test-value-32chars-xxxx")
        assert "some-key-test-value-32chars-xxxx" in api_key_auth._revoked_keys

    def test_revoke_prevents_future_acceptance(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "target-key-test-value-32chars-xx")
        assert api_key_auth._is_known_api_key("target-key-test-value-32chars-xx") is True
        api_key_auth.revoke_api_key("target-key-test-value-32chars-xx")
        assert api_key_auth._is_known_api_key("target-key-test-value-32chars-xx") is False


# ---------------------------------------------------------------------------
# _is_signup_key — ImportError branch
# ---------------------------------------------------------------------------


class TestIsSignupKey:
    def test_import_error_returns_false(self, monkeypatch):
        """When signup module is unavailable, returns False without raising."""
        api_key_auth._cached_get_account = None

        def _raise_import(*args, **kwargs):
            raise ImportError("no signup module")

        with patch.dict(
            api_key_auth._is_signup_key.__globals__,
            {"__builtins__": __builtins__},
        ):
            # Patch the import inside the function via sys.modules
            import sys

            # Remove any cached reference so the lazy import fires
            signup_key = "enhanced_agent_bus.api.routes.signup"
            original = sys.modules.pop(signup_key, None)
            # Also remove any parent path entries that would allow reimport
            blocked = {signup_key: None}
            with patch.dict(sys.modules, blocked):
                result = api_key_auth._is_signup_key("any-key-test-value-32chars-xxxxx")
            if original is not None:
                sys.modules[signup_key] = original
        assert result is False

    def test_signup_key_returned_from_cached_getter(self, monkeypatch):
        """When get_account is cached and finds the key, returns True."""
        mock_getter = MagicMock(return_value={"id": "acct-1"})
        api_key_auth._cached_get_account = mock_getter
        result = api_key_auth._is_signup_key("signup-key-1-test-value-32chars-x")
        assert result is True
        mock_getter.assert_called_once_with("signup-key-1-test-value-32chars-x")

    def test_signup_key_not_found_returns_false(self):
        """When get_account returns None, returns False."""
        mock_getter = MagicMock(return_value=None)
        api_key_auth._cached_get_account = mock_getter
        result = api_key_auth._is_signup_key("not-found-test-value-32chars-xxx")
        assert result is False

    def test_cached_getter_not_reset_on_second_call(self):
        """_cached_get_account is only populated once."""
        mock_getter = MagicMock(return_value=None)
        api_key_auth._cached_get_account = mock_getter
        api_key_auth._is_signup_key("key-1-test-value-32chars-xxxxxxxx")
        api_key_auth._is_signup_key("key-2-test-value-32chars-xxxxxxxx")
        assert api_key_auth._cached_get_account is mock_getter


# ---------------------------------------------------------------------------
# _is_known_api_key
# ---------------------------------------------------------------------------


class TestIsKnownApiKey:
    def test_revoked_key_rejected_immediately(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "valid-key-test-value-32chars-xxxx")
        api_key_auth._get_valid_keys()
        api_key_auth._revoked_keys.add("valid-key-test-value-32chars-xxxx")
        assert api_key_auth._is_known_api_key("valid-key-test-value-32chars-xxxx") is False

    def test_valid_static_key_accepted(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "static-key-test-value-32chars-xxx")
        assert api_key_auth._is_known_api_key("static-key-test-value-32chars-xxx") is True

    def test_unknown_key_rejected(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        assert api_key_auth._is_known_api_key("totally-unknown-test-value-32ch-x") is False

    def test_signup_key_accepted_when_static_miss(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        mock_getter = MagicMock(return_value={"id": "u1"})
        api_key_auth._cached_get_account = mock_getter
        assert api_key_auth._is_known_api_key("signup-only-key-test-value-32ch-x") is True

    def test_revoked_check_uses_hmac_compare(self, monkeypatch):
        """Ensure constant-time comparison is used for revoked key check."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        api_key_auth._revoked_keys.add("rev-key-test-value-32chars-xxxxxx")
        calls = []
        original = hmac.compare_digest

        def tracking(a, b):
            calls.append((a, b))
            return original(a, b)

        monkeypatch.setattr(api_key_auth.hmac, "compare_digest", tracking)
        result = api_key_auth._is_known_api_key("rev-key-test-value-32chars-xxxxxx")
        assert result is False
        assert any(
            c[1] == "rev-key-test-value-32chars-xxxxxx"
            or c[0] == "rev-key-test-value-32chars-xxxxxx"
            for c in calls
        )

    def test_loop_iterates_past_non_matching_key(self, monkeypatch):
        """Cover the loop-continue arc in _is_known_api_key (171->170).

        Force the valid_keys frozenset to have two entries and verify the function
        reaches True even when the first entry in the iteration does not match.
        We use a frozenset with a known-mismatch first element by patching
        _get_valid_keys directly.
        """
        # Patch _get_valid_keys to return a controlled two-element set
        sentinel_other = "other-key-z99-test-value-32chars-x"
        sentinel_target = "target-key-a01-test-value-32chars-x"
        # Build a frozenset; iterate it to find the order Python picks.
        fs = frozenset({sentinel_other, sentinel_target})
        monkeypatch.setattr(api_key_auth, "_get_valid_keys", lambda: fs)
        monkeypatch.setattr(api_key_auth, "_is_signup_key", lambda k: False)
        # Regardless of iteration order, both keys must be accepted and
        # at least one will cause the loop to continue past a False comparison.
        assert api_key_auth._is_known_api_key(sentinel_other) is True
        assert api_key_auth._is_known_api_key(sentinel_target) is True


# ---------------------------------------------------------------------------
# require_api_key (async)
# ---------------------------------------------------------------------------


class TestRequireApiKey:
    async def test_missing_key_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            await api_key_auth.require_api_key(None)
        assert exc.value.status_code == 401
        assert "Missing" in exc.value.detail

    async def test_empty_string_raises_401(self):
        with pytest.raises(HTTPException) as exc:
            await api_key_auth.require_api_key("")
        assert exc.value.status_code == 401

    async def test_invalid_key_raises_401(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ACGS_API_KEYS", raising=False)
        with pytest.raises(HTTPException) as exc:
            await api_key_auth.require_api_key("not-a-real-key")
        assert exc.value.status_code == 401
        assert "Invalid" in exc.value.detail

    async def test_valid_key_returns_key(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "prod-key-ok-test-value-32chars-xx")
        result = await api_key_auth.require_api_key("prod-key-ok-test-value-32chars-xx")
        assert result == "prod-key-ok-test-value-32chars-xx"

    async def test_revoked_key_raises_401(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ACGS_API_KEYS", "revokable-key-test-value-32chars-x")
        api_key_auth._get_valid_keys()
        api_key_auth.revoke_api_key("revokable-key-test-value-32chars-x")
        with pytest.raises(HTTPException) as exc:
            await api_key_auth.require_api_key("revokable-key-test-value-32chars-x")
        assert exc.value.status_code == 401
