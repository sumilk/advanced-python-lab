"""Streamz — reference solution.

The whole design is one idea: a Stream owns an iterator, and every
transformation returns a *new* Stream wrapping a generator over the old one.
Nothing runs until a terminal method pulls.
"""
from __future__ import annotations

import itertools
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from typing import Any


class StreamConsumed(RuntimeError):
    """Raised when a stream is iterated a second time."""


_MISSING = object()


class Stream:
    __slots__ = ("_it", "_consumed", "_iterating")

    def __init__(self, iterable: Iterable):
        self._it: Iterator = iter(iterable)
        self._consumed = False
        self._iterating = False

    # -- construction ------------------------------------------------------
    @classmethod
    def of(cls, iterable: Iterable) -> Stream:
        return cls(iterable)

    @classmethod
    def counter(cls, start: int = 0, step: int = 1) -> Stream:
        """An infinite arithmetic stream. Named `counter` so that `count()`
        can be the terminal 'how many items' operation."""
        return cls(itertools.count(start, step))

    @classmethod
    def repeat(cls, value: Any, times: int | None = None) -> Stream:
        return cls(itertools.repeat(value) if times is None
                   else itertools.repeat(value, times))

    # -- protocol ----------------------------------------------------------
    def __iter__(self) -> Stream:
        # Idempotent while a loop is in progress: `iter(s) is s` followed by
        # `for x in s` must not look like a second consumer.
        if not self._iterating:
            self._claim()
            self._iterating = True
        return self

    def __next__(self):
        try:
            return next(self._it)
        except StopIteration:
            self._iterating = False      # the loop is over; no restarts
            raise

    def __or__(self, stage: Callable[[Iterator], Iterable]) -> Stream:
        return Stream(stage(self._take_iter()))

    def _claim(self) -> None:
        """Take ownership of this stream, refusing a second consumer."""
        if self._consumed:
            raise StreamConsumed("this stream has already been consumed")
        self._consumed = True

    def _take_iter(self) -> Iterator:
        """Hand the underlying iterator downstream, exactly once, and detach
        it so a stray `next()` on this object cannot steal an item."""
        self._claim()
        source, self._it = self._it, iter(())
        return source

    # -- transformations (lazy) -------------------------------------------
    def map(self, fn) -> Stream:
        source = self._take_iter()
        return Stream(fn(item) for item in source)

    def filter(self, pred) -> Stream:
        source = self._take_iter()
        return Stream(item for item in source if pred(item))

    def reject(self, pred) -> Stream:
        source = self._take_iter()
        return Stream(item for item in source if not pred(item))

    def flat_map(self, fn) -> Stream:
        source = self._take_iter()
        return Stream(inner for item in source for inner in fn(item))

    def take(self, n) -> Stream:
        return Stream(itertools.islice(self._take_iter(), n))

    def drop(self, n) -> Stream:
        return Stream(itertools.islice(self._take_iter(), n, None))

    def take_while(self, pred) -> Stream:
        return Stream(itertools.takewhile(pred, self._take_iter()))

    def drop_while(self, pred) -> Stream:
        return Stream(itertools.dropwhile(pred, self._take_iter()))

    def distinct(self, key=None) -> Stream:
        source = self._take_iter()

        def generate():
            seen = set()
            for item in source:
                marker = item if key is None else key(item)
                if marker not in seen:
                    seen.add(marker)
                    yield item

        return Stream(generate())

    def enumerate(self, start: int = 0) -> Stream:
        return Stream(enumerate(self._take_iter(), start))

    def window(self, n: int) -> Stream:
        if n < 1:
            raise ValueError("window size must be at least 1")
        source = self._take_iter()

        def generate():
            buffer = deque(maxlen=n)
            for item in source:
                buffer.append(item)
                if len(buffer) == n:
                    yield tuple(buffer)

        return Stream(generate())

    def chunk(self, n: int) -> Stream:
        if n < 1:
            raise ValueError("chunk size must be at least 1")
        source = self._take_iter()

        def generate():
            buffer = []
            for item in source:
                buffer.append(item)
                if len(buffer) == n:
                    yield tuple(buffer)
                    buffer = []
            if buffer:
                yield tuple(buffer)

        return Stream(generate())

    def peek(self, fn) -> Stream:
        source = self._take_iter()

        def generate():
            for item in source:
                fn(item)
                yield item

        return Stream(generate())

    def scan(self, fn, initial) -> Stream:
        source = self._take_iter()

        def generate():
            accumulator = initial
            for item in source:
                accumulator = fn(accumulator, item)
                yield accumulator

        return Stream(generate())

    def zip_with(self, other) -> Stream:
        return Stream(zip(self._take_iter(), other))

    def map_safe(self, fn, on_error=None) -> Stream:
        """map(), but an item whose transform raises is skipped.

        Note this *has* to be part of the mapping stage: once a generator
        lets an exception escape, that generator is finished for good. A
        downstream "catch errors" stage could never resume it.
        """
        source = self._take_iter()

        def generate():
            for item in source:
                try:
                    yield fn(item)
                except Exception as exc:                 # noqa: BLE001
                    if on_error is not None:
                        on_error(exc, item)

        return Stream(generate())

    # -- terminals (consume) ----------------------------------------------
    def to_list(self) -> list:
        return list(self._take_iter())

    def to_tuple(self) -> tuple:
        return tuple(self._take_iter())

    def to_set(self) -> set:
        return set(self._take_iter())

    def first(self, default=None):
        return next(self._take_iter(), default)

    def last(self, default=None):
        result = default
        for item in self._take_iter():
            result = item
        return result

    def count(self) -> int:
        return sum(1 for _ in self._take_iter())

    def sum(self):
        return sum(self._take_iter())

    def min(self, key=None):
        return min(self._take_iter(), key=key, default=None)

    def max(self, key=None):
        return max(self._take_iter(), key=key, default=None)

    def reduce(self, fn, initial=_MISSING):
        import functools

        source = self._take_iter()
        if initial is _MISSING:
            return functools.reduce(fn, source)
        return functools.reduce(fn, source, initial)

    def any(self, pred=bool) -> bool:
        return any(pred(item) for item in self._take_iter())

    def all(self, pred=bool) -> bool:
        return all(pred(item) for item in self._take_iter())

    def for_each(self, fn) -> None:
        for item in self._take_iter():
            fn(item)

    def group_by(self, key) -> dict:
        groups: dict = {}
        for item in self._take_iter():
            groups.setdefault(key(item), []).append(item)
        return groups

    def partition(self, pred) -> tuple[list, list]:
        matching, other = [], []
        for item in self._take_iter():
            (matching if pred(item) else other).append(item)
        return matching, other

    def __repr__(self) -> str:
        state = "consumed" if self._consumed else "ready"
        return f"<Stream {state}>"
