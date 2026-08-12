"""Resilient — reference solution."""
from __future__ import annotations

import functools
import threading
import time
from contextlib import ContextDecorator

# Injectable seams. Tests replace these module globals; every call site below
# uses the bare name so the substitution actually takes effect.
now = time.monotonic
sleep = time.sleep


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ResilienceError(Exception):
    """Base for everything this toolkit raises."""


class CircuitOpen(ResilienceError):
    def __init__(self, message, retry_after=0.0):
        super().__init__(message, retry_after)
        self.retry_after = retry_after

    def __str__(self):
        return self.args[0]


class BulkheadFull(ResilienceError):
    pass


# ---------------------------------------------------------------------------
# Backoff strategies
# ---------------------------------------------------------------------------
def constant(delay):
    return lambda attempt: float(delay)


def linear(base):
    return lambda attempt: float(base) * attempt


def exponential(base, factor=2.0, cap=None):
    def strategy(attempt):
        value = float(base) * (factor ** (attempt - 1))
        return min(value, cap) if cap is not None else value
    return strategy


def jittered(strategy, rng):
    return lambda attempt: rng.uniform(0, strategy(attempt))


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
def retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None,
          give_up_on=()):
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except give_up_on:
                    raise
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    delay = backoff(attempt) if backoff else 0.0
                    if on_retry is not None:
                        on_retry(exc, attempt, delay)
                    if delay:
                        sleep(delay)
        wrapper.attempts = attempts
        return wrapper
    return decorate


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class CircuitBreaker(ContextDecorator):
    def __init__(self, failure_threshold=5, reset_after=30.0,
                 half_open_successes=1, exceptions=(Exception,)):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        self.failure_threshold = failure_threshold
        self.reset_after = reset_after
        self.half_open_successes = half_open_successes
        self.exceptions = exceptions
        self._lock = threading.RLock()
        self.reset()

    # -- state -------------------------------------------------------------
    def reset(self):
        with self._lock:
            self._failures = 0
            self._successes = 0
            self._opened_at = None

    @property
    def state(self):
        with self._lock:
            if self._opened_at is None:
                return "closed"
            if now() - self._opened_at >= self.reset_after:
                return "half_open"
            return "open"

    @property
    def retry_after(self):
        with self._lock:
            if self._opened_at is None:
                return 0.0
            return max(0.0, self.reset_after - (now() - self._opened_at))

    # -- transitions -------------------------------------------------------
    def _before(self):
        if self.state == "open":
            raise CircuitOpen(
                f"circuit is open; retry in {self.retry_after:.2f}s",
                self.retry_after,
            )

    def _record_success(self):
        with self._lock:
            if self.state == "half_open":
                self._successes += 1
                if self._successes >= self.half_open_successes:
                    self._failures = self._successes = 0
                    self._opened_at = None
            else:
                self._failures = 0

    def _record_failure(self):
        with self._lock:
            if self.state == "half_open":
                self._successes = 0
                self._opened_at = now()          # re-open, restart the timer
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = now()

    # -- usage -------------------------------------------------------------
    def call(self, fn, *args, **kwargs):
        self._before()
        try:
            result = fn(*args, **kwargs)
        except self.exceptions:
            self._record_failure()
            raise
        except Exception:
            raise                                # not our concern; not a failure
        self._record_success()
        return result

    def __enter__(self):
        self._before()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._record_success()
        elif issubclass(exc_type, self.exceptions):
            self._record_failure()
        return False


def circuit_breaker(**kwargs):
    """Decorator factory returning a fresh breaker per decorated function."""
    breaker = CircuitBreaker(**kwargs)

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs_):
            return breaker.call(fn, *args, **kwargs_)
        wrapper.breaker = breaker
        return wrapper
    return decorate


# ---------------------------------------------------------------------------
# Rate limiter — token bucket
# ---------------------------------------------------------------------------
class RateLimiter(ContextDecorator):
    def __init__(self, rate, capacity=None):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        self._tokens = self.capacity
        self._checked_at = now()
        self._lock = threading.Lock()

    def _refill(self):
        current = now()
        elapsed = current - self._checked_at
        self._checked_at = current
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)

    @property
    def available(self):
        with self._lock:
            self._refill()
            return self._tokens

    def try_acquire(self, tokens=1):
        if tokens > self.capacity:
            raise ValueError(
                f"cannot acquire {tokens} tokens from a bucket of {self.capacity}"
            )
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens=1):
        if tokens > self.capacity:
            raise ValueError(
                f"cannot acquire {tokens} tokens from a bucket of {self.capacity}"
            )
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return self
                shortfall = (tokens - self._tokens) / self.rate
            sleep(shortfall)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc_info):
        return False


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------
class Bulkhead(ContextDecorator):
    def __init__(self, limit, wait=False):
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self.limit = limit
        self.wait = wait
        self.in_flight = 0
        self.max_seen = 0
        self._lock = threading.Lock()
        self._slot = threading.Semaphore(limit)

    def __enter__(self):
        if not self._slot.acquire(blocking=self.wait):
            raise BulkheadFull(f"bulkhead limit of {self.limit} reached")
        with self._lock:
            self.in_flight += 1
            self.max_seen = max(self.max_seen, self.in_flight)
        return self

    def __exit__(self, *exc_info):
        with self._lock:
            self.in_flight -= 1
        self._slot.release()
        return False
