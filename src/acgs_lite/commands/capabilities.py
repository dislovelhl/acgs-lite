# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.
# Commercial license: https://acgs.ai

"""acgs capabilities — inspect and validate the pinned capability manifest."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from acgs_lite.provider_capabilities import (
    CapabilityStability,
    get_manifest_path,
    load_capability_manifest,
    validate_capability_manifest,
)

_PROVIDER_SOURCES: dict[str, tuple[str, str]] = {
    "openai": ("https://developers.openai.com/api/docs/models", r"\b(?:gpt|o)\-[a-z0-9\.\-]+\b"),
    "anthropic": (
        "https://docs.anthropic.com/en/docs/about-claude/models",
        r"\bclaude\-[a-z0-9\-]+\b",
    ),
    "google": (
        "https://ai.google.dev/gemini-api/docs/models",
        r"\bgemini\-[a-z0-9\.\-]+(?:preview|lite|flash|pro)?\b",
    ),
}


def _fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; acgs-lite/2.7; +https://acgs.ai)",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310
        return cast(str, response.read().decode("utf-8", errors="replace"))


def _normalize_candidate_model(raw: str) -> str:
    return raw.strip().lower()


def _known_provider_tokens(provider: str) -> set[str]:
    tokens: set[str] = set()
    for profile in load_capability_manifest():
        if profile.provider_type != provider:
            continue
        tokens.add(profile.model_id)
        tokens.update(profile.aliases)
    return {_normalize_candidate_model(token) for token in tokens}


def _extract_models(provider: str, text: str) -> list[str]:
    _, pattern = _PROVIDER_SOURCES[provider]
    known_tokens = _known_provider_tokens(provider)
    matches = {
        normalized
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
        for normalized in [_normalize_candidate_model(match.group(0))]
        if normalized in known_tokens
    }
    return sorted(matches)


def _refresh_manifest_snapshot(
    providers: list[str],
    *,
    fetch_text: Callable[[str], str] = _fetch_text,
) -> tuple[list[dict[str, object]], dict[str, list[str]], dict[str, str]]:
    profiles = load_capability_manifest()
    manifest = [profile.to_dict() for profile in profiles]
    discovered: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    today = date.today().isoformat()

    for provider in providers:
        url, _ = _PROVIDER_SOURCES[provider]
        try:
            text = fetch_text(url)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            errors[provider] = f"{type(exc).__name__}: {exc}"
            continue
        discovered_models = _extract_models(provider, text)
        discovered[provider] = discovered_models
        for entry in manifest:
            if entry["provider_type"] != provider:
                continue
            if str(entry["model_id"]) in discovered_models:
                entry["checked_at"] = today
                entry["evidence_source"] = url
                entry["is_active"] = True
            elif entry["stability"] == CapabilityStability.PREVIEW.value:
                entry["is_active"] = False

    return manifest, discovered, errors


def _render_manifest_diff(candidate_manifest: list[dict[str, object]]) -> str:
    current_text = get_manifest_path().read_text(encoding="utf-8").splitlines(keepends=True)
    candidate_text = json.dumps(candidate_manifest, indent=2).splitlines(keepends=True)
    diff = difflib.unified_diff(
        current_text,
        candidate_text,
        fromfile=str(get_manifest_path()),
        tofile=f"{get_manifest_path()} (candidate)",
    )
    return "".join(diff)


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register capability-manifest subcommands."""
    p = sub.add_parser("capabilities", help="Inspect pinned model capability metadata")
    caps_sub = p.add_subparsers(dest="capability_action", required=True)

    validate_parser = caps_sub.add_parser(
        "validate", help="Validate capability manifest drift rules"
    )
    validate_parser.add_argument("--max-age-days", type=int, default=45)
    validate_parser.add_argument("--json", dest="json_out", action="store_true")

    dump_parser = caps_sub.add_parser("dump", help="Dump the current pinned capability manifest")
    dump_parser.add_argument("--json", dest="json_out", action="store_true")

    refresh_parser = caps_sub.add_parser(
        "refresh",
        help="Fetch provider live sources and emit a proposed manifest diff",
    )
    refresh_parser.add_argument(
        "--provider",
        action="append",
        choices=sorted(_PROVIDER_SOURCES),
        dest="providers",
        help="Provider(s) to refresh (default: all)",
    )
    refresh_parser.add_argument(
        "--write-candidate",
        type=Path,
        help="Optional path to write the candidate manifest JSON",
    )
    refresh_parser.add_argument("--json", dest="json_out", action="store_true")


def handler(args: argparse.Namespace) -> int:
    """Handle capability manifest inspection commands."""
    action = args.capability_action

    if action == "dump":
        manifest_payload = [profile.to_dict() for profile in load_capability_manifest()]
        if getattr(args, "json_out", False):
            print(json.dumps(manifest_payload, indent=2))
        else:
            for profile in manifest_payload:
                print(
                    f"{profile['provider_type']} {profile['model_id']} "
                    f"shape={profile['request_shape']} support={profile['support_level']} "
                    f"stability={profile['stability']}"
                )
        return 0

    if action == "validate":
        issues = validate_capability_manifest(max_age_days=getattr(args, "max_age_days", 45))
        if getattr(args, "json_out", False):
            print(json.dumps([issue.__dict__ for issue in issues], indent=2))
        else:
            if not issues:
                print("Capability manifest validation passed.")
            else:
                for issue in issues:
                    print(f"{issue.code}: {issue.model_id} - {issue.message}")
        return 0 if not issues else 1

    if action == "refresh":
        providers = args.providers or sorted(_PROVIDER_SOURCES)
        candidate_manifest, discovered, errors = _refresh_manifest_snapshot(providers)
        diff_text = _render_manifest_diff(candidate_manifest)

        if args.write_candidate:
            args.write_candidate.write_text(
                json.dumps(candidate_manifest, indent=2) + "\n", encoding="utf-8"
            )

        payload: dict[str, Any] = {
            "providers": providers,
            "discovered": discovered,
            "errors": errors,
            "candidate_path": str(args.write_candidate) if args.write_candidate else None,
            "diff": diff_text,
        }
        if getattr(args, "json_out", False):
            print(json.dumps(payload, indent=2))
        else:
            if errors:
                for provider, error in errors.items():
                    print(f"{provider}: {error}")
            print(diff_text or "No manifest changes proposed.")
        return 0 if not errors else 1

    raise ValueError(f"Unsupported capabilities action: {action}")
