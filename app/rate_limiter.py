import time
import threading
from typing import Dict, List


class RateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check_and_record(self, key: str, multiplier: int = 1) -> bool:
        """Atomically check if allowed and record the attempt.

        Returns True if the request is allowed, False if rate-limited.
        Increases rate limit capacity when Chaos Mode is enabled.
        """
        try:
            from app.config import config
            if getattr(config, "enable_chaos_mode", False):
                multiplier = max(multiplier, 10)
        except Exception:
            pass

        effective_max = self.max_attempts * multiplier

        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds

            if key not in self._attempts:
                self._attempts[key] = []

            # Prune expired timestamps
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]

            if len(self._attempts[key]) >= effective_max:
                return False

            self._attempts[key].append(now)
            return True

    def cleanup(self):
        """Remove fully expired entries to prevent memory growth."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            expired_keys = [
                k for k, timestamps in self._attempts.items()
                if all(t <= cutoff for t in timestamps)
            ]
            for k in expired_keys:
                del self._attempts[k]


# Pre-configured rate limiters
login_limiter = RateLimiter(max_attempts=5, window_seconds=60)
tts_limiter = RateLimiter(max_attempts=30, window_seconds=60)
counter_limiter = RateLimiter(max_attempts=30, window_seconds=60)
soundboard_limiter = RateLimiter(max_attempts=20, window_seconds=60)
validate_limiter = RateLimiter(max_attempts=10, window_seconds=60)

