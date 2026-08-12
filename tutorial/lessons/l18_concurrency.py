"""Lesson 18 — Threads, processes, and the GIL."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=18,
    slug="concurrency",
    title="Threads, Processes, and the GIL",
    summary="""
    Choosing wrongly between threads and processes is the most expensive
    mistake in Python performance work. This lesson explains what the GIL
    actually locks, measures the difference on both I/O-bound and CPU-bound
    work, covers the synchronisation primitives and the races they prevent,
    and shows the `concurrent.futures` API you should normally reach for.
    """,
    tags=("threads", "gil", "multiprocessing", "concurrency"),
    blocks=[
        Text("""
        ## What the GIL is

        The Global Interpreter Lock is one mutex protecting CPython's
        interpreter state. **Only one thread executes Python bytecode at a
        time.** Consequences:

        - CPU-bound Python code gets **no** speedup from threads — often a
          slowdown from lock contention.
        - I/O-bound code parallelises fine: the GIL is released around
          blocking syscalls (`read`, `write`, `recv`, `sleep`).
        - C extensions (NumPy, `hashlib`, compression) release the GIL during
          heavy computation, so they *do* parallelise.
        - It does **not** make your code thread-safe: the switch can happen
          between any two bytecodes.

        3.12 added per-interpreter GILs (PEP 684) and 3.13 ships an
        experimental free-threaded build — but for now, plan around the GIL.
        """),
        Demo(
            code="""
            import sys
            import threading
            import time

            def cpu_work(n):
                total = 0
                for i in range(n):
                    total += i * i
                return total

            N = 2_000_000

            start = time.perf_counter()
            cpu_work(N); cpu_work(N)
            serial = time.perf_counter() - start

            start = time.perf_counter()
            threads = [threading.Thread(target=cpu_work, args=(N,)) for _ in range(2)]
            for t in threads: t.start()
            for t in threads: t.join()
            threaded = time.perf_counter() - start

            print(f"serial   : {serial*1000:6.0f} ms")
            print(f"2 threads: {threaded*1000:6.0f} ms")
            print(f"speedup  : {serial/threaded:.2f}x  (1.0 = no benefit at all)")
            print()
            print("switch interval:", sys.getswitchinterval(), "seconds")
            """,
        ),
        Demo(
            code="""
            import threading
            import time

            def io_work(duration):
                time.sleep(duration)         # releases the GIL

            start = time.perf_counter()
            for _ in range(4):
                io_work(0.05)
            serial = time.perf_counter() - start

            start = time.perf_counter()
            threads = [threading.Thread(target=io_work, args=(0.05,)) for _ in range(4)]
            for t in threads: t.start()
            for t in threads: t.join()
            threaded = time.perf_counter() - start

            print(f"serial   : {serial*1000:6.0f} ms")
            print(f"4 threads: {threaded*1000:6.0f} ms")
            print(f"speedup  : {serial/threaded:.1f}x  <- this is what threads are for")
            """,
        ),
        Question(
            prompt="Your function spends 95% of its time in `requests.get`. Threads or processes?",
            choices=[
                "Processes — always faster",
                "Threads — the GIL is released during I/O, and they are far cheaper than processes",
                "Neither; Python cannot do concurrent I/O",
                "It makes no difference",
            ],
            answer=1,
            explain="For I/O-bound work, threads (or asyncio) win: no pickling, no "
                    "process start-up, shared memory. Processes are for CPU-bound work.",
        ),
        Text("""
        ## Races: why "one bytecode at a time" is not enough

        `counter += 1` is *at least* a load, an add, and a store. A thread
        switch between the load and the store loses an update. The GIL
        guarantees each bytecode is atomic; it guarantees nothing about your
        logical operations.
        """),
        Demo(
            code="""
            import sys
            import threading

            def race(use_lock):
                counter = 0
                lock = threading.Lock()

                def bump():
                    nonlocal counter
                    for _ in range(50_000):
                        if use_lock:
                            with lock:
                                counter += 1
                        else:
                            counter += 1

                threads = [threading.Thread(target=bump) for _ in range(4)]
                for t in threads: t.start()
                for t in threads: t.join()
                return counter

            old = sys.getswitchinterval()
            sys.setswitchinterval(1e-6)          # make the race easy to observe
            try:
                unlocked = race(False)
                locked = race(True)
            finally:
                sys.setswitchinterval(old)

            print(f"expected      : 200000")
            print(f"without a lock: {unlocked}  (lost {200000 - unlocked} updates)")
            print(f"with a lock   : {locked}")
            """,
            explain="""
            Note we shortened the switch interval to make the loss reliable —
            with the default 5 ms you might see the correct answer on a small
            loop and ship a broken program. Races are not reproducible; that
            is what makes them dangerous.
            """,
        ),
        Text("""
        ## The synchronisation primitives

        | primitive | use |
        |---|---|
        | `Lock` | mutual exclusion; not reentrant |
        | `RLock` | reentrant — same thread may acquire repeatedly |
        | `Semaphore(n)` | at most `n` holders; a permit pool |
        | `Event` | one-shot broadcast flag |
        | `Condition` | wait for a predicate, with notify |
        | `Barrier(n)` | release all threads once `n` are waiting |
        | `local()` | per-thread storage |

        And the container that removes the need for most of them: `queue.Queue`
        is already thread-safe.
        """),
        Demo(
            code="""
            import threading
            import time

            # Semaphore as a rate limiter, Event as a shutdown signal.
            permits = threading.Semaphore(2)
            shutdown = threading.Event()
            active, peak, guard = 0, 0, threading.Lock()

            def worker(n):
                nonlocal_active = None
                with permits:
                    global active, peak
                    with guard:
                        active += 1
                        peak = max(peak, active)
                    time.sleep(0.02)
                    with guard:
                        active -= 1

            active = peak = 0
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
            for t in threads: t.start()
            for t in threads: t.join()
            print("max concurrent workers:", peak, "(semaphore allowed 2)")

            # thread-local storage: each thread gets its own attribute space
            local_data = threading.local()
            seen = []

            def use_local(name):
                local_data.name = name
                time.sleep(0.01)
                seen.append((name, local_data.name))

            ts = [threading.Thread(target=use_local, args=(f"t{i}",)) for i in range(3)]
            for t in ts: t.start()
            for t in ts: t.join()
            print("thread-local values kept separate:", all(a == b for a, b in seen))
            """,
        ),
        Demo(
            code="""
            import queue
            import threading

            # The producer/consumer pattern -- no explicit locking at all.
            work = queue.Queue(maxsize=4)
            results = queue.Queue()
            SENTINEL = object()

            def producer(count):
                for i in range(count):
                    work.put(i)
                for _ in range(3):
                    work.put(SENTINEL)        # one per consumer

            def consumer(name):
                while True:
                    item = work.get()
                    try:
                        if item is SENTINEL:
                            return
                        results.put((name, item * item))
                    finally:
                        work.task_done()

            prod = threading.Thread(target=producer, args=(9,))
            cons = [threading.Thread(target=consumer, args=(f"c{i}",)) for i in range(3)]
            prod.start()
            for c in cons: c.start()
            prod.join()
            for c in cons: c.join()

            squares = sorted(v for _, v in list(results.queue))
            print("all work completed:", squares)
            print("queue drained:", work.empty())
            """,
            explain="""
            The sentinel-per-consumer trick is the standard clean shutdown. The
            alternative — `queue.join()` plus daemon threads — leaks threads at
            exit. Note `task_done()` in a `finally`, so an exception in the
            body cannot hang `join()` forever.
            """,
        ),
        Predict(
            code="""
            import threading

            results = []

            def make_workers_buggy():
                threads = []
                for i in range(3):
                    threads.append(threading.Thread(target=lambda: results.append(i)))
                return threads

            ts = make_workers_buggy()
            for t in ts: t.start()
            for t in ts: t.join()
            print(sorted(results))
            """,
            answer="""
            [2, 2, 2]
            """,
            explain="""
            The same late-binding closure bug from lesson 06, now in a thread.
            Every lambda reads `i` from the shared cell after the loop has
            finished. Fix with `args=(i,)` on the Thread, or a default
            argument.
            """,
        ),
        Text("""
        ## Deadlock, and how to avoid it

        Two locks acquired in opposite orders by two threads is all it takes.
        Rules that actually work:

        1. **Always acquire locks in a globally consistent order.**
        2. Use `with lock:` so an exception cannot skip the release.
        3. Prefer `acquire(timeout=...)` in code that must not hang.
        4. Better: avoid multiple locks — use a queue or a single coarse lock.
        """),
        Demo(
            code="""
            import threading
            import time

            lock_a, lock_b = threading.Lock(), threading.Lock()
            outcome = []

            def ordered(first, second, label):
                # Both threads take the locks in the SAME order -> no deadlock.
                with first:
                    time.sleep(0.01)
                    with second:
                        outcome.append(label)

            t1 = threading.Thread(target=ordered, args=(lock_a, lock_b, "t1"))
            t2 = threading.Thread(target=ordered, args=(lock_a, lock_b, "t2"))
            t1.start(); t2.start(); t1.join(); t2.join()
            print("consistent order ->", outcome)

            # Detecting the deadlock-prone version without hanging the lesson:
            got = lock_a.acquire(timeout=0.01)
            print("timeout-based acquire returns a bool:", got)
            if got:
                lock_a.release()
            print("a would-be deadlock shows up as acquire() returning False")
            """,
        ),
        Text("""
        ## `concurrent.futures`: the API to reach for

        One interface, two backends. Swap `ThreadPoolExecutor` for
        `ProcessPoolExecutor` and the code is unchanged.

        - `submit(fn, *args)` → a `Future`
        - `map(fn, iterable)` → results **in input order**, lazily
        - `as_completed(futures)` → results as they finish
        - exceptions surface when you call `future.result()`
        """),
        Demo(
            code="""
            import time
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def fetch(name, delay):
                time.sleep(delay)
                if name == "bad":
                    raise ValueError("this one fails")
                return f"{name} done"

            jobs = [("slow", 0.06), ("bad", 0.01), ("fast", 0.02)]

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(fetch, n, d): n for n, d in jobs}
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        print(f"  {name:5} -> {future.result()}")
                    except ValueError as exc:
                        print(f"  {name:5} -> failed: {exc}")

            print()
            with ThreadPoolExecutor() as pool:
                # map preserves input order and re-raises on iteration
                ordered = pool.map(lambda p: fetch(*p), [("a", 0.03), ("b", 0.01)])
                print("map keeps order:", list(ordered))
            """,
            explain="""
            `pool.map` swallows nothing: the exception is raised when you reach
            that element while iterating. If you need per-item error handling,
            use `submit` + `as_completed` as above.
            """,
        ),
        Demo(
            code="""
            import math
            import os
            import time
            from concurrent.futures import ProcessPoolExecutor

            # First, the constraint everyone hits: the callable must be
            # importable by name in the worker process.
            def locally_defined(n):
                return n * n

            with ProcessPoolExecutor(max_workers=2) as pool:
                try:
                    list(pool.map(locally_defined, [1, 2]))
                except Exception as exc:
                    print(f"{type(exc).__name__}: {str(exc)[:70]}")

            # math.factorial IS importable, and is genuinely CPU-bound.
            N, TASKS = 60_000, 4

            start = time.perf_counter()
            serial = [math.factorial(N) for _ in range(TASKS)]
            t_serial = time.perf_counter() - start

            start = time.perf_counter()
            with ProcessPoolExecutor(max_workers=4) as pool:
                parallel = list(pool.map(math.factorial, [N] * TASKS))
            t_parallel = time.perf_counter() - start

            print()
            print(f"serial    : {t_serial*1000:6.0f} ms")
            print(f"processes : {t_parallel*1000:6.0f} ms")
            print(f"speedup   : {t_serial/t_parallel:.2f}x on {os.cpu_count()} cores")
            print("results identical:", serial == parallel)
            """,
            explain="""
            Two lessons in one demo. The `PicklingError` is not a bug — the
            worker receives *"import this name from this module"*, and a
            function defined inside another scope has no such name.

            Costs to weigh: arguments and results are **pickled** (that
            factorial result is a 250 KB integer travelling back through a
            pipe), process start-up is tens of milliseconds, and on
            macOS/Windows the default `spawn` method re-imports your module in
            every worker. Parallelise chunks of work, not tiny calls.
            """,
        ),
        Question(
            prompt="Why must functions passed to `ProcessPoolExecutor` be defined at module level?",
            choices=[
                "For readability",
                "They are pickled by reference (module + qualname), and lambdas/closures cannot be pickled",
                "Because processes cannot execute nested functions",
                "They do not need to be",
            ],
            answer=1,
            explain="`pickle` stores a function as 'look up this name in this module'. "
                    "A lambda or a closure has no importable name, hence "
                    "`PicklingError`. `multiprocessing` can use `dill` via third-party "
                    "libraries to work around it.",
        ),
        Exercise(
            slug="thread-pool",
            title="A bounded worker pool with results and errors",
            difficulty="tricky",
            brief="""
            Implement `run_pool(fn, items, workers=4, stop_on_error=False)`
            using only `threading` and `queue` — no `concurrent.futures`.

            - runs `fn(item)` across `workers` threads
            - returns `(results, errors)` where `results` is a list of
              `(item, value)` **in the original input order** and `errors` is a
              list of `(item, exception)`, also in input order
            - every item appears in exactly one of the two lists
            - with `stop_on_error=True`, once an item raises, no *new* items
              are started (already-running ones finish); the remaining
              unstarted items appear in neither list
            - `workers < 1` raises `ValueError`
            - an empty input returns `([], [])` and starts no threads
            - all threads must be joined before returning — no daemons left
              running
            - it must be genuinely concurrent: N sleeping items with N workers
              must take about one sleep, not N
            """,
            starter="""
            import queue
            import threading


            def run_pool(fn, items, workers=4, stop_on_error=False):
                ...
            """,
            checks=[
                Check("results come back in input order", lambda ns: _tp_order(ns)),
                Check("errors are captured, not raised", lambda ns: _tp_errors(ns)),
                Check("every item is accounted for exactly once", lambda ns: _tp_complete(ns)),
                Check("actually runs concurrently", lambda ns: _tp_concurrent(ns)),
                Check("workers are bounded", lambda ns: _tp_bounded(ns)),
                Check("stop_on_error halts new work", lambda ns: _tp_stop(ns)),
                Check("edge cases: empty input, bad worker count", lambda ns: _tp_edges(ns)),
                Check("no threads left alive", lambda ns: _tp_joined(ns)),
            ],
            hints=(
                "Put `(index, item)` pairs on the queue so you can restore order "
                "by sorting at the end — or write into a pre-sized results list.",
                "A pre-sized list plus index assignment needs no lock: distinct "
                "indices never collide.",
                "For `stop_on_error`, a `threading.Event` checked at the top of each "
                "worker loop is the clean signal.",
                "Drain the queue after setting the stop event, or workers will block "
                "forever on `get()`. A sentinel per worker also works.",
                "Track concurrency with a counter guarded by a lock if you want to "
                "verify the bound yourself.",
            ),
            solution="""
            import queue
            import threading

            def run_pool(fn, items, workers=4, stop_on_error=False):
                if workers < 1:
                    raise ValueError("workers must be at least 1")

                items = list(items)
                if not items:
                    return [], []

                work = queue.Queue()
                for pair in enumerate(items):
                    work.put(pair)

                slots = [None] * len(items)      # (kind, value) per index
                stop = threading.Event()

                def worker():
                    while True:
                        try:
                            index, item = work.get_nowait()
                        except queue.Empty:
                            return
                        if stop.is_set():
                            work.task_done()
                            continue
                        try:
                            slots[index] = ("ok", fn(item))
                        except Exception as exc:
                            slots[index] = ("error", exc)
                            if stop_on_error:
                                stop.set()
                        finally:
                            work.task_done()

                threads = [threading.Thread(target=worker)
                           for _ in range(min(workers, len(items)))]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                results, errors = [], []
                for item, slot in zip(items, slots):
                    if slot is None:
                        continue                 # never started (stop_on_error)
                    kind, value = slot
                    (results if kind == "ok" else errors).append((item, value))
                return results, errors
            """,
        ),
        Text("""
        ## Takeaways

        - The GIL serialises **bytecode**: threads help I/O, not CPU.
        - Atomic bytecodes ≠ atomic operations. `+=` is a race.
        - Prefer `queue.Queue` over hand-rolled locking.
        - Acquire multiple locks in a consistent global order, always with
          `with`.
        - `concurrent.futures` gives one API for both backends; processes cost
          pickling and start-up, so parallelise chunks.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _tp_order(ns) -> None:
    import random
    import time

    run_pool = ns["run_pool"]

    def slow_square(n):
        time.sleep(random.uniform(0, 0.01))
        return n * n

    results, errors = run_pool(slow_square, [1, 2, 3, 4, 5], workers=5)
    assert errors == [], errors
    assert results == [(1, 1), (2, 4), (3, 9), (4, 16), (5, 25)], results


