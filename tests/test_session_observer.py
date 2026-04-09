import argparse
import json
from pathlib import Path

import pytest

from acgs_lite.commands import observe_session
from acgs_lite.observability.session_observer import ObservationLogger, extract_file_paths


class TestObservationLogger:
    def test_record_writes_jsonl_line(self, tmp_path: Path) -> None:
        path = tmp_path / "observations.jsonl"
        logger = ObservationLogger(path)

        obs = logger.record(
            tool_type="bash",
            duration_ms=42.345,
            success=True,
            file_paths=["src/main.py", "tests/test_main.py"],
            session_id="sess-123",
            metadata={"command": "pytest -q"},
        )

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["tool_type"] == "bash"
        assert record["success"] is True
        assert record["duration_ms"] == 42.34
        assert record["file_paths"] == ["src/main.py", "tests/test_main.py"]
        assert record["session_id"] == "sess-123"
        assert record["timestamp"].endswith("+00:00")

        assert logger.count() == 1
        assert logger.tail(1)[0].observation_id == obs.observation_id

    def test_extract_file_paths_from_nested_payloads(self) -> None:
        paths = extract_file_paths(
            {
                "path": "src/main.py",
                "files": ["tests/test_main.py", "tests/test_main.py"],
                "nested": {
                    "output_path": "dist/report.json",
                    "metadata": {"note": "ignore-me"},
                },
            },
            {
                "artifacts": {
                    "file_paths": ["logs/run.log", "dist/report.json"],
                },
                "message": "no path here",
            },
        )

        assert paths == [
            "src/main.py",
            "tests/test_main.py",
            "dist/report.json",
            "logs/run.log",
        ]

    def test_observe_session_cli_status_and_record(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "observations.jsonl"

        observe_session.run(
            argparse.Namespace(
                action="record",
                tool="bash",
                duration_ms=12.345,
                success=True,
                failure=False,
                error_type=None,
                error_message=None,
                files=["src/main.py"],
                session_id="sess-1",
                meta=["command=pytest -q"],
                path=str(path),
                n=20,
                json_out=False,
            )
        )

        recorded = capsys.readouterr()
        assert "recorded" in recorded.out
        assert "tool=bash" in recorded.out

        observe_session.run(
            argparse.Namespace(
                action="status",
                tool=None,
                duration_ms=None,
                success=True,
                failure=False,
                error_type=None,
                error_message=None,
                files=None,
                session_id=None,
                meta=None,
                path=str(path),
                n=20,
                json_out=False,
            )
        )

        status = capsys.readouterr()
        assert "observations: 1" in status.out
        assert str(path) in status.out

    def test_observe_session_cli_tail_and_export_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "observations.jsonl"
        logger = ObservationLogger(path)
        logger.record(
            tool_type="edit",
            duration_ms=8.0,
            success=False,
            error_type="ValueError",
            error_message="bad input",
            file_paths=["src/app.py"],
            session_id="sess-2",
            metadata={"mode": "test"},
        )

        observe_session.run(
            argparse.Namespace(
                action="tail",
                tool=None,
                duration_ms=None,
                success=True,
                failure=False,
                error_type=None,
                error_message=None,
                files=None,
                session_id=None,
                meta=None,
                path=str(path),
                n=1,
                json_out=True,
            )
        )

        tail = capsys.readouterr()
        tail_record = json.loads(tail.out.strip())
        assert tail_record["tool_type"] == "edit"
        assert tail_record["error_type"] == "ValueError"

        observe_session.run(
            argparse.Namespace(
                action="export",
                tool=None,
                duration_ms=None,
                success=True,
                failure=False,
                error_type=None,
                error_message=None,
                files=None,
                session_id=None,
                meta=None,
                path=str(path),
                n=1,
                json_out=False,
            )
        )

        exported = capsys.readouterr()
        payload = json.loads(exported.out)
        assert payload["count"] == 1
        assert payload["observations"][0]["tool_type"] == "edit"
        assert payload["observations"][0]["metadata"] == {"mode": "test"}
