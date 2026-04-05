"""Import-boundary checks for constitutional_swarm."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "constitutional_swarm"
FORBIDDEN_IMPORT_PREFIXES = (
    "enhanced_agent_bus",
    "packages.",
    "src.",
    "acgs_deliberation",
    "mhc",
)


def _iter_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                imports.append(node.module)
    return imports


def test_runtime_source_avoids_forbidden_cross_package_imports() -> None:
    offenders: list[str] = []
    for path in sorted(SOURCE_ROOT.glob("*.py")):
        for module in _iter_imports(path):
            if any(
                module == prefix.rstrip(".") or module.startswith(prefix)
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                offenders.append(f"{path.name}: {module}")

    assert not offenders, "Forbidden cross-package imports found:\n" + "\n".join(offenders)
