from __future__ import annotations

from acgs_lite.observability.analyze_observations import analyze
from acgs_lite.observability.session_observer import ToolObservation


def _make_observation(
    tool_type: str,
    *,
    success: bool = True,
    error_type: str | None = None,
) -> ToolObservation:
    return ToolObservation(
        tool_type=tool_type,
        timestamp="2026-04-09T00:00:00+00:00",
        duration_ms=1.0,
        success=success,
        error_type=error_type,
        session_id="session-1",
        metadata={},
    )


def test_analyze_empty_observations_returns_zeroed_summary() -> None:
    result = analyze([])

    assert result["total"] == 0
    assert result["success_rate"] == 0.0
    assert result["error_types"] == {}
    assert set(result["categories"]) == {
        "exploration_tools",
        "production_tools",
        "preparation_tools",
        "coordination_tools",
    }
    for category in result["categories"].values():
        assert category["total"] == 0
        assert category["success_rate"] == 0.0
        assert category["error_types"] == {}
        assert all(count == 0 for count in category["tool_frequencies"].values())


def test_analyze_returns_structured_category_summary() -> None:
    observations = [
        _make_observation("grep"),
        _make_observation("bash", success=False, error_type="TimeoutError"),
        _make_observation("edit"),
        _make_observation("write", success=False, error_type="ValidationError"),
        _make_observation("read"),
        _make_observation("question", success=False, error_type="TimeoutError"),
        _make_observation("custom_tool", success=False, error_type="ValueError"),
    ]

    result = analyze(observations)

    assert result["total"] == 7
    assert result["success_rate"] == 3 / 7
    assert result["error_types"] == {
        "TimeoutError": 2,
        "ValidationError": 1,
        "ValueError": 1,
    }

    exploration = result["categories"]["exploration_tools"]
    assert exploration["total"] == 2
    assert exploration["tool_frequencies"]["grep"] == 1
    assert exploration["tool_frequencies"]["bash"] == 1
    assert exploration["success_rate"] == 0.5
    assert exploration["error_types"] == {"TimeoutError": 1}

    production = result["categories"]["production_tools"]
    assert production["total"] == 2
    assert production["tool_frequencies"]["edit"] == 1
    assert production["tool_frequencies"]["write"] == 1
    assert production["success_rate"] == 0.5
    assert production["error_types"] == {"ValidationError": 1}

    preparation = result["categories"]["preparation_tools"]
    assert preparation["total"] == 1
    assert preparation["tool_frequencies"]["read"] == 1
    assert preparation["tool_frequencies"]["skill"] == 0
    assert preparation["success_rate"] == 1.0
    assert preparation["error_types"] == {}

    coordination = result["categories"]["coordination_tools"]
    assert coordination["total"] == 1
    assert coordination["tool_frequencies"]["question"] == 1
    assert coordination["success_rate"] == 0.0
    assert coordination["error_types"] == {"TimeoutError": 1}
