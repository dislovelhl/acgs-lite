from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from enhanced_agent_bus.shared.fail_closed import fail_closed


def test_fail_closed_sync_literal_return() -> None:
    @fail_closed("denied")
    def will_fail() -> str:
        raise RuntimeError("boom")

    assert will_fail() == "denied"


@pytest.mark.asyncio
async def test_fail_closed_async_callable_return_uses_error() -> None:
    class Guard:
        @fail_closed(lambda self, value, *, error: {"allow": False, "reason": str(error)})
        async def evaluate(self, value: str) -> dict[str, object]:
            raise RuntimeError(f"bad:{value}")

    result = await Guard().evaluate("input")
    assert result == {"allow": False, "reason": "bad:input"}


@pytest.mark.asyncio
async def test_fail_closed_async_callable_can_await_cleanup() -> None:
    tracker = MagicMock()

    class Guard:
        @fail_closed(lambda self, *, error: self._deny(error), exceptions=(RuntimeError,))
        async def evaluate(self) -> tuple[bool, str]:
            raise RuntimeError("nope")

        async def _deny(self, error: BaseException) -> tuple[bool, str]:
            tracker(str(error))
            return False, str(error)

    result = await Guard().evaluate()
    assert result == (False, "nope")
    tracker.assert_called_once_with("nope")
