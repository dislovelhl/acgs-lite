# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.

"""Tests for acgs CLI commands: init, assess, report.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change to a clean temporary directory for each test."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestCmdInit:
    """Tests for `acgs init`."""

    def test_creates_rules_yaml(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init

        parser = build_parser()
        args = parser.parse_args(["init", "--force"])
        rc = cmd_init(args)
        assert rc == 0
        rules = tmp_workdir / "rules.yaml"
        assert rules.exists()
        content = rules.read_text()
        assert "safety-001" in content
        assert "privacy-001" in content

    def test_creates_ci_file(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init

        parser = build_parser()
        args = parser.parse_args(["init", "--force"])
        rc = cmd_init(args)
        assert rc == 0
        ci = tmp_workdir / ".gitlab-ci.yml"
        assert ci.exists()
        assert "governance" in ci.read_text()

    def test_github_actions_detected(self, tmp_workdir: Path) -> None:
        """When .github/workflows/ exists, create GitHub Actions config."""
        from acgs_lite.cli import build_parser, cmd_init

        (tmp_workdir / ".github" / "workflows").mkdir(parents=True)
        parser = build_parser()
        args = parser.parse_args(["init", "--force"])
        rc = cmd_init(args)
        assert rc == 0
        gha = tmp_workdir / ".github" / "workflows" / "acgs-governance.yml"
        assert gha.exists()
        assert "ACGS Governance" in gha.read_text()

    def test_no_overwrite_without_force(self, tmp_workdir: Path) -> None:
        (tmp_workdir / "rules.yaml").write_text("existing")
        from acgs_lite.cli import build_parser, cmd_init

        parser = build_parser()
        args = parser.parse_args(["init"])
        rc = cmd_init(args)
        assert rc == 1
        assert (tmp_workdir / "rules.yaml").read_text() == "existing"


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------


class TestCmdAssess:
    """Tests for `acgs assess`."""

    def test_assess_runs(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args([
            "assess",
            "--jurisdiction", "european_union",
            "--domain", "healthcare",
        ])
        rc = cmd_assess(args)
        assert rc == 0

        # Should create cached assessment
        cache = tmp_workdir / ".acgs_assessment.json"
        assert cache.exists()
        data = json.loads(cache.read_text())
        assert "overall_score" in data
        assert data["overall_score"] > 0.0
        assert "by_framework" in data

    def test_assess_us_financial(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args([
            "assess",
            "--jurisdiction", "united_states",
            "--domain", "financial",
        ])
        rc = cmd_assess(args)
        assert rc == 0

        cache = json.loads((tmp_workdir / ".acgs_assessment.json").read_text())
        assert "nist_ai_rmf" in cache["frameworks_assessed"]
        assert "us_fair_lending" in cache["frameworks_assessed"]

    def test_assess_specific_framework(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args([
            "assess",
            "--framework", "gdpr",
        ])
        rc = cmd_assess(args)
        assert rc == 0

        cache = json.loads((tmp_workdir / ".acgs_assessment.json").read_text())
        assert cache["frameworks_assessed"] == ["gdpr"]

    def test_assess_from_acgs_json(self, tmp_workdir: Path) -> None:
        """Test loading config from acgs.json."""
        config = {
            "system_id": "my-test-system",
            "jurisdiction": "european_union",
            "domain": "healthcare",
        }
        (tmp_workdir / "acgs.json").write_text(json.dumps(config))

        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args(["assess"])
        rc = cmd_assess(args)
        assert rc == 0

        cache = json.loads((tmp_workdir / ".acgs_assessment.json").read_text())
        assert cache["system_id"] == "my-test-system"


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


class TestCmdReport:
    """Tests for `acgs report`."""

    def _run_assess_first(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args([
            "assess",
            "--jurisdiction", "european_union",
            "--domain", "healthcare",
        ])
        cmd_assess(args)

    def test_report_markdown(self, tmp_workdir: Path) -> None:
        self._run_assess_first(tmp_workdir)
        from acgs_lite.cli import build_parser, cmd_report

        parser = build_parser()
        args = parser.parse_args(["report", "--markdown"])
        rc = cmd_report(args)
        assert rc == 0

        md_files = list(tmp_workdir.glob("*.md"))
        assert len(md_files) >= 1
        content = md_files[0].read_text()
        assert "ACGS Compliance Assessment Report" in content
        assert "Executive Summary" in content
        assert "Constitutional Hash" in content
        assert "Disclaimer" in content

    def test_report_json(self, tmp_workdir: Path) -> None:
        self._run_assess_first(tmp_workdir)
        from acgs_lite.cli import build_parser, cmd_report

        parser = build_parser()
        args = parser.parse_args(["report", "--json"])
        rc = cmd_report(args)
        assert rc == 0

        json_files = list(tmp_workdir.glob("acgs_compliance_*.json"))
        assert len(json_files) >= 1
        data = json.loads(json_files[0].read_text())
        assert "overall_score" in data
        assert "disclaimer" in data

    def test_report_pdf(self, tmp_workdir: Path) -> None:
        pytest.importorskip("fpdf")
        self._run_assess_first(tmp_workdir)
        from acgs_lite.cli import build_parser, cmd_report

        parser = build_parser()
        args = parser.parse_args(["report", "--pdf"])
        rc = cmd_report(args)
        assert rc == 0

        pdf_files = list(tmp_workdir.glob("*.pdf"))
        assert len(pdf_files) >= 1
        # PDF should be > 5KB (not empty)
        assert pdf_files[0].stat().st_size > 5000

    def test_report_custom_output(self, tmp_workdir: Path) -> None:
        self._run_assess_first(tmp_workdir)
        from acgs_lite.cli import build_parser, cmd_report

        parser = build_parser()
        args = parser.parse_args([
            "report", "--markdown", "-o", "my_report.md",
        ])
        rc = cmd_report(args)
        assert rc == 0
        assert (tmp_workdir / "my_report.md").exists()

    def test_report_without_prior_assess(self, tmp_workdir: Path) -> None:
        """Report should auto-run assessment if no cache exists."""
        from acgs_lite.cli import build_parser, cmd_report

        parser = build_parser()
        args = parser.parse_args(["report", "--json"])
        rc = cmd_report(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# report module
# ---------------------------------------------------------------------------


class TestReportModule:
    """Tests for acgs_lite.report module directly."""

    def _make_report_data(self) -> dict:
        from acgs_lite.compliance import MultiFrameworkAssessor

        assessor = MultiFrameworkAssessor()
        report = assessor.assess({
            "system_id": "test-system",
            "jurisdiction": "european_union",
            "domain": "healthcare",
        })
        return report.to_dict()

    def test_generate_markdown_report(self) -> None:
        from acgs_lite.report import generate_markdown_report

        data = self._make_report_data()
        md = generate_markdown_report(data)
        assert "# ACGS Compliance Assessment Report" in md
        assert "test-system" in md
        assert "Constitutional Hash" in md
        assert "Disclaimer" in md
        assert "Executive Summary" in md

    def test_markdown_contains_framework_tables(self) -> None:
        from acgs_lite.report import generate_markdown_report

        data = self._make_report_data()
        md = generate_markdown_report(data)
        assert "| Status |" in md
        assert "GDPR" in md

    def test_generate_report_json(self, tmp_path: Path) -> None:
        from acgs_lite.report import generate_report

        data = self._make_report_data()
        result = generate_report(data, tmp_path / "test.json", format="json")
        assert result.suffix == ".json"
        assert result.exists()
        loaded = json.loads(result.read_text())
        assert loaded["system_id"] == "test-system"

    def test_generate_report_markdown(self, tmp_path: Path) -> None:
        from acgs_lite.report import generate_report

        data = self._make_report_data()
        result = generate_report(data, tmp_path / "test.md", format="markdown")
        assert result.suffix == ".md"
        assert result.exists()
        assert "ACGS Compliance" in result.read_text()

    def test_generate_report_pdf(self, tmp_path: Path) -> None:
        pytest.importorskip("fpdf")
        from acgs_lite.report import generate_report

        data = self._make_report_data()
        result = generate_report(data, tmp_path / "test.pdf", format="pdf")
        assert result.suffix == ".pdf"
        assert result.exists()
        assert result.stat().st_size > 5000

    def test_score_bar(self) -> None:
        from acgs_lite.report import _score_bar

        bar = _score_bar(0.75, width=10)
        assert "75%" in bar
        assert "█" in bar
        assert "░" in bar


# ---------------------------------------------------------------------------
# CLI integration (subprocess)
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """End-to-end subprocess tests for the acgs CLI."""

    def test_acgs_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "Constitutional governance" in result.stdout

    def test_acgs_init_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "init", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--force" in result.stdout

    def test_acgs_assess_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "assess", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "jurisdiction" in result.stdout

    def test_acgs_eu_ai_act_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "eu-ai-act", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--system-id" in result.stdout
        assert "--domain" in result.stdout

    def test_acgs_lint_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "lint", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "rules" in result.stdout.lower()


# ---------------------------------------------------------------------------
# eu-ai-act command
# ---------------------------------------------------------------------------


class TestCmdEuAiAct:
    """Tests for `acgs eu-ai-act`."""

    def test_eu_ai_act_runs(self, tmp_workdir: Path) -> None:
        pytest.importorskip("fpdf")
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args([
            "eu-ai-act",
            "--system-id", "test-system",
            "--domain", "healthcare",
        ])
        rc = cmd_eu_ai_act(args)
        assert rc == 0

        pdf_files = list(tmp_workdir.glob("eu_ai_act_*.pdf"))
        assert len(pdf_files) >= 1

    def test_eu_ai_act_markdown(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args([
            "eu-ai-act",
            "--system-id", "test-system",
            "--markdown",
        ])
        rc = cmd_eu_ai_act(args)
        assert rc == 0

        md_files = list(tmp_workdir.glob("eu_ai_act_*.md"))
        assert len(md_files) >= 1

    def test_eu_ai_act_includes_hipaa_for_healthcare(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args([
            "eu-ai-act",
            "--system-id", "test-system",
            "--domain", "healthcare",
            "--markdown",
        ])
        rc = cmd_eu_ai_act(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# lint command
# ---------------------------------------------------------------------------


class TestCmdLint:
    """Tests for `acgs lint`."""

    def test_lint_passes_on_valid_rules(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_lint

        # Create rules.yaml
        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))

        args = parser.parse_args(["lint"])
        rc = cmd_lint(args)
        assert rc == 0  # warnings only, no errors

    def test_lint_missing_file(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_lint

        parser = build_parser()
        args = parser.parse_args(["lint", "nonexistent.yaml"])
        rc = cmd_lint(args)
        assert rc == 1

    def test_lint_custom_path(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_lint

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))

        # Rename rules to custom path
        (tmp_workdir / "rules.yaml").rename(tmp_workdir / "my_rules.yaml")

        args = parser.parse_args(["lint", "my_rules.yaml"])
        rc = cmd_lint(args)
        assert rc == 0


# ---------------------------------------------------------------------------
# init generates acgs.json
# ---------------------------------------------------------------------------


class TestInitConfig:
    """Tests for acgs.json generation by init."""

    def test_init_creates_acgs_json(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))

        config_path = tmp_workdir / "acgs.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert "system_id" in config
        assert "jurisdiction" in config
        assert "domain" in config
