"""Circuit breaker for the protected AWS model adapter (Prompt 14 Part F, item 5).

F.5 requires the Catalyst -> AWS path to use "timeouts, circuit breaking, retry
with jitter, idempotency". Retry-with-jitter, timeouts and idempotency already
live in ``adapter.py``; this module adds the missing **circuit breaker** so that
when the downstream AWS API Gateway / Lambda / SageMaker plane is failing, the
AppSail service stops hammering it and fails fast (fail-closed) until a cooldown
elapses.

Design (classic three-state breaker, thread-safe):

    CLOSED     — normal operation. Consecutive failures are counted; once they
                 reach ``failure_threshold`` the breaker trips to OPEN.
    OPEN       — fail fast: ``before_call`` raises ``CircuitOpenError`` without
                 touching the network, until ``reset_timeout_s`` has elapsed,
                 then it moves to HALF_OPEN to probe recovery.
    HALF_OPEN  — allow a bounded number of trial calls. A success closes the
                 breaker; any failure re-opens it and restarts the cooldown.

One breaker call corresponds to one *logical* adapter request (the caller's own
retry-with-jitter loop is a single logical call): a request that exhausts its
retries records exactly one failure, so the breaker measures backend health, not
individual socket attempts.

The breaker holds no request data — only counters and timestamps — so it can
never leak an envelope, a secret or PII.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised by ``before_call`` when the breaker is OPEN (fail fast)."""


@dataclass(frozen=True)
class CircuitSnapshot:
    """Point-in-time view for redacted observability (no request data)."""
    state: CircuitState
    consecutive_failures: int
    opened_for_s: float
    cooldown_remaining_s: float


class CircuitBreaker:
    """Thread-safe circuit breaker.

    Parameters
    ----------
    failure_threshold:
        Consecutive failures in CLOSED that trip the breaker to OPEN.
    reset_timeout_s:
        Cooldown after opening before a single HALF_OPEN trial is allowed.
    half_open_max_calls:
        Concurrent trial calls permitted while HALF_OPEN (default 1).
    success_threshold:
        Successful trials required to move HALF_OPEN -> CLOSED (default 1).
    name:
        Label used only in the (redacted) error message / snapshot.
    """

    def __init__(self, *, failure_threshold: int = 5, reset_timeout_s: float = 30.0,
                 half_open_max_calls: int = 1, success_threshold: int = 1,
                 name: str = "aws-adapter",
                 time_fn: Callable[[], float] = time.monotonic) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if reset_timeout_s <= 0:
            raise ValueError("reset_timeout_s must be > 0")
        self._failure_threshold = failure_threshold
        self._reset_timeout_s = reset_timeout_s
        self._half_open_max_calls = max(1, half_open_max_calls)
        self._success_threshold = max(1, success_threshold)
        self._name = name
        self._now = time_fn

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None
        self._half_open_inflight = 0
        self._half_open_successes = 0

    # -- introspection -------------------------------------------------------
    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            now = self._now()
            opened_for = (now - self._opened_at) if self._opened_at is not None else 0.0
            remaining = 0.0
            if self._state is CircuitState.OPEN and self._opened_at is not None:
                remaining = max(0.0, self._reset_timeout_s - (now - self._opened_at))
            return CircuitSnapshot(
                state=self._state,
                consecutive_failures=self._consecutive_failures,
                opened_for_s=round(opened_for, 3),
                cooldown_remaining_s=round(remaining, 3))

    # -- gate ----------------------------------------------------------------
    def before_call(self) -> None:
        """Admission control. Raises ``CircuitOpenError`` when the breaker is
        OPEN and the cooldown has not elapsed, or when HALF_OPEN is already at
        its trial-call ceiling. Otherwise returns and (when appropriate) moves
        OPEN -> HALF_OPEN and reserves a trial slot."""
        with self._lock:
            now = self._now()
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if now - self._opened_at < self._reset_timeout_s:
                    remaining = self._reset_timeout_s - (now - self._opened_at)
                    raise CircuitOpenError(
                        f"circuit '{self._name}' open; retry in {remaining:.1f}s")
                # cooldown elapsed -> probe with a single trial
                self._state = CircuitState.HALF_OPEN
                self._half_open_inflight = 0
                self._half_open_successes = 0

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_inflight >= self._half_open_max_calls:
                    raise CircuitOpenError(
                        f"circuit '{self._name}' half-open; trial in progress")
                self._half_open_inflight += 1

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                self._half_open_inflight = max(0, self._half_open_inflight - 1)
                if self._half_open_successes >= self._success_threshold:
                    self._close_locked()
            else:
                self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                # A failed probe re-opens immediately and restarts the cooldown.
                self._open_locked()
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._open_locked()

    # -- convenience ---------------------------------------------------------
    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Run ``fn`` through the breaker. Re-raises the callee's exception
        after recording a failure; raises ``CircuitOpenError`` if not admitted."""
        self.before_call()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    # -- internal (lock held) ------------------------------------------------
    def _open_locked(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._now()
        self._half_open_inflight = 0
        self._half_open_successes = 0

    def _close_locked(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_inflight = 0
        self._half_open_successes = 0
