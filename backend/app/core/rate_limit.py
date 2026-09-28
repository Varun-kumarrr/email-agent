"""Small in-memory sliding-window rate limiter.

Protects login/registration against brute force and the AI endpoint against
cost abuse. State is per process: with several workers or servers, use a shared
store such as Redis instead (see README, production recommendations).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.exceptions import RateLimitError


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: float, message: str):
        self.max_calls = max_calls
        self.window = window_seconds
        self.message = message
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.max_calls:
                retry_after = int(self.window - (now - hits[0])) + 1
                raise RateLimitError(self.message, headers={"Retry-After": str(retry_after)})
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, configure uvicorn --proxy-headers so this is the real client IP.
    return request.client.host if request.client else "unknown"


login_limiter = RateLimiter(10, 300, "Too many login attempts. Please wait a few minutes and try again.")
register_limiter = RateLimiter(20, 3600, "Too many registrations from this address. Try again later.")
generation_limiter = RateLimiter(30, 60, "Too many AI generation requests. Please wait a minute.")

ALL_LIMITERS = (login_limiter, register_limiter, generation_limiter)
