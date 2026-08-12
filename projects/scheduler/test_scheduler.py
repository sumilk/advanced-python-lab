"""Grading suite for the Scheduler capstone.

    uv run learn.py projects test scheduler
"""
from __future__ import annotations

import asyncio

import pytest

from conftest import load

pytestmark = pytest.mark.project

sched = load("scheduler")


def run(coro):
    return asyncio.run(coro)


def make(max_concurrency=4):
    return sched.Scheduler(max_concurrency=max_concurrency)


async def value(v, delay=0.0):
    if delay:
        await asyncio.sleep(delay)
    return v


class Boom(Exception):
    pass


# ---------------------------------------------------------------------------
# Graph construction and validation
# ---------------------------------------------------------------------------
class TestGraph:
    def test_add_is_chainable(self):
        s = make()
        assert s.add("a", lambda: value(1)) is s

    def test_duplicate_task(self):
        s = make().add("a", lambda: value(1))
        with pytest.raises(sched.DuplicateTask):
            s.add("a", lambda: value(2))

    def test_unknown_dependency(self):
        s = make().add("a", lambda: value(1), depends_on=["ghost"])
        with pytest.raises(sched.UnknownDependency):
            s.order()

    def test_cycle_detected_and_named(self):
        s = (make()
             .add("a", lambda **k: value(1), depends_on=["c"])
             .add("b", lambda **k: value(2), depends_on=["a"])
             .add("c", lambda **k: value(3), depends_on=["b"]))
        with pytest.raises(sched.CyclicDependency) as info:
            s.order()
        message = str(info.value)
        assert all(name in message for name in "abc"), message

    def test_self_dependency_is_a_cycle(self):
        s = make().add("a", lambda **k: value(1), depends_on=["a"])
        with pytest.raises(sched.CyclicDependency):
            s.order()

    def test_order_levels(self):
        s = (make()
             .add("fetch", lambda: value(1))
             .add("also", lambda: value(2))
             .add("parse", lambda **k: value(3), depends_on=["fetch"])
             .add("report", lambda **k: value(4), depends_on=["parse", "also"]))
        assert s.order() == [["also", "fetch"], ["parse"], ["report"]]

    def test_order_of_independent_tasks_is_one_level(self):
        s = make()
        for name in "abc":
            s.add(name, lambda: value(1))
        assert s.order() == [["a", "b", "c"]]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
