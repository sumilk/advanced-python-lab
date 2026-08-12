"""Resilient — a fault-tolerance toolkit.

Read README.md in this directory for the full specification.

    uv run learn.py projects test resilient

IMPORTANT: read the clock through `now()` and sleep through `sleep(...)`,
using these module-level names. The tests replace them.
"""
from __future__ import annotations

import functools
import threading
import time
from contextlib import ContextDecorator

now = time.monotonic
sleep = time.sleep


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ResilienceError(Exception):
    """Base for everything this toolkit raises."""


class CircuitOpen(ResilienceError):
    """The breaker is open; the call was not attempted."""


class BulkheadFull(ResilienceError):
    """No capacity left in the bulkhead."""


# ---------------------------------------------------------------------------
# Backoff strategies: attempt number (1-based) -> seconds
# ---------------------------------------------------------------------------
def constant(delay):
    ...


def linear(base):
    ...


def exponential(base, factor=2.0, cap=None):
    ...


def jittered(strategy, rng):
    ...


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
def retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None,
          give_up_on=()):
    ...


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class CircuitBreaker(ContextDecorator):
    def __init__(self, failure_threshold=5, reset_after=30.0,
                 half_open_successes=1, exceptions=(Exception,)):
        ...

    @property
    def state(self):
        """'closed' | 'open' | 'half_open', computed from the clock."""
        ...

    @property
    def retry_after(self):
        ...

    def call(self, fn, *args, **kwargs):
        ...

    def reset(self):
        ...

    def __enter__(self):
        ...

    def __exit__(self, exc_type, exc, tb):
        ...


def circuit_breaker(**kwargs):
    """Decorator factory: one breaker per decorated function."""
    ...


# ---------------------------------------------------------------------------
# Rate limiter — token bucket
# ---------------------------------------------------------------------------
class RateLimiter(ContextDecorator):
    def __init__(self, rate, capacity=None):
        ...

    @property
    def available(self):
        ...

    def try_acquire(self, tokens=1):
        ...

    def acquire(self, tokens=1):
        ...

    def __enter__(self):
        ...

    def __exit__(self, *exc_info):
        ...


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------
class Bulkhead(ContextDecorator):
    def __init__(self, limit, wait=False):
        ...

    def __enter__(self):
        ...

    def __exit__(self, *exc_info):
        ...
