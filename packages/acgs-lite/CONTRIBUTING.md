# Contributing to acgs-lite

Thank you for your interest in contributing to acgs-lite! This guide will help you get
started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/dislovelhl/acgs-lite.git
cd acgs-lite

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify the installation
make test-quick
```

No API keys are required. All tests use `InMemory*` stubs for external dependencies.
Set placeholder keys to silence import-time validation:

```bash
export OPENAI_API_KEY=test-key-for-unit-tests
export ANTHROPIC_API_KEY=test-key-for-unit-tests
```

## Workflow

1. **Fork** the repository and create a feature branch from `main`
2. **Write tests first** (TDD): tests go in `tests/`
3. **Implement** the feature or fix
4. **Run checks**:
   ```bash
   make lint          # Ruff linter
   make typecheck     # MyPy strict mode
   make test-quick    # Fast test suite
   make test-cov      # Full suite with coverage
   ```
5. **Submit** a pull request with conventional commit messages

## Commit Format

```
<type>: <description>
```

Types: `feat`, `fix`, `refactor`, `chore`, `test`, `ci`, `docs`

Examples:
- `feat: add HIPAA compliance mapping`
- `fix: handle empty constitution in validate()`
- `test: add MACI self-validation prevention tests`

## Code Style

- Python 3.10+ (use `X | Y` union syntax, not `Union[X, Y]`)
- Explicit type annotations everywhere
- `async def` for all I/O operations
- Pydantic models at API boundaries
- Ruff line length: 100

## Testing

- All tests use the `InMemory*` stub pattern (see `examples/mock_stub_testing/`)
- Never import live services in test code
- Run from repo root: `python -m pytest tests/ -v --import-mode=importlib`
- Target 70% minimum coverage (80% for core engine)

## Mock/Stub Pattern

Every external dependency is defined as a `typing.Protocol` with an `InMemory*` stub:

```python
# Define the interface
class MyBackend(Protocol):
    def save(self, key: str, value: str) -> None: ...
    def load(self, key: str) -> str | None: ...

# Provide the test stub alongside it
class InMemoryMyBackend:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.save_calls: list[tuple[str, str]] = []

    def save(self, key: str, value: str) -> None:
        self.store[key] = value
        self.save_calls.append((key, value))

    def load(self, key: str) -> str | None:
        return self.store.get(key)
```

## Architecture Guidelines

- **MACI separation**: agents never validate their own output (Proposer / Validator /
  Executor / Observer are separate roles)
- **Fail-closed**: governance decisions default to deny on error
- **Constitutional hash**: the canonical hash is `608508a9bd224290` -- flag any other
  value as stale

## What to Contribute

- Bug fixes with regression tests
- New compliance framework mappings
- New integration adapters (follow existing patterns in `src/acgs_lite/integrations/`)
- Documentation improvements
- Performance improvements with benchmarks

## Security Issues

If you discover a security vulnerability, please report it responsibly.
See [SECURITY.md](SECURITY.md) for our disclosure policy.

## License

By contributing, you agree that your contributions will be licensed under the
Apache-2.0 license. See [LICENSE](LICENSE) for details.
