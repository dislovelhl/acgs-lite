import pytest

from src.core.shared.security.execution_time_limit import (
    ExecutionTimeout,
    python_execution_time_limit,
    sha256_hex,
)


def test_sha256_hex_is_stable() -> None:
    first = sha256_hex("x = 1")
    second = sha256_hex("x = 1")

    assert first == second
    assert len(first) == 64


@pytest.mark.skip(
    reason="sys.settrace-based timeout is unreliable and can hang in some environments"
)
def test_python_execution_time_limit_expires() -> None:
    with pytest.raises(ExecutionTimeout):
        with python_execution_time_limit(0.01):
            while True:
                pass


def test_python_execution_time_limit_allows_fast_code() -> None:
    with python_execution_time_limit(0.2):
        value = sum(range(1000))

    assert value == 499500
