"""
Circuit Breaker
================

Circuit breaker pattern for infrastructure adapters (DB, vector store,
graph store, LLM). Prevents cascading failures by short-circuiting
calls to failing services.

States:
    CLOSED → normal operation, calls pass through
    OPEN → calls are blocked (raises CircuitBreakerOpenError)
    HALF_OPEN → single test call allowed to check recovery
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, TypeVar

from app.core.exceptions import CircuitBreakerOpenError
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Circuit breaker for wrapping infrastructure calls.

    Usage:
        cb = CircuitBreaker(service_name="opensearch", failure_threshold=5)
        result = cb.call(opensearch_client.search, query=q)
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        """
        Args:
            service_name: Name of the service being protected
            failure_threshold: Consecutive failures before opening the circuit
            recovery_timeout_seconds: Time before transitioning from OPEN → HALF_OPEN
            half_open_max_calls: Max test calls in HALF_OPEN state
        """
        self._service_name = service_name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state, considering recovery timeout."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(
                    "circuit_breaker_half_open",
                    service=self._service_name,
                )
        return self._state

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.

        Raises:
            CircuitBreakerOpenError if the circuit is OPEN
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                service_name=self._service_name,
                failure_count=self._failure_count,
            )

        if (
            current_state == CircuitState.HALF_OPEN
            and self._half_open_calls >= self._half_open_max_calls
        ):
            raise CircuitBreakerOpenError(
                service_name=self._service_name,
                failure_count=self._failure_count,
            )

        try:
            if current_state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

            result = func(*args, **kwargs)

            # Success — reset
            self._on_success()
            return result

        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self) -> None:
        """Handle a successful call — close the circuit."""
        if self._state != CircuitState.CLOSED:
            logger.info(
                "circuit_breaker_closed",
                service=self._service_name,
                previous_failures=self._failure_count,
            )
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

    def _on_failure(self) -> None:
        """Handle a failed call — potentially open the circuit."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                service=self._service_name,
                failure_count=self._failure_count,
                recovery_timeout=self._recovery_timeout,
            )
        else:
            logger.warning(
                "circuit_breaker_failure",
                service=self._service_name,
                failure_count=self._failure_count,
                threshold=self._failure_threshold,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker (admin operation)."""
        logger.info("circuit_breaker_reset", service=self._service_name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
