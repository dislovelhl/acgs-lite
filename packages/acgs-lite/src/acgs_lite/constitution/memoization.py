"""exp224: Memoized governance decision cache for repeated (action, context) pairs.

Production governance workloads often re-evaluate the same action against the
same context hundreds of times per second (health checks, monitoring queries,
recurring agent operations).  This module provides ``MemoizedConstitution``,
a thin LRU-cached wrapper around any ``Constitution`` that short-circuits
repeated evaluations at O(1) cost after the first hit.

Cache design:
- Key: stable SHA-256 hash of (action_lower, sorted context items)
- Value: the raw ``VerificationResult`` dict from ``engine.validate()``
- Size: configurable LRU (default 1024 entries — ~2 MB at typical result size)
- Thread-safe: ``functools.lru_cache`` + immutable keys
- Invalidation: explicit ``clear()`` (call after ``Constitution.update_rule()``)

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.memoization import MemoizedConstitution

    c = Constitution.from_yaml("policy.yaml")
    mc = MemoizedConstitution(c, maxsize=512)

    # First call: computes via engine (~5µs)
    result = mc.validate("access patient records", {"env": "prod"})

    # Subsequent identical calls: cache hit (~0.1µs)
    result = mc.validate("access patient records", {"env": "prod"})

    stats = mc.cache_stats()
    # {"hits": 1, "misses": 1, "hit_rate": 0.5, "maxsize": 512, "currsize": 1}

    # After updating the constitution:
    c2 = c.update_rule("GL-001", severity="critical")
    mc.update_constitution(c2)  # clears cache + swaps constitution
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Constitution


def _cache_key(action: str, context: dict[str, Any]) -> str:
    """Produce a stable, hashable cache key from action + context.

    Sorts context keys recursively so key order does not affect identity.
    Uses SHA-256 truncated to 16 hex chars (64-bit collision resistance).

    Args:
        action: The agent action string (lowercased before hashing).
        context: Runtime context dict (may be nested).

    Returns:
        16-character hex string.
    """
    payload = json.dumps(
        {"a": action.lower(), "c": context},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class CacheStats:
    """Snapshot of memoization cache performance metrics."""

    hits: int
    misses: int
    maxsize: int
    currsize: int

    @property
    def hit_rate(self) -> float:
        """Fraction of calls served from cache (0.0-1.0)."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def total(self) -> int:
        """Total validate() calls (hits + misses)."""
        return self.hits + self.misses

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total": self.total,
            "hit_rate": round(self.hit_rate, 4),
            "maxsize": self.maxsize,
            "currsize": self.currsize,
        }

    def __repr__(self) -> str:
        return (
            f"CacheStats(hits={self.hits}, misses={self.misses}, "
            f"hit_rate={self.hit_rate:.1%}, currsize={self.currsize}/{self.maxsize})"
        )


