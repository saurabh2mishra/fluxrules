"""Unit tests for the circuit breaker fault-tolerance primitive.

Covers the full CLOSED -> OPEN -> HALF_OPEN -> CLOSED lifecycle, the failure
threshold, the recovery timeout gate, manual reset, and the exception-scoping
behaviour of ``expected_exception``.
"""

from __future__ import annotations

import pytest

from fluxrules.services.circuit_breaker import CircuitBreaker, CircuitState


def _boom() -> None:
    raise ValueError("boom")


def test_starts_closed_and_passes_results_through() -> None:
    cb = CircuitBreaker("svc")
    assert cb.get_state() == CircuitState.CLOSED.value
    assert cb.call(lambda x: x + 1, 41) == 42
    assert cb.get_state() == CircuitState.CLOSED.value


def test_forwards_args_and_kwargs() -> None:
    cb = CircuitBreaker("svc")
    assert cb.call(lambda a, b, c: (a, b, c), 1, 2, c=3) == (1, 2, 3)


def test_opens_after_reaching_failure_threshold() -> None:
    cb = CircuitBreaker("svc", failure_threshold=3)

    for _ in range(3):
        with pytest.raises(ValueError):
            cb.call(_boom)

    assert cb.get_state() == CircuitState.OPEN.value


def test_open_circuit_rejects_calls_without_invoking_func() -> None:
    cb = CircuitBreaker("svc", failure_threshold=1, recovery_timeout_seconds=3600)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.get_state() == CircuitState.OPEN.value

    calls: list[int] = []

    def _tracked() -> str:
        calls.append(1)
        return "ok"

    with pytest.raises(RuntimeError, match="is OPEN"):
        cb.call(_tracked)
    assert calls == []  # func must not run while OPEN


def test_half_open_success_closes_circuit() -> None:
    # recovery_timeout_seconds=0 => the reset window is immediately elapsed.
    cb = CircuitBreaker("svc", failure_threshold=1, recovery_timeout_seconds=0)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.get_state() == CircuitState.OPEN.value

    # Next call transitions OPEN -> HALF_OPEN, succeeds, then closes.
    assert cb.call(lambda: "recovered") == "recovered"
    assert cb.get_state() == CircuitState.CLOSED.value


def test_half_open_failure_reopens_circuit() -> None:
    cb = CircuitBreaker("svc", failure_threshold=1, recovery_timeout_seconds=0)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.get_state() == CircuitState.OPEN.value

    # Attempt reset -> HALF_OPEN, but the call fails again -> OPEN.
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.get_state() == CircuitState.OPEN.value


def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker("svc", failure_threshold=3)
    for _ in range(2):
        with pytest.raises(ValueError):
            cb.call(_boom)
    # A success wipes the accumulated failures, so 2 more are not enough to open.
    cb.call(lambda: "ok")
    for _ in range(2):
        with pytest.raises(ValueError):
            cb.call(_boom)
    assert cb.get_state() == CircuitState.CLOSED.value


def test_manual_reset_returns_to_closed() -> None:
    cb = CircuitBreaker("svc", failure_threshold=1, recovery_timeout_seconds=3600)
    with pytest.raises(ValueError):
        cb.call(_boom)
    assert cb.get_state() == CircuitState.OPEN.value

    cb.reset()
    assert cb.get_state() == CircuitState.CLOSED.value
    assert cb.call(lambda: "ok") == "ok"


def test_unexpected_exception_is_not_counted_as_failure() -> None:
    # Only ValueError is "expected"; a different exception propagates but must
    # not trip the breaker.
    cb = CircuitBreaker("svc", failure_threshold=1, expected_exception=ValueError)

    def _type_error() -> None:
        raise TypeError("unrelated")

    with pytest.raises(TypeError):
        cb.call(_type_error)
    assert cb.get_state() == CircuitState.CLOSED.value
