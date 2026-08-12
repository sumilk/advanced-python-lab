# 19 — Asyncio and Coroutines

Asyncio gives you thousands of concurrent I/O operations on one thread,
with no locks — at the cost of a strict rule: never block the event loop.
This lesson covers coroutines and tasks, the difference between
`gather` and `TaskGroup`, cancellation (which is delivered as an
exception), timeouts, async iteration and context managers, and the
synchronisation primitives you still need.

## Coroutines, tasks, and the loop

- `async def` creates a **coroutine function**; calling it returns a
  coroutine object and runs **nothing**.
- `await x` suspends the current coroutine until `x` completes,
  handing control back to the event loop.
- Concurrency starts only when you create a **Task** — via
  `asyncio.create_task`, `TaskGroup`, or `gather`.
- `asyncio.run(main())` starts a loop, runs one coroutine, and
  shuts down cleanly.

Sequential `await`s are just... sequential. That is the single most
common misunderstanding.

```python
import asyncio
import time

async def fetch(name, delay):
    await asyncio.sleep(delay)
    return f"{name} ({delay}s)"

async def sequential():
    start = time.perf_counter()
    a = await fetch("a", 0.05)
    b = await fetch("b", 0.05)
    return time.perf_counter() - start, [a, b]

async def concurrent():
    start = time.perf_counter()
    task_a = asyncio.create_task(fetch("a", 0.05))
    task_b = asyncio.create_task(fetch("b", 0.05))
    results = [await task_a, await task_b]
    return time.perf_counter() - start, results

async def main():
    t1, r1 = await sequential()
    t2, r2 = await concurrent()
    print(f"sequential awaits : {t1*1000:5.0f} ms  {r1}")
    print(f"tasks             : {t2*1000:5.0f} ms  {r2}")

asyncio.run(main())

# Calling a coroutine function runs nothing:
coro = fetch("unused", 0)
print("\ncalling it produced:", type(coro).__name__)
coro.close()
```
Both versions do identical work; only the *scheduling* differs.
Two `await`s cost 0.05 + 0.05 because `await` means **wait here** —
nothing overlaps. `create_task` hands each coroutine to the loop
straight away, so both sleeps are already in flight before the
first `await task_a` runs, and the pair costs one 0.05s wait.

The tail shows the other half of the rule: `fetch("unused", 0)`
builds a coroutine object and executes **not one line** of the
body. A coroutine you forget to await or wrap in a task simply
never runs — the most common asyncio bug there is. (`close()`
here just avoids the "never awaited" warning at shutdown.)

**Quiz.** `await slow_a(); await slow_b()` — do these run concurrently?

- a) Yes, `await` schedules them in parallel
- b) No — each `await` waits for completion before the next line runs
- c) Only if they are I/O-bound
- d) Only inside `asyncio.run`

<details><summary>answer</summary>

**b** — `await` means *wait here*. Concurrency needs tasks: `asyncio.gather(...)` or a `TaskGroup`.
</details>

## `gather` vs `TaskGroup`

`asyncio.gather(*aws)` — returns results in argument order. With
`return_exceptions=True` failures come back as values; otherwise the
first exception propagates while **the other tasks keep running**,
which is usually not what you want.

`asyncio.TaskGroup()` (3.11+) — structured concurrency. If any task
fails, the rest are **cancelled**, and the errors surface together as
an `ExceptionGroup`. Prefer it.

```python
import asyncio

async def job(name, delay, fail=False):
    await asyncio.sleep(delay)
    if fail:
        raise ValueError(f"{name} failed")
    return name

async def with_gather():
    results = await asyncio.gather(
        job("a", 0.01), job("b", 0.02, fail=True), job("c", 0.03),
        return_exceptions=True,
    )
    return [r if not isinstance(r, Exception) else f"<{r}>" for r in results]

async def main():
    print("gather(return_exceptions=True):", await with_gather())

asyncio.run(main())
```
`return_exceptions=True` turns a failure into a *value*: the
results list still has one entry per argument, in
**argument order**, with the exception object sitting in the
failed slot. You have to check types on the way out — nothing
raises.

