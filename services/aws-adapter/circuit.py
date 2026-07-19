"""Compact circuit breaker for the adapter's DOWNSTREAM calls (Part F, item 5).

Self-contained copy of the breaker in ``services/ml/app/predict/circuit.py`` (the
adapter is a separate deployment and must not import the FastAPI app). It guards
the adapter's calls to SageMaker / AWS Batch: when the model plane is failing,
the adapter stops invoking it and fails fast for a cooldown.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised by ``before_call`` when the breaker is OPEN (fail fast)."""


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, reset_timeout_s: float = 30.0,
                 name: str = "downstream", time_fn: Callable[[], float] = time.monotonic) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._reset_timeout_s = max(0.001, reset_timeout_s)
        self._name = name
        self._now = time_fn
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def before_call(self) -> None:
        with self._lock:
            if self._state is CircuitState.OPEN:
                if self._now() - self._opened_at < self._reset_timeout_s:
                    raise CircuitOpenError(f"circuit '{self._name}' open")
                self._state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._now()
                return
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._now()
