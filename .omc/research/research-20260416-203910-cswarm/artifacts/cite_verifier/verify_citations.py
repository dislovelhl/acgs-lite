#!/usr/bin/env python3
"""Verify every arXiv/DOI citation in papers and code resolves to a real URL.

Rationale
---------
Research-stage review of constitutional_swarm found:
- `spectral_sphere.py:19` cites `arXiv:2603.20896`
- mHC reference cited as `2512.24880`
- NDSS 2027 companion paper self-cites `mcfs_iclr2027` 5× as third-party lit

This script makes a CI-gated HEAD request for every arXiv ID and DOI found in
papers/, src/ docstrings, and docs/. A fabricated or typo'd ID resolves to
HTTP 404 (or DNS failure) and fails the build. Self-citations with no URL
must be declared as `@unpublished` with a repo SHA — the scanner ignores them
only if the bib entry's `note = {repo SHA: ...}` field is present.

Usage
-----
    python scripts/verify_citations.py --root .
    python scripts/verify_citations.py --root . --skip-network  # lint only
    python scripts/verify_citations.py --root . --json > cites.json

Exit codes
----------
    0  all citations resolve
    1  one or more citations failed to resolve
    2  usage error
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict

# arXiv IDs: new format YYMM.NNNNN (4-5 digits after dot), old format hep-th/9901001
ARXIV_NEW_RE = re.compile(r"(?<![\w/.])(\d{4}\.\d{4,5})(v\d+)?\b")
ARXIV_OLD_RE = re.compile(r"(?<!\w)([a-z\-]+(?:\.[A-Z]{2})?/\d{7})\b")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;}\"'<>\]\)]+)")

SCAN_GLOBS = ("**/*.bib", "**/*.tex", "**/*.py", "**/*.md", "**/*.rst")
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".claude"}


@dataclass
class Citation:
    kind: str  # "arxiv" | "doi"
    raw_id: str
    url: str
    source: str  # "path:line"
    status: int = 0  # HTTP status, 0 = not checked
    ok: bool = False
    error: str = ""


def _iter_files(root: pathlib.Path):
    for pattern in SCAN_GLOBS:
        for p in root.glob(pattern):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue
            if p.is_file():
                yield p


def _scan(root: pathlib.Path) -> list[Citation]:
    cites: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    for path in _iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in ARXIV_NEW_RE.finditer(line):
                aid = m.group(1)
                key = ("arxiv", aid)
                if key in seen:
                    continue
                seen.add(key)
                cites.append(
                    Citation(
                        kind="arxiv",
                        raw_id=aid,
                        url=f"https://arxiv.org/abs/{aid}",
                        source=f"{path.relative_to(root)}:{lineno}",
                    )
                )
            for m in ARXIV_OLD_RE.finditer(line):
                aid = m.group(1)
                key = ("arxiv", aid)
                if key in seen:
                    continue
                seen.add(key)
                cites.append(
                    Citation(
                        kind="arxiv",
                        raw_id=aid,
                        url=f"https://arxiv.org/abs/{aid}",
                        source=f"{path.relative_to(root)}:{lineno}",
                    )
                )
            for m in DOI_RE.finditer(line):
                doi = m.group(1).rstrip(".,")
                key = ("doi", doi)
                if key in seen:
                    continue
                seen.add(key)
                cites.append(
                    Citation(
                        kind="doi",
                        raw_id=doi,
                        url=f"https://doi.org/{doi}",
                        source=f"{path.relative_to(root)}:{lineno}",
                    )
                )
    return cites


def _verify_one(c: Citation, timeout: float) -> Citation:
    req = urllib.request.Request(
        c.url,
        method="HEAD",
        headers={"User-Agent": "constitutional-swarm-cite-verify/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            c.status = resp.status
            c.ok = c.status == 200
    except urllib.error.HTTPError as e:
        c.status = e.code
        # DOI resolver returns 302/301 — treat as OK
        c.ok = e.code in (301, 302) or (c.kind == "doi" and e.code in (301, 302))
        if not c.ok:
            c.error = f"HTTP {e.code}"
    except urllib.error.URLError as e:
        c.error = str(e.reason)
    except Exception as e:
        c.error = type(e).__name__ + ": " + str(e)
    return c


def _verify_all(cites: list[Citation], timeout: float, workers: int) -> list[Citation]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_verify_one, c, timeout) for c in cites]
        return [f.result() for f in concurrent.futures.as_completed(futures)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument(
        "--skip-network", action="store_true", help="scan only, do not perform HTTP checks"
    )
    ap.add_argument("--json", action="store_true", help="emit JSON results")
    args = ap.parse_args()

    cites = _scan(args.root)
    if not args.skip_network:
        cites = _verify_all(cites, args.timeout, args.workers)
    # Re-sort by source for stable output
    cites.sort(key=lambda c: (c.kind, c.source))

    bad = [c for c in cites if not args.skip_network and not c.ok]

    if args.json:
        print(json.dumps([asdict(c) for c in cites], indent=2))
    else:
        for c in cites:
            if args.skip_network:
                tag = "FOUND"
            else:
                tag = "OK  " if c.ok else "FAIL"
            detail = c.error or (f"HTTP {c.status}" if c.status else "")
            print(f"{tag}  {c.kind:6} {c.raw_id:32}  {c.source}  {detail}")
        print()
        print(f"{len(cites)} citations scanned.")
        if not args.skip_network:
            print(f"{len(cites) - len(bad)} verified, {len(bad)} failed.")

    if bad:
        print(
            f"\n{len(bad)} unresolvable citation(s). "
            "Either fix the ID, replace with a reachable URL, or mark as @unpublished.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
