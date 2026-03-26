# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/utils.py
Targets ≥90% coverage of all utility functions and classes.
"""

import time
from collections import OrderedDict
from datetime import UTC, timezone
from unittest.mock import patch

from enhanced_agent_bus.utils import (
    LRUCache,
    TTLCache,
    get_iso_timestamp,
    redact_error_message,
)

# ---------------------------------------------------------------------------
# redact_error_message
# ---------------------------------------------------------------------------


class TestRedactErrorMessage:
    def test_plain_message_unchanged(self):
        err = ValueError("something went wrong")
        result = redact_error_message(err)
        assert result == "something went wrong"

    def test_redacts_http_url(self):
        err = Exception("Failed to connect to http://example.com/api/v1")
        result = redact_error_message(err)
        assert "http://example.com/api/v1" not in result
        assert "[REDACTED_URI]" in result

    def test_redacts_https_url(self):
        err = Exception("GET https://secret.service.internal/token failed")
        result = redact_error_message(err)
        assert "https://secret.service.internal/token" not in result
        assert "[REDACTED_URI]" in result

    def test_redacts_redis_url(self):
        err = Exception("Cannot reach redis://localhost:6379/0")
        result = redact_error_message(err)
        assert "redis://localhost:6379/0" not in result
        assert "[REDACTED_URI]" in result

    def test_redacts_key_credential(self):
        err = Exception("Invalid key=supersecret123 provided")
        result = redact_error_message(err)
        assert "supersecret123" not in result
        assert "key=[REDACTED]" in result

    def test_redacts_token_credential(self):
        err = Exception("token=eyJhbGciOiJIUzI1NiJ9.abc is invalid")
        result = redact_error_message(err)
        assert "eyJhbGciOiJIUzI1NiJ9.abc" not in result
        assert "token=[REDACTED]" in result

    def test_redacts_password_credential(self):
        err = Exception("password=hunter2 rejected")
        result = redact_error_message(err)
        assert "hunter2" not in result
        assert "password=[REDACTED]" in result

    def test_redacts_secret_credential(self):
        err = Exception("secret=my-top-secret-value")
        result = redact_error_message(err)
        assert "my-top-secret-value" not in result
        assert "secret=[REDACTED]" in result

    def test_redacts_auth_credential(self):
        err = Exception("auth=Bearer_token_value request failed")
        result = redact_error_message(err)
        assert "Bearer_token_value" not in result
        assert "auth=[REDACTED]" in result

    def test_redacts_pwd_credential(self):
        err = Exception("pwd=mypassword123 is wrong")
        result = redact_error_message(err)
        assert "mypassword123" not in result
        assert "pwd=[REDACTED]" in result

    def test_redacts_unix_file_path(self):
        err = Exception("File not found: /home/user/secrets/config.json")
        result = redact_error_message(err)
        assert "/home/user/secrets/config.json" not in result
        assert "[REDACTED_PATH]" in result

    def test_redacts_nested_path(self):
        err = Exception("Cannot read /etc/ssl/private/key.pem")
        result = redact_error_message(err)
        assert "/etc/ssl/private/key.pem" not in result
        assert "[REDACTED_PATH]" in result

    def test_combined_redactions(self):
        err = Exception("Error: key=abc123 at /var/app/config.yml via https://api.example.com/v1")
        result = redact_error_message(err)
        assert "abc123" not in result
        assert "https://api.example.com/v1" not in result
        assert "/var/app/config.yml" not in result

    def test_case_insensitive_credentials(self):
        err = Exception("KEY=SomeSecret TOKEN=AnotherSecret")
        result = redact_error_message(err)
        assert "SomeSecret" not in result
        assert "AnotherSecret" not in result

    def test_empty_error_message(self):
        err = Exception("")
        result = redact_error_message(err)
        assert result == ""

    def test_returns_string(self):
        err = RuntimeError("test error")
        result = redact_error_message(err)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_iso_timestamp
# ---------------------------------------------------------------------------


class TestGetIsoTimestamp:
    def test_returns_string(self):
        ts = get_iso_timestamp()
        assert isinstance(ts, str)

    def test_contains_utc_offset(self):
        ts = get_iso_timestamp()
        # ISO format with timezone.utc timezone ends with +00:00
        assert "+00:00" in ts

    def test_format_parseable(self):
        from datetime import datetime

        ts = get_iso_timestamp()
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

    def test_recent_timestamp(self):
        from datetime import datetime

        before = datetime.now(UTC)
        ts = get_iso_timestamp()
        after = datetime.now(UTC)
        parsed = datetime.fromisoformat(ts)
        assert before <= parsed <= after


# ---------------------------------------------------------------------------
# LRUCache
# ---------------------------------------------------------------------------


class TestLRUCache:
    def test_basic_set_and_get(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=10)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_get_missing_key_returns_none(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=10)
        assert cache.get("missing") is None

    def test_overwrite_existing_key(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=5)
        cache.set("x", 10)
        cache.set("x", 20)
        assert cache.get("x") == 20

    def test_eviction_on_full(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access "a" to make it recently used
        cache.get("a")
        # Adding "d" should evict "b" (LRU)
        cache.set("d", 4)
        # "b" should be evicted
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_clear_empties_cache(self):
        cache: LRUCache[str, str] = LRUCache(maxsize=10)
        cache.set("key1", "val1")
        cache.set("key2", "val2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_clear_empties_backing_and_view(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.clear()
        assert len(cache._cache) == 0
        assert len(cache._backing) == 0

    def test_ordereddict_view_kept_in_sync(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.set("b", 2)
        assert set(cache._cache.keys()) == {"a", "b"}

    def test_get_moves_to_end_in_view(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        keys = list(cache._cache.keys())
        assert keys[-1] == "a"

    def test_default_maxsize(self):
        cache: LRUCache[str, int] = LRUCache()
        assert cache._maxsize == 1000

    def test_eviction_prunes_ordereddict_view(self):
        cache: LRUCache[int, str] = LRUCache(maxsize=2)
        cache.set(1, "one")
        cache.set(2, "two")
        # This should evict key 1 from backing (LRU)
        cache.set(3, "three")
        # The view should not contain key 1 anymore
        assert 1 not in cache._cache

    def test_set_existing_key_moves_to_end(self):
        cache: LRUCache[str, int] = LRUCache(maxsize=5)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Update "a" — should move it to end
        cache.set("a", 100)
        keys = list(cache._cache.keys())
        assert keys[-1] == "a"
        assert cache.get("a") == 100

    def test_large_cache(self):
        cache: LRUCache[int, int] = LRUCache(maxsize=100)
        for i in range(100):
            cache.set(i, i * 2)
        for i in range(100):
            assert cache.get(i) == i * 2

    def test_get_key_in_backing_not_in_view(self):
        """Cover branch: key exists in _backing but not in _cache OrderedDict view.

        This exercises the else-branch of 'if key in self._cache' in get().
        """
        cache: LRUCache[str, int] = LRUCache(maxsize=10)
        # Directly insert into _backing only (bypass set() which also updates _cache)
        cache._backing["orphan"] = 42
        # _cache does NOT have "orphan", so the 'if key in self._cache' branch is False
        result = cache.get("orphan")
        assert result == 42


# ---------------------------------------------------------------------------
# TTLCache
# ---------------------------------------------------------------------------


class TestTTLCache:
    def test_basic_set_and_get(self):
        cache: TTLCache[str, int] = TTLCache(maxsize=100, ttl_seconds=60)
        cache.set("key", 42)
        assert cache.get("key") == 42

    def test_get_missing_key_returns_none(self):
        cache: TTLCache[str, int] = TTLCache()
        assert cache.get("nonexistent") is None

    def test_missing_increments_misses(self):
        cache: TTLCache[str, int] = TTLCache()
        cache.get("missing")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_hit_increments_hits(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        cache.set("k", 99)
        cache.get("k")
        stats = cache.get_stats()
        assert stats["hits"] == 1

    def test_expired_entry_returns_none(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=0.01)
        cache.set("expiring", "value")
        time.sleep(0.02)
        result = cache.get("expiring")
        assert result is None

    def test_expired_entry_increments_misses(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=0.01)
        cache.set("expiring", "value")
        time.sleep(0.02)
        cache.get("expiring")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_expired_entry_removed_from_cache(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=0.01)
        cache.set("expiring", "value")
        time.sleep(0.02)
        cache.get("expiring")
        assert "expiring" not in cache._cache

    def test_custom_ttl_per_entry(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=60)
        cache.set("short", "val", ttl=0.01)
        time.sleep(0.02)
        assert cache.get("short") is None

    def test_custom_ttl_none_uses_default(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        cache.set("k", 1, ttl=None)
        assert cache.get("k") == 1

    def test_lru_eviction_when_over_capacity(self):
        cache: TTLCache[int, str] = TTLCache(maxsize=3, ttl_seconds=60)
        cache.set(1, "one")
        cache.set(2, "two")
        cache.set(3, "three")
        cache.set(4, "four")  # Should evict oldest (1)
        assert 1 not in cache._cache
        assert cache.get(2) == "two"
        assert cache.get(3) == "three"
        assert cache.get(4) == "four"

    def test_set_existing_key_moves_to_end(self):
        cache: TTLCache[str, int] = TTLCache(maxsize=3, ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Re-set "a" to move it to end
        cache.set("a", 10)
        # Now "b" is LRU; adding "d" evicts "b"
        cache.set("d", 4)
        assert cache.get("b") is None
        assert cache.get("a") == 10

    def test_clear_resets_all(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        cache.set("x", 1)
        cache.get("x")
        cache.get("missing")
        cache.clear()
        assert len(cache) == 0
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cleanup_expired_removes_stale(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=0.01)
        cache.set("a", "val_a")
        cache.set("b", "val_b")
        time.sleep(0.02)
        removed = cache.cleanup_expired()
        assert removed == 2
        assert len(cache) == 0

    def test_cleanup_expired_keeps_valid(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=60)
        cache.set("keep", "val")
        removed = cache.cleanup_expired()
        assert removed == 0
        assert cache.get("keep") == "val"

    def test_cleanup_expired_mixed(self):
        cache: TTLCache[str, str] = TTLCache(ttl_seconds=60)
        cache.set("keep", "val_keep")
        cache.set("expire", "val_expire", ttl=0.01)
        time.sleep(0.02)
        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.get("keep") == "val_keep"

    def test_get_stats_structure(self):
        cache: TTLCache[str, int] = TTLCache(maxsize=50, ttl_seconds=120)
        stats = cache.get_stats()
        assert "size" in stats
        assert "maxsize" in stats
        assert "ttl_seconds" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats

    def test_get_stats_hit_rate_zero_when_no_requests(self):
        cache: TTLCache[str, int] = TTLCache()
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_get_stats_hit_rate_calculation(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        cache.set("k", 1)
        cache.get("k")  # hit
        cache.get("missing")  # miss
        stats = cache.get_stats()
        assert abs(stats["hit_rate"] - 0.5) < 1e-9

    def test_len_reflects_current_entries(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        assert len(cache) == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2
        cache.clear()
        assert len(cache) == 0

    def test_contains_true_for_valid(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        cache.set("present", 7)
        assert "present" in cache

    def test_contains_false_for_missing(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
        assert "absent" not in cache

    def test_contains_false_for_expired(self):
        cache: TTLCache[str, int] = TTLCache(ttl_seconds=0.01)
        cache.set("k", 5)
        time.sleep(0.02)
        assert "k" not in cache

    def test_get_lru_moves_to_end(self):
        cache: TTLCache[str, int] = TTLCache(maxsize=5, ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # moves "a" to end
        keys = list(cache._cache.keys())
        assert keys[-1] == "a"

    def test_default_parameters(self):
        cache: TTLCache[str, str] = TTLCache()
        assert cache._maxsize == 10000
        assert cache._ttl == 300.0

    def test_stats_maxsize_and_ttl_reflected(self):
        cache: TTLCache[str, int] = TTLCache(maxsize=42, ttl_seconds=99)
        stats = cache.get_stats()
        assert stats["maxsize"] == 42
        assert stats["ttl_seconds"] == 99

    def test_multiple_evictions(self):
        cache: TTLCache[int, str] = TTLCache(maxsize=2, ttl_seconds=60)
        cache.set(1, "a")
        cache.set(2, "b")
        cache.set(3, "c")  # evicts 1
        cache.set(4, "d")  # evicts 2
        assert cache.get(1) is None
        assert cache.get(2) is None
        assert cache.get(3) == "c"
        assert cache.get(4) == "d"
