"""Lesson 15 — itertools, functools, and operator."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=15,
    slug="functional",
    title="The Functional Toolbox",
    summary="""
    `itertools`, `functools` and `operator` are three small modules that
    together eliminate an astonishing amount of hand-written loop code — and
    run in C while doing it. This lesson is a working tour: what each tool
    does, when it beats the obvious loop, and the traps (shared iterators,
    grouping without sorting, `reduce` readability).
    """,
    tags=("itertools", "functools", "operator", "functional"),
    blocks=[
        Text("""
        ## `itertools`, by category

        **Infinite:** `count(start, step)`, `cycle(iterable)`, `repeat(x, n)`

        **Terminating:** `accumulate`, `chain`, `compress`, `dropwhile`,
        `takewhile`, `filterfalse`, `groupby`, `islice`, `pairwise`,
        `starmap`, `tee`, `zip_longest`, `batched` (3.12)

        **Combinatoric:** `product`, `permutations`, `combinations`,
        `combinations_with_replacement`

        Every one of them is lazy, and they compose into pipelines that never
        materialise an intermediate list.
        """),
        Demo(
            code="""
            import itertools as it

            print("count      :", list(it.islice(it.count(10, 5), 4)))
            print("cycle      :", list(it.islice(it.cycle("abc"), 7)))
            print("repeat     :", list(it.repeat("x", 3)))
            print("accumulate :", list(it.accumulate([1, 2, 3, 4])))
            print("running max:", list(it.accumulate([3, 1, 4, 1, 5], max)))
            print("chain      :", list(it.chain([1, 2], "ab", (3,))))
            print("from_iter  :", list(it.chain.from_iterable([[1, 2], [3, 4]])))
            print("compress   :", list(it.compress("abcdef", [1, 0, 1, 0, 1, 1])))
            print("takewhile  :", list(it.takewhile(lambda n: n < 3, [1, 2, 3, 1])))
            print("dropwhile  :", list(it.dropwhile(lambda n: n < 3, [1, 2, 3, 1])))
            print("pairwise   :", list(it.pairwise([1, 2, 3, 4])))
            print("starmap    :", list(it.starmap(pow, [(2, 3), (3, 2)])))
            print("zip_longest:", list(it.zip_longest("ab", "xyz", fillvalue="-")))
            print("batched    :", list(it.batched("abcdefg", 3)))
            """,
            explain="""
            Five families, and knowing which is which is most of the value:

            - **infinite sources** — `count`, `cycle`, `repeat`. Every one
              needs something downstream to stop it; the `islice` calls here
              are not decoration.
            - **running aggregates** — `accumulate` takes any binary
              function, so a running maximum is one argument away from a
              running total.
            - **flatteners** — `chain` for separate arguments,
              `chain.from_iterable` when you have a single iterable *of*
              iterables. Reaching for the wrong one is the usual stumble.
            - **selectors** — `compress` picks by mask; `takewhile` and
              `dropwhile` stop testing after the first failure, which is why
              `dropwhile` keeps the trailing `1` rather than filtering it.
            - **reshapers** — `pairwise` for sliding windows, `batched`
              (3.12) for fixed chunks, `zip_longest` when the inputs differ in
              length and truncating would lose data.

            All of them return iterators. Nothing is computed until consumed,
            which is what makes chaining them cheap.
            """,
        ),
        Demo(
            code="""
            import itertools as it

            print("product         :", list(it.product("ab", [1, 2])))
            print("product repeat  :", list(it.product([0, 1], repeat=3))[:4], "...")
            print("permutations    :", list(it.permutations("abc", 2)))
            print("combinations    :", list(it.combinations("abcd", 2)))
            print("with replacement:", list(it.combinations_with_replacement("ab", 2)))

            # product is the flat way to write nested loops:
            grid = [(r, c) for r, c in it.product(range(2), range(3))]
            print("nested loops    :", grid)
            """,
            explain="""
            `product` is nested loops written flat — two arguments is a double
            `for`, and `repeat=3` is three nested loops over the same
            iterable. The `grid` line at the bottom is the idiom worth
            keeping: it removes a level of indentation without changing the
            meaning.

            The distinction among the other three is order and reuse.
            `permutations` treats `("a","b")` and `("b","a")` as different;
            `combinations` does not; `combinations_with_replacement` allows an
            element to appear twice. All three select by **position**, not by
            value — feed them a sequence with duplicates and you get duplicate
            results back.

            Watch the growth. These are factorial and exponential functions,
            so `list()` on a product of a few modest inputs is how a script
            quietly consumes all available memory. Bound them first.
            """,
        ),
        Text("""
        ## `groupby` groups *consecutive* runs

        This is the single most misunderstood function in the module. It does
        not build a mapping — it yields `(key, group)` pairs as the key
        changes. **Sort by the same key first**, or you get fragments.

        The group is also a lazy iterator sharing the underlying source: once
        you advance to the next group, the previous one is spent.
        """),
        Demo(
            code="""
            from itertools import groupby
            from operator import itemgetter

            rows = [
                {"dept": "eng", "name": "ada"},
                {"dept": "ops", "name": "bob"},
                {"dept": "eng", "name": "cy"},
            ]

            print("unsorted:")
            for key, group in groupby(rows, key=itemgetter("dept")):
                print("  ", key, [r["name"] for r in group])

            print("sorted first:")
            rows.sort(key=itemgetter("dept"))
            for key, group in groupby(rows, key=itemgetter("dept")):
                print("  ", key, [r["name"] for r in group])

            # The sharing trap:
            groups = list(groupby("aabbb"))
            print("materialised too late:", [(k, list(g)) for k, g in groups])
            print("...every group is empty because the source moved on")
            """,
            explain="""
            If you want a real mapping, `collections.defaultdict(list)` in a
            plain loop is clearer, needs no sort, and is O(n) rather than
            O(n log n). Use `groupby` for run-length work and for streaming
            over already-sorted data.
            """,
        ),
        Question(
            prompt="`groupby` on unsorted data gives you what?",
            choices=[
                "A correct grouping, order-independent",
                "One group per *run* of consecutive equal keys, so keys can repeat",
                "An error",
                "Groups sorted by key automatically",
            ],
            answer=1,
            explain="It is a streaming run-detector. Sort by the same key first, or "
                    "use a `defaultdict(list)`.",
        ),
        Text("""
        ## `functools`

        | tool | purpose |
        |---|---|
        | `reduce(fn, it, init)` | fold a sequence into one value |
        | `partial` / `partialmethod` | pre-bind arguments |
        | `cache` / `lru_cache` | memoisation |
        | `cached_property` | per-instance lazy attribute |
        | `singledispatch(method)` | type-based overloading |
        | `wraps` / `update_wrapper` | metadata for decorators |
        | `total_ordering` | derive all comparisons |
        | `cmp_to_key` | adapt an old-style comparison function |
        """),
        Demo(
            code="""
            from functools import cmp_to_key, partial, reduce
            import operator

            print("sum via reduce  :", reduce(operator.add, [1, 2, 3, 4]))
            print("product         :", reduce(operator.mul, [1, 2, 3, 4]))
            print("with initial    :", reduce(operator.add, [], 0))
            print("flatten         :", reduce(operator.iconcat, [[1, 2], [3]], []))
            print("max via reduce  :", reduce(lambda a, b: a if a > b else b, [3, 9, 2]))

            # ...but prefer the built-in when one exists:
            print("built-ins win   :", sum([1, 2, 3, 4]), max([3, 9, 2]))

            # cmp_to_key: sorting by a rule that is not a simple key.
            def compare(a, b):
                if len(a) != len(b):
                    return len(a) - len(b)
                return (a > b) - (a < b)

            words = ["pear", "fig", "apple", "kiwi"]
            print("cmp_to_key      :", sorted(words, key=cmp_to_key(compare)))

            # partial for configuration
            to_binary = partial(int, base=2)
            print("partial         :", to_binary("1011"))
            """,
            explain="""
            `reduce` is powerful and often unreadable. Reach for it only when
            no built-in fits and the operation is genuinely a fold — and
            always give it an explicit initial value so an empty input does
            not raise.
            """,
        ),
        Demo(
            code="""
            from functools import singledispatch, singledispatchmethod

            @singledispatch
            def to_json(value):
                raise TypeError(f"cannot serialise {type(value).__name__}")

            @to_json.register
            def _(value: int | float | bool):   # union registration works
                return str(value).lower()

            @to_json.register
            def _(value: str):
                return f'"{value}"'

            @to_json.register
            def _(value: list):
                return "[" + ",".join(to_json(v) for v in value) + "]"

            @to_json.register
            def _(value: dict):
                return "{" + ",".join(f'"{k}":{to_json(v)}' for k, v in value.items()) + "}"

            print(to_json({"a": [1, "two", True], "b": 3.5}))

            # Dispatch follows the MRO -- register an ABC to catch a family.
            from collections.abc import Sequence

            @singledispatch
            def size(obj): return "unknown"
            @size.register
            def _(obj: Sequence): return f"sequence of {len(obj)}"

            print(size((1, 2, 3)), "|", size([1]), "|", size(5))
            """,
            explain="""
            `singledispatch` turns a wall of `isinstance` checks into
            registrations that live next to the types they handle — and, more
            usefully, lets a *different module* add a case later without
            touching the original function. That is the extensibility an
            if-chain cannot offer.

            Dispatch is on the **first argument only**, and it follows the
            MRO: registering `Sequence` catches tuples and lists together,
            because both are registered subclasses of that ABC. The base
            implementation is the fallback for everything unmatched, and
            raising there beats returning `None` — an unserialisable type
            should fail loudly rather than silently produce nothing.

            Inside a class you want `singledispatchmethod`, since the plain
            decorator would dispatch on `self` and match every call.
            """,
        ),
        Text("""
        ## `operator`: functions for the syntax

        Every operator has a function form, implemented in C. They are faster
        than an equivalent `lambda` and, more importantly, they say what they
        mean.

        - `itemgetter(k)`, `itemgetter(0, 2)` (returns a tuple)
        - `attrgetter("a.b")` — follows dots
        - `methodcaller("strip", "x")` — calls a method with arguments
        - `add`, `mul`, `lt`, `eq`, `contains`, `not_`, `truth`, `getitem`
        """),
        Demo(
            code="""
            import timeit
            from operator import attrgetter, itemgetter, methodcaller

            pairs = [(3, "c"), (1, "a"), (2, "b")]
            print("itemgetter :", sorted(pairs, key=itemgetter(0)))
            print("multi      :", itemgetter(0, 1)(pairs[0]))

            class Node:
                def __init__(self, name, depth): self.name, self.depth = name, depth
                class Meta: version = 2
                meta = Meta()

            nodes = [Node("b", 2), Node("a", 1)]
            print("attrgetter :", [n.name for n in sorted(nodes, key=attrgetter("depth"))])
            print("dotted     :", attrgetter("meta.version")(nodes[0]))
            print("methodcall :", list(map(methodcaller("upper"), ["a", "b"])))

            data = [(i, str(i)) for i in range(2000)]
            t_lambda = timeit.timeit(lambda: sorted(data, key=lambda p: p[0]), number=100)
            t_getter = timeit.timeit(lambda: sorted(data, key=itemgetter(0)), number=100)
            print(f"lambda {t_lambda*1000:.1f} ms vs itemgetter {t_getter*1000:.1f} ms"
                  f"  ({t_lambda/t_getter:.2f}x)")
            """,
            explain="""
            Roughly three times quicker, and the reason is structural rather
            than clever: `itemgetter` is C code called directly by `sorted`,
            while `lambda p: p[0]` is a Python frame pushed and popped once
            per comparison. On a sort key — the hottest callback there is —
            that overhead is the bulk of the work.

            The extras are worth knowing beyond the speed. `itemgetter(0, 1)`
            pulls several fields as a tuple, which is exactly the shape of a
            multi-column sort key. `attrgetter` follows dotted paths, so
            `"meta.version"` works without a lambda. And `methodcaller` covers
            the `map(lambda s: s.upper(), ...)` case.
            """,
        ),
        Predict(
            code="""
            from itertools import chain, islice

            source = iter(range(6))
            a = list(islice(source, 2))
            b = list(islice(source, 2))
            c = list(chain(a, b, source))
            print(a, b, c)
            """,
            answer="""
            [0, 1] [2, 3] [0, 1, 2, 3, 4, 5]
            """,
            explain="""
            `islice` consumes from the shared iterator, so the second call
            continues where the first stopped — this is the standard way to
            take chunks off a stream. `chain` then stitches the already-taken
            pieces back together with whatever remains.
            """,
        ),
        Text("""
        ## Recipes worth memorising

        The `itertools` docs ship a "recipes" section; these four come up
        constantly.
        """),
        Demo(
            code="""
            import itertools as it
            from collections import deque

            def take(n, iterable):
                return list(it.islice(iterable, n))

            def unique_everseen(iterable, key=None):
                seen = set()
                for item in iterable:
                    k = item if key is None else key(item)
                    if k not in seen:
                        seen.add(k)
                        yield item

            def sliding_window(iterable, n):
                iterable = iter(iterable)       # REQUIRED -- see the note below
                window = deque(it.islice(iterable, n - 1), maxlen=n)
                for item in iterable:
                    window.append(item)
                    yield tuple(window)

            def partition(predicate, iterable):
                t1, t2 = it.tee(iterable)
                return it.filterfalse(predicate, t1), filter(predicate, t2)

            print("take          :", take(3, it.count()))
            print("unique_everseen:", list(unique_everseen("AAAABBBCCDAABBB")))
            print("by key         :", list(unique_everseen(["a", "A", "b"], key=str.lower)))
            print("sliding_window :", list(sliding_window(range(5), 3)))
            odd, even = partition(lambda n: n % 2 == 0, range(6))
            print("partition      :", list(odd), list(even))
            """,
            explain="""
            The `iter(iterable)` line in `sliding_window` is the one to study,
            because without it the function is subtly wrong. `islice` would
            consume the first `n-1` items from a *fresh* iterator over
            `range(5)`, and the `for` loop would then start again from zero —
            producing `(0, 1, 0), (1, 0, 1)` before accidentally coming right.
            Passing `iter(range(5))` would have masked it.

            The general rule: **any function that reads from an iterable in
            two separate steps must call `iter()` first**. A list or range
            hands out a new iterator each time it is iterated; a generator
            does not. Without the call, your function quietly behaves
            differently depending on what it was handed.

            The others are worth keeping as written. `unique_everseen`
            preserves order where `set()` would not, and its `key` argument
            gives you case-insensitive dedup for free; `partition` gets both
            halves in one pass — subject to `tee`'s buffering caveat from
            lesson 05.
            """,
        ),
        Question(
            prompt="Which is the right tool for `[[1,2],[3,4]]` → `[1,2,3,4]`?",
            choices=[
                "`itertools.product`",
                "`itertools.chain.from_iterable`",
                "`functools.reduce(operator.add, ...)`",
                "`itertools.zip_longest`",
            ],
            answer=1,
            explain="`chain.from_iterable` is lazy and O(n). The `reduce` version is "
                    "O(n²) because it builds a new list on every step.",
        ),
        Exercise(
            slug="stream-tools",
            title="Four streaming utilities",
            difficulty="tricky",
            brief="""
            Implement four lazy utilities. All must work on infinite inputs and
            must not materialise the source.

            `run_lengths(iterable)` → yields `(value, count)` for each run of
            consecutive equal values. `"aabbbc"` → `("a",2), ("b",3), ("c",1)`.

            `chunk_by(iterable, key)` → yields **lists** of consecutive items
            sharing a key. `chunk_by([1,3,2,4,5], lambda n: n % 2)` →
            `[1,3], [2,4], [5]`.

            `interleave(*iterables)` → round-robin across the inputs, skipping
            exhausted ones. `interleave("abc", "12", "")` → `a,1,b,2,c`.

            `window_max(iterable, k)` → the maximum of each sliding window of
            width `k`, in **O(n) total** (each element enters and leaves a
            deque once — no `max()` per window). Fewer than `k` items yields
            nothing.
            """,
            starter="""
            from collections import deque
            from itertools import groupby, islice


            def run_lengths(iterable):
                ...


            def chunk_by(iterable, key):
                ...


            def interleave(*iterables):
                ...


            def window_max(iterable, k):
                ...
            """,
            checks=[
                Check("run_lengths counts consecutive runs", lambda ns: _st_runs(ns)),
                Check("chunk_by groups by key changes", lambda ns: _st_chunk(ns)),
                Check("interleave round-robins and skips exhausted",
                      lambda ns: _st_interleave(ns)),
                Check("window_max is correct", lambda ns: _st_wmax(ns)),
                Check("window_max is O(n): no max() per window", lambda ns: _st_wmax_cost(ns)),
                Check("everything stays lazy on infinite input", lambda ns: _st_lazy(ns)),
                Check("edge cases: empty inputs", lambda ns: _st_empty(ns)),
            ],
            hints=(
                "`groupby` with no key gives you runs directly — "
                "`sum(1 for _ in group)` counts one without building a list.",
                "For `interleave`, keep a deque of iterators; pop one, take a value, "
                "push it back if it did not raise StopIteration.",
                "The O(n) sliding maximum keeps a deque of *indices* whose values are "
                "strictly decreasing; the front is always the current window's max.",
                "Pop from the back of that deque while the incoming value is >= the "
                "value at the back, and pop from the front once its index leaves the "
                "window.",
            ),
            solution="""
            from collections import deque
            from itertools import groupby, islice

            def run_lengths(iterable):
                for value, group in groupby(iterable):
                    yield value, sum(1 for _ in group)

            def chunk_by(iterable, key):
                for _, group in groupby(iterable, key=key):
                    yield list(group)

            def interleave(*iterables):
                pending = deque(iter(it) for it in iterables)
                while pending:
                    current = pending.popleft()
                    try:
                        yield next(current)
                    except StopIteration:
                        continue
                    pending.append(current)

            def window_max(iterable, k):
                if k < 1:
                    raise ValueError("k must be positive")
                candidates = deque()          # indices, values strictly decreasing
                for index, value in enumerate(iterable):
                    while candidates and candidates[-1][1] <= value:
                        candidates.pop()
                    candidates.append((index, value))
                    if candidates[0][0] <= index - k:
                        candidates.popleft()
                    if index >= k - 1:
                        yield candidates[0][1]
            """,
        ),
        Text("""
        ## Takeaways

        - `itertools` composes lazily — chain stages instead of building
          intermediate lists.
        - `groupby` needs sorted input and yields *shared, one-shot* groups.
        - Prefer `sum`/`max`/`any` over `reduce`; keep `reduce` for real folds.
        - `singledispatch` replaces `isinstance` ladders and honours the MRO.
        - `operator.itemgetter`/`attrgetter` are faster and clearer than
          equivalent lambdas.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _st_runs(ns) -> None:
    run_lengths = ns["run_lengths"]
    got = list(run_lengths("aabbbc"))
    assert got == [("a", 2), ("b", 3), ("c", 1)], got
    assert list(run_lengths([1, 1, 2, 1])) == [(1, 2), (2, 1), (1, 1)], (
        "non-adjacent equal values are separate runs"
    )


