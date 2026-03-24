#!/usr/bin/env python3
"""Admin script to generate acgs-lite license keys.

Constitutional Hash: cdd01ef066bc6cf2

Usage:
    python generate_license.py --tier PRO --days 365 --secret $ACGS_LICENSE_SECRET
    python generate_license.py --tier TEAM --days 30
    python generate_license.py --tier ENTERPRISE --days 0  # no expiry

Environment:
    ACGS_LICENSE_SECRET  Signing secret (falls back to dev default if not set)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running this script directly without installing the package
_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from acgs_lite.licensing import (
    _DEFAULT_DEV_SECRET,
    Tier,
    generate_license_key,
    validate_license_key,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a signed acgs-lite license key.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_license.py --tier PRO --days 365
  python generate_license.py --tier ENTERPRISE --days 0 --secret mysecret
  python generate_license.py --tier TEAM --days 30 --count 5
        """,
    )
    parser.add_argument(
        "--tier",
        required=True,
        choices=[t.name for t in Tier],
        help="License tier: FREE, PRO, TEAM, ENTERPRISE",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Validity in days. 0 = no expiry. (default: 365)",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="HMAC signing secret. Falls back to ACGS_LICENSE_SECRET env var, "
        "then the default dev secret.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of keys to generate. (default: 1)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Output keys only (no info text), one per line.",
    )

    args = parser.parse_args()

    secret = args.secret or os.environ.get("ACGS_LICENSE_SECRET", _DEFAULT_DEV_SECRET)
    using_default = secret == _DEFAULT_DEV_SECRET

    if not args.quiet:
        print(
            f"Generating {args.count} x {args.tier} key(s)  "
            f"({'no expiry' if args.days == 0 else f'{args.days} days'})"
        )
        if using_default:
            print(
                "  [WARNING] Using default dev secret. Set ACGS_LICENSE_SECRET for production keys."
            )
        print()

    for i in range(args.count):
        key = generate_license_key(args.tier, args.days, secret)
        if args.quiet:
            print(key)
        else:
            info = validate_license_key(key, secret)
            expiry_str = info.expiry_date or "never"
            print(f"  {key}")
            print(f"    Tier:   {info.tier.name}")
            print(f"    Expiry: {expiry_str}")
            if i < args.count - 1:
                print()

    if not args.quiet:
        print()
        print("Distribute these keys to your customers.")
        print("They can activate with: acgs-lite activate <key>")
        print("Or set: export ACGS_LICENSE_KEY=<key>")


if __name__ == "__main__":
    main()
