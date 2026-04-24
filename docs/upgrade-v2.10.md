# Upgrading to v2.10.0

## Breaking change: `require_auth` defaults to `True`

`create_governance_app()` now requires an API key by default. If you call it without
one, you'll get a `ValueError` at startup:

```
ValueError: require_auth=True but no api_key / ACGS_API_KEY configured.
Pass api_key=... or set ACGS_LIFECYCLE_API_KEY env var, or pass require_auth=False.
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
- See [CHANGELOG.md](../CHANGELOG.md) for the full list.
