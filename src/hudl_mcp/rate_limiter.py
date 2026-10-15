"""Async Token Bucket Rate Limiter and Retry Handler for Hudl MCP.

Provides defense against aggressive LLM tool loops that could trigger
Hudl rate limits or WAF security blocks. Enforces a maximum request rate
(default: 2 requests/second) and jittered exponential backoff on HTTP 429/5xx.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, Optional, TypeVar
import httpx

T = TypeVar("T")


class AsyncTokenBucket:
    """Thread-safe and asyncio-safe token bucket rate limiter.
    
    Attributes:
        rate: Maximum number of requests allowed per second.
        capacity: Maximum burst capacity of the token bucket.
    """

    def __init__(self, rate: float = 2.0, capacity: float = 2.0) -> None:
        self.rate = max(0.1, float(rate))
        self.capacity = max(1.0, float(capacity))
        self._tokens = self.capacity
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available to perform an HTTP request."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_update
                self._last_update = now

                # Add new tokens generated over elapsed time
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                # Calculate sleep duration needed for at least 1 token
                deficit = 1.0 - self._tokens
                sleep_time = deficit / self.rate
                await asyncio.sleep(sleep_time)


# Global default rate limiter: 2 requests/second
DEFAULT_RATE_LIMITER = AsyncTokenBucket(rate=2.0, capacity=2.0)


async def execute_with_retry(
    func: Callable[[], Awaitable[httpx.Response]],
    rate_limiter: Optional[AsyncTokenBucket] = None,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
) -> httpx.Response:
    """Execute an async HTTP request with rate limiting and exponential backoff retry.
    
    Retries automatically on HTTP 429 (Too Many Requests) or HTTP 5xx server errors.
    
    Args:
        func: Zero-arg async callable that returns an httpx.Response.
        rate_limiter: Rate limiter to use (defaults to global 2 req/sec limiter).
        max_retries: Maximum number of retry attempts.
        initial_backoff: Initial base backoff time in seconds.
        
    Returns:
        The final httpx.Response.
    """
    limiter = rate_limiter or DEFAULT_RATE_LIMITER

    for attempt in range(max_retries + 1):
        await limiter.acquire()

        try:
            response = await func()
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            if attempt == max_retries:
                raise
            jitter = random.uniform(0.1, 0.5)
            backoff = (initial_backoff * (2 ** attempt)) + jitter
            await asyncio.sleep(backoff)
            continue

        # Retry on HTTP 429 (Rate Limited) or 5xx (Server Error)
        if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
            # Check Retry-After header if present
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    sleep_seconds = float(retry_after)
                except ValueError:
                    sleep_seconds = initial_backoff * (2 ** attempt)
            else:
                jitter = random.uniform(0.1, 0.5)
                sleep_seconds = (initial_backoff * (2 ** attempt)) + jitter

            await asyncio.sleep(sleep_seconds)
            continue

        return response

    return response
