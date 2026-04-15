from __future__ import annotations

import pytest


def test_agno_integration_imports_and_helpers() -> None:
    from acgs_lite.integrations import agno as agno_integration

    assert isinstance(agno_integration.AGNO_AVAILABLE, bool)

    class StubRunInput:
        def __init__(self, content: str) -> None:
            self._content = content

        def input_content_string(self) -> str:
            return self._content

    class StubRunOutput:
        def __init__(self, content: object) -> None:
            self.content = content

    assert agno_integration._extract_run_input_text(StubRunInput("hello")) == "hello"
    assert agno_integration._extract_run_output_text(StubRunOutput("ok")) == "ok"
    assert agno_integration._extract_run_output_text(StubRunOutput({"k": "v"})) == "{'k': 'v'}"


def test_agno_governor_missing_dependency_error_message() -> None:
    from acgs_lite.integrations.agno import AGNO_AVAILABLE, AgnoACGSGovernor

    if AGNO_AVAILABLE:
        pytest.skip("agno is installed; skip missing-dependency path")

    with pytest.raises(ImportError) as excinfo:
        AgnoACGSGovernor()

    assert "pip install acgs-lite[agno]" in str(excinfo.value)