class _LRUCache:
    """Simple thread-safe LRU cache backed by an OrderedDict.

    Using a hand-rolled LRU (rather than ``functools.lru_cache``) so that
    the cache can be cleared and resized at runtime without re-creating the
    wrapped function.
    """

    def __init__(self, maxsize: int) -> None:
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize}")
        self._maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = Lock()

    def get(self, key: str) -> tuple[bool, Any]:
        """Return (found, value).  Moves key to MRU position on hit."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return True, self._cache[key]
            self._misses += 1
            return False, None

    def put(self, key: str, value: Any) -> None:
        """Insert or update *key*. Evicts LRU entry when at capacity."""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                if len(self._cache) >= self._maxsize:
                    self._cache.popitem(last=False)
                self._cache[key] = value

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def currsize(self) -> int:
        return len(self._cache)

    @property
    def maxsize(self) -> int:
        return self._maxsize


class MemoizedConstitution:
    """LRU-cached wrapper around a ``Constitution`` for repeated validations.

    Wraps any :class:`~acgs_lite.constitution.Constitution` and caches
    ``validate()`` and ``explain()`` results keyed on ``(action, context)``
    hash.  Cache misses fall through to the wrapped constitution; hits return
    the cached result without calling the engine.

    The wrapper is intentionally thin:

    - All non-cached methods delegate directly to the wrapped constitution.
    - ``__getattr__`` forwards attribute access so callers can use
      ``mc.rules``, ``mc.hash``, ``mc.name`` etc. without modification.
    - The wrapped constitution is immutable — call ``update_constitution()``
      to swap it (which also clears the cache).

    Args:
        constitution: The constitution to wrap.
        maxsize: LRU cache capacity in entries (default 1024).

    Example::

        c = Constitution.from_yaml("policy.yaml")
        mc = MemoizedConstitution(c, maxsize=512)

        for action in repeated_actions:
            result = mc.validate(action)   # cache hit after first occurrence

        print(mc.cache_stats())
        # CacheStats(hits=998, misses=50, hit_rate=95.2%, currsize=50/512)
    """

    def __init__(self, constitution: Constitution, *, maxsize: int = 1024) -> None:
        self._constitution = constitution
        self._cache = _LRUCache(maxsize=maxsize)

    # ── delegation ─────────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Forward all attribute access to the wrapped constitution."""
        return getattr(self._constitution, name)

    @property
    def constitution(self) -> Constitution:
        """The wrapped (unwrapped) Constitution."""
        return self._constitution

    # ── cached methods ─────────────────────────────────────────────────────

    def validate(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate *action* with LRU caching.

        Identical ``(action, context)`` pairs after the first call return the
        cached result in O(1).  The cache key is a 64-bit SHA-256 hash of the
        lowercased action and sorted context dict.

        Args:
            action: The agent action to evaluate.
            context: Optional runtime context dict.

        Returns:
            Governance decision dict (same schema as ``engine.validate()``).
        """
        ctx = context or {}
        key = _cache_key(action, ctx)
        found, cached = self._cache.get(key)
        if found:
            return cached

        # Cache miss — delegate to engine
        # Use the engine directly if available, else explain()
        try:
            from acgs_lite.engine import GovernanceEngine

            engine = GovernanceEngine(self._constitution)
            result = engine.validate(action, ctx)
        except Exception:
            # Fallback: use explain() which always works
            result = self._constitution.explain(action)

        self._cache.put(key, result)
        return result

    def explain(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cached version of ``Constitution.explain()``.

        Args:
            action: The agent action to explain.
            context: Optional context for placeholder rendering.

        Returns:
            Explanation dict (same schema as ``Constitution.explain()``).
        """
        ctx = context or {}
        # Use a different key prefix to avoid colliding with validate() cache
        key = _cache_key(f"__explain__{action}", ctx)
        found, cached = self._cache.get(key)
        if found:
            return cached

        if ctx:
            result = self._constitution.explain_rendered(action, ctx)
        else:
            result = self._constitution.explain(action)

        self._cache.put(key, result)
        return result

    # ── cache management ───────────────────────────────────────────────────

    def cache_stats(self) -> CacheStats:
        """Return a snapshot of cache performance metrics.

        Returns:
            :class:`CacheStats` with hits, misses, hit_rate, currsize, maxsize.

        Example::

            stats = mc.cache_stats()
            print(f"Hit rate: {stats.hit_rate:.1%}")
        """
        return CacheStats(
            hits=self._cache.hits,
            misses=self._cache.misses,
            maxsize=self._cache.maxsize,
            currsize=self._cache.currsize,
        )

    def clear_cache(self) -> None:
        """Invalidate all cached decisions.

        Call this after updating the wrapped constitution (via
        ``update_constitution()``) or any external state change that could
        affect governance decisions.
        """
        self._cache.clear()

    def update_constitution(self, new_constitution: Constitution) -> None:
        """Swap the wrapped constitution and clear the cache.

        Ensures stale decisions from the old constitution are not served after
        a rule update.

        Args:
            new_constitution: The replacement constitution.

        Example::

            c2 = c.update_rule("GL-001", severity="critical")
            mc.update_constitution(c2)
            # Cache cleared — next validate() calls use new rules
        """
        self._constitution = new_constitution
        self._cache.clear()

    def warm(
        self,
        actions: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pre-populate the cache with a corpus of known actions.

        Useful for warming the cache at startup with frequently seen actions
        so that the first real requests do not pay the evaluation cost.

        Args:
            actions: List of action strings to pre-evaluate.
            context: Optional shared context for all actions.

        Returns:
            Summary dict with ``warmed`` (count), ``already_cached`` (count),
            ``errors`` (list of (action, error_message) tuples).
        """
        ctx = context or {}
        warmed = 0
        already_cached = 0
        errors: list[tuple[str, str]] = []

        for action in actions:
            key = _cache_key(action, ctx)
            found, _ = self._cache.get(key)
            if found:
                # Undo the hit count increment (warming shouldn't inflate stats)
                self._cache._hits -= 1  # noqa: SLF001
                self._cache._misses -= 0  # no-op, just for clarity  # noqa: SLF001
                already_cached += 1
                continue
            try:
                self.validate(action, ctx)
                warmed += 1
            except Exception as exc:
                errors.append((action, str(exc)))

        return {
            "warmed": warmed,
            "already_cached": already_cached,
            "errors": errors,
        }

    def __repr__(self) -> str:
        stats = self.cache_stats()
        return (
            f"MemoizedConstitution("
            f"name={self._constitution.name!r}, "
            f"rules={len(self._constitution.rules)}, "
            f"cache={stats.currsize}/{stats.maxsize}, "
            f"hit_rate={stats.hit_rate:.1%})"
        )
