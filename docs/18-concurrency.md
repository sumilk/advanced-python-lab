# 18 — Threads, Processes, and the GIL

Choosing wrongly between threads and processes is the most expensive
mistake in Python performance work. This lesson explains what the GIL
actually locks, measures the difference on both I/O-bound and CPU-bound
work, covers the synchronisation primitives and the races they prevent,
and shows the `concurrent.futures` API you should normally reach for.

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

```python
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
```

```python
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
```

**Quiz.** Your function spends 95% of its time in `requests.get`. Threads or processes?

- a) Processes — always faster
- b) Threads — the GIL is released during I/O, and they are far cheaper than processes
- c) Neither; Python cannot do concurrent I/O
- d) It makes no difference

<details><summary>answer</summary>

**b** — For I/O-bound work, threads (or asyncio) win: no pickling, no process start-up, shared memory. Processes are for CPU-bound work.
</details>

## Races: why "one bytecode at a time" is not enough

`counter += 1` is *at least* a load, an add, and a store. A thread
switch between the load and the store loses an update. The GIL
guarantees each bytecode is atomic; it guarantees nothing about your
logical operations.

```python
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
```
Note we shortened the switch interval to make the loss reliable —
with the default 5 ms you might see the correct answer on a small
loop and ship a broken program. Races are not reproducible; that
is what makes them dangerous.

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

```python
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
```

```python
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
```
The sentinel-per-consumer trick is the standard clean shutdown. The
alternative — `queue.join()` plus daemon threads — leaks threads at
exit. Note `task_done()` in a `finally`, so an exception in the
body cannot hang `join()` forever.


## Deadlock, and how to avoid it

Two locks acquired in opposite orders by two threads is all it takes.
Rules that actually work:

1. **Always acquire locks in a globally consistent order.**
2. Use `with lock:` so an exception cannot skip the release.
3. Prefer `acquire(timeout=...)` in code that must not hang.
4. Better: avoid multiple locks — use a queue or a single coarse lock.

```python
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
```

## `concurrent.futures`: the API to reach for

One interface, two backends. Swap `ThreadPoolExecutor` for
`ProcessPoolExecutor` and the code is unchanged.

- `submit(fn, *args)` → a `Future`
- `map(fn, iterable)` → results **in input order**, lazily
- `as_completed(futures)` → results as they finish
- exceptions surface when you call `future.result()`

```python
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
```
`pool.map` swallows nothing: the exception is raised when you reach
that element while iterating. If you need per-item error handling,
use `submit` + `as_completed` as above.

```python
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
```
Two lessons in one demo. The `PicklingError` is not a bug — the
worker receives *"import this name from this module"*, and a
function defined inside another scope has no such name.

Costs to weigh: arguments and results are **pickled** (that
factorial result is a 250 KB integer travelling back through a
pipe), process start-up is tens of milliseconds, and on
macOS/Windows the default `spawn` method re-imports your module in
every worker. Parallelise chunks of work, not tiny calls.

**Quiz.** Why must functions passed to `ProcessPoolExecutor` be defined at module level?

- a) For readability
- b) They are pickled by reference (module + qualname), and lambdas/closures cannot be pickled
- c) Because processes cannot execute nested functions
- d) They do not need to be

<details><summary>answer</summary>

**b** — `pickle` stores a function as 'look up this name in this module'. A lambda or a closure has no importable name, hence `PicklingError`. `multiprocessing` can use `dill` via third-party libraries to work around it.
</details>

## Exercise — A bounded worker pool with results and errors `[tricky]`

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
```python
import queue
import threading


def run_pool(fn, items, workers=4, stop_on_error=False):
    ...
```

## Takeaways

- The GIL serialises **bytecode**: threads help I/O, not CPU.
- Atomic bytecodes ≠ atomic operations. `+=` is a race.
- Prefer `queue.Queue` over hand-rolled locking.
- Acquire multiple locks in a consistent global order, always with
  `with`.
- `concurrent.futures` gives one API for both backends; processes cost
  pickling and start-up, so parallelise chunks.