Drop that flag and the `ValueError` propagates out of the `await`
as soon as `b` fails — but `c` is **still running**. `gather` does
not cancel siblings. That is the trap: the caller handles an error
while orphaned work continues in the background, usually surfacing
later as a "Task exception was never retrieved" warning.

```python
import asyncio

async def job(name, delay, fail=False):
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        print(f"  {name} was cancelled")
        raise
    if fail:
        raise ValueError(f"{name} failed")
    print(f"  {name} finished")
    return name

async def main():
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(job("fast", 0.01))
            group.create_task(job("broken", 0.02, fail=True))
            group.create_task(job("slow", 0.20))
    except* ValueError as group:
        print("caught:", [str(e) for e in group.exceptions])

asyncio.run(main())
print()
print("'slow' never completed: a TaskGroup cancels its siblings on failure")
```
This is *structured concurrency*: no task outlives the block, and
no failure is silently dropped. With bare `gather`, "slow" would
have kept running after the error surfaced — and if nothing
awaited it, you would get a "Task exception was never retrieved"
warning at shutdown, or nothing at all.

## Cancellation is an exception

`task.cancel()` schedules `asyncio.CancelledError` to be raised
**at the task's current await point**. Since 3.8 it inherits from
`BaseException`, so `except Exception:` will not swallow it.

Rules:

- clean up in `finally`, and keep the cleanup non-blocking
- if you catch `CancelledError`, **re-raise** it
- use `asyncio.shield(aw)` to protect a critical section
- a task that never awaits cannot be cancelled

```python
import asyncio

async def worker():
    try:
        await asyncio.sleep(10)
    except asyncio.CancelledError:
        print("  worker: cleaning up")
        raise                       # ALWAYS re-raise
    finally:
        print("  worker: finally block")

async def swallower():
    try:
        await asyncio.sleep(10)
    except asyncio.CancelledError:
        print("  swallower: ignoring cancellation (bad idea)")
        return "escaped"

async def main():
    good = asyncio.create_task(worker())
    await asyncio.sleep(0.01)
    good.cancel()
    try:
        await good
    except asyncio.CancelledError:
        print("cancellation propagated:", good.cancelled())

    bad = asyncio.create_task(swallower())
    await asyncio.sleep(0.01)
    bad.cancel()
    result = await bad
    print("swallowed -> task returned:", result, "| cancelled:", bad.cancelled())

asyncio.run(main())
```
`good.cancel()` raises `CancelledError` inside `worker`
**at its current await point** — the `sleep(10)` — so the
`except` runs, then `finally`. Because the handler re-raises,
the task settles in
the *cancelled* state: `await good` raises and `good.cancelled()`
is True.

`swallower` catches and returns instead, and the cancellation is
simply lost. The task completes **successfully** with `"escaped"`,
`bad.cancelled()` is False, and the code that asked for the
cancellation has no way to learn it was ignored. `cancel()` is a
request, not a guarantee — the only correct response is to clean
up and `raise`.

```python
import asyncio

async def slow():
    await asyncio.sleep(1)
    return "never"

async def critical():
    await asyncio.sleep(0.05)
    return "committed"

async def main():
    # timeout: cancels the inner operation
    try:
        await asyncio.wait_for(slow(), timeout=0.05)
    except TimeoutError:
        print("wait_for  -> TimeoutError, inner task cancelled")

    # the 3.11 context-manager form, which composes better
    try:
        async with asyncio.timeout(0.05):
            await slow()
    except TimeoutError:
        print("timeout() -> TimeoutError")

    # shield: the outer wait is cancelled, the inner work is not
    task = asyncio.create_task(critical())
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=0.01)
    except TimeoutError:
        print("shield    -> outer timed out; inner still running:",
              not task.done())
    print("           -> shielded result:", await task)

asyncio.run(main())
```
Three tools, one mechanism: a timeout works by **cancelling** what
it wraps. Which means everything from the previous demo applies —
a coroutine that swallows `CancelledError` cannot be timed out.

