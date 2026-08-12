"""Lesson 19 — asyncio."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=19,
    slug="asyncio",
    title="Asyncio and Coroutines",
    summary="""
    Asyncio gives you thousands of concurrent I/O operations on one thread,
    with no locks — at the cost of a strict rule: never block the event loop.
    This lesson covers coroutines and tasks, the difference between
    `gather` and `TaskGroup`, cancellation (which is delivered as an
    exception), timeouts, async iteration and context managers, and the
    synchronisation primitives you still need.
    """,
    tags=("asyncio", "async", "coroutines", "concurrency"),
    blocks=[
        Text("""
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
        """),
        Demo(
            code="""
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
            print("\\ncalling it produced:", type(coro).__name__)
            coro.close()
            """,
        ),
        Question(
            prompt="`await slow_a(); await slow_b()` — do these run concurrently?",
            choices=[
                "Yes, `await` schedules them in parallel",
                "No — each `await` waits for completion before the next line runs",
                "Only if they are I/O-bound",
                "Only inside `asyncio.run`",
            ],
            answer=1,
            explain="`await` means *wait here*. Concurrency needs tasks: "
                    "`asyncio.gather(...)` or a `TaskGroup`.",
        ),
        Text("""
        ## `gather` vs `TaskGroup`

        `asyncio.gather(*aws)` — returns results in argument order. With
        `return_exceptions=True` failures come back as values; otherwise the
        first exception propagates while **the other tasks keep running**,
        which is usually not what you want.

        `asyncio.TaskGroup()` (3.11+) — structured concurrency. If any task
        fails, the rest are **cancelled**, and the errors surface together as
        an `ExceptionGroup`. Prefer it.
        """),
        Demo(
            code="""
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
            """,
        ),
        Demo(
            min_version=(3, 11),
            code="""
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
            """,
            explain="""
            This is *structured concurrency*: no task outlives the block, and
            no failure is silently dropped. With bare `gather`, "slow" would
            have kept running after the error surfaced — and if nothing
            awaited it, you would get a "Task exception was never retrieved"
            warning at shutdown, or nothing at all.
            """,
        ),
        Text("""
        ## Cancellation is an exception

        `task.cancel()` schedules `asyncio.CancelledError` to be raised **at
        the task's current await point**. Since 3.8 it inherits from
        `BaseException`, so `except Exception:` will not swallow it.

        Rules:

        - clean up in `finally`, and keep the cleanup non-blocking
        - if you catch `CancelledError`, **re-raise** it
        - use `asyncio.shield(aw)` to protect a critical section
        - a task that never awaits cannot be cancelled
        """),
        Demo(
            code="""
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
            """,
        ),
        Demo(
            code="""
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
            """,
        ),
        Predict(
            code="""
            import asyncio

            async def main():
                async def child():
                    await asyncio.sleep(0.01)
                    return "done"

                task = asyncio.create_task(child())
                print(task.done())
                await asyncio.sleep(0.05)
                print(task.done(), task.result())

            asyncio.run(main())
            """,
            answer="""
            False
            True done
            """,
            explain="""
            `create_task` schedules the coroutine but does not start it — the
            loop only runs it when the current coroutine next suspends. So
            `task.done()` is immediately False; after our `sleep` yields
            control, the child gets to run and finish.
            """,
        ),
        Text("""
        ## Never block the loop

        A blocking call freezes **every** coroutine, because there is only one
        thread. `time.sleep`, `requests.get`, heavy CPU work, and blocking
        file I/O are all forbidden inside a coroutine.

        The escape hatch is `asyncio.to_thread(fn, *args)` (or
        `loop.run_in_executor`) which runs the blocking call on a worker
        thread and gives you an awaitable.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            The tick counts tell the whole story: during the blocking call the
            loop made no progress at all. `to_thread` keeps the loop
            responsive — and it is the standard way to use a synchronous
            database driver from async code.
            """,
        ),
        Text("""
        ## Async iteration, context managers, and generators

        - `async for` needs `__aiter__` / `__anext__`, ending with
          `StopAsyncIteration`.
        - `async with` needs `__aenter__` / `__aexit__`.
        - `async def` + `yield` gives an **async generator**; combine with
          `contextlib.asynccontextmanager` for the manager form.
        - Async comprehensions work: `[x async for x in agen()]`.
        """),
        Demo(
            code="""
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
            """,
        ),
        Demo(
            code="""
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
            """,
        ),
        Question(
            prompt="What happens if you call `time.sleep(5)` inside a coroutine?",
            choices=[
                "Only that coroutine pauses; others keep running",
                "The entire event loop — and every other coroutine — freezes for 5 seconds",
                "asyncio raises a RuntimeError",
                "It is automatically converted to `asyncio.sleep`",
            ],
            answer=1,
            explain="One thread, one loop. Use `await asyncio.sleep(5)`, or "
                    "`await asyncio.to_thread(...)` for unavoidably blocking calls.",
        ),
        Exercise(
            slug="async-limiter",
            title="A concurrency-limited async mapper",
            difficulty="brutal",
            brief="""
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
            """,
            starter="""
            import asyncio


            async def gather_limited(coro_fn, items, limit, *,
                                     return_exceptions=False, timeout=None):
                ...


            async def collect_ordered(tasks):
                ...
            """,
            checks=[
                Check("maps and preserves order", lambda ns: _al_order(ns)),
                Check("respects the concurrency limit", lambda ns: _al_limit(ns)),
                Check("first error propagates and cancels the rest", lambda ns: _al_error(ns)),
                Check("return_exceptions collects failures", lambda ns: _al_collect(ns)),
                Check("timeout cancels everything and raises", lambda ns: _al_timeout(ns)),
                Check("edge cases: empty input, bad limit", lambda ns: _al_edges(ns)),
                Check("leaves no tasks running", lambda ns: _al_no_leaks(ns)),
                Check("collect_ordered works", lambda ns: _al_collect_ordered(ns)),
            ],
            hints=(
                "`asyncio.Semaphore(limit)` inside a small wrapper coroutine is the "
                "whole concurrency control: `async with sem: return await coro_fn(item)`.",
                "Order comes free if you build the task list in input order and "
                "await them in that order — or just hand the wrappers to `gather`.",
                "For cancellation on error, wrap the body in try/except and call "
                "`.cancel()` on every task that is not done, then await them with "
                "`return_exceptions=True` so the cancellations settle.",
                "`asyncio.timeout(timeout)` (3.11+) around the whole gather gives "
                "you the timeout behaviour, but you still must clean up the tasks.",
                "`asyncio.gather` with `return_exceptions=True` never raises, which "
                "makes it a good tool for *draining* cancelled tasks.",
            ),
            solution="""
            import asyncio

            async def gather_limited(coro_fn, items, limit, *,
                                     return_exceptions=False, timeout=None):
                if limit < 1:
                    raise ValueError("limit must be at least 1")
                items = list(items)
                if not items:
                    return []

                semaphore = asyncio.Semaphore(limit)

                async def guarded(item):
                    async with semaphore:
                        return await coro_fn(item)

                tasks = [asyncio.create_task(guarded(item)) for item in items]

                async def drain():
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

                try:
                    if timeout is None:
                        return await asyncio.gather(
                            *tasks, return_exceptions=return_exceptions
                        )
                    async with asyncio.timeout(timeout):
                        return await asyncio.gather(
                            *tasks, return_exceptions=return_exceptions
                        )
                except (Exception, asyncio.CancelledError):
                    await drain()
                    raise

            async def collect_ordered(tasks):
                return [await task for task in tasks]
            """,
        ),
        Text("""
        ## Takeaways

        - Calling a coroutine function runs nothing; tasks create concurrency.
        - `TaskGroup` over `gather`: siblings get cancelled, errors group up.
        - `CancelledError` is a `BaseException` — clean up in `finally` and
          always re-raise.
        - One blocking call freezes the whole loop; use `asyncio.to_thread`.
        - `async for` / `async with` / async generators exist and compose.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _al_order(ns) -> None:
    import asyncio
    import random

    gather_limited = ns["gather_limited"]

    async def work(n):
        await asyncio.sleep(random.uniform(0, 0.01))
        return n * n

    async def main():
        return await gather_limited(work, [1, 2, 3, 4, 5], limit=2)

    assert _run(main()) == [1, 4, 9, 16, 25], _run(main())


