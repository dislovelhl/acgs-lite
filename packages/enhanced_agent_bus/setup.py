"""Dynamic package discovery for enhanced-agent-bus.

The package root IS the source directory, so setuptools find_packages
cannot discover subpackages from pyproject.toml alone. This setup.py
walks the directory tree and maps every __init__.py-bearing directory
to an enhanced_agent_bus.* subpackage.
"""

import os

from setuptools import setup

SKIP = {
    "tests",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "docs",
    "data",
    "rust",
    "runtime",
    "specs",
    "node_modules",
    "fixtures",
    "examples",
    "htmlcov",
    ".mypy_cache",
}


def _find_packages() -> list[str]:
    pkgs = ["enhanced_agent_bus"]
    for dirpath, _dirnames, filenames in os.walk("."):
        parts = dirpath.split(os.sep)
        if any(s in parts for s in SKIP):
            continue
        if "__init__.py" in filenames and dirpath != ".":
            subpkg = dirpath[2:].replace(os.sep, ".")
            pkgs.append(f"enhanced_agent_bus.{subpkg}")
    pkgs.sort()
    return pkgs


setup(
    packages=_find_packages(),
    package_dir={"enhanced_agent_bus": "."},
)
