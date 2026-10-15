"""Fixed-window rate limiter.

Uses an in-process store, which is correct for a single backend instance.
For multi-instance deployments configure a shared store (see docs/SECURITY.md).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import RateLimitError


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            if len(self._buckets) > 50_000:  # bound memory
                cutoff = now - window_seconds
                self._buckets = {k: v for k, v in self._buckets.items() if v[0] >= cutoff}
            retry_after = int(window_seconds - (now - start)) + 1
            return count <= limit, retry_after

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = FixedWindowLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit_getter: Callable[[], int], window_seconds: int = 60) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        if not get_settings().RATE_LIMIT_ENABLED:
            return
        user_key = getattr(request.state, "user_id", None) or client_ip(request)
        allowed, retry_after = limiter.hit(f"{scope}:{user_key}", limit_getter(), window_seconds)
        if not allowed:
            raise RateLimitError("Too many requests. Please wait and try again.", details={"retry_after_seconds": retry_after})

    return dependency


auth_rate_limit = rate_limit("auth", lambda: get_settings().RATE_LIMIT_AUTH_PER_MINUTE)
ai_rate_limit = rate_limit("ai", lambda: get_settings().RATE_LIMIT_AI_PER_MINUTE)