- `wait_for` cancels the inner coroutine and raises
  `TimeoutError`. Since 3.11 that *is* the builtin `TimeoutError`;
  `asyncio.TimeoutError` is now just an alias.
- `asyncio.timeout()` (3.11+) is the same thing as a block, so one
  deadline can cover several awaits instead of one call.
- `shield` breaks the chain: the cancellation stops at the shield,
  so the outer `wait_for` gives up while `critical()` runs on to
  completion — which is why `await task` still yields
  `"committed"`.

Reach for `shield` when work must not be left half-done, and note
that you are still on the hook for awaiting the task you shielded;
the timeout no longer does it for you.


## Never block the loop

A blocking call freezes **every** coroutine, because there is only one
thread. `time.sleep`, `requests.get`, heavy CPU work, and blocking
file I/O are all forbidden inside a coroutine.

The escape hatch is `asyncio.to_thread(fn, *args)` (or
`loop.run_in_executor`) which runs the blocking call on a worker
thread and gives you an awaitable.

```python
import asyncio
import time

def blocking(label, seconds):
    time.sleep(seconds)             # a stand-in for a sync library
    return f"{label} done"

async def ticker(stop):
    ticks = 0
    while not stop.is_set():
        ticks += 1
        await asyncio.sleep(0.01)
    return ticks

async def main():
    # Wrong: blocks the loop, so the ticker never runs.
    stop = asyncio.Event()
    task = asyncio.create_task(ticker(stop))
    await asyncio.sleep(0)          # let the ticker start
    blocking("sync call", 0.1)
    stop.set()
    print("ticks while blocking  :", await task)

    # Right: offload to a thread.
    stop = asyncio.Event()
    task = asyncio.create_task(ticker(stop))
    result = await asyncio.to_thread(blocking, "threaded", 0.1)
    stop.set()
    print("ticks while to_thread :", await task, f"({result})")

asyncio.run(main())
```
The tick counts tell the whole story: during the blocking call the
loop made no progress at all. `to_thread` keeps the loop
responsive — and it is the standard way to use a synchronous
database driver from async code.

## Async iteration, context managers, and generators

- `async for` needs `__aiter__` / `__anext__`, ending with
  `StopAsyncIteration`.
- `async with` needs `__aenter__` / `__aexit__`.
- `async def` + `yield` gives an **async generator**; combine with
  `contextlib.asynccontextmanager` for the manager form.
- Async comprehensions work: `[x async for x in agen()]`.

```python
import asyncio
from contextlib import asynccontextmanager

async def stream(n):
    '''An async generator.'''
    for i in range(n):
        await asyncio.sleep(0.001)
        yield i * i

class Paged:
    '''Manual async iterator over 'pages'.'''
    def __init__(self, pages): self.pages, self.i = pages, 0
    def __aiter__(self): return self
    async def __anext__(self):
        if self.i >= self.pages:
            raise StopAsyncIteration
        await asyncio.sleep(0.001)
        self.i += 1
        return f"page{self.i}"

@asynccontextmanager
async def session(name):
    print(f"  open {name}")
    try:
        yield {"name": name}
    finally:
        await asyncio.sleep(0)      # async cleanup is allowed here
        print(f"  close {name}")

async def main():
    print("async comprehension:", [x async for x in stream(4)])
    print("filtered:", [x async for x in stream(6) if x % 2 == 0])

    async for page in Paged(3):
        print("  got", page)

    async with session("db") as s:
        print("  using", s["name"])

asyncio.run(main())
```
Three distinct protocols, side by side.

`stream` is an **async generator** — `async def` plus `yield` —
and the thing a plain generator cannot do is `await` between
yields, which is exactly what streaming rows off a socket needs.
`Paged` spells the same protocol out by hand: `__aiter__` returns
the iterator, `__anext__` is a *coroutine*, and the loop ends on
`StopAsyncIteration` — not `StopIteration`, which would be
swallowed as an ordinary generator return.

