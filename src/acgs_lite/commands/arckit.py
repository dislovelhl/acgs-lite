# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""acgs arckit — bridge arc-kit governance artifacts into ACGS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from acgs_lite.arckit.command_emitter import write_command
from acgs_lite.arckit.exporter import export_evidence
from acgs_lite.arckit.generator import generate_constitution, manifest_to_yaml
from acgs_lite.arckit.parser import parse_project


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the arckit command group."""
    parser = sub.add_parser(
        "arckit",
        help="Bridge arc-kit artifacts into ACGS governance",
        description="Bridge arc-kit artifacts into ACGS governance",
    )
    arckit_sub = parser.add_subparsers(dest="arckit_command", required=True)

    generate = arckit_sub.add_parser(
        "generate",
        help="Generate constitution.yaml from ARC artifacts",
        description="Generate constitution.yaml from ARC artifacts",
    )
    generate.add_argument("--from", dest="from_path", type=Path, required=True)
    generate.add_argument("--out", type=Path, default=Path("constitution.yaml"))
    generate.add_argument("--name", default=None)
    generate.add_argument("--version", default="1.0")
    generate.add_argument("--dry-run", action="store_true")

    export = arckit_sub.add_parser("export", help="Export ACGS compliance evidence as arc-kit Markdown")
    export.add_argument("--project-id", required=True)
    export.add_argument("--system-id", required=True)
    export.add_argument("--domain", default="general")
    export.add_argument("--constitution", type=Path, default=None)
    export.add_argument("--audit-log", type=Path, default=None)
    export.add_argument("--out", type=Path, default=None)
    export.add_argument("--dry-run", action="store_true")

    emit = arckit_sub.add_parser("emit-command", help="Emit an arc-kit command or Codex skill file")
    emit.add_argument("--format", default="opencode")
    emit.add_argument("--out", type=Path, default=Path("arckit.acgs.md"))


def handler(args: argparse.Namespace) -> int:
    """Dispatch arckit subcommands."""
    command = args.arckit_command
    if command == "generate":
        return _generate(args)
    if command == "export":
        return _export(args)
    if command == "emit-command":
        return _emit_command(args)
    print(f"Unknown arckit command: {command}", file=sys.stderr)
    return 1


def _generate(args: argparse.Namespace) -> int:
    from_path: Path = args.from_path
    if not from_path.exists() or not from_path.is_dir():
        print(f"arc-kit project directory not found: {from_path}", file=sys.stderr)
        return 1

    manifest = generate_constitution(
        parse_project(from_path),
        name=args.name,
        version=args.version,
    )
    yaml_text = manifest_to_yaml(manifest)
    if args.dry_run:
        print(yaml_text, end="")
        return 0
    args.out.write_text(yaml_text, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


def _export(args: argparse.Namespace) -> int:
    markdown = export_evidence(
        system_id=args.system_id,
        project_id=args.project_id,
        domain=args.domain,
        constitution_path=args.constitution,
        audit_log_path=args.audit_log,
    )
    if args.dry_run:
        print(markdown, end="")
        return 0
    target = args.out or Path(f"ARC-{args.project_id}-ACGS-v1.0.md")
    target.write_text(markdown, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


def _emit_command(args: argparse.Namespace) -> int:
    out: Path = args.out
    if out.name == "arckit.acgs.md" and args.format.lower() == "codex":
        out = Path("SKILL.md")
    try:
        write_command(args.format, out)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Wrote {out}")
    return 0
