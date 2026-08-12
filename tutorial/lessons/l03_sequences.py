"""Lesson 03 — Sequences, slicing, and the container zoo."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=3,
    slug="sequences",
    title="Sequences, Slicing, and Containers",
    summary="""
    Choosing the right container is the cheapest performance work you will
    ever do. This lesson covers slicing in full (including assignment and
    deletion), sorting with keys, how dicts and sets really work, and the
    `collections` types that solve problems you have been solving by hand.
    """,
    tags=("containers", "slicing", "sorting", "complexity"),
    blocks=[
        Text("""
        ## Slicing: `seq[start:stop:step]`

        - `start` is inclusive, `stop` exclusive — so `len(s[a:b]) == b - a`
        - omitted values mean "from the beginning" / "to the end"
        - negative indices count from the right; `-1` is the last item
        - out-of-range slice bounds are **clamped**, not an error (unlike
          out-of-range indexing)
        - a slice of a list is always a **new, shallow** list
        """),
        Demo(
            code="""
            s = list(range(10))
            print("s          ", s)
            print("s[2:5]     ", s[2:5])
            print("s[:3]      ", s[:3])
            print("s[7:]      ", s[7:])
            print("s[-3:]     ", s[-3:])
            print("s[::2]     ", s[::2])
            print("s[::-1]    ", s[::-1], "  <- reversed copy")
            print("s[8:2:-2]  ", s[8:2:-2])
            print("s[100:200] ", s[100:200], "  <- clamped, no IndexError")
            try:
                s[100]
            except IndexError as exc:
                print("but s[100] ->", type(exc).__name__, exc)
            """,
            explain="""
            The last two lines are the ones to remember: **slicing clamps,
            indexing raises**. `s[100:200]` hands back an empty list rather
            than complaining, which is convenient right up until it hides an
            off-by-one — a slice that silently yields `[]` looks exactly like
            a slice that legitimately found nothing.

            Note also that `s[::-1]` builds a **reversed copy**, not a view.
            On a large list that is real work; `reversed(s)` gives you an
            iterator instead. And with a negative step, `start` is the higher
            index — `s[8:2:-2]` walks *down* from 8, stopping before 2.
            """,
        ),
        Text("""
        ## Slice assignment and deletion

        Slices are *lvalues*. Assigning to one splices — the replacement need
        not be the same length (unless the slice is extended, i.e. has a
        step ≠ 1).
        """),
        Demo(
            code="""
            xs = list("abcdef")
            xs[1:3] = ["X"]                 # shrink
            print(xs)
            xs[1:2] = ["p", "q", "r"]       # grow
            print(xs)
            print("xs[::2] covers", len(xs[::2]), "slots")
            xs[::2] = ["1", "2", "3", "4"]  # extended slice: length MUST match
            print(xs)
            try:
                xs[::2] = ["only-one"]
            except ValueError as exc:
                print("extended slice mismatch ->", exc)

            del xs[1::2]                    # delete every other element
            print("after del:", xs)

            ys = [1, 2, 3]
            ys[:] = [9, 9]                  # mutate in place, keeps identity
            print("ys[:]= keeps the object:", ys)
            """,
            explain="""
            `lst[:] = other` is the idiom for "replace the contents while
            keeping the same list object" — important when other references
            to that list exist elsewhere.
            """,
        ),
        Predict(
            code="""
            a = [1, 2, 3, 4, 5]
            b = a[:]
            c = a
            a[:] = [9]
            print(a, b, c)
            """,
            answer="""
            [9] [1, 2, 3, 4, 5] [9]
            """,
            explain="""
            `b = a[:]` copied; `c = a` aliased. `a[:] = [9]` mutated the shared
            object, so `c` sees it and `b` does not.
            """,
        ),
        Text("""
        ## `slice` objects and `__index__`

        `s[1:5:2]` builds `slice(1, 5, 2)` and passes it to `__getitem__`.
        `sl.indices(length)` normalises it into concrete `(start, stop, step)`
        — the single most useful method when writing your own sequence.
        """),
        Demo(
            code="""
            sl = slice(None, -1, 2)
            print("slice object:", sl)
            print("normalised over len 10:", sl.indices(10))
            print("as a range:", list(range(*sl.indices(10))))

            # Anything with __index__ can be used as an index.
            class Port:
                def __init__(self, n): self.n = n
                def __index__(self): return self.n

            data = list("abcdef")
            print("custom index:", data[Port(2)], data[Port(1):Port(4)])
            """,
            explain="""
            A slice is an ordinary object you can build, store and pass
            around — `seq[a:b:c]` just calls `__getitem__` with
            `slice(a, b, c)`. `.indices(length)` is the piece worth knowing:
            it resolves the `None`s and the negative values against a concrete
            length and hands back a plain `(start, stop, step)` triple, which
            is how you implement slicing on your own sequence without
            reimplementing the clamping rules.

            `__index__` is the hook that makes an object usable as an index,
            and it is deliberately **not** `__int__`. Floats define `__int__`
            and still cannot index a list — because a lossy conversion is
            exactly the kind of thing you do not want happening silently
            inside `data[x]`.
            """,
        ),
        Text("""
        ## Sorting: keys, stability, and `operator`

        - `sorted(iterable)` returns a new list; `list.sort()` sorts in place
          and returns `None`
        - `key=` is called **once per element** (fast); `cmp` is long gone
        - Python's sort is **stable**: equal elements keep their relative
          order. That makes multi-pass sorting possible.
        - descending: `reverse=True` — do not negate keys unless numeric
        """),
        Demo(
            code="""
            from operator import attrgetter, itemgetter

            people = [
                {"name": "ada", "dept": "eng", "age": 36},
                {"name": "bob", "dept": "ops", "age": 29},
                {"name": "cy",  "dept": "eng", "age": 29},
                {"name": "dee", "dept": "ops", "age": 41},
            ]

            print("by age:", [p["name"] for p in sorted(people, key=itemgetter("age"))])
            print("dept, then -age:",
                  [p["name"] for p in sorted(people, key=lambda p: (p["dept"], -p["age"]))])

            # Stability lets you sort in passes: last key sorted is the primary.
            tmp = sorted(people, key=itemgetter("name"))         # secondary
            tmp = sorted(tmp, key=itemgetter("dept"))            # primary
            print("two-pass:", [(p["dept"], p["name"]) for p in tmp])

            # For mixed direction on non-numeric keys, two passes is the way.
            print("sort() returns:", [1, 3, 2].sort())
            """,
            explain="""
            `itemgetter("age")` beats `lambda p: p["age"]` — it is implemented
            in C and avoids a Python-level call per element. `itemgetter("a","b")`
            returns a tuple, which is exactly what a compound sort key wants.
            """,
        ),
        Question(
            prompt="`data.sort(key=len)` — what does it return?",
            choices=["The sorted list", "`None`", "An iterator", "A copy of the list"],
            answer=1,
            explain="In-place mutators return `None` by convention, so you cannot "
                    "accidentally chain and think you got a copy. Use `sorted()` for a value.",
        ),
        Text("""
        ## Dicts: ordered, compact, and O(1)

        Since 3.7 insertion order is a **language guarantee**. Internally a
        dict is a compact array of entries plus a sparse index table — which
        is why iteration is fast and memory use dropped ~25% in 3.6.

        Key operations and their costs:

        | operation | cost |
        |---|---|
        | `d[k]`, `d[k] = v`, `del d[k]`, `k in d` | O(1) average |
        | iteration | O(n) in insertion order |
        | `d.popitem()` | O(1), **LIFO** |
        """),
        Demo(
            code="""
            d = {"a": 1, "b": 2}

            # setdefault vs defaultdict vs get -- three different jobs
            d.setdefault("c", []).append(3)      # insert-if-missing, returns value
            print("setdefault:", d)
            print("get is read-only:", d.get("zz", "fallback"), "|", d)

            # Merging: | (3.9+), |=, and dict(**a, **b)
            defaults = {"debug": False, "level": "info"}
            user = {"level": "debug"}
            print("merged:", defaults | user)     # right side wins
            print("originals intact:", defaults, user)

            # Views are live windows, not snapshots
            view = d.keys()
            d["new"] = 0
            print("live view:", list(view))
            print("views support set algebra:", d.keys() & {"a", "zz"})

            # Mutating during iteration is an error, by design
            try:
                for k in d:
                    d[k + "!"] = 1
            except RuntimeError as exc:
                print("RuntimeError:", exc)
            """,
            explain="""
            Iterate over `list(d)` if you must add or remove keys in the loop.
            The `RuntimeError` protects you from a corrupted traversal after a
            resize.
            """,
        ),
        Demo(
            code="""
            # Dict key subtleties: equality, not identity, decides.
            d = {1: "int one", True: "bool true", 1.0: "float one"}
            print(d, "  <- 1 == True == 1.0, so one slot")

            print("hash equality:", hash(1) == hash(1.0) == hash(True))

            # First key inserted wins the slot; later assignments only overwrite
            # the VALUE, never the stored key object.
            d2 = {1.0: "a"}
            d2[1] = "b"
            print(d2, "| key type is still", type(next(iter(d2))).__name__)
            """,
            explain="""
            A dict slot is claimed by **hash plus equality**, never by type.
            Since `1 == True == 1.0` and all three hash alike, the three-entry
            literal collapses to a single entry holding the last value written.

            The second half is the subtle one: assigning to an existing key
            replaces the **value** and keeps the **original key object**. So
            `d2` still reports a `float` key after `d2[1] = "b"`. Anywhere you
            round-trip a dict through code that cares about key types —
            serialisation especially — mixed numeric keys will bite.
            """,
        ),
        Text("""
        ## Sets: membership, algebra, and the hashability tax

        `x in some_set` is O(1); `x in some_list` is O(n). Converting a list
        to a set before a membership-heavy loop is the classic instant speedup.
        Sets are unordered and elements must be hashable — use `frozenset`
        when you need a set inside a set or as a dict key.
        """),
        Demo(
            code="""
            import timeit

            haystack_list = list(range(20_000))
            haystack_set = set(haystack_list)
            needle = 19_999

            t_list = timeit.timeit(lambda: needle in haystack_list, number=200)
            t_set = timeit.timeit(lambda: needle in haystack_set, number=200)
            print(f"list scan: {t_list*1000:7.3f} ms")
            print(f"set probe: {t_set*1000:7.3f} ms")
            print(f"speedup:   {t_list/t_set:,.0f}x")

            a, b = {1, 2, 3, 4}, {3, 4, 5}
            print("union       ", a | b)
            print("intersection", a & b)
            print("difference  ", a - b)
            print("symmetric   ", a ^ b)
            print("subset      ", {1, 2} <= a)
            print("disjoint    ", a.isdisjoint({9}))
            print("nested needs frozenset:", {frozenset({1, 2}), frozenset({1, 2})})
            """,
            explain="""
            Roughly a thousandfold, and the gap widens with size: `in` on a
            list compares elements one at a time, while on a set it is one
            hash and a probe — O(n) against O(1). If you test membership
            inside a loop, build the set first; you repay the construction
            cost within a handful of lookups.

            The algebra is the other reason to reach for sets: `|`, `&`, `-`,
            `^` express "which users lost access" far more directly than
            nested loops. The tax is hashability — a set cannot contain a set,
            so nesting needs `frozenset`, and two equal frozensets collapse
            into one element exactly as you would want.
            """,
        ),
        Question(
            prompt="Which container gives O(1) appends *and* O(1) pops from the LEFT?",
            choices=["`list`", "`collections.deque`", "`set`", "`tuple`"],
            answer=1,
            explain="`list.pop(0)` and `list.insert(0, x)` are O(n) — every element "
                    "shifts. `deque` is a doubly-linked list of blocks: both ends are O(1).",
        ),
        Text("""
        ## The `collections` toolbox

        - `deque` — O(1) both ends, `maxlen` gives you a ring buffer for free
        - `defaultdict` — auto-creates missing values from a factory
        - `Counter` — multiset with `most_common`, arithmetic, `total()`
        - `ChainMap` — layered lookup without copying (configs, scopes)
        - `namedtuple` — tuple with names, tiny memory footprint
        - `OrderedDict` — still useful: `move_to_end`, order-sensitive `==`
        """),
        Demo(
            code="""
            from collections import ChainMap, Counter, defaultdict, deque, namedtuple

            # deque as a fixed-size rolling window
            window = deque(maxlen=3)
            for x in range(6):
                window.append(x)
            print("last 3 seen:", list(window))
            window.rotate(1)
            print("rotated:", list(window))

            # defaultdict for grouping -- no key checks anywhere
            words = ["apple", "avocado", "banana", "blueberry", "cherry"]
            by_letter = defaultdict(list)
            for w in words:
                by_letter[w[0]].append(w)
            print("grouped:", dict(by_letter))

            # Counter
            c = Counter("mississippi")
            print("top 2:", c.most_common(2), "| total:", c.total())
            print("counter math:", Counter("aab") - Counter("ab"))

            # ChainMap: precedence without merging
            cli, env, defaults = {"level": "debug"}, {"host": "envhost"}, {"host": "localhost", "level": "info"}
            cfg = ChainMap(cli, env, defaults)
            print("resolved:", dict(cfg), "| host ->", cfg["host"])

            Point = namedtuple("Point", "x y")
            p = Point(1, 2)
            print("namedtuple:", p, p.x, "| unpacks:", (lambda x, y: x + y)(*p))
            print("_replace:", p._replace(y=99), "| _asdict:", p._asdict())
            """,
            explain="""
            Each of these replaces a pattern you would otherwise hand-roll:

            - `deque(maxlen=3)` drops from the far end as you append, giving a
              rolling window with no bookkeeping — and it is O(1) at *both*
              ends, where `list.pop(0)` is O(n).
            - `defaultdict(list)` runs the factory on a missing-key lookup, so
              grouping loops need no `setdefault` and no `if key in`. The
              flip side: a stray *read* creates an entry.
            - `Counter` subtraction discards non-positive counts, which is why
              `"aab" - "ab"` leaves only `{'a': 1}` rather than a zero entry.
            - `ChainMap` layers mappings without copying them — first match
              wins, so CLI beats env beats defaults, and the underlying dicts
              stay live.
            - `namedtuple` is a real tuple: it unpacks positionally, compares
              by value, and `_replace` returns a **new** instance.
            """,
        ),
        Text("""
        ## Complexity cheat sheet

        | operation | list | deque | dict/set |
        |---|---|---|---|
        | index `s[i]` | O(1) | O(n) | – |
        | append / add | O(1)* | O(1) | O(1)* |
        | insert/pop at 0 | O(n) | O(1) | – |
        | `x in s` | O(n) | O(n) | **O(1)*** |
        | sort | O(n log n) | – | – |

        \\* amortised. Growth reallocates occasionally but averages out.
        """),
        Demo(
            code="""
            import sys

            # Why 'amortised': lists over-allocate in geometric steps.
            prev, xs = 0, []
            growth_points = []
            for i in range(80):
                xs.append(i)
                size = sys.getsizeof(xs)
                if size != prev:
                    growth_points.append((len(xs), size))
                    prev = size
            print("reallocations at (len, bytes):")
            print("  ", growth_points)

            # A tuple is smaller than an equivalent list: no growth headroom.
            print("list  of 5:", sys.getsizeof([1, 2, 3, 4, 5]), "bytes")
            print("tuple of 5:", sys.getsizeof((1, 2, 3, 4, 5)), "bytes")
            """,
            explain="""
            The gaps between reallocations get wider as the list grows: 1, 5,
            9, 17, 25, 33... Capacity is raised in **geometric** steps, so
            across n appends the copying totals O(n) — which is what
            *amortised* O(1) means. Any single `append` that trips a
            reallocation really is O(n); it just happens rarely enough that
            the average stays flat.

            The tuple is smaller because it is sized exactly once and never
            grows, so it carries no spare capacity. Note `getsizeof` measures
            the container alone — the integers it points at are counted
            separately, which is why this is a poor way to size a nested
            structure (lesson 17 has the tool that does it properly).
            """,
        ),
        Exercise(
            slug="rolling-stats",
            title="A fixed-window rolling statistic",
            difficulty="medium",
            brief="""
            Implement `RollingWindow(size)` that keeps only the most recent
            `size` values and reports statistics in O(1) per push where
            possible.

            - `push(x)` adds a value, evicting the oldest once full
            - `values` property → a `list` of the current window, oldest first
            - `mean` → arithmetic mean, or `None` when empty
            - `total` → sum of the window, maintained incrementally (do **not**
              re-sum the whole window on each call)
            - `max` → the largest value in the window, or `None` when empty
            - `__len__`, and `full` → True once it holds `size` items
            - `size <= 0` raises `ValueError`
            """,
            starter="""
            from collections import deque


            class RollingWindow:
                def __init__(self, size: int):
                    ...
            """,
            checks=[
                Check("rejects a non-positive size", lambda ns: _rw_validate(ns["RollingWindow"])),
                Check("evicts oldest past the window", lambda ns: _rw_evict(ns["RollingWindow"])),
                Check("mean and max, empty-safe", lambda ns: _rw_stats(ns["RollingWindow"])),
                Check("total is maintained incrementally", lambda ns: _rw_incremental(ns["RollingWindow"])),
                Check("len and full", lambda ns: _rw_len(ns["RollingWindow"])),
                Check("values is a snapshot, not the live deque",
                      lambda ns: _rw_snapshot(ns["RollingWindow"])),
            ],
            hints=(
                "`deque(maxlen=size)` evicts for you — but it does not tell you "
                "what it dropped.",
                "To keep a running total, capture the oldest value *before* the "
                "append that evicts it.",
                "`values` must return a new list; returning the deque itself would "
                "let a caller corrupt your state.",
                "A truly O(1) rolling max needs a monotonic deque — `max()` over the "
                "window is acceptable here, but know the difference.",
            ),
            solution="""
            from collections import deque

            class RollingWindow:
                def __init__(self, size: int):
                    if size <= 0:
                        raise ValueError("size must be positive")
                    self.size = size
                    self._buf = deque()
                    self._total = 0

                def push(self, x):
                    self._buf.append(x)
                    self._total += x
                    if len(self._buf) > self.size:
                        self._total -= self._buf.popleft()
                    return self

                @property
                def values(self): return list(self._buf)
                @property
                def total(self): return self._total
                @property
                def mean(self):
                    return self._total / len(self._buf) if self._buf else None
                @property
                def max(self):
                    return max(self._buf) if self._buf else None
                @property
                def full(self): return len(self._buf) == self.size
                def __len__(self): return len(self._buf)
            """,
        ),
        Exercise(
            slug="group-sort",
            title="Multi-key grouping and ranking",
            difficulty="tricky",
            brief="""
            Write `rank_by_group(records, group_key, sort_key, top=None)`:

            - `records` is a list of dicts
            - group them by `records[group_key]`
            - within each group, sort **descending** by `records[sort_key]`,
              breaking ties by ascending `name` so the result is deterministic
            - if `top` is given, keep only the first `top` of each group
            - return a `dict[group -> list[record]]` whose groups appear in the
              order of each group's **first appearance** in `records`
            - the input list and its dicts must not be modified

            Then also expose `flatten(ranked)` returning a flat list of
            `(group, rank, name)` tuples where `rank` starts at 1 per group.
            """,
            starter="""
            def rank_by_group(records, group_key, sort_key, top=None):
                ...


            def flatten(ranked):
                ...
            """,
            checks=[
                Check("groups in first-appearance order", lambda ns: _gs_order(ns["rank_by_group"])),
                Check("descending sort with name tiebreak", lambda ns: _gs_sort(ns["rank_by_group"])),
                Check("top-N truncation per group", lambda ns: _gs_top(ns["rank_by_group"])),
                Check("input is untouched", lambda ns: _gs_pure(ns["rank_by_group"])),
                Check("flatten produces per-group ranks",
                      lambda ns: _gs_flatten(ns["rank_by_group"], ns["flatten"])),
            ],
            hints=(
                "`defaultdict(list)` preserves insertion order like any dict, so "
                "first-appearance ordering is automatic.",
                "Mixed sort directions: `key=lambda r: (-r[sort_key], r['name'])` "
                "works when the descending key is numeric.",
                "Slice with `[:top]` — `None` is not valid there, so branch or use "
                "`[:top] if top else [:]`.",
                "`enumerate(items, 1)` gives you 1-based ranks.",
            ),
            solution="""
            from collections import defaultdict

            def rank_by_group(records, group_key, sort_key, top=None):
                groups = defaultdict(list)
                for record in records:
                    groups[record[group_key]].append(record)

                ranked = {}
                for group, items in groups.items():
                    ordered = sorted(items, key=lambda r: (-r[sort_key], r["name"]))
                    ranked[group] = ordered[:top] if top is not None else ordered
                return ranked

            def flatten(ranked):
                return [(group, rank, rec["name"])
                        for group, recs in ranked.items()
                        for rank, rec in enumerate(recs, 1)]
            """,
        ),
        Text("""
        ## Takeaways

        - Slices copy, clamp, and can be assigned to or deleted from.
        - `lst[:] = new` replaces contents in place; `lst = new` rebinds.
        - Sort is stable — chain passes for multi-key ordering.
        - Reach for `set`/`dict` the moment membership is in a loop.
        - `collections` already implements the container you were about to
          write by hand.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _rw_validate(RW) -> None:
    for bad in (0, -1):
        try:
            RW(bad)
        except ValueError:
            continue
        raise AssertionError(f"size={bad} should raise ValueError")


