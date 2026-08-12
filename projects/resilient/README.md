# Resilient — a fault-tolerance toolkit

Four patterns every production service needs, each usable as a **decorator**
and as a **context manager**, all driven by an injectable clock so the tests
run instantly.

**Lessons drawn on:** 07 (decorators), 11 (context managers), 12 (exception
design), 18 (thread safety).

```python
@retry(attempts=3, backoff=exponential(0.1))
@circuit_breaker(failure_threshold=5, reset_after=30)
def call_api(): ...

with rate_limiter.acquire():
    ...
```

## Requirements

Everything reads the clock through the module-level name `now` and sleeps
through the module-level name `sleep`. The tests replace both — do not call
`time.monotonic` or `time.sleep` directly anywhere.

### 1. Backoff strategies

Plain functions returning `float` seconds for a 1-based attempt number:

- `constant(delay)` → always `delay`
- `linear(base)` → `base * attempt`
- `exponential(base, factor=2.0, cap=None)` → `base * factor**(attempt-1)`,
  clamped to `cap` when given
- `jittered(strategy, rng)` → `rng.uniform(0, strategy(attempt))`

### 2. `retry`

`retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None,
give_up_on=())`

- retries up to `attempts` times total; re-raises the last exception
- `give_up_on` types are never retried, even if they also match `exceptions`
- sleeps `backoff(attempt)` between tries; never sleeps after the last one
- `on_retry(exc, attempt, delay)` fires between attempts only
- works on a function and preserves its metadata
- `attempts < 1` → `ValueError` at decoration time

### 3. `CircuitBreaker`

States: `closed` → (too many failures) → `open` → (after `reset_after`) →
`half_open` → (a success) → `closed`, or (a failure) → `open`.

- `CircuitBreaker(failure_threshold=5, reset_after=30.0, half_open_successes=1,
  exceptions=(Exception,))`
- `.state` → `"closed" | "open" | "half_open"`
- calling through an **open** breaker raises `CircuitOpen` **without**
  invoking the wrapped function
- consecutive failures trip it; **any success in the closed state resets the
  counter to zero**
- after `reset_after` seconds the next call is allowed through as a trial
  (`half_open`); `half_open_successes` consecutive successes close it, one
  failure re-opens it and restarts the timer
- usable as `@breaker`, as `with breaker:`, and via `breaker.call(fn, *args)`
- `.reset()` forces it closed and clears the counters
- exceptions not in `exceptions` pass through **without** counting as failures

### 4. `RateLimiter` — token bucket

`RateLimiter(rate, capacity=None)` — `rate` tokens per second, bucket holds
`capacity` (defaults to `rate`).

- `.try_acquire(tokens=1)` → `bool`, never blocks
- `.acquire(tokens=1)` → blocks by calling `sleep(...)` for exactly the
  shortfall, then consumes
- tokens refill continuously from the clock — no background thread
- the bucket never exceeds `capacity`
- `tokens > capacity` raises `ValueError` (it could never be satisfied)
- `.available` → the current token count as a float
- usable as a decorator and as a context manager

### 5. `Bulkhead`

`Bulkhead(limit)` — at most `limit` concurrent holders.

- as a context manager; `BulkheadFull` when the limit is exceeded and
  `wait=False`
- `.in_flight` and `.max_seen`
- thread-safe: 20 threads hammering a `Bulkhead(3)` must never see a fourth
  concurrent holder

### 6. Exceptions

`ResilienceError` is the base; `CircuitOpen` and `BulkheadFull` inherit from
it. `CircuitOpen` carries `.retry_after` (seconds until the trial).

## Grading

```bash
uv run learn.py projects test resilient
```

## Hints

- Write `sleep(...)`/`now()` as bare module-level names so a test can
  monkeypatch them; `import time` then `time.sleep(...)` cannot be replaced.
- `ContextDecorator` from `contextlib` gets you "works as both `with` and
  `@`" for free — subclass it and implement `__enter__`/`__exit__`.
- For the circuit breaker, compute the state lazily in a `state` property
  rather than with a timer: `open` becomes `half_open` when
  `now() - opened_at >= reset_after`.
- Token bucket refill is one line: `tokens = min(capacity, tokens + elapsed *
  rate)`, computed on each access from the last-checked timestamp.
- Guard every piece of breaker/limiter state with a `threading.Lock`; the
  tests run some of it from several threads.
