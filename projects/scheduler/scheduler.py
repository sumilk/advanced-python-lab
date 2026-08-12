"""Scheduler — an async DAG task runner.

Read README.md in this directory for the full specification.

    uv run learn.py projects test scheduler
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


class SchedulerError(Exception):
    """Base for scheduler configuration problems."""


class DuplicateTask(SchedulerError):
    pass


class UnknownDependency(SchedulerError):
    pass


class CyclicDependency(SchedulerError):
    pass


@dataclass
class RunResult:
    outputs: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)
    skipped: set = field(default_factory=set)
    duration: float = 0.0

    @property
    def succeeded(self) -> bool:
        ...

    @property
    def failed(self) -> bool:
        ...


class Scheduler:
    def __init__(self, max_concurrency: int = 4):
        ...

    def add(self, name, coro_fn, *, depends_on=(), retries=0, timeout=None):
        """Register a task. Returns self so calls chain."""
        ...

    def on_event(self, callback):
        """callback(event, name, detail) for start/success/failure/retry/skip."""
        ...

    def order(self):
        """-> list of levels; raises UnknownDependency / CyclicDependency."""
        ...

    async def run(self, fail_fast: bool = True) -> RunResult:
        ...
