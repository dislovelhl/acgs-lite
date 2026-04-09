"""Tests for the fail_closed decorator."""

import asyncio

import pytest

from acgs_lite.fail_closed import fail_closed


class TestFailClosedSync:
    def test_success_passes_through(self):
        @fail_closed(deny_value=False)
        def check() -> bool:
            return True

        assert check() is True

    def test_exception_returns_deny_value(self):
        @fail_closed(deny_value=False)
        def check() -> bool:
            raise ValueError("boom")

        assert check() is False

    def test_custom_deny_value(self):
        @fail_closed(deny_value={"allowed": False, "reason": "error"})
        def check() -> dict:
            raise RuntimeError("fail")

        result = check()
        assert result == {"allowed": False, "reason": "error"}

    def test_keyboard_interrupt_not_swallowed(self):
        @fail_closed(deny_value=False)
        def check() -> bool:
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            check()

    def test_system_exit_not_swallowed(self):
        @fail_closed(deny_value=False)
        def check() -> bool:
            raise SystemExit(1)

        with pytest.raises(SystemExit):
            check()

    def test_none_deny_value(self):
        @fail_closed(deny_value=None)
        def check() -> str | None:
            raise ValueError("fail")

        assert check() is None

    def test_preserves_function_name(self):
        @fail_closed(deny_value=False)
        def my_function() -> bool:
            return True

        assert my_function.__name__ == "my_function"

    def test_args_passed_through(self):
        @fail_closed(deny_value=-1)
        def add(a: int, b: int) -> int:
            return a + b

        assert add(3, 4) == 7

    def test_deny_value_is_list(self):
        @fail_closed(deny_value=[])
        def get_items() -> list:
            raise RuntimeError("db error")

        assert get_items() == []


class TestFailClosedAsync:
    def test_async_success(self):
        @fail_closed(deny_value=False)
        async def check() -> bool:
            return True

        assert asyncio.run(check()) is True

    def test_async_exception_returns_deny(self):
        @fail_closed(deny_value=False)
        async def check() -> bool:
            raise ValueError("async boom")

        assert asyncio.run(check()) is False

    def test_async_keyboard_interrupt_propagates(self):
        @fail_closed(deny_value=False)
        async def check() -> bool:
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            asyncio.run(check())

    def test_async_preserves_name(self):
        @fail_closed(deny_value=False)
        async def async_validator() -> bool:
            return True

        assert async_validator.__name__ == "async_validator"


class TestFailClosedCustomReraise:
    def test_custom_reraise_propagates(self):
        @fail_closed(deny_value=False, reraise=(TypeError,))
        def check() -> bool:
            raise TypeError("custom reraise")

        with pytest.raises(TypeError):
            check()

    def test_non_reraise_still_caught(self):
        @fail_closed(deny_value=False, reraise=(TypeError,))
        def check() -> bool:
            raise ValueError("should be caught")

        assert check() is False