class TestExecution:
    def test_runs_and_collects_outputs(self):
        s = (make()
             .add("a", lambda: value(1))
             .add("b", lambda **k: value(k["a"] + 1), depends_on=["a"]))
        result = run(s.run())
        assert result.outputs == {"a": 1, "b": 2}
        assert result.succeeded is True
        assert result.failures == {}

    def test_dependencies_arrive_as_keyword_arguments(self):
        seen = {}

        async def collector(**kwargs):
            seen.update(kwargs)
            return "done"

        s = (make()
             .add("x", lambda: value(10))
             .add("y", lambda: value(20))
             .add("z", collector, depends_on=["x", "y"]))
        run(s.run())
        assert seen == {"x": 10, "y": 20}, seen

    def test_a_task_with_no_dependencies_takes_no_arguments(self):
        async def no_args():
            return "ok"

        result = run(make().add("solo", no_args).run())
        assert result.outputs == {"solo": "ok"}

    def test_ordering_is_respected(self):
        order = []

        def step(name):
            async def run_step(**kwargs):
                order.append(name)
                await asyncio.sleep(0.01)
                return name
            return run_step

        s = (make()
             .add("first", step("first"))
             .add("second", step("second"), depends_on=["first"])
             .add("third", step("third"), depends_on=["second"]))
        run(s.run())
        assert order == ["first", "second", "third"]

    def test_independent_tasks_run_concurrently(self):
        async def slow(**kwargs):
            await asyncio.sleep(0.05)
            return 1

        s = make(max_concurrency=4)
        for name in "abcd":
            s.add(name, slow)
        result = run(s.run())
        assert result.duration < 0.15, (
            f"4 x 50ms with concurrency 4 took {result.duration:.2f}s — that is serial"
        )

    def test_max_concurrency_is_respected(self):
        state = {"active": 0, "peak": 0}

        async def tracked(**kwargs):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.02)
            state["active"] -= 1
            return 1

        s = make(max_concurrency=2)
        for i in range(6):
            s.add(f"t{i}", tracked)
        run(s.run())
        assert state["peak"] <= 2, f"peak concurrency was {state['peak']}, limit was 2"
        assert state["peak"] > 1, "nothing ran concurrently"

    def test_diamond_runs_the_middle_in_parallel(self):
        state = {"active": 0, "peak": 0}

        async def tracked(**kwargs):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.02)
            state["active"] -= 1
            return 1

        s = (make(max_concurrency=4)
             .add("top", tracked)
             .add("left", tracked, depends_on=["top"])
             .add("right", tracked, depends_on=["top"])
             .add("bottom", tracked, depends_on=["left", "right"]))
        result = run(s.run())
        assert result.outputs.keys() == {"top", "left", "right", "bottom"}
        assert state["peak"] == 2, f"left and right should overlap, peak={state['peak']}"


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------
class TestFailures:
    def test_fail_fast_raises_an_exception_group(self):
        async def bad(**kwargs):
            raise Boom("nope")

        s = make().add("a", bad)
        with pytest.raises(ExceptionGroup) as info:
            run(s.run())
        assert any(isinstance(e, Boom) for e in info.value.exceptions)

    def test_dependents_are_skipped_not_failed(self):
        async def bad(**kwargs):
            raise Boom("nope")

        s = (make()
             .add("a", bad)
             .add("b", lambda **k: value(1), depends_on=["a"])
             .add("c", lambda **k: value(2), depends_on=["b"]))
        result = run(s.run(fail_fast=False))
        assert set(result.failures) == {"a"}
        assert result.skipped == {"b", "c"}, result.skipped
        assert result.outputs == {}

    def test_independent_branch_survives_without_fail_fast(self):
        async def bad(**kwargs):
            raise Boom("nope")

        s = (make()
             .add("bad", bad)
             .add("good", lambda: value("fine"))
             .add("after_bad", lambda **k: value(1), depends_on=["bad"]))
        result = run(s.run(fail_fast=False))
        assert result.outputs == {"good": "fine"}
        assert set(result.failures) == {"bad"}
        assert result.skipped == {"after_bad"}
        assert result.failed is True

    def test_fail_fast_stops_running_work(self):
        finished = []

        async def bad(**kwargs):
            await asyncio.sleep(0.01)
            raise Boom("nope")

        async def slow(**kwargs):
            await asyncio.sleep(0.5)
            finished.append(1)
            return 1

        s = make(max_concurrency=4).add("bad", bad)
        for i in range(3):
            s.add(f"slow{i}", slow)

        with pytest.raises(ExceptionGroup):
            run(s.run(fail_fast=True))
        assert finished == [], "still-running tasks should have been cancelled"

    def test_retries(self):
        attempts = []

        async def flaky(**kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise Boom("again")
            return "recovered"

        s = make().add("a", flaky, retries=2)
        result = run(s.run())
        assert result.outputs == {"a": "recovered"}
        assert len(attempts) == 3

    def test_retries_exhausted(self):
        attempts = []

        async def always(**kwargs):
            attempts.append(1)
            raise Boom("never")

        s = make().add("a", always, retries=2)
        result = run(s.run(fail_fast=False))
        assert len(attempts) == 3
        assert isinstance(result.failures["a"], Boom)

    def test_timeout(self):
        async def slow(**kwargs):
            await asyncio.sleep(5)
            return "too late"

        s = make().add("a", slow, timeout=0.05)
        result = run(s.run(fail_fast=False))
        assert "a" in result.failures
        assert isinstance(result.failures["a"], TimeoutError), (
            f"expected TimeoutError, got {type(result.failures['a']).__name__}"
        )
        assert result.duration < 1.0, "the task was not actually cancelled"

    def test_no_tasks_left_running(self):
        async def bad(**kwargs):
            raise Boom("x")

        async def main():
            s = make().add("bad", bad).add("slow", lambda: value(1, 0.2))
            try:
                await s.run(fail_fast=True)
            except ExceptionGroup:
                pass
            await asyncio.sleep(0)
            return [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

        assert run(main()) == [], "tasks were left running after run() returned"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
class TestEvents:
    def test_lifecycle_events(self):
        events = []
        s = (make()
             .add("a", lambda: value(1))
             .add("b", lambda **k: value(2), depends_on=["a"]))
        s.on_event(lambda event, name, detail: events.append((event, name)))
        run(s.run())
        kinds = [e for e, _ in events]
        assert kinds.count("start") == 2
        assert kinds.count("success") == 2
        assert ("start", "a") in events and ("success", "b") in events

    def test_failure_and_skip_events(self):
        events = []

        async def bad(**kwargs):
            raise Boom("x")

        s = (make()
             .add("a", bad)
             .add("b", lambda **k: value(1), depends_on=["a"]))
        s.on_event(lambda event, name, detail: events.append((event, name)))
        run(s.run(fail_fast=False))
        assert ("failure", "a") in events, events
        assert ("skip", "b") in events, events

    def test_retry_events(self):
        events = []
        attempts = []

        async def flaky(**kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                raise Boom("again")
            return 1

        s = make().add("a", flaky, retries=1)
        s.on_event(lambda event, name, detail: events.append(event))
        run(s.run())
        assert "retry" in events, events
