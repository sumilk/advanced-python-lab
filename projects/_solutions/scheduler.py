"""Scheduler — reference solution.

The core idea: give every task its own `asyncio.Event`. A task first awaits
the events of its dependencies, *then* acquires a concurrency slot, then
runs. That ordering matters — waiting inside the slot would let blocked tasks
starve runnable ones.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class SchedulerError(Exception):
    """Base for scheduler configuration problems."""


class DuplicateTask(SchedulerError):
    pass


class UnknownDependency(SchedulerError):
    pass


class CyclicDependency(SchedulerError):
    pass


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class Task:
    name: str
    fn: Callable
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    timeout: float | None = None


@dataclass
class RunResult:
    outputs: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, BaseException] = field(default_factory=dict)
    skipped: set[str] = field(default_factory=set)
    duration: float = 0.0

    @property
    def succeeded(self) -> bool:
        return not self.failures

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    def __repr__(self) -> str:
        return (f"RunResult(ok={len(self.outputs)}, failed={len(self.failures)}, "
                f"skipped={len(self.skipped)}, {self.duration:.3f}s)")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
class Scheduler:
    def __init__(self, max_concurrency: int = 4):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.max_concurrency = max_concurrency
        self._tasks: dict[str, Task] = {}
        self._listeners: list[Callable[[str, str, Any], None]] = []

    # -- graph -------------------------------------------------------------
    def add(self, name: str, coro_fn: Callable, *, depends_on: Iterable[str] = (),
            retries: int = 0, timeout: float | None = None) -> Scheduler:
        if name in self._tasks:
            raise DuplicateTask(f"task {name!r} is already registered")
        self._tasks[name] = Task(name, coro_fn, tuple(depends_on), retries, timeout)
        return self

    def on_event(self, callback) -> Scheduler:
        self._listeners.append(callback)
        return self

    def _emit(self, event: str, name: str, detail: Any = None) -> None:
        for listener in self._listeners:
            listener(event, name, detail)

    def _validate(self) -> None:
        for task in self._tasks.values():
            for dependency in task.depends_on:
                if dependency not in self._tasks:
                    raise UnknownDependency(
                        f"task {task.name!r} depends on unknown task {dependency!r}"
                    )

    def order(self) -> list[list[str]]:
        """Kahn's algorithm, emitting one level per parallelisable stage."""
        self._validate()
        remaining = {name: set(task.depends_on) for name, task in self._tasks.items()}
        levels: list[list[str]] = []

        while remaining:
            ready = sorted(n for n, deps in remaining.items() if not deps)
            if not ready:
                raise CyclicDependency(
                    "dependency cycle among: " + ", ".join(sorted(remaining))
                )
            levels.append(ready)
            for name in ready:
                del remaining[name]
            for deps in remaining.values():
                deps.difference_update(ready)
        return levels

    # -- execution ---------------------------------------------------------
    async def run(self, fail_fast: bool = True) -> RunResult:
        self.order()                     # validates: unknown deps and cycles

        result = RunResult()
        started = time.perf_counter()

        done: dict[str, asyncio.Event] = {
            name: asyncio.Event() for name in self._tasks
        }
        blocked: set[str] = set()        # dependency failed or was skipped
        slots = asyncio.Semaphore(self.max_concurrency)
        first_failure = asyncio.Event()

        async def run_one(task: Task) -> None:
            # 1. wait for dependencies (outside the concurrency slot)
            for dependency in task.depends_on:
                await done[dependency].wait()

            if any(d in blocked or d in result.failures for d in task.depends_on):
                blocked.add(task.name)
                result.skipped.add(task.name)
                self._emit("skip", task.name, "dependency failed")
                done[task.name].set()
                return

            if fail_fast and first_failure.is_set():
                blocked.add(task.name)
                result.skipped.add(task.name)
                self._emit("skip", task.name, "run aborted")
                done[task.name].set()
                return

            kwargs = {d: result.outputs[d] for d in task.depends_on}

            # 2. take a slot, then actually run
            async with slots:
                for attempt in range(task.retries + 1):
                    try:
                        self._emit("start", task.name, attempt)
                        if task.timeout is None:
                            value = await task.fn(**kwargs)
                        else:
                            async with asyncio.timeout(task.timeout):
                                value = await task.fn(**kwargs)
                    except asyncio.CancelledError:
                        raise                        # never swallow this
                    except (Exception, TimeoutError) as exc:
                        if attempt < task.retries:
                            self._emit("retry", task.name, attempt + 1)
                            continue
                        result.failures[task.name] = exc
                        self._emit("failure", task.name, exc)
                        first_failure.set()
                        break
                    else:
                        result.outputs[task.name] = value
                        self._emit("success", task.name, value)
                        break
            done[task.name].set()

        runners = [asyncio.create_task(run_one(task), name=task.name)
                   for task in self._tasks.values()]

        try:
            if fail_fast:
                waiter = asyncio.create_task(first_failure.wait())
                pending = set(runners) | {waiter}
                while True:
                    finished, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED
                    )
                    if waiter in finished:
                        break
                    if not (pending - {waiter}):
                        waiter.cancel()
                        break
                # A failure happened (or everything finished). Stop the rest.
                for runner in runners:
                    if not runner.done():
                        runner.cancel()
                await asyncio.gather(*runners, return_exceptions=True)
                if not waiter.done():
                    waiter.cancel()
            else:
                await asyncio.gather(*runners, return_exceptions=True)
        finally:
            for runner in runners:
                if not runner.done():
                    runner.cancel()
            await asyncio.gather(*runners, return_exceptions=True)
            result.duration = time.perf_counter() - started

        # Anything that never produced an output or a failure was cut short.
        for name in self._tasks:
            if name not in result.outputs and name not in result.failures:
                result.skipped.add(name)

        if fail_fast and result.failures:
            raise ExceptionGroup(
                "scheduler run failed", list(result.failures.values())
            )
        return result
