# Contributing to ACGS

## Scope

This repository publishes the ACGS library on PyPI as `acgs`. The compatibility import namespace `acgs_lite` remains supported inside the codebase. Naming rules are defined in [docs/brand-architecture.md](docs/brand-architecture.md).

## Development Setup

```bash
make setup
make test-quick
make lint
```

All repository `pytest` invocations should include `--import-mode=importlib`.

## Contribution Terms

- The repository source code is licensed under `Apache-2.0`.
- By submitting a contribution, you agree that your contribution is made available under `Apache-2.0`.

## Pull Requests

- Keep changes scoped and explain user-visible behavior changes.
- Add or update tests when behavior changes.
- Prefer the canonical public package name `acgs` in external-facing docs and release notes.
- Use `acgs_lite` only when an exact import path or filesystem path requires it.
