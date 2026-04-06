# Contributing: Building the Future of AI Governance

**Meta Description**: Join the ACGS-Lite community. Learn how to contribute new compliance mappings, integration adapters, and core engine improvements using our 2026-ready development workflow.

---

Thank you for your interest in contributing to ACGS-Lite! We are building the foundational infrastructure for safe, autonomous AI, and we welcome contributions from developers, security researchers, and policy experts.

## 🏗️ What to Contribute

We are particularly looking for contributions in these areas:
1.  **Compliance Frameworks**: Mapping new regional or industry regulations (e.g., Canadian AIDA, Japan AI Guidelines) to ACGS rule templates.
2.  **Integration Adapters**: Adding support for new AI frameworks or tool ecosystems (e.g., PydanticAI, Swarms, Magentic).
3.  **Formal Verification**: Improving our Z3 and Lean 4 verification modules.
4.  **Documentation**: Use cases, tutorials, and security best practices.

## 🛠️ Development Setup

ACGS-Lite is a Python 3.10+ project. We use `ruff` for linting and `pytest` for testing.

```bash
# 1. Clone the repo
git clone https://github.com/dislovelhl/acgs-lite.git
cd acgs-lite

# 2. Install in editable mode with dev dependencies
pip install -e ".[dev,mcp,all]"

# 3. Verify the installation
make test-quick
```

**Note**: All tests use `InMemory` stubs. You do **not** need live API keys for OpenAI or Anthropic to run the test suite.

## 🧪 Testing Policy (TDD)

We follow a strict **Test-Driven Development** workflow. Every feature or fix must be accompanied by tests.
*   **Location**: All tests go in the `tests/` directory.
*   **Stubs**: Use the `InMemoryAuditBackend` and `InMemoryGovernanceEngine` patterns to keep tests fast and deterministic.
*   **Coverage**: We target **80%+ coverage** for the core engine and **70%+** for integration adapters.

## 📏 Coding Standards

- **Explicit Typing**: Use Python 3.10+ type hints (`X | Y` instead of `Union[X, Y]`).
- **Async First**: All I/O-bound integrations (network calls, file writes) must be `async`.
- **Fail-Closed**: Always design for the "worst-case" failure. If a check fails to run, it must block the action.
- **Line Length**: 100 characters (enforced by Ruff).

## 🚢 Pull Request Process

1.  **Fork** the repository.
2.  Create a **Feature Branch** (`git checkout -b feat/my-new-feature`).
3.  Implement your changes and add tests.
4.  Run the verification suite:
    ```bash
    make lint
    make typecheck
    make test-cov
    ```
5.  Submit your PR with a **Conventional Commit** message (e.g., `feat: add NIST AI RMF mapping`).

## 🛡️ Security Disclosures

If you find a security vulnerability, please do **not** open a public issue. Instead, follow our [Security Policy](SECURITY.md) to report it responsibly.

## 📜 License

By contributing to ACGS-Lite, you agree that your contributions will be licensed under the **Apache-2.0 License**.
