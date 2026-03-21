# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""CLI for acgs-lite license management.

Constitutional Hash: cdd01ef066bc6cf2

Commands:
    acgs-lite activate <key>   Store license key to ~/.acgs-lite/license
    acgs-lite status           Show current tier, expiry, and available features
    acgs-lite verify           Validate license key integrity (offline)
"""

from __future__ import annotations

import argparse
import sys

from acgs_lite.licensing import (
    LicenseError,
    LicenseExpiredError,
    LicenseInfo,
    LicenseManager,
    Tier,
    _write_license_file,
    validate_license_key,
)


def _fmt_tier_badge(tier: Tier) -> str:
    badges = {
        Tier.FREE: "FREE",
        Tier.PRO: "PRO ✓",
        Tier.TEAM: "TEAM ✓",
        Tier.ENTERPRISE: "ENTERPRISE ✓",
    }
    return badges.get(tier, tier.name)


def _print_info(info: LicenseInfo) -> None:
    print(f"  Tier:    {_fmt_tier_badge(info.tier)}")
    if info.expiry_date:
        print(f"  Expiry:  {info.expiry_date}")
    else:
        print("  Expiry:  none (perpetual)")
    print()
    print("  Features:")
    for feature in info.features:
        print(f"    • {feature}")


def cmd_activate(args: argparse.Namespace) -> int:
    key: str = args.key.strip()
    try:
        info = validate_license_key(key)
    except LicenseExpiredError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LicenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _write_license_file(key)
    print(f"License activated: {info.tier.name}")
    _print_info(info)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    manager = LicenseManager()
    try:
        info = manager.load()
    except LicenseExpiredError as exc:
        print(f"Warning: {exc}", file=sys.stderr)
        # Still show info even if expired
        from acgs_lite.licensing import _read_license_file, validate_license_key

        key = __import__("os").environ.get("ACGS_LICENSE_KEY") or _read_license_file()
        if key:
            try:
                info = validate_license_key.__wrapped__(key)  # type: ignore[attr-defined]
            except Exception:
                print("Could not parse license key.", file=sys.stderr)
                return 1
        else:
            return 1
    except LicenseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("acgs-lite License Status")
    print("=" * 40)
    _print_info(info)

    if info.tier == Tier.FREE:
        print()
        print("  → Upgrade to Pro for EU AI Act compliance:")
        print("    https://acgs2.ai/pricing")

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Validate a key passed via --key flag or the currently loaded key."""
    key_arg: str | None = getattr(args, "key", None)
    key: str | None

    if key_arg:
        key = key_arg.strip()
    else:
        import os

        from acgs_lite.licensing import _read_license_file

        env_key = os.environ.get("ACGS_LICENSE_KEY")
        key = env_key if env_key is not None else _read_license_file()

    if not key:
        print("No license key found. Run 'acgs-lite activate <key>' first.", file=sys.stderr)
        return 1

    print(f"Verifying key: {key[:20]}...")
    try:
        info = validate_license_key(key)
        print("✓ Key is valid.")
        _print_info(info)
        return 0
    except LicenseExpiredError as exc:
        print(f"✗ Key is EXPIRED: {exc}", file=sys.stderr)
        return 1
    except LicenseError as exc:
        print(f"✗ Key is INVALID: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acgs-lite",
        description="acgs-lite license management",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # activate
    p_activate = sub.add_parser("activate", help="Store a license key")
    p_activate.add_argument("key", help="License key (ACGS-{TIER}-...)")

    # status
    sub.add_parser("status", help="Show current license tier and features")

    # verify
    p_verify = sub.add_parser("verify", help="Validate license key integrity")
    p_verify.add_argument("--key", help="Key to verify (default: currently loaded key)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "activate": cmd_activate,
        "status": cmd_status,
        "verify": cmd_verify,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