def _st_chunk(ns) -> None:
    chunk_by = ns["chunk_by"]
    got = list(chunk_by([1, 3, 2, 4, 5], lambda n: n % 2))
    assert got == [[1, 3], [2, 4], [5]], got
    assert all(isinstance(c, list) for c in got), "chunks must be lists"
    words = ["ant", "ape", "bee", "cow", "cat"]
    assert list(chunk_by(words, lambda w: w[0])) == [
        ["ant", "ape"], ["bee"], ["cow", "cat"]
    ], list(chunk_by(words, lambda w: w[0]))


def _st_interleave(ns) -> None:
    interleave = ns["interleave"]
    assert list(interleave("abc", "12", "")) == ["a", "1", "b", "2", "c"], (
        list(interleave("abc", "12", ""))
    )
    assert list(interleave([1, 2], [3, 4], [5, 6])) == [1, 3, 5, 2, 4, 6]
    assert list(interleave()) == []
    assert list(interleave("abc")) == ["a", "b", "c"]


def _st_wmax(ns) -> None:
    window_max = ns["window_max"]
    assert list(window_max([1, 3, 2, 5, 4], 3)) == [3, 5, 5], list(window_max([1, 3, 2, 5, 4], 3))
    assert list(window_max([5, 4, 3, 2], 2)) == [5, 4, 3]
    assert list(window_max([1, 2], 3)) == [], "fewer items than k yields nothing"
    assert list(window_max([7], 1)) == [7]
    assert list(window_max([2, 2, 2], 2)) == [2, 2], "duplicates must not break it"


