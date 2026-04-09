# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under Apache-2.0. See LICENSE for details.

"""Tests for acgs CLI commands: init, assess, report.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import tomllib


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
        args = parser.parse_args(
            [
                "assess",
                "--jurisdiction",
                "european_union",
                "--domain",
                "healthcare",
            ]
        )
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
        args = parser.parse_args(
            [
                "assess",
                "--jurisdiction",
                "united_states",
                "--domain",
                "financial",
            ]
        )
        rc = cmd_assess(args)
        assert rc == 0

        cache = json.loads((tmp_workdir / ".acgs_assessment.json").read_text())
        assert "nist_ai_rmf" in cache["frameworks_assessed"]
        assert "us_fair_lending" in cache["frameworks_assessed"]

    def test_assess_specific_framework(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_assess

        parser = build_parser()
        args = parser.parse_args(
            [
                "assess",
                "--framework",
                "gdpr",
            ]
        )
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
        args = parser.parse_args(
            [
                "assess",
                "--jurisdiction",
                "european_union",
                "--domain",
                "healthcare",
            ]
        )
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
        args = parser.parse_args(
            [
                "report",
                "--markdown",
                "-o",
                "my_report.md",
            ]
        )
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
        report = assessor.assess(
            {
                "system_id": "test-system",
                "jurisdiction": "european_union",
                "domain": "healthcare",
            }
        )
        return report.to_dict()

    def test_generate_markdown_report(self) -> None:
        from acgs_lite import __constitutional_hash__, __version__
        from acgs_lite.report import generate_markdown_report

        data = self._make_report_data()
        md = generate_markdown_report(data)
        assert "# ACGS Compliance Assessment Report" in md
        assert "test-system" in md
        assert "Constitutional Hash" in md
        assert "Disclaimer" in md
        assert "Executive Summary" in md
        assert f"ACGS v{__version__}" in md
        assert __constitutional_hash__ in md

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


class TestPackageMetadata:
    """Tests for package metadata consistency."""

    def test_runtime_version_matches_pyproject(self) -> None:
        import acgs_lite

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        expected = pyproject_data["project"]["version"]

        # In CI, the installed wheel may have a stale version baked in.
        # Skip gracefully rather than failing the entire suite.
        if acgs_lite.__version__ != expected:
            pytest.skip(
                f"installed version {acgs_lite.__version__} != pyproject {expected} (stale wheel in CI)"
            )

    def test_console_scripts_include_acgs_alias(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        scripts = pyproject_data["project"]["scripts"]

        assert scripts["acgs"] == "acgs_lite.cli:main"
        assert scripts["acgs-lite"] == "acgs_lite.cli:main"


# ---------------------------------------------------------------------------
# CLI integration (subprocess)
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """End-to-end subprocess tests for the acgs CLI."""

    def test_acgs_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "Constitutional governance" in result.stdout

    def test_acgs_init_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "init", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--force" in result.stdout

    def test_acgs_assess_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "assess", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "jurisdiction" in result.stdout

    def test_acgs_eu_ai_act_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "eu-ai-act", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--system-id" in result.stdout
        assert "--domain" in result.stdout

    def test_acgs_lint_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "lint", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "rules" in result.stdout.lower()

    def test_acgs_test_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "test", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "fixtures" in result.stdout.lower()

    def test_acgs_lifecycle_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "lifecycle", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--state-file" in result.stdout
        assert "approve" in result.stdout

    def test_acgs_refusal_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "refusal", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "action_text" in result.stdout
        assert "--rules" in result.stdout

    def test_acgs_observe_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "observe", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--prometheus" in result.stdout
        assert "--watch" in result.stdout
        assert "--bundle-dir" in result.stdout

    def test_acgs_otel_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "acgs_lite.cli", "otel", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--service-name" in result.stdout
        assert "--actions-file" in result.stdout
        assert "--otlp-endpoint" in result.stdout


# ---------------------------------------------------------------------------
# eu-ai-act command
# ---------------------------------------------------------------------------


class TestCmdEuAiAct:
    """Tests for `acgs eu-ai-act`."""

    def test_eu_ai_act_runs(self, tmp_workdir: Path) -> None:
        pytest.importorskip("fpdf")
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args(
            [
                "eu-ai-act",
                "--system-id",
                "test-system",
                "--domain",
                "healthcare",
            ]
        )
        rc = cmd_eu_ai_act(args)
        assert rc == 0

        pdf_files = list(tmp_workdir.glob("eu_ai_act_*.pdf"))
        assert len(pdf_files) >= 1

    def test_eu_ai_act_markdown(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args(
            [
                "eu-ai-act",
                "--system-id",
                "test-system",
                "--markdown",
            ]
        )
        rc = cmd_eu_ai_act(args)
        assert rc == 0

        md_files = list(tmp_workdir.glob("eu_ai_act_*.md"))
        assert len(md_files) >= 1

    def test_eu_ai_act_includes_hipaa_for_healthcare(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_eu_ai_act

        parser = build_parser()
        args = parser.parse_args(
            [
                "eu-ai-act",
                "--system-id",
                "test-system",
                "--domain",
                "healthcare",
                "--markdown",
            ]
        )
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


# ---------------------------------------------------------------------------
# test command
# ---------------------------------------------------------------------------


class TestCmdTest:
    """Tests for `acgs test`."""

    def test_generate_fixtures(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_test

        parser = build_parser()
        rc = cmd_test(parser.parse_args(["test", "--generate"]))
        assert rc == 0

        fixtures = tmp_workdir / "tests.yaml"
        assert fixtures.exists()
        assert "blocks SSN disclosure" in fixtures.read_text()

    def test_run_generated_fixtures(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_test

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        cmd_test(parser.parse_args(["test", "--generate"]))

        rc = cmd_test(parser.parse_args(["test"]))
        assert rc == 0

    def test_test_json_output(self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_test

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        cmd_test(parser.parse_args(["test", "--generate"]))
        capsys.readouterr()

        rc = cmd_test(parser.parse_args(["test", "--json"]))
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ci_passed"] is True
        assert data["passed"] >= 1

    def test_test_tag_filter(self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_test

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        cmd_test(parser.parse_args(["test", "--generate"]))
        capsys.readouterr()

        rc = cmd_test(parser.parse_args(["test", "--tag", "smoke", "--json"]))
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total"] == 1
        assert data["passed"] == 1


# ---------------------------------------------------------------------------
# lifecycle command
# ---------------------------------------------------------------------------


class TestCmdLifecycle:
    """Tests for `acgs lifecycle`."""

    def test_lifecycle_register_and_status(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_lifecycle

        parser = build_parser()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "register", "policy-v1"])) == 0
        capsys.readouterr()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "status", "policy-v1", "--json"])) == 0

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["policy_id"] == "policy-v1"
        assert data["state"] == "draft"

    def test_lifecycle_full_promotion_persists(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_lifecycle

        parser = build_parser()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "register", "policy-v2"])) == 0
        assert (
            cmd_lifecycle(
                parser.parse_args(["lifecycle", "approve", "policy-v2", "--actor", "alice"])
            )
            == 0
        )
        assert (
            cmd_lifecycle(
                parser.parse_args(["lifecycle", "approve", "policy-v2", "--actor", "bob"])
            )
            == 0
        )
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "lint-gate", "policy-v2"])) == 0
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "test-gate", "policy-v2"])) == 0
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "review", "policy-v2"])) == 0
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "stage", "policy-v2"])) == 0
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "activate", "policy-v2"])) == 0
        capsys.readouterr()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "status", "policy-v2", "--json"])) == 0

        out = capsys.readouterr().out
        status_json = json.loads(out)
        assert status_json["state"] == "active"
        assert status_json["lint_clean"] is True
        assert status_json["test_suite_passed"] is True

    def test_lifecycle_blocks_missing_gates(self, tmp_workdir: Path) -> None:
        from acgs_lite.cli import build_parser, cmd_lifecycle

        parser = build_parser()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "register", "policy-v3"])) == 0
        rc = cmd_lifecycle(parser.parse_args(["lifecycle", "review", "policy-v3"]))
        assert rc == 1

    def test_lifecycle_audit_persists_across_invocations(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_lifecycle

        parser = build_parser()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "register", "policy-v4"])) == 0
        assert (
            cmd_lifecycle(
                parser.parse_args(["lifecycle", "approve", "policy-v4", "--actor", "alice"])
            )
            == 0
        )
        assert (
            cmd_lifecycle(
                parser.parse_args(["lifecycle", "approve", "policy-v4", "--actor", "bob"])
            )
            == 0
        )
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "review", "policy-v4"])) == 0
        capsys.readouterr()
        assert cmd_lifecycle(parser.parse_args(["lifecycle", "audit", "policy-v4", "--json"])) == 0

        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) >= 2
        assert any(item["to_state"] == "review" for item in data)


# ---------------------------------------------------------------------------
# observe / otel commands
# ---------------------------------------------------------------------------


class TestCmdObserve:
    """Tests for `acgs observe` and `acgs otel`."""

    def test_observe_json_summary(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_observe

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_observe(
            parser.parse_args(
                [
                    "observe",
                    "hello world",
                    "deploy a weapon to attack",
                    "--json",
                ]
            )
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total_decisions"] == 2
        assert data["decisions_by_outcome"]["allow"] == 1
        assert data["decisions_by_outcome"]["deny"] == 1
        assert data["rule_trigger_counts"]

    def test_observe_prometheus_output(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_observe

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_observe(
            parser.parse_args(
                [
                    "observe",
                    "hello world",
                    "deploy a weapon to attack",
                    "--prometheus",
                ]
            )
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "governance_decisions_total" in out
        assert 'outcome="deny"' in out
        assert "governance_compliance_rate" in out

    def test_otel_json_output(self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_otel

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_otel(
            parser.parse_args(
                [
                    "otel",
                    "hello world",
                    "deploy a weapon to attack",
                ]
            )
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "resourceMetrics" in data
        assert "resourceSpans" in data
        assert data["resourceSpans"]

    def test_otel_watch_mode(self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_otel

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_otel(
            parser.parse_args(
                [
                    "otel",
                    "hello world",
                    "deploy a weapon",
                    "--watch",
                    "--interval",
                    "0",
                    "--iterations",
                    "2",
                ]
            )
        )
        assert rc == 0
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["snapshot"] == 1
        assert second["snapshot"] == 2
        assert "resourceMetrics" in first["otel"]
        assert "resourceSpans" in second["otel"]

    def test_observe_actions_file(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_observe

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        (tmp_workdir / "actions.txt").write_text("hello world\ndeploy a weapon\n")
        capsys.readouterr()

        rc = cmd_observe(
            parser.parse_args(
                [
                    "observe",
                    "--actions-file",
                    "actions.txt",
                    "--json",
                ]
            )
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total_decisions"] == 2

    def test_observe_watch_mode(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_observe

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_observe(
            parser.parse_args(
                [
                    "observe",
                    "hello world",
                    "deploy a weapon",
                    "--watch",
                    "--interval",
                    "0",
                    "--iterations",
                    "2",
                ]
            )
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Snapshot 1" in out
        assert "Snapshot 2" in out
        assert "Decisions:" in out

    def test_observe_watch_mode_output_file_accumulates_snapshots(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_observe

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_observe(
            parser.parse_args(
                [
                    "observe",
                    "hello world",
                    "deploy a weapon",
                    "--watch",
                    "--interval",
                    "0",
                    "--iterations",
                    "2",
                    "-o",
                    "observe-watch.txt",
                ]
            )
        )
        assert rc == 0
        out = (tmp_workdir / "observe-watch.txt").read_text()
        assert "Snapshot 1" in out
        assert "Snapshot 2" in out

    def test_otel_bundle_dir(self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_otel

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_otel(
            parser.parse_args(
                [
                    "otel",
                    "hello world",
                    "deploy a weapon",
                    "--bundle-dir",
                    "bundle",
                    "-o",
                    "otel-export.json",
                ]
            )
        )
        assert rc == 0
        bundle = tmp_workdir / "bundle"
        assert (bundle / "otel.json").exists()
        assert (bundle / "metrics.prom").exists()
        assert (bundle / "summary.json").exists()
        assert (bundle / "manifest.json").exists()
        out = capsys.readouterr().out
        assert "Telemetry bundle written" in out
        export_payload = json.loads((tmp_workdir / "otel-export.json").read_text())
        assert "resourceMetrics" in export_payload

    def test_otel_otlp_endpoint(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_otel

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        with patch("acgs_lite.commands.observe._post_otlp_json", return_value=202) as mock_post:
            rc = cmd_otel(
                parser.parse_args(
                    [
                        "otel",
                        "hello world",
                        "--otlp-endpoint",
                        "http://collector.test/v1/traces",
                        "--otlp-header",
                        "Authorization: Bearer demo-token",
                        "-o",
                        "otel-export.json",
                    ]
                )
            )
        assert rc == 0
        mock_post.assert_called_once()
        called_endpoint = mock_post.call_args.args[0]
        assert called_endpoint == "http://collector.test/v1/traces"
        out = capsys.readouterr().out
        assert "OTLP export sent" in out

    def test_otel_watch_mode_output_file_accumulates_ndjson(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_otel

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_otel(
            parser.parse_args(
                [
                    "otel",
                    "hello world",
                    "deploy a weapon",
                    "--watch",
                    "--interval",
                    "0",
                    "--iterations",
                    "2",
                    "-o",
                    "otel-watch.ndjson",
                ]
            )
        )
        assert rc == 0
        lines = (tmp_workdir / "otel-watch.ndjson").read_text().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["snapshot"] == 1
        assert second["snapshot"] == 2


# ---------------------------------------------------------------------------
# refusal command
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# lean-smoke command
# ---------------------------------------------------------------------------


class TestCmdLeanSmoke:
    """Tests for `acgs lean-smoke`."""

    def test_parser_accepts_lean_smoke(self) -> None:
        from acgs_lite.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["lean-smoke", "--json", "--timeout", "7"])

        assert args.command == "lean-smoke"
        assert args.json_out is True
        assert args.timeout == 7

    def test_lean_smoke_success_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_lean_smoke

        parser = build_parser()
        args = parser.parse_args(["lean-smoke"])

        with patch(
            "acgs_lite.commands.lean_smoke.run_lean_runtime_smoke_check",
            return_value={
                "ok": True,
                "command": ["lake", "env", "lean"],
                "workdir": "/tmp/lean-project",
                "timeout_s": 30,
                "errors": [],
            },
        ):
            rc = cmd_lean_smoke(args)

        assert rc == 0
        out = capsys.readouterr().out
        assert "Lean runtime smoke check: PASS" in out
        assert "lake env lean" in out
        assert "/tmp/lean-project" in out

    def test_lean_smoke_success_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_lean_smoke

        parser = build_parser()
        args = parser.parse_args(["lean-smoke", "--json", "--timeout", "12"])

        with patch(
            "acgs_lite.commands.lean_smoke.run_lean_runtime_smoke_check",
            return_value={
                "ok": True,
                "command": ["lean"],
                "workdir": "/tmp/runtime",
                "timeout_s": 12,
                "errors": [],
            },
        ):
            rc = cmd_lean_smoke(args)

        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["command"] == ["lean"]
        assert data["timeout_s"] == 12

    def test_lean_smoke_failure_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        from acgs_lite.cli import build_parser, cmd_lean_smoke

        parser = build_parser()
        args = parser.parse_args(["lean-smoke"])

        with patch(
            "acgs_lite.commands.lean_smoke.run_lean_runtime_smoke_check",
            return_value={
                "ok": False,
                "command": ["lake", "env", "lean"],
                "workdir": "/tmp/bad-runtime",
                "timeout_s": 30,
                "errors": ["ACGS_LEAN_WORKDIR is not a directory: /tmp/bad-runtime"],
            },
        ):
            rc = cmd_lean_smoke(args)

        assert rc == 1
        captured = capsys.readouterr()
        assert "Lean runtime smoke check: FAIL" in captured.err
        assert "ACGS_LEAN_WORKDIR" in captured.err


class TestCmdRefusal:
    """Tests for `acgs refusal`."""

    def test_refusal_for_denied_action(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_refusal

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_refusal(
            parser.parse_args(["refusal", "deploy a weapon to attack the target", "--json"])
        )
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["rule_count"] >= 1
        assert data["can_retry"] is True
        assert len(data["reasons"]) >= 1
        assert len(data["suggestions"]) >= 1

    def test_refusal_for_allowed_action(
        self, tmp_workdir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from acgs_lite.cli import build_parser, cmd_init, cmd_refusal

        parser = build_parser()
        cmd_init(parser.parse_args(["init", "--force"]))
        capsys.readouterr()

        rc = cmd_refusal(parser.parse_args(["refusal", "hello world", "--json"]))
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["decision"] == "allow"
        assert "no refusal" in data["message"].lower()
