"""Resilience helpers for external calls (Splunk, hosted model).

Provides a retry-with-backoff wrapper and a lightweight circuit breaker so a
flapping or down dependency degrades gracefully instead of hammering it.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when the circuit is open and calls are short-circuited."""


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_after_seconds: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: datetime | None = field(default=None, init=False)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if self._now() - self._opened_at >= timedelta(seconds=self.reset_after_seconds):
            # Half-open: allow a trial call.
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._now()


async def with_retry(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.05,
    breaker: CircuitBreaker | None = None,
    dont_retry: tuple[type[Exception], ...] = (),
) -> T:
    """Call ``func`` with exponential backoff; respect a circuit breaker.

    Exceptions in ``dont_retry`` are raised immediately without retrying or
    tripping the breaker (e.g. deterministic validation errors).
    """
    if breaker is not None and breaker.is_open:
        raise CircuitOpenError("Circuit is open; dependency unavailable")
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            result = await func()
            if breaker is not None:
                breaker.record_success()
            return result
        except dont_retry:
            raise
        except Exception as exc:  # noqa: BLE001 - resilience boundary
            last_exc = exc
            if breaker is not None:
                breaker.record_failure()
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc
