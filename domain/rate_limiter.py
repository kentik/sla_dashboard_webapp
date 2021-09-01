import threading
import time
from collections import defaultdict
from typing import Dict


class RateLimiter:
    def __init__(self, interval_seconds: int) -> None:
        self._lock = threading.Lock()
        self._interval_seconds = interval_seconds
        self._last_update: Dict[str, int] = defaultdict(int)

    def check_and_update(self, key: str = "") -> bool:
        now = int(time.monotonic())
        with self._lock:
            if now - self._last_update[key] > self._interval_seconds:
                self._last_update[key] = now
                return True
            return False

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds
