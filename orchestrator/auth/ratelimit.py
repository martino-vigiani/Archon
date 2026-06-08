"""In-process rate limiting / brute-force lockout for auth endpoints.

A tiny, dependency-free sliding-window failure counter with temporary lockout,
suitable for a single-process self-hosted API. After ``max_attempts`` failures
within ``window_seconds`` a key (e.g. ``"<ip>:<username>"``) is locked out for
``lockout_seconds``. A successful login clears the key.

For multi-process / HA deployments, front this with a shared store (e.g. Redis)
instead; this implementation is per-process.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class LoginRateLimiter:
    """Sliding-window failed-login limiter with temporary lockout.

    Attributes:
        max_attempts: Failures allowed within the window before lockout.
        window_seconds: Rolling window over which failures are counted.
        lockout_seconds: How long a key stays locked once tripped.
    """

    max_attempts: int = 5
    window_seconds: float = 300.0
    lockout_seconds: float = 300.0
    _fails: dict[str, list[float]] = field(default_factory=dict, repr=False)
    _locked_until: dict[str, float] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def retry_after(self, key: str) -> float:
        """Return remaining lockout seconds for ``key`` (0.0 if not locked)."""
        with self._lock:
            remaining = self._locked_until.get(key, 0.0) - self._now()
            if remaining <= 0:
                self._locked_until.pop(key, None)
                return 0.0
            return remaining

    def is_locked(self, key: str) -> bool:
        """Return True if ``key`` is currently locked out."""
        return self.retry_after(key) > 0

    def record_failure(self, key: str) -> None:
        """Record a failed attempt; trip the lockout once the window is exceeded."""
        with self._lock:
            now = self._now()
            window = [t for t in self._fails.get(key, []) if now - t < self.window_seconds]
            window.append(now)
            if len(window) >= self.max_attempts:
                self._locked_until[key] = now + self.lockout_seconds
                self._fails.pop(key, None)
            else:
                self._fails[key] = window

    def record_success(self, key: str) -> None:
        """Clear any failure/lockout state for ``key`` after a successful login."""
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)
