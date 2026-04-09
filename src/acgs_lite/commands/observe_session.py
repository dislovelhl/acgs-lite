# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""acgs observe-session — record and query tool-call observations."""

from __future__ import annotations

import argparse
import json
import sys

from acgs_lite.observability.session_observer import ObservationLogger, ToolObservation


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "observe-session",
        help="Record and query AI coding session observations",
    )
    p.add_argument(
        "action", nargs="?", default="status", choices=("record", "status", "tail", "export")
    )
    p.add_argument("--tool", help="Tool type (bash, grep, edit, read, task, …)")
    p.add_argument("--duration-ms", type=float, help="Tool execution time in ms")
    p.add_argument("--success", action="store_true", default=True, help="Mark as success (default)")
    p.add_argument("--failure", action="store_true", help="Mark as failure")
    p.add_argument("--error-type", help="Error class name")
    p.add_argument("--error-message", help="Error detail")
    p.add_argument("--file", action="append", dest="files", help="File path (repeatable)")
    p.add_argument("--session-id", help="Session identifier")
    p.add_argument("--meta", action="append", dest="meta", help="Key=value metadata (repeatable)")
    p.add_argument("--path", help="Observation log path (default: ~/.acgs/observations.jsonl)")
    p.add_argument("-n", type=int, default=20, help="Number of records for tail/export")
    p.add_argument("--json-out", action="store_true", help="JSON output for tail/export")


def _parse_meta(items: list[str] | None) -> dict[str, str]:
    if not items:
        return {}
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            print(f"warn: skipping malformed --meta '{item}' (expected key=value)", file=sys.stderr)
            continue
        k, v = item.split("=", 1)
        result[k] = v
    return result


def _cmd_record(args: argparse.Namespace, logger: ObservationLogger) -> ToolObservation:
    if not args.tool:
        print("error: --tool is required for 'record'", file=sys.stderr)
        sys.exit(1)
    if args.duration_ms is None:
        print("error: --duration-ms is required for 'record'", file=sys.stderr)
        sys.exit(1)

    obs = logger.record(
        tool_type=args.tool,
        duration_ms=args.duration_ms,
        success=not args.failure,
        error_type=args.error_type,
        error_message=args.error_message,
        file_paths=args.files or [],
        session_id=args.session_id,
        metadata=_parse_meta(args.meta),
    )
    print(f"recorded {obs.observation_id}  tool={obs.tool_type}  success={obs.success}")
    return obs


def _cmd_status(args: argparse.Namespace, logger: ObservationLogger) -> None:
    count = logger.count()
    print(f"observations: {count}")
    print(f"log file:     {logger.path}")
    if logger.path.exists():
        size_kb = logger.path.stat().st_size / 1024
        print(f"log size:       {size_kb:.1f} KB")


def _cmd_tail(args: argparse.Namespace, logger: ObservationLogger) -> None:
    records = logger.tail(args.n)
    if args.json_out:
        for r in records:
            print(r.to_json())
        return
    for r in records:
        status = "ok" if r.success else f"FAIL {r.error_type or ''}"
        files = f"  files={','.join(r.file_paths[:3])}" if r.file_paths else ""
        print(f"  {r.timestamp[:19]}  {r.tool_type:12s}  {r.duration_ms:8.1f}ms  {status}{files}")


def _cmd_export(args: argparse.Namespace, logger: ObservationLogger) -> None:
    records = logger.tail(args.n)
    export = {
        "count": len(records),
        "log_file": str(logger.path),
        "observations": [
            {
                "tool_type": r.tool_type,
                "timestamp": r.timestamp,
                "duration_ms": r.duration_ms,
                "success": r.success,
                "error_type": r.error_type,
                "file_paths": r.file_paths,
                "session_id": r.session_id,
                "metadata": r.metadata,
            }
            for r in records
        ],
    }
    print(json.dumps(export, indent=2))


def run(args: argparse.Namespace) -> None:
    logger = ObservationLogger(args.path)
    cmd = args.action or "status"
    handlers = {
        "record": _cmd_record,
        "status": _cmd_status,
        "tail": _cmd_tail,
        "export": _cmd_export,
    }
    handlers[cmd](args, logger)
