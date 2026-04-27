"""Error recovery utilities: retry, circuit breaker, graceful degradation.

Provides decorators and utilities for making LLM tool calls resilient
against transient API failures (DashScope 429/500).
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ── Retry decorator for LLM calls ───────────────────────────────

def with_llm_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
) -> Callable[[F], F]:
    """Decorator that adds exponential backoff retry to async LLM calls.

    Retries on:
    - httpx.HTTPStatusError (429, 500, 502, 503)
    - openai.APIError and subclasses
    - ConnectionError, TimeoutError

    Args:
        max_attempts: Maximum number of attempts (including first).
        min_wait: Minimum wait between retries (seconds).
        max_wait: Maximum wait between retries (seconds).
    """
    def decorator(func: F) -> F:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((
                ConnectionError,
                TimeoutError,
            )),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Check for retryable HTTP status codes
                status = getattr(e, "status_code", None) or getattr(e, "status", None)
                if status in (429, 500, 502, 503):
                    logger.warning("Retryable API error (status=%s): %s", status, e)
                    raise ConnectionError(f"Retryable API error: {e}") from e
                raise

        return wrapper  # type: ignore
    return decorator


# ── Circuit breaker ──────────────────────────────────────────────

class CircuitBreaker:
    """Simple circuit breaker for agent execution.

    Tracks turn count and estimated cost, stopping execution
    when limits are exceeded.
    """

    def __init__(
        self,
        max_turns: int = 50,
        max_cost_usd: float = 5.0,
    ) -> None:
        self.max_turns = max_turns
        self.max_cost_usd = max_cost_usd
        self.turn_count = 0
        self.estimated_cost = 0.0

    def check(self) -> None:
        """Raise if circuit breaker should trip."""
        if self.turn_count >= self.max_turns:
            raise CircuitBreakerTripped(
                f"Turn limit exceeded: {self.turn_count}/{self.max_turns}"
            )
        if self.estimated_cost >= self.max_cost_usd:
            raise CircuitBreakerTripped(
                f"Cost limit exceeded: ${self.estimated_cost:.2f}/${self.max_cost_usd:.2f}"
            )

    def record_turn(self, cost_increment: float = 0.0) -> None:
        """Record a completed turn."""
        self.turn_count += 1
        self.estimated_cost += cost_increment


class CircuitBreakerTripped(Exception):
    """Raised when the circuit breaker trips."""
    pass
