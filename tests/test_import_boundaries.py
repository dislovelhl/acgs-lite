"""Import-boundary checks for acgs_lite.

acgs-lite is the core governance library. It must not depend on higher-level
packages (enhanced_agent_bus, constitutional_swarm, mhc). Imports of src.*
are allowed only inside the integrations/ subpackage.

KNOWN_VIOLATIONS tracks existing architectural debt. The test fails when:
  - a NEW violation appears (add it to KNOWN_VIOLATIONS after review), or
  - a KNOWN violation disappears (remove it from the set — debt paid off).
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "acgs_lite"

# Prefixes forbidden in ALL runtime source (tests excluded).
FORBIDDEN_UNCONDITIONAL = (
    "enhanced_agent_bus",
    "constitutional_swarm",
    "mhc",
)

# Prefixes forbidden outside the integrations/ subpackage.
FORBIDDEN_OUTSIDE_INTEGRATIONS = ("src.",)

# Pre-existing violations being tracked. Remove each entry once the underlying
# code is fixed. Adding a new violation here requires an explicit review comment.
KNOWN_VIOLATIONS: set[str] = {
    # integrations/workflow.py imports constitutional_swarm as an optional dependency
    # (guarded by try/except ImportError). This is intentional — the workflow
    # integration requires constitutional_swarm when it is installed.
    "integrations/workflow.py: constitutional_swarm",
    "integrations/workflow.py: constitutional_swarm.artifact",
    "integrations/workflow.py: constitutional_swarm.execution",
    "integrations/workflow.py: constitutional_swarm.swarm",
}


def _iter_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                imports.append(node.module)
    return imports


def _is_integration_file(path: Path) -> bool:
    return "integrations" in path.parts


def test_runtime_source_import_boundaries() -> None:
    found: set[str] = set()

    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if "test" in path.name or path.name.startswith("_test"):
            continue
        rel = path.relative_to(SOURCE_ROOT)
        key_prefix = str(rel)
        is_integration = _is_integration_file(path)

        for module in _iter_imports(path):
            violation = None

            for prefix in FORBIDDEN_UNCONDITIONAL:
                if module == prefix or module.startswith(prefix + "."):
                    violation = f"{key_prefix}: {module}"
                    break

            if violation is None and not is_integration:
                for prefix in FORBIDDEN_OUTSIDE_INTEGRATIONS:
                    if module.startswith(prefix):
                        violation = f"{key_prefix}: {module}"
                        break

            if violation:
                found.add(violation)

    new_violations = found - KNOWN_VIOLATIONS
    cleared_violations = KNOWN_VIOLATIONS - found

    messages: list[str] = []
    if new_violations:
        messages.append(
            "NEW boundary violations (fix or add to KNOWN_VIOLATIONS with review comment):\n"
            + "\n".join(f"  {v}" for v in sorted(new_violations))
        )
    if cleared_violations:
        messages.append(
            "Violations no longer present — remove from KNOWN_VIOLATIONS:\n"
            + "\n".join(f"  {v}" for v in sorted(cleared_violations))
        )

    assert not messages, "\n\n".join(messages)