def _rw_evict(RW) -> None:
    w = RW(3)
    for x in [1, 2, 3, 4, 5]:
        w.push(x)
    assert w.values == [3, 4, 5], f"expected [3, 4, 5], got {w.values}"


def _rw_stats(RW) -> None:
    w = RW(3)
    assert w.mean is None and w.max is None, "empty window must report None"
    for x in [10, 20, 30, 40]:
        w.push(x)
    assert w.values == [20, 30, 40]
    assert w.mean == 30, f"mean should be 30, got {w.mean}"
    assert w.max == 40, f"max should be 40, got {w.max}"


def _rw_incremental(RW) -> None:
    w = RW(2)
    w.push(5)
    w.push(7)
    assert w.total == 12, f"total should be 12, got {w.total}"
    w.push(1)
    assert w.total == 8, f"after eviction total should be 8, got {w.total}"
    assert w.total == sum(w.values), "total must agree with the window contents"


def _rw_len(RW) -> None:
    w = RW(2)
    assert len(w) == 0 and not w.full
    w.push(1)
    assert len(w) == 1 and not w.full
    w.push(2)
    assert len(w) == 2 and w.full
    w.push(3)
    assert len(w) == 2 and w.full, "len must never exceed size"


def _rw_snapshot(RW) -> None:
    w = RW(3)
    w.push(1)
    snap = w.values
    assert isinstance(snap, list), f"values must be a list, got {type(snap).__name__}"
    snap.append(999)
    assert w.values == [1], "mutating the returned list corrupted the window"


