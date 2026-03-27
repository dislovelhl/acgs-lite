# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""Shared CLI helpers used across command modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def cli_bar(score: float, width: int = 20) -> str:
    """Render a text bar for terminal output."""
    filled = int(score * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {score:.0%}"


def load_system_description(args: argparse.Namespace) -> dict[str, Any]:
    """Build system description from CLI args or config file."""
    desc: dict[str, Any] = {}

    config_path = Path("acgs.json")
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            desc = json.load(f)

    if getattr(args, "system_id", None):
        desc["system_id"] = args.system_id
    if getattr(args, "jurisdiction", None):
        desc["jurisdiction"] = args.jurisdiction
    if getattr(args, "domain", None):
        desc["domain"] = args.domain
    if getattr(args, "framework", None):
        desc["_frameworks"] = args.framework

    desc.setdefault("system_id", Path.cwd().name)

    return desc
