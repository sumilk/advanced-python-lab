# Scheduler — an async DAG task runner

Run a graph of async tasks with declared dependencies: maximum parallelism
where the graph allows it, strict ordering where it does not, plus retries,
timeouts, cancellation and honest failure reporting.

**Lessons drawn on:** 12 (exceptions & groups), 18 (concurrency), 19
(asyncio).

```python
scheduler = Scheduler(max_concurrency=4)
scheduler.add("fetch", fetch_data)
scheduler.add("parse", parse, depends_on=["fetch"])
scheduler.add("report", build_report, depends_on=["parse", "fetch"])

result = await scheduler.run()
result.outputs["report"]
```

## Requirements

### 1. Declaring the graph

- `add(name, coro_fn, *, depends_on=(), retries=0, timeout=None)` returns the
  scheduler so calls can be chained
- a duplicate name raises `DuplicateTask`
- `depends_on` may name a task added later; the graph is only validated at
  `run()`
- a dependency that is never added raises `UnknownDependency` at `run()`
- a cycle raises `CyclicDependency` at `run()`, and the message lists the
  names involved
- `order()` → a list of *levels*: each level is the sorted list of task names
  that may run in parallel at that stage

### 2. Running

`await scheduler.run(fail_fast=True)` → a `RunResult` with:

- `.outputs` — `dict[name, value]` for tasks that completed
- `.failures` — `dict[name, exception]`
- `.skipped` — set of names never started because a dependency failed
- `.succeeded` / `.failed` — booleans
- `.duration` — wall-clock seconds

Semantics:

- a task's callable receives the outputs of its dependencies as keyword
  arguments: `parse(fetch=<output of fetch>)`. A task with no dependencies is
  called with no arguments.
- tasks with satisfied dependencies run **concurrently**, capped by
  `max_concurrency`
- when a task fails, every task that transitively depends on it is
  **skipped**, not failed
- `fail_fast=True` (default): the first failure cancels tasks that are still
  running, and `run()` raises an `ExceptionGroup` of the failures once
  everything has settled
- `fail_fast=False`: independent branches run to completion and `run()`
  returns the `RunResult` with the failures recorded
- `retries=n` retries that task up to `n` extra times before recording a
  failure
- `timeout=s` cancels that task after `s` seconds and records `TimeoutError`
- a task cancelled from outside must propagate `asyncio.CancelledError`, not
  swallow it
- no task may still be running when `run()` returns

### 3. Observability

- `on_event(callback)` registers `callback(event, name, detail)` where
  `event` is one of `"start" | "success" | "failure" | "retry" | "skip"`
- events fire in real time, not at the end

## Grading

```bash
uv run learn.py projects test scheduler
```

## Hints

- Kahn's algorithm gives you both the level ordering and cycle detection:
  repeatedly take every node with in-degree zero as one level. Whatever is
  left over when no node has in-degree zero *is* the cycle.
- Run one level at a time with a `TaskGroup` — but that serialises at the
  level boundary. For real parallelism, start each task as soon as its
  dependencies are done: give every task an `asyncio.Event` and have it await
  its dependencies' events first.
- An `asyncio.Semaphore(max_concurrency)` acquired *after* the dependency
  wait keeps a blocked task from occupying a slot.
- Wrap each task body in try/except so a failure sets its event (marked
  failed) instead of hanging the dependents forever.
- Re-raise `asyncio.CancelledError` from every handler; catching it with
  `except Exception` will not work — it derives from `BaseException`.
- `asyncio.timeout(s)` (3.11+) is cleaner than `wait_for` when you also need
  retries around it.