`session` is the `async with` form. Its advantage over a sync
manager is the `await` in the `finally`: cleanup can flush a
socket or roll back a transaction rather than only closing a
handle.

Note where `async` sits in `[x async for x in stream(4)]` — it
belongs to the `for`. A plain `for` over an async generator is a
`TypeError`, not a blocking wait.

```python
import asyncio

# Async primitives: same names as threading, but never block the loop.
async def main():
    limiter = asyncio.Semaphore(2)
    order = []

    async def guarded(n):
        async with limiter:
            order.append(f"start{n}")
            await asyncio.sleep(0.01)
            order.append(f"end{n}")

    await asyncio.gather(*(guarded(i) for i in range(4)))
    print("at most 2 at a time:", order[:4])

    # Queue: the async producer/consumer pattern
    queue = asyncio.Queue(maxsize=2)
    collected = []

    async def producer():
        for i in range(5):
            await queue.put(i)
        await queue.put(None)

    async def consumer():
        while True:
            item = await queue.get()
            queue.task_done()
            if item is None:
                return
            collected.append(item * 10)

    await asyncio.gather(producer(), consumer())
    print("queue results:", collected)

asyncio.run(main())
```
`asyncio.Semaphore` has the same shape as the threading one but
**suspends instead of blocking**, so the two coroutines waiting
their turn cost nothing while parked. This is the standard way to
cap concurrent requests to one host — and the core of this
lesson's exercise.

`maxsize=2` on the queue gives you **back-pressure**: `put`
suspends once the queue is full, so a fast producer cannot run
ahead of a slow consumer and grow the buffer without bound. The
`None` sentinel is what ends the consumer; without it the
`while True` would park forever on an empty queue, and
`asyncio.run` would hang. (`task_done` does nothing on its own
here — it pairs with a `queue.join()` when you want a producer to
wait for the backlog to drain instead of using a sentinel.)

**Quiz.** What happens if you call `time.sleep(5)` inside a coroutine?

- a) Only that coroutine pauses; others keep running
- b) The entire event loop — and every other coroutine — freezes for 5 seconds
- c) asyncio raises a RuntimeError
- d) It is automatically converted to `asyncio.sleep`

<details><summary>answer</summary>

**b** — One thread, one loop. Use `await asyncio.sleep(5)`, or `await asyncio.to_thread(...)` for unavoidably blocking calls.
</details>

## Exercise — A concurrency-limited async mapper `[brutal]`

Write `async def gather_limited(coro_fn, items, limit, *,
return_exceptions=False, timeout=None)`.

- applies the **async** function `coro_fn` to every item with at
  most `limit` running concurrently
- returns results in **input order**
- `return_exceptions=False` (default): the first failure
  propagates and all other in-flight work is cancelled
- `return_exceptions=True`: exceptions appear in the result list
  in place of their value, and every item is attempted
- `timeout` (seconds) applies to the **whole** operation; on
  expiry raise `TimeoutError` after cancelling everything
- `limit < 1` raises `ValueError`; an empty input returns `[]`
  without awaiting anything
- no task may be left running when the function returns

Also write `async def collect_ordered(tasks)` returning the results
of an ordered iterable of tasks — used by the checks to verify you
are not just calling `asyncio.gather`.
```python
import asyncio


async def gather_limited(coro_fn, items, limit, *,
                         return_exceptions=False, timeout=None):
    ...


async def collect_ordered(tasks):
    ...
```

## Takeaways

- Calling a coroutine function runs nothing; tasks create concurrency.
- `TaskGroup` over `gather`: siblings get cancelled, errors group up.
- `CancelledError` is a `BaseException` — clean up in `finally` and
  always re-raise.
- One blocking call freezes the whole loop; use `asyncio.to_thread`.
- `async for` / `async with` / async generators exist and compose.
