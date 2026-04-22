from __future__ import annotations

from pathlib import Path

ARCKIT_TEST_ROOT = Path(__file__).resolve().parent


def fixture_path(name: str) -> Path:
    return ARCKIT_TEST_ROOT / "fixtures" / name


def fixtures_dir() -> Path:
    return ARCKIT_TEST_ROOT / "fixtures"