def _tp_errors(ns) -> None:
    run_pool = ns["run_pool"]

    def maybe_fail(n):
        if n % 2 == 0:
            raise ValueError(f"even: {n}")
        return n

    results, errors = run_pool(maybe_fail, [1, 2, 3, 4], workers=2)
    assert [item for item, _ in results] == [1, 3], results
    assert [item for item, _ in errors] == [2, 4], errors
    assert all(isinstance(exc, ValueError) for _, exc in errors)


def _tp_complete(ns) -> None:
    run_pool = ns["run_pool"]
    items = list(range(20))

    def sometimes(n):
        if n % 3 == 0:
            raise RuntimeError(n)
        return n

    results, errors = run_pool(sometimes, items, workers=4)
    seen = [item for item, _ in results] + [item for item, _ in errors]
    assert sorted(seen) == items, f"missing or duplicated items: {sorted(seen)}"


def _tp_concurrent(ns) -> None:
    import time

    run_pool = ns["run_pool"]

    def sleeper(n):
        time.sleep(0.05)
        return n

    start = time.perf_counter()
    results, errors = run_pool(sleeper, list(range(4)), workers=4)
    elapsed = time.perf_counter() - start
    assert len(results) == 4 and not errors
    assert elapsed < 0.15, (
        f"4 x 50ms with 4 workers took {elapsed*1000:.0f}ms — that is serial"
    )


