from __future__ import annotations

import json
from pathlib import Path

import pytest

from acgs_lite.commands import capabilities


def test_capabilities_dump_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = capabilities.handler(type("Args", (), {"capability_action": "dump", "json_out": True})())
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload


def test_capabilities_validate_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = capabilities.handler(
        type("Args", (), {"capability_action": "validate", "max_age_days": 365, "json_out": True})()
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == []


def test_capabilities_refresh_json(tmp_path: Path) -> None:
    fake_pages = {
        "https://developers.openai.com/api/docs/models": "GPT-5.4 o3 gpt-image-1.5.png",
        "https://docs.anthropic.com/en/docs/about-claude/models": "claude-sonnet-4-6 claude-haiku-4-5 claude-api-guide",
        "https://ai.google.dev/gemini-api/docs/models": "gemini-2.5-flash gemini-3-flash-preview gemini-api-card",
    }

    def fake_fetch(url: str) -> str:
        return fake_pages[url]

    candidate_path = tmp_path / "candidate.json"
    candidate_manifest, discovered, errors = capabilities._refresh_manifest_snapshot(  # type: ignore[attr-defined]
        ["openai", "anthropic", "google"],
        fetch_text=fake_fetch,
    )
    diff = capabilities._render_manifest_diff(candidate_manifest)  # type: ignore[attr-defined]
    candidate_path.write_text(json.dumps(candidate_manifest, indent=2), encoding="utf-8")

    assert errors == {}
    assert "gpt-5.4" in discovered["openai"]
    assert "gpt-image-1.5.png" not in discovered["openai"]
    assert "claude-sonnet-4-6" in discovered["anthropic"]
    assert "claude-api-guide" not in discovered["anthropic"]
    assert "gemini-3-flash-preview" in discovered["google"]
    assert "gemini-api-card" not in discovered["google"]
    assert isinstance(diff, str)
    assert "candidate" in diff or diff == ""
    assert candidate_path.exists()


def test_capabilities_refresh_collects_provider_errors() -> None:
    def fake_fetch(url: str) -> str:
        if "openai" in url:
            return "gpt-5.4"
        raise RuntimeError("blocked")

    _candidate_manifest, discovered, errors = capabilities._refresh_manifest_snapshot(  # type: ignore[attr-defined]
        ["openai", "anthropic"],
        fetch_text=fake_fetch,
    )

    assert "gpt-5.4" in discovered["openai"]
    assert "anthropic" in errors
