"""Grading suite for the Resilient capstone.

    uv run learn.py projects test resilient
"""
from __future__ import annotations

import random
import threading

import pytest

from conftest import load

pytestmark = pytest.mark.project

rz = load("resilient")


class Clock:
    """A controllable stand-in for time.monotonic + time.sleep."""

    def __init__(self, start=1000.0):
        self.t = start
        self.slept: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rz, "now", c)
    monkeypatch.setattr(rz, "sleep", c.sleep)
    return c


class Boom(Exception):
    pass


class Other(Exception):
    pass


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------
class TestBackoff:
    def test_constant(self):
        strategy = rz.constant(0.5)
        assert [strategy(n) for n in (1, 2, 3)] == [0.5, 0.5, 0.5]

    def test_linear(self):
        strategy = rz.linear(2)
        assert [strategy(n) for n in (1, 2, 3)] == [2.0, 4.0, 6.0]

    def test_exponential(self):
        strategy = rz.exponential(1, factor=2)
        assert [strategy(n) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 8.0]

    def test_exponential_cap(self):
        strategy = rz.exponential(1, factor=10, cap=25)
        assert [strategy(n) for n in (1, 2, 3)] == [1.0, 10.0, 25.0]

    def test_jittered_stays_in_range(self):
        rng = random.Random(0)
        strategy = rz.jittered(rz.constant(4), rng)
        values = [strategy(1) for _ in range(50)]
        assert all(0 <= v <= 4 for v in values)
        assert len(set(values)) > 1, "jitter should actually vary"


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
class TestRetry:
    def test_success_costs_nothing(self, clock):
        calls = []

        @rz.retry(attempts=3, backoff=rz.constant(1))
        def ok():
            calls.append(1)
            return "fine"

        assert ok() == "fine"
        assert calls == [1]
        assert clock.slept == []

    def test_retries_then_succeeds(self, clock):
        calls = []

        @rz.retry(attempts=3, exceptions=(Boom,))
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise Boom("again")
            return "recovered"

        assert flaky() == "recovered"
        assert len(calls) == 3

    def test_reraises_the_last_error(self, clock):
        @rz.retry(attempts=2, exceptions=(Boom,))
        def always():
            raise Boom("final")

        with pytest.raises(Boom, match="final"):
            always()

    def test_backoff_delays(self, clock):
        @rz.retry(attempts=4, exceptions=(Boom,), backoff=rz.exponential(1, factor=2))
        def always():
            raise Boom("x")

        with pytest.raises(Boom):
            always()
        assert clock.slept == [1.0, 2.0, 4.0], clock.slept

    def test_on_retry_hook(self, clock):
        seen = []

        @rz.retry(attempts=3, exceptions=(Boom,), backoff=rz.constant(2),
                  on_retry=lambda exc, attempt, delay: seen.append((attempt, delay)))
        def always():
            raise Boom("x")

        with pytest.raises(Boom):
            always()
        assert seen == [(1, 2.0), (2, 2.0)], seen

    def test_unlisted_exception_passes_through(self, clock):
        calls = []

        @rz.retry(attempts=5, exceptions=(Boom,))
        def wrong():
            calls.append(1)
            raise Other("nope")

        with pytest.raises(Other):
            wrong()
        assert calls == [1]

    def test_give_up_on_wins_over_exceptions(self, clock):
        calls = []

        @rz.retry(attempts=5, exceptions=(Exception,), give_up_on=(Boom,))
        def fatal():
            calls.append(1)
            raise Boom("do not retry me")

        with pytest.raises(Boom):
            fatal()
        assert calls == [1], "give_up_on must take precedence"

    def test_metadata_and_validation(self):
        @rz.retry(attempts=2)
        def documented(a, b=1):
            """Docs."""
            return a + b

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "Docs."
        assert documented(1) == 2
        with pytest.raises(ValueError):
            rz.retry(attempts=0)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class TestCircuitBreaker:
    def test_starts_closed(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=2)
        assert breaker.state == "closed"

    def test_trips_after_threshold(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=3, reset_after=10)

        def fail():
            raise Boom("x")

        for _ in range(3):
            with pytest.raises(Boom):
                breaker.call(fail)
        assert breaker.state == "open"

    def test_open_short_circuits_without_calling(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10)
        calls = []

        def fail():
            calls.append(1)
            raise Boom("x")

        with pytest.raises(Boom):
            breaker.call(fail)
        assert breaker.state == "open"

        with pytest.raises(rz.CircuitOpen) as info:
            breaker.call(fail)
        assert calls == [1], "an open breaker must not invoke the function"
        assert info.value.retry_after == pytest.approx(10.0)

    def test_success_resets_the_failure_count(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=3, reset_after=10)

        def fail():
            raise Boom("x")

        for _ in range(2):
            with pytest.raises(Boom):
                breaker.call(fail)
        breaker.call(lambda: "ok")
        for _ in range(2):
            with pytest.raises(Boom):
                breaker.call(fail)
        assert breaker.state == "closed", (
            "a success should have cleared the earlier failures"
        )

    def test_half_open_after_reset_window(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10)
        with pytest.raises(Boom):
            breaker.call(lambda: (_ for _ in ()).throw(Boom("x")))
        assert breaker.state == "open"
        clock.advance(9.9)
        assert breaker.state == "open"
        clock.advance(0.2)
        assert breaker.state == "half_open"

    def test_half_open_success_closes(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10)
        with pytest.raises(Boom):
            breaker.call(lambda: (_ for _ in ()).throw(Boom("x")))
        clock.advance(11)
        assert breaker.call(lambda: "ok") == "ok"
        assert breaker.state == "closed"

    def test_half_open_failure_reopens(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10)

        def fail():
            raise Boom("x")

        with pytest.raises(Boom):
            breaker.call(fail)
        clock.advance(11)
        assert breaker.state == "half_open"
        with pytest.raises(Boom):
            breaker.call(fail)
        assert breaker.state == "open", "a half-open failure must re-open it"
        assert breaker.retry_after == pytest.approx(10.0), (
            "re-opening should restart the reset timer"
        )

    def test_half_open_requires_n_successes(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10,
                                    half_open_successes=2)
        with pytest.raises(Boom):
            breaker.call(lambda: (_ for _ in ()).throw(Boom("x")))
        clock.advance(11)
        breaker.call(lambda: "ok")
        assert breaker.state == "half_open", "one success is not enough"
        breaker.call(lambda: "ok")
        assert breaker.state == "closed"

    def test_unlisted_exception_is_not_a_failure(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, exceptions=(Boom,))
        with pytest.raises(Other):
            breaker.call(lambda: (_ for _ in ()).throw(Other("x")))
        assert breaker.state == "closed"

    def test_as_context_manager(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=10)
        with pytest.raises(Boom):
            with breaker:
                raise Boom("x")
        assert breaker.state == "open"
        with pytest.raises(rz.CircuitOpen):
            with breaker:
                pass

    def test_as_decorator(self, clock):
        calls = []

        @rz.circuit_breaker(failure_threshold=1, reset_after=10)
        def flaky():
            calls.append(1)
            raise Boom("x")

        with pytest.raises(Boom):
            flaky()
        with pytest.raises(rz.CircuitOpen):
            flaky()
        assert calls == [1]
        assert flaky.__name__ == "flaky"

    def test_reset(self, clock):
        breaker = rz.CircuitBreaker(failure_threshold=1, reset_after=100)
        with pytest.raises(Boom):
            breaker.call(lambda: (_ for _ in ()).throw(Boom("x")))
        assert breaker.state == "open"
        breaker.reset()
        assert breaker.state == "closed"

    def test_circuit_open_is_a_resilience_error(self):
        assert issubclass(rz.CircuitOpen, rz.ResilienceError)
        assert issubclass(rz.BulkheadFull, rz.ResilienceError)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
