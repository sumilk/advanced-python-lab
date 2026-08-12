"""Grading suite for the Streamz capstone.

    uv run learn.py projects test streamz
"""
from __future__ import annotations

import itertools

import pytest

from conftest import load

pytestmark = pytest.mark.project

sz = load("streamz")
Stream = getattr(sz, "Stream", None)


@pytest.fixture(autouse=True)
def _implemented():
    if Stream is None:
        pytest.fail("streamz: Stream is not defined yet")


# ---------------------------------------------------------------------------
# Construction and protocol
# ---------------------------------------------------------------------------
class TestProtocol:
    def test_of_and_to_list(self):
        assert Stream.of([1, 2, 3]).to_list() == [1, 2, 3]
        assert Stream.of("abc").to_list() == ["a", "b", "c"]
        assert Stream.of([]).to_list() == []

    def test_counter_is_infinite(self):
        assert Stream.counter().take(4).to_list() == [0, 1, 2, 3]
        assert Stream.counter(10, 5).take(3).to_list() == [10, 15, 20]

    def test_repeat(self):
        assert Stream.repeat("x", 3).to_list() == ["x", "x", "x"]
        assert Stream.repeat("y").take(2).to_list() == ["y", "y"]

    def test_is_its_own_iterator(self):
        s = Stream.of([1, 2])
        assert iter(s) is s
        assert [x for x in s] == [1, 2]

    def test_second_consumption_raises(self):
        s = Stream.of([1, 2, 3])
        assert s.to_list() == [1, 2, 3]
        with pytest.raises(sz.StreamConsumed):
            s.to_list()

    def test_reusing_an_already_piped_stream_raises(self):
        s = Stream.of([1, 2, 3])
        s.map(lambda n: n)
        with pytest.raises(sz.StreamConsumed):
            s.to_list()

    def test_iterating_twice_raises(self):
        s = Stream.of([1, 2])
        list(s)
        with pytest.raises(sz.StreamConsumed):
            list(s)

    def test_pipe_operator(self):
        def evens(iterator):
            return (x for x in iterator if x % 2 == 0)

        assert (Stream.of(range(6)) | evens).to_list() == [0, 2, 4]


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------
class TestTransformations:
    def test_map_filter_reject(self):
        assert Stream.of(range(5)).map(lambda n: n * 2).to_list() == [0, 2, 4, 6, 8]
        assert Stream.of(range(6)).filter(lambda n: n % 2).to_list() == [1, 3, 5]
        assert Stream.of(range(6)).reject(lambda n: n % 2).to_list() == [0, 2, 4]

    def test_flat_map(self):
        got = Stream.of([[1, 2], [3], []]).flat_map(lambda xs: xs).to_list()
        assert got == [1, 2, 3]
        assert Stream.of("ab").flat_map(lambda c: c * 2).to_list() == ["a", "a", "b", "b"]

    def test_take_and_drop(self):
        assert Stream.of(range(6)).take(2).to_list() == [0, 1]
        assert Stream.of(range(6)).drop(4).to_list() == [4, 5]
        assert Stream.of(range(3)).take(10).to_list() == [0, 1, 2]
        assert Stream.of(range(3)).drop(10).to_list() == []

    def test_take_while_drop_while(self):
        assert Stream.of([1, 2, 9, 1]).take_while(lambda n: n < 5).to_list() == [1, 2]
        assert Stream.of([1, 2, 9, 1]).drop_while(lambda n: n < 5).to_list() == [9, 1]

    def test_distinct(self):
        assert Stream.of([1, 2, 1, 3, 2]).distinct().to_list() == [1, 2, 3]
        got = Stream.of(["a", "A", "b"]).distinct(key=str.lower).to_list()
        assert got == ["a", "b"]

    def test_enumerate(self):
        assert Stream.of("ab").enumerate().to_list() == [(0, "a"), (1, "b")]
        assert Stream.of("ab").enumerate(1).to_list() == [(1, "a"), (2, "b")]

    def test_window(self):
        assert Stream.of(range(5)).window(3).to_list() == [
            (0, 1, 2), (1, 2, 3), (2, 3, 4)
        ]
        assert Stream.of([1, 2]).window(3).to_list() == [], (
            "a stream shorter than the window yields nothing"
        )
        assert Stream.of([1, 2]).window(1).to_list() == [(1,), (2,)]

    def test_chunk(self):
        assert Stream.of(range(5)).chunk(2).to_list() == [(0, 1), (2, 3), (4,)]
        assert Stream.of(range(4)).chunk(2).to_list() == [(0, 1), (2, 3)]
        assert Stream.of([]).chunk(2).to_list() == []

    def test_peek_is_transparent(self):
        seen = []
        got = Stream.of([1, 2, 3]).peek(seen.append).map(lambda n: n * 10).to_list()
        assert got == [10, 20, 30]
        assert seen == [1, 2, 3]

    def test_scan(self):
        assert Stream.of([1, 2, 3]).scan(lambda a, b: a + b, 0).to_list() == [1, 3, 6]
        assert Stream.of([]).scan(lambda a, b: a + b, 0).to_list() == []

    def test_zip_with(self):
        assert Stream.of([1, 2, 3]).zip_with("ab").to_list() == [(1, "a"), (2, "b")]

    def test_map_safe_skips_the_bad_item(self):
        errors = []

        def risky(n):
            if n == 2:
                raise ValueError("bad")
            return n * 10

        got = Stream.of([1, 2, 3]).map_safe(
            risky, on_error=lambda exc, item: errors.append((exc, item))
        ).to_list()
        assert got == [10, 30], f"the failing item should be skipped, got {got}"
        assert len(errors) == 1
        exc, item = errors[0]
        assert isinstance(exc, ValueError) and item == 2

    def test_map_safe_without_a_handler(self):
        got = Stream.of([1, 0, 2]).map_safe(lambda n: 10 // n).to_list()
        assert got == [10, 5], got

    def test_map_safe_stays_lazy(self):
        got = Stream.counter().map_safe(lambda n: 10 // n).take(2).to_list()
        assert got == [10, 5], got

    def test_long_chain(self):
        got = (Stream.of(range(100))
               .map(lambda n: n * 3)
               .filter(lambda n: n % 2 == 0)
               .distinct()
               .take(5)
               .to_list())
        assert got == [0, 6, 12, 18, 24], got


# ---------------------------------------------------------------------------
# Terminals
# ---------------------------------------------------------------------------
class TestTerminals:
    def test_collections(self):
        assert Stream.of([1, 2]).to_tuple() == (1, 2)
        assert Stream.of([1, 2, 1]).to_set() == {1, 2}

    def test_first_and_last(self):
        assert Stream.of([1, 2, 3]).first() == 1
        assert Stream.of([1, 2, 3]).last() == 3
        assert Stream.of([]).first() is None
        assert Stream.of([]).last("none") == "none"
        assert Stream.counter().first() == 0, "first() must not consume the whole stream"

    def test_aggregates(self):
        assert Stream.of([1, 2, 3]).count() == 3
        assert Stream.of([1, 2, 3]).sum() == 6
        assert Stream.of([3, 1, 2]).min() == 1
        assert Stream.of([3, 1, 2]).max() == 3
        assert Stream.of(["bb", "a"]).min(key=len) == "a"

    def test_empty_aggregates(self):
        assert Stream.of([]).count() == 0
        assert Stream.of([]).sum() == 0
        assert Stream.of([]).min() is None
        assert Stream.of([]).max() is None

    def test_reduce(self):
        assert Stream.of([1, 2, 3]).reduce(lambda a, b: a * b, 1) == 6
        assert Stream.of([]).reduce(lambda a, b: a + b, 100) == 100

    def test_any_all(self):
        assert Stream.of([0, 1]).any() is True
        assert Stream.of([0, 0]).any() is False
        assert Stream.of([1, 2]).all(lambda n: n > 0) is True
        assert Stream.of([1, -1]).all(lambda n: n > 0) is False

    def test_for_each(self):
        collected = []
        Stream.of([1, 2]).for_each(collected.append)
        assert collected == [1, 2]

    def test_group_by_preserves_first_appearance(self):
        rows = [
            {"dept": "ops", "n": 1},
            {"dept": "eng", "n": 2},
            {"dept": "ops", "n": 3},
        ]
        groups = Stream.of(rows).group_by(lambda r: r["dept"])
        assert list(groups) == ["ops", "eng"], list(groups)
        assert [r["n"] for r in groups["ops"]] == [1, 3]

    def test_partition(self):
        evens, odds = Stream.of(range(5)).partition(lambda n: n % 2 == 0)
        assert evens == [0, 2, 4] and odds == [1, 3]


# ---------------------------------------------------------------------------
# Laziness — the whole point
# ---------------------------------------------------------------------------
class TestLaziness:
    def test_building_a_pipeline_computes_nothing(self):
        calls = []
        (Stream.of([1, 2, 3])
         .map(lambda n: calls.append(n) or n)
         .filter(lambda n: True)
         .window(2))
        assert calls == [], f"{len(calls)} items were computed before a terminal ran"

    def test_terminates_on_an_infinite_source(self):
        got = (Stream.counter()
               .map(lambda n: n * n)
               .filter(lambda n: n % 3 == 0)
               .take(3)
               .to_list())
        assert got == [0, 9, 36], got

    def test_take_pulls_only_what_it_needs(self):
        pulled = []

        def source():
            for i in itertools.count():
                pulled.append(i)
                yield i

        Stream.of(source()).map(lambda n: n).take(3).to_list()
        assert len(pulled) <= 4, (
            f"pulled {len(pulled)} items to produce 3 — a stage is not lazy"
        )

    def test_window_does_not_buffer_the_stream(self):
        got = Stream.counter().window(3).take(2).to_list()
        assert got == [(0, 1, 2), (1, 2, 3)], got

    def test_chunk_is_lazy(self):
        got = Stream.counter().chunk(2).take(2).to_list()
        assert got == [(0, 1), (2, 3)], got

    def test_single_pass_over_the_source(self):
        source = iter([1, 2, 3, 4])
        assert Stream.of(source).filter(lambda n: n % 2).to_list() == [1, 3]
        assert list(source) == [], "the source iterator should be fully consumed once"

    def test_first_short_circuits_a_long_chain(self):
        calls = []
        result = (Stream.counter()
                  .peek(calls.append)
                  .map(lambda n: n + 100)
                  .first())
        assert result == 100
        assert len(calls) <= 2, f"first() pulled {len(calls)} items"
