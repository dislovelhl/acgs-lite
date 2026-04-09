# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""acgs halt / acgs resume — EU AI Act Article 14 kill-switch.

Immediately halt or resume all governed agents for a given system.
Uses the GovernanceCircuitBreaker's cross-process file signaling.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import argparse
import sys

from acgs_lite.circuit_breaker import GovernanceCircuitBreaker


def add_parser(sub: argparse._SubParsersAction) -> None:
    """Register halt and resume subcommands."""
    p_halt = sub.add_parser(
        "halt",
        help="Halt all governed agents for a system (Article 14 kill-switch)",
    )
    p_halt.add_argument(
        "--system-id",
        required=True,
        help="System identifier to halt",
    )
    p_halt.add_argument(
        "--reason",
        default="Manual halt via CLI",
        help="Reason for the halt (logged in signal file)",
    )

    p_resume = sub.add_parser(
        "resume",
        help="Resume governed agents after a halt",
    )
    p_resume.add_argument(
        "--system-id",
        required=True,
        help="System identifier to resume",
    )

    p_breaker_status = sub.add_parser(
        "breaker-status",
        help="Check circuit breaker status for a system",
    )
    p_breaker_status.add_argument(
        "--system-id",
        required=True,
        help="System identifier to check",
    )


def cmd_halt(args: argparse.Namespace) -> int:
    """Halt all governed agents for a system."""
    system_id: str = args.system_id
    reason: str = args.reason

    breaker = GovernanceCircuitBreaker(system_id=system_id)

    if breaker.is_tripped:
        existing_reason = breaker.trip_reason
        print(
            f"System '{system_id}' is already halted: {existing_reason}",
            file=sys.stderr,
        )
        return 0

    breaker.trip(reason=reason)
    print(f"HALTED system '{system_id}'")
    print(f"  Reason: {reason}")
    print(f"  Signal: {breaker._signal_path}")
    print()
    print("All GovernedAgent.run() calls will raise GovernanceHaltError.")
    print(f"To resume: acgs resume --system-id {system_id}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume governed agents after a halt."""
    system_id: str = args.system_id

    breaker = GovernanceCircuitBreaker(system_id=system_id)

    if not breaker.is_tripped:
        print(f"System '{system_id}' is not halted.", file=sys.stderr)
        return 0

    breaker.reset()
    print(f"RESUMED system '{system_id}'")
    print("Governed agents can now process requests.")
    return 0


def cmd_breaker_status(args: argparse.Namespace) -> int:
    """Check circuit breaker status."""
    system_id: str = args.system_id

    breaker = GovernanceCircuitBreaker(system_id=system_id)

    if breaker.is_tripped:
        reason = breaker.trip_reason
        print(f"System '{system_id}': HALTED")
        print(f"  Reason: {reason}")
        print(f"  Signal: {breaker._signal_path}")
        return 1
    else:
        print(f"System '{system_id}': OK")
        return 0
