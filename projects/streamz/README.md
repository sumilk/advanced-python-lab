# Streamz — a lazy data pipeline

A composable streaming toolkit. Every stage is lazy, the whole pipeline makes
a **single pass** over the source, and memory stays O(1) in the length of the
stream regardless of how many stages you chain.

**Lessons drawn on:** 04 (comprehensions & laziness), 05 (iterators &
generators), 15 (itertools).

## What you are building

```python
result = (Stream.of(range(1000))
          .map(lambda n: n * 3)
          .filter(lambda n: n % 2 == 0)
          .distinct()
          .take(5)
          .to_list())

Stream.of(records).group_by(lambda r: r["dept"])      # {dept: [records]}
Stream.of(numbers).window(3).map(sum).to_list()       # rolling sums
```

## Requirements

### 1. `Stream` is a lazy, single-use wrapper

- `Stream.of(iterable)` — build one; `Stream.counter(start=0, step=1)` —
  infinite (named `counter` so the instance method `count()` can be the
  terminal 'how many items')
- `Stream.repeat(value, times=None)` — infinite unless `times` is given
- constructing a Stream and chaining stages must consume **nothing**
- a Stream is an iterator: `iter(s) is s`, and it works in a `for` loop
- consuming it twice raises `StreamConsumed` (a `RuntimeError`) — no silent
  empty results
- `Stream` supports `|` for composition: `stream | stage_fn` where `stage_fn`
  takes an iterator and returns an iterator

### 2. Transformations — all lazy, all returning a new `Stream`

| method | behaviour |
|---|---|
| `map(fn)` | apply `fn` to each item |
| `filter(pred)` | keep truthy |
| `reject(pred)` | drop truthy |
| `flat_map(fn)` | apply `fn`, flatten one level |
| `take(n)` / `drop(n)` | first n / skip n |
| `take_while(pred)` / `drop_while(pred)` | as `itertools` |
| `distinct(key=None)` | first occurrence only, order preserved |
| `enumerate(start=0)` | yields `(index, item)` |
| `window(n)` | tuples of n consecutive items, sliding by one |
| `chunk(n)` | non-overlapping tuples; a short final chunk is kept |
| `peek(fn)` | call `fn(item)` for its side effect, yield item unchanged |
| `scan(fn, initial)` | running fold; yields each intermediate value |
| `zip_with(other)` | pair with another iterable, stopping at the shorter |
| `map_safe(fn, on_error=None)` | like `map`, but an item whose transform raises is skipped and `on_error(exc, item)` is called |

### 3. Terminals — these consume the stream

`to_list()`, `to_tuple()`, `to_set()`, `first(default=None)`, `last(default=None)`,
`count()`, `sum()`, `min(key=None)`, `max(key=None)`, `reduce(fn, initial)`,
`any(pred)`, `all(pred)`, `for_each(fn)`, `group_by(key)` →
`dict[key, list]` in first-appearance order, `partition(pred)` →
`(matching, not_matching)` as two lists.

`min`/`max` on an empty stream return `None`; `sum` returns 0; `count`
returns 0.

### 4. Laziness is the point

- `Stream.counter().map(f).filter(g).take(3).to_list()` must terminate
- a pipeline over an infinite source with `take(k)` must call each stage at
  most `k + O(1)` times — no computing ahead
- `window` and `chunk` must not buffer more than `n` items
- `distinct` is allowed to remember the keys it has seen; nothing else may
  accumulate

## Grading

```bash
uv run learn.py projects test streamz
```

## Hints

- Every transformation is `return Stream(<generator expression over self._it>)`.
  Keep the generator lazy: no `list()` anywhere in a transformation.
- Guard consumption with a `_consumed` flag set by the terminal operations
  and by `__next__`; raise `StreamConsumed` when a second consumer arrives.
- `window` is a `deque(maxlen=n)`; yield `tuple(window)` only once it is full.
- `scan` is `itertools.accumulate` with an initial value — but write it
  yourself, it is four lines.
- `map_safe` must catch **inside the mapping stage**. It cannot be a
  separate downstream stage: once a generator lets an exception escape it is
  finished, so there is nothing left to resume (lesson 05).
- `__iter__` needs to stay idempotent while a loop is running — `iter(s)`
  followed by `for x in s` is one consumer, not two.