_ROWS = [
    {"name": "ada", "team": "eng", "score": 90},
    {"name": "bob", "team": "ops", "score": 70},
    {"name": "cy", "team": "eng", "score": 95},
    {"name": "dee", "team": "ops", "score": 70},
    {"name": "eve", "team": "eng", "score": 90},
]


def _gs_order(rank) -> None:
    out = rank([dict(r) for r in _ROWS], "team", "score")
    assert list(out) == ["eng", "ops"], f"group order wrong: {list(out)}"


def _gs_sort(rank) -> None:
    out = rank([dict(r) for r in _ROWS], "team", "score")
    names = [r["name"] for r in out["eng"]]
    assert names == ["cy", "ada", "eve"], f"eng order wrong: {names}"
    ops = [r["name"] for r in out["ops"]]
    assert ops == ["bob", "dee"], f"tie should break on name ascending: {ops}"


def _gs_top(rank) -> None:
    out = rank([dict(r) for r in _ROWS], "team", "score", top=2)
    assert [r["name"] for r in out["eng"]] == ["cy", "ada"]
    assert len(out["ops"]) == 2, "a group smaller than top must not be padded"
    out1 = rank([dict(r) for r in _ROWS], "team", "score", top=1)
    assert [r["name"] for r in out1["ops"]] == ["bob"]


def _gs_pure(rank) -> None:
    rows = [dict(r) for r in _ROWS]
    snapshot = [dict(r) for r in rows]
    rank(rows, "team", "score")
    assert rows == snapshot, "the input records were modified"


def _gs_flatten(rank, flatten) -> None:
    out = rank([dict(r) for r in _ROWS], "team", "score")
    flat = flatten(out)
    assert flat[:3] == [("eng", 1, "cy"), ("eng", 2, "ada"), ("eng", 3, "eve")], flat[:3]
    assert flat[3:] == [("ops", 1, "bob"), ("ops", 2, "dee")], flat[3:]
