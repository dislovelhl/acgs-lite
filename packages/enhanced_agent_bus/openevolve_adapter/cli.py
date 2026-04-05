"""
OpenEvolve Governance Adapter — CLI Entry Point
Constitutional Hash: 608508a9bd224290

Usage
-----
python -m enhanced_agent_bus.openevolve_adapter.cli --help

Commands
--------
  evaluate   Run cascade evaluation on a JSON candidate file.
  gate       Run rollout gate check only (no cascade).
  info       Print adapter version / constitutional hash.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "608508a9bd224290"  # pragma: allowlist secret

_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Stub verifier for CLI use (no real external service required)
# ---------------------------------------------------------------------------


class _StubVerifier:
    """
    Offline verifier that echoes the candidate's own payload back.

    Suitable for dry-run / CI evaluation where no live validator endpoint
    is available.  Should NEVER be used in production.
    """

    async def verify(self, candidate: Any) -> Any:
        return candidate.verification_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_candidate_from_file(path: Path) -> Any:
    """Load and deserialise an EvolutionCandidate from a JSON file."""
    from enhanced_agent_bus.openevolve_adapter.integration import (
        _deserialise_candidate,
    )

    raw = json.loads(path.read_text())
    return _deserialise_candidate(raw)


def _print_json(data: dict[str, Any], *, indent: int = 2) -> None:
    print(json.dumps(data, indent=indent, default=str))


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openevolve-adapter",
        description=(
            f"OpenEvolve Governance Adapter CLI\nConstitutional Hash: {CONSTITUTIONAL_HASH}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── evaluate ────────────────────────────────────────────────────────
    ev = sub.add_parser(
        "evaluate",
        help="Run the full cascade evaluation pipeline on a candidate JSON file.",
    )
    ev.add_argument(
        "candidate_file",
        type=Path,
        help="Path to a JSON file containing a serialised evolution candidate.",
    )
    ev.add_argument(
        "--performance-score",
        type=float,
        default=0.0,
        metavar="SCORE",
        help="Raw task performance score in [0, 1] (default: 0.0).",
    )
    ev.add_argument(
        "--quick-threshold",
        type=float,
        default=0.3,
        metavar="THRESH",
        help="Minimum quick-score to advance past Stage 2 (default: 0.3).",
    )
    ev.add_argument(
        "--full-threshold",
        type=float,
        default=0.5,
        metavar="THRESH",
        help="Minimum full fitness to pass Stage 3 (default: 0.5).",
    )
    ev.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    ev.add_argument(
        "--gate",
        action="store_true",
        help="Also run the rollout gate after a successful cascade.",
    )

    # ── gate ────────────────────────────────────────────────────────────
    gt = sub.add_parser(
        "gate",
        help="Run rollout gate check only (no cascade evaluation).",
    )
    gt.add_argument(
        "candidate_file",
        type=Path,
        help="Path to a JSON file containing a serialised evolution candidate.",
    )
    gt.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )

    # ── info ────────────────────────────────────────────────────────────
    sub.add_parser("info", help="Print adapter version and constitutional hash.")

    return parser


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


async def _cmd_evaluate(args: argparse.Namespace) -> int:
    from enhanced_agent_bus.openevolve_adapter.cascade import CascadeEvaluator
    from enhanced_agent_bus.openevolve_adapter.rollout import RolloutController

    try:
        candidate = _load_candidate_from_file(args.candidate_file)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        _err(f"Failed to load candidate: {exc}", json_output=args.json_output)
        return 1

    evaluator = CascadeEvaluator(
        _StubVerifier(),
        quick_threshold=args.quick_threshold,
        full_threshold=args.full_threshold,
    )

    result = await evaluator.evaluate(candidate, performance_score=args.performance_score)

    gate_data: dict[str, Any] | None = None
    if args.gate and result.passed:
        ctrl = RolloutController()
        decision = ctrl.gate(candidate)
        gate_data = decision.to_dict()

    output: dict[str, Any] = {
        "command": "evaluate",
        "timestamp": datetime.now(UTC).isoformat(),
        "candidate_id": candidate.candidate_id,
        "result": result.to_dict(),
    }
    if gate_data is not None:
        output["gate"] = gate_data

    if args.json_output:
        _print_json(output)
    else:
        status = "✓ PASSED" if result.passed else "✗ FAILED"
        print(f"\nCandidate : {candidate.candidate_id}")
        print(f"Status    : {status}")
        print(f"Exit stage: {result.exit_stage.value}")
        print(f"Score     : {result.score:.4f}")
        if result.rejection_reason:
            print(f"Reason    : {result.rejection_reason}")
        if result.stage_timings_ms:
            print("Timings   :", {k: f"{v:.2f}ms" for k, v in result.stage_timings_ms.items()})
        if gate_data:
            gate_ok = "✓ ALLOWED" if gate_data["allowed"] else "✗ DENIED"
            print(f"\nRollout gate: {gate_ok}")
            print(f"Gate reason : {gate_data['reason']}")

    return 0 if result.passed else 2


async def _cmd_gate(args: argparse.Namespace) -> int:
    from enhanced_agent_bus.openevolve_adapter.rollout import RolloutController

    try:
        candidate = _load_candidate_from_file(args.candidate_file)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as exc:
        _err(f"Failed to load candidate: {exc}", json_output=args.json_output)
        return 1

    ctrl = RolloutController()
    decision = ctrl.gate(candidate)

    if args.json_output:
        _print_json(
            {
                "command": "gate",
                "timestamp": datetime.now(UTC).isoformat(),
                "decision": decision.to_dict(),
            }
        )
    else:
        status = "✓ ALLOWED" if decision.allowed else "✗ DENIED"
        print(f"\nCandidate   : {decision.candidate_id}")
        print(f"Risk tier   : {decision.risk_tier}")
        print(f"Stage       : {decision.proposed_stage}")
        print(f"Gate status : {status}")
        print(f"Reason      : {decision.reason}")

    return 0 if decision.allowed else 2


def _cmd_info() -> int:
    print(f"OpenEvolve Governance Adapter v{_VERSION}")
    print(f"Constitutional Hash : {CONSTITUTIONAL_HASH}")
    print("Modules            : candidate, fitness, evolver, rollout, cascade, integration")
    return 0


def _err(msg: str, *, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps({"error": msg}))
    else:
        print(f"ERROR: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command == "info":
        return _cmd_info()
    if args.command == "evaluate":
        return asyncio.run(_cmd_evaluate(args))
    if args.command == "gate":
        return asyncio.run(_cmd_gate(args))

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
