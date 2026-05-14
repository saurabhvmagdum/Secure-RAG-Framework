"""
Safe Retry Utility
==================

Retry wrapper with exponential backoff for idempotent operations only.
Non-idempotent operations must NOT use retry — use circuit breaker instead.

Uses tenacity for retry logic. No external network calls.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def safe_retry(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    min_wait_seconds: float = 0.5,
    max_wait_seconds: float = 10.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    operation_name: str = "unknown",
    **kwargs: Any,
) -> T:
    """
    Execute a function with exponential backoff retry.

    ONLY use for idempotent operations (read queries, health checks, etc.).
    NEVER use for write operations unless they are truly idempotent.

    Args:
        func: The callable to retry
        *args: Positional arguments for func
        max_attempts: Maximum number of attempts
        min_wait_seconds: Minimum wait between retries
        max_wait_seconds: Maximum wait between retries
        retry_on: Tuple of exception types to retry on
        operation_name: Name for logging
        **kwargs: Keyword arguments for func

    Returns:
        The result of func(*args, **kwargs)

    Raises:
        The last exception if all retries are exhausted
    """

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=min_wait_seconds,
            max=max_wait_seconds,
        ),
        retry=retry_if_exception_type(retry_on),
        reraise=True,
    )
    def _execute() -> T:
        return func(*args, **kwargs)

    try:
        logger.debug(
            "retry_attempt_start",
            operation=operation_name,
            max_attempts=max_attempts,
        )
        result = _execute()
        return result

    except RetryError as exc:
        logger.error(
            "retry_exhausted",
            operation=operation_name,
            max_attempts=max_attempts,
            last_error=str(exc.last_attempt.exception()) if exc.last_attempt else "unknown",
        )
        # Re-raise the original exception, not the RetryError wrapper
        if exc.last_attempt and exc.last_attempt.exception():
            raise exc.last_attempt.exception() from exc
        raise
