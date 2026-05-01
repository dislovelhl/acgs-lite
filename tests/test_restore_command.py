"""Tests for ``acgs restore`` — hot-backup recovery command.

Locked argv: ``acgs restore --bundle-id ID --backup-path PATH [--system-id ID]
[--dry-run] [--json] [--debug]``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from acgs_lite import (
    MACIRole,
    ProductionProfile,
)
from acgs_lite.cli import build_parser
from acgs_lite.commands import restore as restore_cmd

CONSTITUTION_YAML = """
name: production-test
version: 1.0.0
rules:
  - id: no-secret-exfiltration
    text: Do not exfiltrate secrets
    severity: critical
    keywords: [secret, exfiltrate]
"""

ALT_CONSTITUTION_YAML = """
name: production-test-alt
version: 1.0.1
rules:
  - id: no-pii-leak
    text: Do not leak PII
    severity: critical
    keywords: [pii, leak]
"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mk_profile(
    *,
    constitution_path: Path,
    backup_path: Path,
    constitutional_hash: str,
    bundle_id: str = "test-bundle-1",
) -> ProductionProfile:
    return ProductionProfile(
        enforce_maci=True,
        maci_role=MACIRole.PROPOSER,
        constitution_artifact_path=constitution_path,
        expected_artifact_sha256=_sha256(constitution_path.read_bytes()),
        expected_constitutional_hash=constitutional_hash,
        backup_artifact_path=backup_path,
        rollback_bundle_id=bundle_id,
        rbac_enabled=True,
    )


@pytest.fixture
def profile_loader_env(monkeypatch, tmp_path: Path):
    """Yield a helper that registers a loader callable on the env path."""

    state: dict[str, ProductionProfile] = {}

    # We register the loader in restore_cmd's importable namespace so that
    # ACGS_PRODUCTION_PROFILE_LOADER can resolve via importlib.
    import acgs_lite.commands.restore as restore_mod

    def loader() -> ProductionProfile:
        return state["profile"]

    restore_mod._test_profile_loader = loader  # type: ignore[attr-defined]
    monkeypatch.setenv(
        "ACGS_PRODUCTION_PROFILE_LOADER",
        "acgs_lite.commands.restore:_test_profile_loader",
    )

    def install(profile: ProductionProfile) -> None:
        state["profile"] = profile

    yield install


def _compute_constitution_hash(yaml_text: str, tmp_path: Path) -> str:
    """Write yaml to disk and parse it to derive the canonical constitutional hash."""
    from acgs_lite.constitution import Constitution

    path = tmp_path / "_hash_probe.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return Constitution.from_yaml(path).hash


