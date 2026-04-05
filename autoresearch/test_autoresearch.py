"""
Tests for autoresearch tooling: results_utils, feature_grid, bench_stable, log_run.

Run from repo root:
    python3 -m pytest autoresearch/test_autoresearch.py -v --import-mode=importlib
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTORESEARCH = Path(__file__).parent
PYTHON = sys.executable


def _tsv(rows: list[str]) -> str:
    header = "commit\tcomposite\tcompliance\tp99_ms\tscope\tstatus\tdescription\n"
    return header + "\n".join(rows) + "\n"


def _row(
    commit: str = "abc1234",
    composite: float = 0.999800,
    compliance: float = 1.0,
    p99_ms: float = 0.005,
    scope: str = "hot-path",
    status: str = "improved",
    description: str = "engine: fast dispatch",
) -> str:
    return f"{commit}\t{composite:.6f}\t{compliance:.6f}\t{p99_ms:.6f}\t{scope}\t{status}\t{description}"


# ---------------------------------------------------------------------------
# results_utils
# ---------------------------------------------------------------------------


class TestResultsUtils:
    @pytest.fixture(autouse=True)
    def _import(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import results_utils

        self.ru = importlib.reload(results_utils)

    # --- extract_family ---

    def test_extract_family_matcher(self):
        assert self.ru.extract_family("matcher: aho-corasick shared scanner") == "matcher"

    def test_extract_family_constitution(self):
        assert self.ru.extract_family("constitution: precompute rule tuples") == "constitution"

    def test_extract_family_rust(self):
        assert self.ru.extract_family("rust: bitmask scan_hot path") == "rust"

    def test_extract_family_warmup(self):
        assert self.ru.extract_family("gc.disable() after gc.freeze") == "warmup"

    def test_extract_family_engine(self):
        assert self.ru.extract_family("engine: unified validate dispatch") == "engine"

    def test_extract_family_method(self):
        assert self.ru.extract_family("method: tighter tie-band baseline") == "method"

    def test_extract_family_general_fallback(self):
        assert self.ru.extract_family("exp99: some random change") == "general"

    def test_extract_family_strips_sidecar_marker(self):
        # Sidecar prefix shouldn't prevent family detection
        result = self.ru.extract_family("[sidecar] matcher: keyword scan")
        assert result == "matcher"

    # --- ceiling_detected ---

    def test_ceiling_not_detected_with_improvement(self, tmp_path):
        rows_text = _tsv(
            [
                _row(status="discard"),
                _row(status="discard"),
                _row(status="discard"),
                _row(status="discard"),
                _row(status="improved"),  # improvement in window → no ceiling
            ]
        )
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_detected(rows, scope="hot-path", window=5) is False

    def test_ceiling_detected_all_discards(self, tmp_path):
        rows_text = _tsv([_row(status="discard")] * 5)
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_detected(rows, scope="hot-path", window=5) is True

    def test_ceiling_detected_neutral_only(self, tmp_path):
        rows_text = _tsv([_row(status="neutral-kept")] * 5)
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_detected(rows, scope="hot-path", window=5) is True

    def test_ceiling_not_detected_below_window(self, tmp_path):
        rows_text = _tsv([_row(status="discard")] * 3)
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_detected(rows, scope="hot-path", window=5) is False

    def test_ceiling_scope_isolated(self, tmp_path):
        """Ceiling in sidecar should not affect hot-path detection."""
        rows_text = _tsv(
            [_row(scope="sidecar", status="discard")] * 5
            + [_row(scope="hot-path", status="improved")]
        )
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_detected(rows, scope="hot-path", window=5) is False
        assert self.ru.ceiling_detected(rows, scope="sidecar", window=5) is True

    # --- ceiling_tightness ---

    def test_ceiling_tightness_none_when_no_ceiling(self, tmp_path):
        rows_text = _tsv([_row(status="improved")] * 5)
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_tightness(rows, scope="hot-path") is None

    def test_ceiling_tightness_tight(self, tmp_path):
        # All composites within 0.000050 of each other → tight
        base = 0.999800
        rows_text = _tsv([_row(composite=base + i * 0.000010, status="discard") for i in range(5)])
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_tightness(rows, scope="hot-path", tight_band=0.0001) == "tight"

    def test_ceiling_tightness_loose(self, tmp_path):
        # Composites spread 0.000300 → loose
        rows_text = _tsv(
            [
                _row(composite=0.999500, status="discard"),
                _row(composite=0.999700, status="discard"),
                _row(composite=0.999600, status="discard"),
                _row(composite=0.999550, status="discard"),
                _row(composite=0.999800, status="discard"),
            ]
        )
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_tightness(rows, scope="hot-path", tight_band=0.0001) == "loose"

    def test_ceiling_tightness_respects_window(self, tmp_path):
        # Only 3 rows → window=5 not reached → None
        rows_text = _tsv([_row(status="discard")] * 3)
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.ceiling_tightness(rows, scope="hot-path", window=5) is None

    # --- uncommitted_count ---

    def test_uncommitted_count_zero(self, tmp_path):
        rows_text = _tsv([_row(commit="abc1234"), _row(commit="def5678")])
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.uncommitted_count(rows) == 0

    def test_uncommitted_count_some(self, tmp_path):
        rows_text = _tsv(
            [
                _row(commit="uncommitted"),
                _row(commit="abc1234"),
                _row(commit="uncommitted"),
            ]
        )
        tsv = tmp_path / "results.tsv"
        tsv.write_text(rows_text)
        rows = self.ru.load_rows(tsv)
        assert self.ru.uncommitted_count(rows) == 2


# ---------------------------------------------------------------------------
# feature_grid
# ---------------------------------------------------------------------------


class TestFeatureGrid:
    @pytest.fixture(autouse=True)
    def _import(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import feature_grid

        self.fg = importlib.reload(feature_grid)
        import results_utils

        self.ru = importlib.reload(results_utils)

    def _load(self, tmp_path: Path, rows: list[str]):
        tsv = tmp_path / "results.tsv"
        tsv.write_text(_tsv(rows))
        return self.ru.load_rows(tsv)

    def test_build_grid_picks_best_composite(self, tmp_path):
        rows = self._load(
            tmp_path,
            [
                _row(
                    composite=0.999800,
                    scope="hot-path",
                    status="improved",
                    description="matcher: scan",
                ),
                _row(
                    composite=0.999850,
                    scope="hot-path",
                    status="neutral-kept",
                    description="matcher: scan v2",
                ),
                _row(
                    composite=0.999700,
                    scope="hot-path",
                    status="improved",
                    description="matcher: scan v3",
                ),
            ],
        )
        grid = self.fg.build_grid(rows)
        best = grid.get(("matcher", "hot-path"))
        assert best is not None
        assert float(best["composite"]) == pytest.approx(0.999850)

    def test_build_grid_excludes_discards_by_default(self, tmp_path):
        rows = self._load(
            tmp_path,
            [
                _row(
                    composite=0.999900,
                    scope="hot-path",
                    status="discard",
                    description="matcher: scan",
                ),
            ],
        )
        grid = self.fg.build_grid(rows, kept_only=True)
        assert ("matcher", "hot-path") not in grid

    def test_build_grid_includes_discards_when_requested(self, tmp_path):
        rows = self._load(
            tmp_path,
            [
                _row(
                    composite=0.999900,
                    scope="hot-path",
                    status="discard",
                    description="matcher: scan",
                ),
            ],
        )
        grid = self.fg.build_grid(rows, kept_only=False)
        assert ("matcher", "hot-path") in grid

    def test_build_grid_family_scope_isolation(self, tmp_path):
        rows = self._load(
            tmp_path,
            [
                _row(
                    composite=0.999800,
                    scope="hot-path",
                    status="improved",
                    description="matcher: scan",
                ),
                _row(
                    composite=0.999900,
                    scope="sidecar",
                    status="neutral-kept",
                    description="engine: batch",
                ),
            ],
        )
        grid = self.fg.build_grid(rows)
        assert ("matcher", "hot-path") in grid
        assert ("engine", "sidecar") in grid
        assert ("matcher", "sidecar") not in grid

    def test_ceiling_detected_integration(self, tmp_path):
        rows = self._load(tmp_path, [_row(status="discard")] * 5)
        assert self.ru.ceiling_detected(rows, "hot-path") is True

    def test_print_grid_runs_without_error(self, tmp_path, capsys):
        rows = self._load(
            tmp_path,
            [
                _row(composite=0.999800, status="improved", description="matcher: aho-corasick"),
                _row(
                    composite=0.999700,
                    status="neutral-kept",
                    scope="sidecar",
                    description="engine: batch",
                ),
            ],
        )
        self.fg.print_grid(rows, "any")
        out = capsys.readouterr().out
        assert "MAP-Elites" in out
        assert "matcher" in out

    def test_best_family_recency_penalty_deprioritises_exhausted(self, tmp_path):
        """A family tried > _RECENT_EXHAUSTION_THRESHOLD times recently should rank lower."""
        # Build 20 recent rows all in 'engine' family (exhausted)
        engine_rows = [
            _row(scope="hot-path", status="discard", description="engine: dispatch variant")
            for _ in range(20)
        ]
        # Plus one matcher row (not exhausted)
        matcher_row = _row(
            scope="hot-path",
            status="improved",
            description="matcher: aho-corasick",
            composite=0.999700,
        )
        rows = self._load(tmp_path, engine_rows + [matcher_row])
        grid = self.fg.build_grid(rows)

        suggestion = self.fg._best_family_to_explore(grid, rows, "hot-path")
        # Engine is exhausted (20 recent attempts >> threshold 5)
        # Any unexplored or less-exhausted family should be suggested instead
        assert suggestion != "engine"

    def test_best_family_prefers_unexplored_over_low_composite(self, tmp_path):
        """Completely unexplored families beat low-composite explored ones."""
        # Only 'engine' has a result — all others unexplored
        rows = self._load(
            tmp_path,
            [
                _row(composite=0.999500, status="improved", description="engine: fast dispatch"),
            ],
        )
        grid = self.fg.build_grid(rows)

        suggestion = self.fg._best_family_to_explore(grid, rows, "hot-path")
        # Should suggest an unexplored family, not engine (already explored)
        assert suggestion != "engine"
        assert suggestion in self.fg._ALL_FAMILIES

    def test_ceiling_tightness_used_in_print_grid(self, tmp_path, capsys):
        """Tight ceiling message differs from loose ceiling message."""
        # Tight: all composites within 0.000050
        base = 0.999800
        tight_rows = [_row(composite=base + i * 0.000010, status="discard") for i in range(5)]
        rows = self._load(tmp_path, tight_rows)
        self.fg.print_grid(rows, "hot-path")
        out = capsys.readouterr().out
        assert "TIGHT" in out or "tight" in out.lower()


# ---------------------------------------------------------------------------
# bench_stable
# ---------------------------------------------------------------------------


class TestBenchStable:
    def test_help_exits_zero(self):
        r = subprocess.run(
            [PYTHON, str(AUTORESEARCH / "bench_stable.py"), "--help"],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0
        assert "--trials" in r.stdout

    def test_invalid_trials_exits_nonzero(self):
        r = subprocess.run(
            [PYTHON, str(AUTORESEARCH / "bench_stable.py"), "--trials", "0"],
            capture_output=True,
            text=True,
        )
        assert r.returncode != 0

    def test_single_trial_produces_parseable_log(self, tmp_path):
        out = tmp_path / "run.log"
        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "bench_stable.py"),
                "--trials",
                "1",
                "--out",
                str(out),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=str(AUTORESEARCH.parent),
        )
        assert r.returncode == 0, f"stderr: {r.stderr[:500]}"
        assert out.exists()
        content = out.read_text()
        assert "composite_score" in content
        assert "compliance_rate" in content
        # Parseable by log_run metric pattern
        assert re.search(r"composite_score:\s+[\d.]+", content)

    def test_median_metrics_internal(self):
        """_median_metrics returns element-wise medians."""
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        trials = [
            {"composite_score": 0.9998, "p99_latency_ms": 0.005},
            {"composite_score": 0.9999, "p99_latency_ms": 0.004},
            {"composite_score": 0.9997, "p99_latency_ms": 0.006},
        ]
        result = bs._median_metrics(trials)
        assert result["composite_score"] == pytest.approx(0.9998)
        assert result["p99_latency_ms"] == pytest.approx(0.005)

    def test_format_block_contains_separator(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        metrics = {
            "composite_score": 0.999800,
            "compliance_rate": 1.0,
            "p99_latency_ms": 0.005,
            "errors": 0.0,
            "scenarios_tested": 532.0,
        }
        block = bs._format_block(metrics)
        assert block.startswith("---")
        assert block.endswith("---")
        assert "composite_score" in block
        # Integer metrics should not show decimals
        assert "532" in block
        assert "0.000000" not in block.split("errors")[1].split("\n")[0]

    def test_cascade_check_compliance_failure(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        bad = {
            "composite_score": 0.999800,
            "compliance_rate": 0.98,
            "false_negative_rate": 0.0,
            "errors": 0,
        }
        reason = bs._cascade_check(bad)
        assert reason is not None
        assert "compliance" in reason.lower()

    def test_cascade_check_fn_failure(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        bad = {
            "composite_score": 0.999800,
            "compliance_rate": 1.0,
            "false_negative_rate": 0.02,
            "errors": 0,
        }
        reason = bs._cascade_check(bad)
        assert reason is not None
        assert "false_negative" in reason.lower()

    def test_cascade_check_error_count(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        bad = {
            "composite_score": 0.999800,
            "compliance_rate": 1.0,
            "false_negative_rate": 0.0,
            "errors": 3,
        }
        reason = bs._cascade_check(bad)
        assert reason is not None
        assert "error" in reason.lower()

    def test_cascade_check_good_result_returns_none(self):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        good = {
            "composite_score": 0.999900,
            "compliance_rate": 1.0,
            "false_negative_rate": 0.0,
            "errors": 0,
        }
        assert bs._cascade_check(good) is None

    def test_checkpoint_save_load_cleanup(self, tmp_path):
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        out = tmp_path / "run.log"
        metrics = {"composite_score": 0.9998, "p99_latency_ms": 0.005, "compliance_rate": 1.0}

        bs._save_trial(out, 1, metrics)
        assert bs._artifact_path(out, 1).exists()

        cached = bs._load_cached_trials(out, 3)
        assert 1 in cached
        assert cached[1]["composite_score"] == pytest.approx(0.9998)
        assert 2 not in cached  # trial 2 was never saved

        bs._cleanup_trials(out, 3)
        assert not bs._artifact_path(out, 1).exists()

    def test_timeout_handled_gracefully(self):
        """_run_trial with a very short timeout returns None without crashing."""
        import importlib
        import sys as _sys

        if str(AUTORESEARCH) not in _sys.path:
            _sys.path.insert(0, str(AUTORESEARCH))
        import bench_stable

        bs = importlib.reload(bench_stable)

        # Use timeout=0 to force immediate expiry on any subprocess
        # We patch subprocess.run to raise TimeoutExpired
        import subprocess as sp
        import unittest.mock as mock

        with mock.patch(
            "bench_stable.subprocess.run", side_effect=sp.TimeoutExpired(cmd="python3", timeout=0)
        ):
            result = bs._run_trial(1, quiet=True, timeout=0)
        assert result is None

    def test_provenance_header_in_output(self, tmp_path):
        """Output file should contain provenance metadata outside the --- block."""
        out = tmp_path / "run.log"
        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "bench_stable.py"),
                "--trials",
                "1",
                "--out",
                str(out),
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=str(AUTORESEARCH.parent),
        )
        assert r.returncode == 0
        content = out.read_text()
        assert "bench_stable_trials:" in content
        assert "composite_spread:" in content
        assert "p99_spread_ms:" in content


# ---------------------------------------------------------------------------
# log_run
# ---------------------------------------------------------------------------


class TestLogRun:
    def test_uncommitted_warning_printed(self, tmp_path, capsys):
        """log_run warns to stderr when commit is 'uncommitted'."""
        # Create a minimal fake log
        log = tmp_path / "run.log"
        log.write_text(
            textwrap.dedent("""\
            ---
            composite_score:       0.999800
            compliance_rate:       1.000000
            p99_latency_ms:        0.005000
            false_negative_rate:   0.000000
            false_positive_rate:   0.000000
            errors:                       0
            ---
        """)
        )
        tsv = tmp_path / "results.tsv"
        # Write a baseline row so status computation has a reference
        tsv.write_text(
            "commit\tcomposite\tcompliance\tp99_ms\tscope\tstatus\tdescription\n"
            "abc1234\t0.999700\t1.000000\t0.006000\thot-path\tbaseline\tinitial baseline\n"
        )

        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "log_run.py"),
                str(log),
                "--commit",
                "uncommitted",
                "--description",
                "test experiment",
            ],
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONPATH": str(AUTORESEARCH)},
            cwd=str(AUTORESEARCH),
        )
        # Should succeed (status improved or neutral), but warn
        assert "uncommitted" in r.stderr.lower() or "WARNING" in r.stderr

    def test_ceiling_warning_after_five_discards(self, tmp_path):
        """log_run prints ceiling warning after logging a 6th consecutive non-improved row."""
        tsv = tmp_path / "results.tsv"
        tsv.write_text(
            "commit\tcomposite\tcompliance\tp99_ms\tscope\tstatus\tdescription\n"
            + "\n".join(
                f"abc{i}\t0.999800\t1.000000\t0.005000\thot-path\tdiscard\texp{i}: thing"
                for i in range(5)
            )
            + "\n"
        )
        log = tmp_path / "run.log"
        log.write_text(
            textwrap.dedent("""\
            ---
            composite_score:       0.999750
            compliance_rate:       1.000000
            p99_latency_ms:        0.005500
            false_negative_rate:   0.000000
            false_positive_rate:   0.000000
            errors:                       0
            ---
        """)
        )

        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "log_run.py"),
                str(log),
                "--commit",
                "def9999",
                "--description",
                "exp6: another attempt",
            ],
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "PYTHONPATH": str(AUTORESEARCH),
                "AUTORESEARCH_RESULTS_TSV": str(tsv),
            },
            cwd=str(AUTORESEARCH),
        )
        combined = r.stdout + r.stderr
        assert "CEILING" in combined or "ceiling" in combined.lower()

    def test_recommend_flag_outputs_keep_or_discard(self, tmp_path):
        log = tmp_path / "run.log"
        log.write_text(
            textwrap.dedent("""\
            ---
            composite_score:       0.999900
            compliance_rate:       1.000000
            p99_latency_ms:        0.004000
            false_negative_rate:   0.000000
            false_positive_rate:   0.000000
            errors:                       0
            ---
        """)
        )
        r = subprocess.run(
            [PYTHON, str(AUTORESEARCH / "log_run.py"), str(log), "--recommend"],
            capture_output=True,
            text=True,
            cwd=str(AUTORESEARCH),
        )
        assert r.returncode == 0
        assert r.stdout.strip() in {"keep", "discard"}


# ---------------------------------------------------------------------------
# setup_run (smoke)
# ---------------------------------------------------------------------------


class TestSetupRun:
    def test_dry_run_exits_zero(self):
        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "setup_run.py"),
                "--tag",
                "test-ci",
                "--dry-run",
                "--dirty",
            ],
            capture_output=True,
            text=True,
            cwd=str(AUTORESEARCH),
        )
        assert r.returncode == 0
        assert "autoresearch/test-ci" in r.stdout

    def test_feature_grid_appears_in_output(self):
        r = subprocess.run(
            [
                PYTHON,
                str(AUTORESEARCH / "setup_run.py"),
                "--tag",
                "test-ci",
                "--dry-run",
                "--dirty",
            ],
            capture_output=True,
            text=True,
            cwd=str(AUTORESEARCH),
        )
        assert r.returncode == 0
        assert "MAP-Elites" in r.stdout or "feature" in r.stdout.lower()