def _tp_bounded(ns) -> None:
    import threading
    import time

    run_pool = ns["run_pool"]
    active, peak, guard = 0, 0, threading.Lock()

    def tracked(n):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return n

    run_pool(tracked, list(range(12)), workers=3)
    assert peak <= 3, f"{peak} tasks ran at once with workers=3"
    assert peak > 1, f"peak concurrency was {peak} — the pool is running serially"


def _tp_stop(ns) -> None:
    import threading
    import time

    run_pool = ns["run_pool"]
    started = []
    guard = threading.Lock()

    def fail_on_first(n):
        with guard:
            started.append(n)
        if n == 0:
            raise RuntimeError("stop here")
        time.sleep(0.01)
        return n

    results, errors = run_pool(fail_on_first, list(range(30)), workers=2,
                               stop_on_error=True)
    assert len(errors) >= 1, "the failure should be recorded"
    assert len(started) < 30, (
        f"stop_on_error should prevent new work; all {len(started)} items started"
    )
    handled = {item for item, _ in results} | {item for item, _ in errors}
    assert handled <= set(started), "an item was reported without being started"


def _tp_edges(ns) -> None:
    run_pool = ns["run_pool"]
    assert run_pool(lambda x: x, []) == ([], []), "empty input should return two empty lists"
    try:
        run_pool(lambda x: x, [1], workers=0)
    except ValueError:
        return
    raise AssertionError("workers < 1 must raise ValueError")


def _tp_joined(ns) -> None:
    import threading

    run_pool = ns["run_pool"]
    before = threading.active_count()
    run_pool(lambda n: n * 2, list(range(10)), workers=4)
    after = threading.active_count()
    assert after <= before, (
        f"{after - before} thread(s) still alive after run_pool returned — join them"
    )