def _make_args(**kwargs):
    """Build an argparse.Namespace mimicking the parser output."""
    defaults = dict(
        bundle_id="test-bundle-1",
        backup_path=None,
        system_id=None,
        dry_run=False,
        json_out=False,
        debug=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Argv signature
# ---------------------------------------------------------------------------


class TestRestoreHelpArgvSignature:
    def test_restore_help_argv_signature(self):
        """`acgs restore --help` advertises the locked argv signature."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["restore", "--help"])

    def test_restore_requires_bundle_id(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["restore"])  # missing --bundle-id

    def test_restore_parses_full_argv(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "restore",
                "--bundle-id",
                "b1",
                "--backup-path",
                "/tmp/x.yaml",
                "--system-id",
                "sys-1",
                "--dry-run",
                "--json",
                "--debug",
            ]
        )
        assert args.command == "restore"
        assert args.bundle_id == "b1"
        assert args.backup_path == "/tmp/x.yaml"
        assert args.system_id == "sys-1"
        assert args.dry_run is True
        assert args.json_out is True
        assert args.debug is True


# ---------------------------------------------------------------------------
# Round-trip + happy path
# ---------------------------------------------------------------------------


class TestRestoreRoundTrip:
    def test_restore_round_trip(self, profile_loader_env, tmp_path: Path):
        """backup → corrupt active → restore → re-validate → hash matches."""
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        # Corrupt the active artifact.
        active.write_text("CORRUPTED", encoding="utf-8")

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_OK

        # After restore, active should match original CONSTITUTION_YAML.
        assert active.read_text(encoding="utf-8") == CONSTITUTION_YAML
        # Backup file is preserved (copy + atomic-replace, not destructive move)
        # so that re-validation can still find it and so the next failover
        # has a known-good artifact still on disk.
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == CONSTITUTION_YAML


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestRestoreMissingBackup:
    def test_restore_missing_backup_exits_3(self, profile_loader_env, tmp_path: Path):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "missing-backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_IO


class TestRestoreCorruptBackup:
    def test_restore_corrupt_backup_exits_2_clean_message(
        self, profile_loader_env, tmp_path: Path, capsys
    ):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text("not: valid: yaml: at: all: !!\n  bogus", encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_VALIDATION

        captured = capsys.readouterr()
        # Clean error message — no path leak in non-debug mode, no raw exc str.
        assert "docs:" in captured.err
        assert "cause:" in captured.err
        # Path must NOT appear in non-debug message.
        assert str(backup) not in captured.err
        # Active must still be intact (no atomic move performed).
        assert active.read_text(encoding="utf-8") == CONSTITUTION_YAML


class TestRestoreHashMismatch:
    def test_restore_post_validate_hash_mismatch_exits_4(
        self, profile_loader_env, tmp_path: Path, monkeypatch
    ):
        """Force a post-restore hash mismatch by mutating loader between calls.

        We simulate the scenario where the active profile's expected hash drifts
        from the backup's actual content: the backup parses cleanly + matches
        expected at pre-validation, but a substitute validator returns a
        different hash to model the post-restore mismatch surface.
        """
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        from acgs_lite.production import ProductionProfileValidation

        def fake_validate(prof):
            return ProductionProfileValidation(
                constitution_artifact_path=Path(prof.constitution_artifact_path),
                artifact_sha256="0" * 64,
                constitutional_hash="DIFFERENT_HASH_AFTER_RESTORE",
                backup_artifact_path=Path(str(prof.backup_artifact_path)),
                rollback_bundle_id=prof.rollback_bundle_id,
                audit_log_path=None,
            )

        monkeypatch.setattr(restore_cmd, "validate_production_profile", fake_validate)

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_HASH_MISMATCH


# ---------------------------------------------------------------------------
# Dry-run + JSON
# ---------------------------------------------------------------------------


class TestRestoreDryRun:
    def test_restore_dry_run_does_not_mutate(self, profile_loader_env, tmp_path: Path):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        original_active_bytes = active.read_bytes()
        original_backup_bytes = backup.read_bytes()

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(
                bundle_id="test-bundle-1",
                backup_path=str(backup),
                dry_run=True,
            ),
        )
        assert rc == restore_cmd.EXIT_OK
        # Neither file mutated.
        assert active.read_bytes() == original_active_bytes
        assert backup.read_bytes() == original_backup_bytes


class TestRestoreJsonOutput:
    def test_restore_json_output_machine_readable(self, profile_loader_env, tmp_path: Path, capsys):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(
                bundle_id="test-bundle-1",
                backup_path=str(backup),
                dry_run=True,
                json_out=True,
            ),
        )
        assert rc == restore_cmd.EXIT_OK

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is True
        assert payload["bundle_id"] == "test-bundle-1"
        assert payload["constitutional_hash"] == c_hash
        assert payload["dry_run"] is True


# ---------------------------------------------------------------------------
# Security: path/hash redaction without --debug
# ---------------------------------------------------------------------------


class TestRestoreRedactsPathsWithoutDebugFlag:
    def test_restore_redacts_paths_without_debug_flag(
        self, profile_loader_env, tmp_path: Path, capsys
    ):
        """Non-debug error messages must not leak filesystem paths."""
        active = tmp_path / "constitution-SENSITIVE.yaml"
        backup = tmp_path / "constitution.backup-SENSITIVE.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text("CORRUPTED YAML !!!", encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_VALIDATION

        captured = capsys.readouterr()
        # No path-leak in the non-debug error message.
        assert "SENSITIVE" not in captured.err
        # No raw constitutional_hash in non-debug error.
        assert c_hash not in captured.err

    def test_restore_debug_includes_paths(self, profile_loader_env, tmp_path: Path, capsys):
        active = tmp_path / "constitution-DBG.yaml"
        backup = tmp_path / "missing-DBG.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(
                bundle_id="test-bundle-1",
                backup_path=str(backup),
                debug=True,
            ),
        )
        assert rc == restore_cmd.EXIT_IO
        captured = capsys.readouterr()
        # Debug mode includes path detail.
        assert "DBG" in captured.err


# ---------------------------------------------------------------------------
# Bundle-id mismatch
# ---------------------------------------------------------------------------


class TestRestoreBundleIdMismatch:
    def test_bundle_id_must_match_active_profile(self, profile_loader_env, tmp_path: Path):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
            bundle_id="bundle-A",
        )
        profile_loader_env(profile)

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="bundle-WRONG", backup_path=str(backup)),
        )
        assert rc == restore_cmd.EXIT_VALIDATION


# ---------------------------------------------------------------------------
# Env-var fallback
# ---------------------------------------------------------------------------


class TestRestoreEnvFallback:
    def test_env_var_used_when_flag_omitted(self, profile_loader_env, tmp_path: Path, monkeypatch):
        active = tmp_path / "constitution.yaml"
        backup = tmp_path / "constitution.backup.yaml"
        active.write_text(CONSTITUTION_YAML, encoding="utf-8")
        backup.write_text(CONSTITUTION_YAML, encoding="utf-8")

        c_hash = _compute_constitution_hash(CONSTITUTION_YAML, tmp_path)
        profile = _mk_profile(
            constitution_path=active,
            backup_path=backup,
            constitutional_hash=c_hash,
        )
        profile_loader_env(profile)

        monkeypatch.setenv("LEGALGUARD_BACKUP_PATH", str(backup))

        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=None, dry_run=True),
        )
        assert rc == restore_cmd.EXIT_OK

    def test_no_backup_anywhere_exits_usage(self, profile_loader_env, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("LEGALGUARD_BACKUP_PATH", raising=False)
        rc = restore_cmd.cmd_restore(
            _make_args(bundle_id="test-bundle-1", backup_path=None),
        )
        assert rc == restore_cmd.EXIT_USAGE
