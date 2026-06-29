"""Token bucket rate limiter for Toss API groups."""

import time
import threading


class RateLimiter:
    GROUP_LIMITS = {
        "AUTH": 4.0,
        "MARKET_DATA": 8.0,
        "ASSET": 4.0,
        "ORDER": 4.0,
        "ORDER_INFO": 4.0,
        "ORDER_HISTORY": 4.0,
        "ACCOUNT": 0.8,
        "MARKET_INFO": 2.4,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}

    def acquire(self, group: str) -> None:
        tps = self.GROUP_LIMITS.get(group, 2.0)
        min_interval = 1.0 / tps if tps > 0 else 0.5
        with self._lock:
            now = time.monotonic()
            last = self._last.get(group, 0.0)
            wait = min_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._last[group] = time.monotonic()
