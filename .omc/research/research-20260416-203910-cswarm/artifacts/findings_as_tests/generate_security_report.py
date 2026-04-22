#!/usr/bin/env python3
"""Generate security-audit-report.md from pytest --json-report output.

Usage
-----
    python -m pytest tests/security/ -m security \
        --json-report --json-report-file=.security.json
    python scripts/generate_security_report.py .security.json \
        > security-audit-report.md

CI contract
-----------
The workflow runs the two steps above, then diffs the generated report
against the checked-in one. Any drift (new finding, status change,
removed test) fails the build. This makes the report itself derived
data — humans fix tests, the report updates automatically.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

FINDING_ID_RE = re.compile(r"test_finding_([a-z0-9_]+)\.py", re.IGNORECASE)


def _finding_id(nodeid: str) -> str:
    mod = pathlib.Path(nodeid.split("::", 1)[0]).stem
    m = FINDING_ID_RE.search(mod + ".py")
    return m.group(1).upper() if m else mod.upper()


def _load_metadata(nodeid: str, root: pathlib.Path) -> dict[str, str]:
    """Extract FINDING_ID, SEVERITY, STATUS, TITLE constants from the test file."""
    file_path = root / nodeid.split("::", 1)[0]
    if not file_path.exists():
        return {}
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, str] = {}
    for key in ("FINDING_ID", "SEVERITY", "STATUS", "TITLE"):
        m = re.search(rf'^{key}\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if m:
            out[key] = m.group(1)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_security_report.py <pytest-json-report>", file=sys.stderr)
        return 2
    report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = pathlib.Path.cwd()

    by_finding: dict[str, list[dict]] = defaultdict(list)
    metadata: dict[str, dict[str, str]] = {}
    for t in report.get("tests", []):
        fid = _finding_id(t["nodeid"])
        by_finding[fid].append(t)
        metadata.setdefault(fid, _load_metadata(t["nodeid"], root))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("# Security Audit Report (auto-generated)\n")
    print(f"_Generated: {now}_\n")
    print(f"_Source: `pytest -m security` against {len(by_finding)} findings._\n")
    print("**Do not edit by hand.** Fix the tests; the report follows.\n")

    total_pass = total_fail = total_skip = 0
    for fid in sorted(by_finding):
        tests = by_finding[fid]
        outcomes = [t["outcome"] for t in tests]
        status_icon = (
            "PASS"
            if all(o == "passed" for o in outcomes)
            else "FAIL"
            if any(o == "failed" for o in outcomes)
            else "SKIP"
        )
        meta = metadata.get(fid, {})
        title = meta.get("TITLE", fid)
        severity = meta.get("SEVERITY", "?")
        status = meta.get("STATUS", "?")
        print(f"## {fid} — {title}")
        print(f"- Severity: `{severity}`")
        print(f"- Claimed status: `{status}`")
        print(f"- Test verdict: **{status_icon}** ({len(tests)} test case(s))")
        for t in tests:
            print(f"  - `{t['nodeid']}` → {t['outcome']}")
        print()
        total_pass += sum(1 for o in outcomes if o == "passed")
        total_fail += sum(1 for o in outcomes if o == "failed")
        total_skip += sum(1 for o in outcomes if o not in ("passed", "failed"))

    print("---\n")
    print(f"**Totals:** {total_pass} passed, {total_fail} failed, {total_skip} skipped")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
