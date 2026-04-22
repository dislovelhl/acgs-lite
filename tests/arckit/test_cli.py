from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from acgs_lite import Constitution
from acgs_lite.cli import build_parser, cmd_arckit

from .helpers import fixtures_dir


def _invoke(args: list[str]) -> tuple[int, str]:
    parser = build_parser()
    namespace = parser.parse_args(["arckit", *args])
    return cmd_arckit(namespace), ""


def test_cli_001_generate_dry_run_prints_valid_yaml(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code, _ = _invoke(["generate", "--from", str(fixtures_dir()), "--dry-run"])

    assert exit_code == 0
    data = yaml.safe_load(capsys.readouterr().out)
    assert data["rules"]


def test_cli_002_generate_out_writes_file(tmp_path) -> None:
    target = tmp_path / "constitution.yaml"

    exit_code, _ = _invoke(["generate", "--from", str(fixtures_dir()), "--out", str(target)])

    assert exit_code == 0
    assert target.exists()


def test_cli_003_generated_file_loads_with_constitution(tmp_path) -> None:
    target = tmp_path / "constitution.yaml"

    exit_code, _ = _invoke(["generate", "--from", str(fixtures_dir()), "--out", str(target)])

    assert exit_code == 0
    assert Constitution.from_yaml(target).rules


def test_cli_004_generate_nonexistent_dir_nonzero() -> None:
    exit_code, _ = _invoke(["generate", "--from", "/does/not/exist", "--dry-run"])

    assert exit_code != 0


def test_cli_005_export_dry_run_prints_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code, _ = _invoke(
        ["export", "--project-id", "001", "--system-id", "test", "--dry-run"],
    )

    assert exit_code == 0
    assert "ACGS Compliance Evidence" in capsys.readouterr().out


def test_cli_006_export_writes_default_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code, _ = _invoke(["export", "--project-id", "001", "--system-id", "test"])

    assert exit_code == 0
    assert Path("ARC-001-ACGS-v1.0.md").exists()


def test_cli_007_emit_command_opencode_writes_md(tmp_path) -> None:
    target = tmp_path / "arckit.acgs.md"

    exit_code, _ = _invoke(["emit-command", "--format", "opencode", "--out", str(target)])

    assert exit_code == 0
    assert "arckit generate" in target.read_text(encoding="utf-8")


def test_cli_008_emit_command_codex_writes_skill_compatible_file(tmp_path) -> None:
    target = tmp_path / "SKILL.md"

    exit_code, _ = _invoke(["emit-command", "--format", "codex", "--out", str(target)])

    assert exit_code == 0
    assert "name: arckit" in target.read_text(encoding="utf-8")


def test_cli_009_root_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["arckit", "--help"])

    assert exc.value.code == 0
    assert "Bridge arc-kit artifacts" in capsys.readouterr().out


def test_cli_010_generate_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["arckit", "generate", "--help"])

    assert exc.value.code == 0
    assert "Generate constitution.yaml" in capsys.readouterr().out