def _st_wmax_cost(ns) -> None:
    """A quadratic implementation calls __gt__/__le__ O(n*k) times."""
    window_max = ns["window_max"]
    comparisons = [0]

    class Counted:
        def __init__(self, v): self.v = v
        def __le__(self, other):
            comparisons[0] += 1
            return self.v <= other.v
        def __lt__(self, other):
            comparisons[0] += 1
            return self.v < other.v
        def __gt__(self, other):
            comparisons[0] += 1
            return self.v > other.v
        def __ge__(self, other):
            comparisons[0] += 1
            return self.v >= other.v

    n, k = 300, 50
    values = [Counted(i % 37) for i in range(n)]
    list(window_max(values, k))
    assert comparisons[0] < 4 * n, (
        f"{comparisons[0]} comparisons for n={n}, k={k} — that is O(n*k). "
        "Use the monotonic-deque algorithm so each element is pushed and "
        "popped at most once."
    )


def _st_lazy(ns) -> None:
    from itertools import count, cycle, islice

    run_lengths, chunk_by = ns["run_lengths"], ns["chunk_by"]
    interleave, window_max = ns["interleave"], ns["window_max"]

    assert list(islice(run_lengths(cycle("aab")), 3)) == [("a", 2), ("b", 1), ("a", 2)]
    assert list(islice(chunk_by(count(), lambda n: n // 3), 2)) == [[0, 1, 2], [3, 4, 5]]
    assert list(islice(interleave(count(0, 2), count(1, 2)), 4)) == [0, 1, 2, 3]
    assert list(islice(window_max(count(), 3), 3)) == [2, 3, 4]


def _st_empty(ns) -> None:
    assert list(ns["run_lengths"]([])) == []
    assert list(ns["chunk_by"]([], lambda x: x)) == []
    assert list(ns["window_max"]([], 2)) == []