class TestRateLimiter:
    def test_starts_full(self, clock):
        limiter = rz.RateLimiter(rate=10, capacity=5)
        assert limiter.available == pytest.approx(5.0)

    def test_try_acquire_consumes(self, clock):
        limiter = rz.RateLimiter(rate=10, capacity=3)
        assert limiter.try_acquire() is True
        assert limiter.available == pytest.approx(2.0)
        assert limiter.try_acquire(2) is True
        assert limiter.try_acquire() is False, "the bucket should be empty"

    def test_refills_over_time(self, clock):
        limiter = rz.RateLimiter(rate=2, capacity=2)
        assert limiter.try_acquire(2) is True
        assert limiter.try_acquire() is False
        clock.advance(0.5)
        assert limiter.available == pytest.approx(1.0)
        assert limiter.try_acquire() is True

    def test_never_exceeds_capacity(self, clock):
        limiter = rz.RateLimiter(rate=100, capacity=5)
        clock.advance(1000)
        assert limiter.available == pytest.approx(5.0)

    def test_acquire_sleeps_for_the_shortfall(self, clock):
        limiter = rz.RateLimiter(rate=2, capacity=2)
        limiter.acquire(2)
        limiter.acquire(1)
        assert clock.slept == pytest.approx([0.5]), clock.slept

    def test_impossible_request(self, clock):
        limiter = rz.RateLimiter(rate=1, capacity=2)
        with pytest.raises(ValueError):
            limiter.try_acquire(3)
        with pytest.raises(ValueError):
            limiter.acquire(3)

    def test_as_context_manager(self, clock):
        limiter = rz.RateLimiter(rate=10, capacity=2)
        with limiter:
            pass
        assert limiter.available == pytest.approx(1.0)

    def test_smooths_a_burst(self, clock):
        limiter = rz.RateLimiter(rate=5, capacity=1)
        for _ in range(4):
            limiter.acquire()
        # first is free (bucket full), then 0.2s per token
        assert clock.slept == pytest.approx([0.2, 0.2, 0.2]), clock.slept


