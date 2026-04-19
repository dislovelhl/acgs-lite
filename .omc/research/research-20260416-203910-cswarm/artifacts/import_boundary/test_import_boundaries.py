"""Enforce that constitutional_swarm imports only from acgs-lite's public API.

Rationale
---------
The research report (Stage 5) flagged 4-of-8 importing files reaching into
`acgs_lite.scoring.*`, `acgs_lite.z3_verify.*`, and `acgs_lite.constitution.*` —
internal sub-module paths that can break silently if acgs-lite refactors its
namespace without a major version bump.

This test asserts the coupling is bounded to acgs-lite's top-level `__init__.py`
public surface. A violation forces the fix at the right layer: either promote
the needed symbol to `acgs_lite/__init__.py`, or add a narrow adapter in
constitutional_swarm that depends only on the public API.

Adding a new exception MUST include:
- An inline comment explaining why the internal path is required
- A tracking issue link
- Either (a) a plan to promote the symbol upstream, or (b) a stable-contract
  note from the acgs-lite maintainer acknowledging the path as supported.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

SRC_ROOT = pathlib.Path(__file__).parent.parent / "src" / "constitutional_swarm"

# Any dotted acgs_lite path deeper than `acgs_lite.<symbol>` is a contract violation
# unless explicitly grandfathered in ALLOWED_INTERNAL_EXCEPTIONS below.
BANNED_INTERNAL_PATTERNS = (
    "acgs_lite.scoring",
    "acgs_lite.z3_verify",
    "acgs_lite.constitution",
    "acgs_lite.engine",
    "acgs_lite._internal",
)

# Format: {(relative_path, imported_module): "reason + tracking link"}
# Empty to start — make the test green by fixing, not by adding exceptions.
ALLOWED_INTERNAL_EXCEPTIONS: dict[tuple[str, str], str] = {
    # Example (do NOT add without review):
    # ("src/constitutional_swarm/dna.py", "acgs_lite.z3_verify"):
    #     "Z3VerifyResult not re-exported yet — tracked in acgs-lite#1234",
}


def _iter_py_files(root: pathlib.Path):
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def _extract_imports(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return (lineno, dotted_module_name) for every import in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # absolute imports only
                out.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
    return out


def _violates(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in BANNED_INTERNAL_PATTERNS)


def test_no_acgs_lite_internal_imports() -> None:
    """No file under src/constitutional_swarm/ imports acgs_lite internal sub-modules."""
    violations: list[str] = []
    package_root = SRC_ROOT.parent.parent  # repo root
    for path in _iter_py_files(SRC_ROOT):
        rel = str(path.relative_to(package_root))
        for line, module in _extract_imports(path):
            if not _violates(module):
                continue
            if (rel, module) in ALLOWED_INTERNAL_EXCEPTIONS:
                continue
            if any(
                (rel, pat) in ALLOWED_INTERNAL_EXCEPTIONS
                for pat in BANNED_INTERNAL_PATTERNS
                if module.startswith(pat)
            ):
                continue
            violations.append(f"  {rel}:{line}  imports '{module}'")

    assert not violations, (
        "\nacgs-lite internal-path imports detected.\n\n".join(violations)
        + "\n\nFixes (in order of preference):\n"
        + "  1. Promote the needed symbol(s) to acgs_lite/__init__.py and import from there.\n"
        + "  2. Add a narrow adapter in constitutional_swarm that wraps the internal call.\n"
        + "  3. Only as a last resort: add an entry to ALLOWED_INTERNAL_EXCEPTIONS with a\n"
        + "     tracking link and upstream-promotion plan.\n"
    )


def test_exceptions_have_tracking() -> None:
    """Any grandfathered exception must carry a non-empty justification."""
    bad = [k for k, v in ALLOWED_INTERNAL_EXCEPTIONS.items() if not v or len(v) < 20]
    assert not bad, f"Exceptions missing justification: {bad}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
