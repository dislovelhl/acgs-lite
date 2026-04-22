"""Emit arc-kit command files that invoke the bridge package."""

from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_FORMAT_MAP = {
    "opencode": "command_opencode",
    "codex": "command_codex",
    "claude": "command_claude",
}


def emit_command(format: str = "opencode") -> str:
    normalized = format.strip().lower()
    name = _FORMAT_MAP.get(normalized)
    if name is None:
        raise ValueError(f"unsupported command format: {format!r}")
    return (_TEMPLATES_DIR / f"{name}.md").read_text(encoding="utf-8")


def write_command(format: str, path: str | Path) -> None:
    Path(path).write_text(emit_command(format), encoding="utf-8")
