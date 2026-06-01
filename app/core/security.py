"""Security primitives for the service boundary.

- verify_api_key: constant-time compare so a wrong key can't be timing-probed.
- RateLimiter: in-memory token bucket, per client key. No external store — fine for
  a single instance behind one website; swap for Redis if scaled horizontally.
"""
from __future__ import annotations

import hmac
import time
from collections import defaultdict
from collections.abc import Callable


def verify_api_key(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


class RateLimiter:
    """Token bucket: `per_min` capacity, refilled continuously at per_min/60 tokens/sec."""

    def __init__(self, per_min: int, clock: Callable[[], float] = time.monotonic):
        self._capacity = float(per_min)
        self._refill_per_sec = per_min / 60.0
        self._clock = clock
        self._tokens: dict[str, float] = defaultdict(lambda: self._capacity)
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        last = self._last.get(key, now)
        self._tokens[key] = min(
            self._capacity, self._tokens[key] + (now - last) * self._refill_per_sec
        )
        self._last[key] = now
        if self._tokens[key] >= 1.0:
            self._tokens[key] -= 1.0
            return True
        return False