def _al_limit(ns) -> None:
    import asyncio

    gather_limited = ns["gather_limited"]

    async def main():
        active = peak = 0

        async def tracked(n):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return n

        await gather_limited(tracked, list(range(9)), limit=3)
        return peak

    peak = _run(main())
    assert peak <= 3, f"{peak} coroutines ran at once with limit=3"
    assert peak > 1, f"peak concurrency was {peak} — nothing ran concurrently"


def _al_error(ns) -> None:
    import asyncio

    gather_limited = ns["gather_limited"]

    async def main():
        completed = []

        async def maybe_fail(n):
            if n == 1:
                await asyncio.sleep(0.01)
                raise ValueError("item 1 failed")
            await asyncio.sleep(0.2)
            completed.append(n)
            return n

        try:
            await gather_limited(maybe_fail, list(range(6)), limit=6)
        except ValueError as exc:
            return str(exc), completed
        return None, completed

    message, completed = _run(main())
    assert message == "item 1 failed", f"the failure should propagate, got {message!r}"
    assert completed == [], f"siblings should have been cancelled, but {completed} finished"


def _al_collect(ns) -> None:
    import asyncio

    gather_limited = ns["gather_limited"]

    async def main():
        async def maybe_fail(n):
            await asyncio.sleep(0.005)
            if n % 2:
                raise ValueError(f"odd {n}")
            return n

        return await gather_limited(maybe_fail, [0, 1, 2, 3], limit=2,
                                    return_exceptions=True)

    results = _run(main())
    assert len(results) == 4, results
    assert results[0] == 0 and results[2] == 2, results
    assert isinstance(results[1], ValueError), f"expected an exception, got {results[1]!r}"
    assert isinstance(results[3], ValueError)


