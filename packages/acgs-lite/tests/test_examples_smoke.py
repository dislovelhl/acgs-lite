"""Smoke tests for all example scripts.

Runs each example as a subprocess and verifies exit code 0.
No API keys required — all examples use InMemory* stubs.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _discover_examples() -> list[Path]:
    """Find all runnable example scripts."""
    scripts: list[Path] = []

    # Top-level .py scripts (quickstart.py, quickstart_*.py, etc.)
    for py in sorted(EXAMPLES_DIR.glob("*.py")):
        if py.name.startswith("_"):
            continue
        # Skip scripts that require external services, CLI args, or paid license
        if any(skip in py.name for skip in (
            "gitlab_webhook", "gitlab_anthropic", "gitlab_mr_governance",
            "demo_cli", "eu_ai_act_quickstart",
        )):
            continue
        scripts.append(py)

    # Subdirectory examples with main.py
    for main in sorted(EXAMPLES_DIR.glob("*/main.py")):
        scripts.append(main)

    return scripts


EXAMPLE_SCRIPTS = _discover_examples()


@pytest.mark.parametrize(
    "script",
    EXAMPLE_SCRIPTS,
    ids=[str(s.relative_to(EXAMPLES_DIR)) for s in EXAMPLE_SCRIPTS],
)
def test_example_runs_successfully(script: Path) -> None:
    """Each example script must exit 0 with no unhandled exceptions."""
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(Path.home()),
            "PYTHONPATH": str(EXAMPLES_DIR.parent / "src"),
            "OPENAI_API_KEY": "test-key-for-unit-tests",
            "ANTHROPIC_API_KEY": "test-key-for-unit-tests",
        },
    )
    assert result.returncode == 0, (
        f"{script.name} failed (exit {result.returncode}):\n"
        f"STDOUT:\n{result.stdout[-500:]}\n"
        f"STDERR:\n{result.stderr[-500:]}"
    )