# ---------------------------------------------------------------------------
# Bulkhead
# ---------------------------------------------------------------------------
class TestBulkhead:
    def test_allows_up_to_the_limit(self):
        bulkhead = rz.Bulkhead(2)
        with bulkhead:
            with bulkhead:
                assert bulkhead.in_flight == 2
        assert bulkhead.in_flight == 0

    def test_rejects_beyond_the_limit(self):
        bulkhead = rz.Bulkhead(1)
        with bulkhead:
            with pytest.raises(rz.BulkheadFull):
                with bulkhead:
                    pass

    def test_releases_on_exception(self):
        bulkhead = rz.Bulkhead(1)
        with pytest.raises(Boom):
            with bulkhead:
                raise Boom("x")
        assert bulkhead.in_flight == 0
        with bulkhead:
            pass

    def test_max_seen(self):
        bulkhead = rz.Bulkhead(3)
        with bulkhead, bulkhead:
            pass
        assert bulkhead.max_seen == 2

    def test_thread_safe(self):
        bulkhead = rz.Bulkhead(3, wait=True)
        errors = []
        barrier = threading.Barrier(20)

        def worker():
            barrier.wait()
            try:
                with bulkhead:
                    if bulkhead.in_flight > 3:
                        errors.append(bulkhead.in_flight)
            except rz.BulkheadFull:
                pass

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"saw {max(errors)} concurrent holders with limit 3"
        assert bulkhead.in_flight == 0
        assert bulkhead.max_seen <= 3


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
class TestComposition:
    def test_retry_over_a_breaker(self, clock):
        attempts = []
        breaker = rz.CircuitBreaker(failure_threshold=2, reset_after=100)

        @rz.retry(attempts=5, exceptions=(Boom,), give_up_on=(rz.CircuitOpen,),
                  backoff=rz.constant(0.1))
        def call():
            attempts.append(1)
            return breaker.call(lambda: (_ for _ in ()).throw(Boom("x")))

        with pytest.raises(rz.CircuitOpen):
            call()
        assert len(attempts) == 3, (
            f"two real attempts trip the breaker, the third is short-circuited; "
            f"got {len(attempts)}"
        )