def _al_timeout(ns) -> None:
    import asyncio
    import time

    gather_limited = ns["gather_limited"]

    async def main():
        async def slow(n):
            await asyncio.sleep(5)
            return n

        start = time.perf_counter()
        try:
            await gather_limited(slow, list(range(4)), limit=4, timeout=0.05)
        except TimeoutError:
            return "timeout", time.perf_counter() - start
        return "no timeout", time.perf_counter() - start

    kind, elapsed = _run(main())
    assert kind == "timeout", "expected TimeoutError to be raised"
    assert elapsed < 1.0, f"it waited {elapsed:.2f}s — the tasks were not cancelled"


def _al_edges(ns) -> None:
    import asyncio

    gather_limited = ns["gather_limited"]
    started = []

    async def work(n):
        started.append(n)
        return n

    async def main_empty():
        return await gather_limited(work, [], limit=2)

    assert _run(main_empty()) == [], "an empty input should return []"
    assert started == []

    async def main_bad():
        return await gather_limited(work, [1], limit=0)

    try:
        _run(main_bad())
    except ValueError:
        return
    raise AssertionError("limit < 1 must raise ValueError")


def _al_no_leaks(ns) -> None:
    import asyncio

    gather_limited = ns["gather_limited"]

    async def main():
        async def maybe_fail(n):
            await asyncio.sleep(0.01 * n)
            if n == 1:
                raise ValueError("boom")
            return n

        try:
            await gather_limited(maybe_fail, list(range(5)), limit=5)
        except ValueError:
            pass
        await asyncio.sleep(0)
        return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    leftover = _run(main())
    assert leftover == [], f"{len(leftover)} task(s) still running after the failure"


def _al_collect_ordered(ns) -> None:
    import asyncio

    collect_ordered = ns["collect_ordered"]

    async def main():
        async def work(n):
            await asyncio.sleep(0.01 * (3 - n))
            return n

        tasks = [asyncio.create_task(work(i)) for i in range(3)]
        return await collect_ordered(tasks)

    assert _run(main()) == [0, 1, 2], "results must follow task order, not finish order"
