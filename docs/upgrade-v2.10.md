# Upgrading to v2.10.0

## Breaking change: `require_auth` defaults to `True`

`create_governance_app()` now requires an API key by default. If you call it without
one, you'll get a `ValueError` at startup:

```
ValueError: require_auth=True but no api_key / ACGS_API_KEY configured.
Set api_key=... or ACGS_API_KEY env var, or pass require_auth=False to explicitly run
unauthenticated (not recommended for production).
```

### Who is affected

Anyone who calls `create_governance_app()` without passing `api_key` or setting
`ACGS_API_KEY` in the environment. This includes:

- Direct calls like `create_governance_app(constitution=...)`
- FastAPI integrations that mount the governance app without auth
- Scripts and tests that spin up the server locally

### Fix option 1 — Pass an API key (recommended for production)

```python
import os
from acgs_lite.server import create_governance_app

app = create_governance_app(
    api_key=os.environ["ACGS_API_KEY"],
    constitution=constitution,
)
```

Set the environment variable:

```bash
export ACGS_API_KEY="your-secret-key-here"
```

### Fix option 2 — Use the env var

Set `ACGS_API_KEY` and omit `api_key` from the call. The server picks it up
automatically:

```bash
export ACGS_API_KEY="your-secret-key-here"
```

```python
app = create_governance_app(constitution=constitution)
```

`ACGS_API_KEY` protects the main governance server created by
`create_governance_app()`. The lifecycle router uses a separate
`ACGS_LIFECYCLE_API_KEY` when `include_lifecycle=True`; setting only the
lifecycle key does not satisfy the main server startup requirement.

Keep the main API key and lifecycle API key separate in deployment manifests;
using the lifecycle key alone intentionally keeps the main server fail-closed.

### Fix option 3 — Opt out for local dev

```python
app = create_governance_app(
    require_auth=False,
    constitution=constitution,
)
```

> **Warning:** `require_auth=False` disables token validation on all governance
> endpoints. Only use this in local development or trusted internal networks.

## Why this changed

v2.9.x defaulted to `require_auth=None` which silently accepted unauthenticated
requests when no API key was configured. This meant governance validation was
reachable without credentials in default deployments — a fail-open behavior
incompatible with ACGS's security model.

v2.10.0 flips the default to `require_auth=True` so the server fails closed at
startup rather than silently accepting requests without authentication.

## Other changes in v2.10.0

- `PostgresBundleStore` and `SQLiteBundleStore` are now exported from
  `acgs_lite` directly (`from acgs_lite import PostgresBundleStore`).
- Optional extras (`z3-solver`, `redis`, Lean) no longer crash `import acgs_lite`
  when not installed — they raise `ImportError` with an install hint on first use.
- See [CHANGELOG.md](changelog.md) for the full list.

### Additional changes

**Per-call strict override (`validate(strict=False)`)**

`GovernanceEngine.validate()` now accepts a `strict` keyword argument. Pass
`strict=False` to run a single call in non-strict mode without mutating
`engine.strict` and without a context manager:

```python
result = engine.validate(text, agent_id="agent-1", strict=False)
```

This is the recommended pattern for async and concurrent callers. The
`non_strict()` context manager remains available for backward compatibility but
carries a thread-safety caveat documented in its docstring.

**Lazy `transformers`/`torch` import in `scoring.py`**

The `transformers` and `torch` packages are now imported lazily inside
`scoring.py`. In the release benchmark environment, cold `import acgs_lite`
time dropped from ~3.5 s to ~218 ms for users who have the heavy ML stack
installed but do not use semantic scoring. Treat these numbers as
environment-specific reference data, not a product guarantee.

**Python 3.10 compatibility**

The package now supports Python 3.10 through 3.13. Specific fixes:

- `datetime.UTC` (added in 3.11) replaced with `timezone.utc` throughout.
- `StrEnum` (added in 3.11) polyfilled in `_compat.py`.
- `tomllib` (added in 3.11) falls back to the `tomli` third-party package on
  3.10 (already a dependency via `pyproject.toml` optional extras).

**`InMemoryTrajectoryStore` thread safety**

All mutating operations on `InMemoryTrajectoryStore` now hold a
`threading.RLock`. Concurrent agents sharing a single in-memory store no longer
race on read-modify-write cycles.

**`PostgresBundleStore` correctness fixes**

Several correctness bugs were fixed in the Postgres backend (shipped in this
same v2.10.0 release):

- `load_bundles(limit=None)` previously generated invalid SQL (`LIMIT NULL`) —
  now emits `LIMIT ALL`.
- `_init_schema()` concurrent cold-start race fixed with
  `ON CONFLICT DO NOTHING` on the schema migrations insert.
- `save_bundle_transactional()` phantom-row CAS race fixed with
  `pg_advisory_xact_lock` before `SELECT FOR UPDATE`.
- Context manager (`with PostgresBundleStore(...) as store:`) is now supported
  via `__enter__`/`__exit__`.
