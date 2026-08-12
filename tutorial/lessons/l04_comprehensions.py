"""Lesson 04 — Comprehensions, generator expressions, and lazy evaluation."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=4,
    slug="comprehensions",
    title="Comprehensions and Lazy Evaluation",
    summary="""
    Comprehensions are not just terser loops — they are a different execution
    model with their own scope, their own bytecode, and (for generator
    expressions) their own laziness. Knowing where the boundary sits explains
    leaked variables, surprise memory use, and one-shot iterables.
    """,
    tags=("comprehensions", "generators", "scope", "laziness"),
    blocks=[
        Text("""
        ## The four forms

        ```python
        [f(x) for x in it if cond]      # list
        {f(x) for x in it}              # set
        {k(x): v(x) for x in it}        # dict
        (f(x) for x in it)              # generator expression -- LAZY
        ```

        The first three build the whole result immediately. The fourth builds
        nothing until you iterate it. That one-character difference between
        `[` and `(` is the difference between 8 GB of RAM and 200 bytes.
        """),
        Demo(
            code="""
            import sys

            listcomp = [x * x for x in range(100_000)]
            genexp = (x * x for x in range(100_000))

            print("list comp :", type(listcomp).__name__, sys.getsizeof(listcomp), "bytes")
            print("genexp    :", type(genexp).__name__, sys.getsizeof(genexp), "bytes")
            print("both sum to the same thing:", sum(listcomp) == sum(genexp))

            # ...but the generator is now EXHAUSTED.
            print("second pass over the genexp:", sum(genexp))
            print("second pass over the list  :", sum(listcomp))
            """,
            explain="""
            A generator is a **one-shot** iterator. Once consumed it yields
            nothing more — silently, with no error. This is the single most
            common generator bug: passing one to two functions and wondering
            why the second saw an empty sequence.
            """,
        ),
        Text("""
        ## Comprehensions have their own scope

        In Python 3, a comprehension runs in an implicit nested function.
        Consequences:

        - the loop variable does **not** leak into the enclosing scope
        - the comprehension can read enclosing names, but assigning to one
          needs `nonlocal`/`global` (or the walrus, see below)
        - at class scope, the comprehension body cannot see class-level names
          — a genuinely surprising rule
        """),
        Demo(
            code="""
            x = "untouched"
            squares = [x * x for x in range(4)]
            print("loop var did not leak:", x, squares)

            # A plain for loop DOES leak -- and that is sometimes a bug.
            for y in range(4):
                pass
            print("but a for loop leaks:", y)
            """,
        ),
        Predict(
            code="""
            class Config:
                DEFAULTS = {"a": 1, "b": 2}
                KEYS = [k for k in DEFAULTS]                  # works
                try:
                    PAIRS = [(k, DEFAULTS[k]) for k in KEYS]  # fails
                    result = "both worked"
                except NameError as exc:
                    result = f"NameError: {exc}"

            print(Config.KEYS)
            print(Config.result)
            """,
            answer="""
            ['a', 'b']
            NameError: name 'DEFAULTS' is not defined
            """,
            explain="""
            The **first** iterable of a comprehension is evaluated in the
            enclosing (class) scope, so `for k in DEFAULTS` is fine. Everything
            else runs inside the implicit function, and class bodies are not
            enclosing scopes for nested functions — so `DEFAULTS[k]` in the
            expression cannot be resolved. Bind it to a local first, or use a
            plain loop, in class bodies.
            """,
        ),
        Question(
            prompt="Inside a class body, which part of `[f(x) for x in SOURCE]` can see class-level names?",
            choices=[
                "All of it — class scope is a normal enclosing scope",
                "Only `SOURCE`, the outermost iterable",
                "Only the `f(x)` expression",
                "None of it",
            ],
            answer=1,
            explain="The outermost iterable is evaluated eagerly in the enclosing scope "
                    "and passed into the implicit comprehension function; the rest runs inside it.",
        ),
        Text("""
        ## Nesting: loop order reads left to right

        ```python
        [expr for a in A for b in B]     # == for a in A: for b in B: expr
        ```

        The clauses appear in the same order you would write the nested `for`
        statements. The confusing part is that the *output expression* comes
        first, at the far left, even though it executes last.
        """),
        Demo(
            code="""
            matrix = [[1, 2, 3], [4, 5, 6]]

            flat = [cell for row in matrix for cell in row]
            print("flatten:", flat)

            transposed = [[row[i] for row in matrix] for i in range(3)]
            print("transpose:", transposed)
            print("or just:  ", [list(t) for t in zip(*matrix)])

            # A later clause can depend on an earlier one.
            triangle = [(i, j) for i in range(4) for j in range(i)]
            print("dependent:", triangle)

            # Filters attach to the loop they follow.
            print("filtered:", [(i, j) for i in range(4) if i % 2 == 0
                                       for j in range(3) if j > i])
            """,
        ),
        Text("""
        ## Conditional expressions vs filters

        - `if` **after** the `for` is a **filter** — it drops elements.
        - `if/else` **before** the `for` is a **ternary** in the output
          expression — it maps every element.

        You cannot filter with an `else`; you cannot map-with-default using a
        trailing `if`.
        """),
        Demo(
            code="""
            nums = range(6)
            print("filter  :", [n for n in nums if n % 2])
            print("map     :", ["odd" if n % 2 else "even" for n in nums])
            print("both    :", ["big" if n > 3 else "small" for n in nums if n % 2])
            """,
        ),
        Text("""
        ## The walrus operator `:=`

        Assign inside an expression. In comprehensions it lets you compute a
        value once and use it in both the filter and the output — avoiding the
        classic "call the expensive function twice" pattern.

        The walrus target binds in the **enclosing** scope, not the
        comprehension's — one of the few ways a comprehension writes outward.
        """),
        Demo(
            code="""
            calls = []

            def expensive(n):
                calls.append(n)
                return n * n

            # Naive: calls expensive() twice per surviving element.
            calls.clear()
            naive = [expensive(n) for n in range(6) if expensive(n) > 10]
            print("naive result:", naive, "| calls:", len(calls))

            # Walrus: once per element.
            calls.clear()
            walrus = [sq for n in range(6) if (sq := expensive(n)) > 10]
            print("walrus result:", walrus, "| calls:", len(calls))
            print("and sq leaked out to here:", sq)
            """,
            explain="""
            Reading a chunked stream is the other classic use:
            `while chunk := f.read(8192):` replaces the read-before-loop
            plus read-at-the-bottom dance.
            """,
        ),
        Question(
            prompt="What does `[y := 2, y ** 2]` evaluate to?",
            choices=["`[2, 4]`", "A SyntaxError", "`[2, 2]`", "`[None, 4]`"],
            answer=0,
            explain="The walrus binds `y` to 2 *and* evaluates to 2, so the second "
                    "element sees `y == 2`. Legal, but do not write this in real code.",
        ),
        Text("""
        ## Laziness: what it buys and what it costs

        **Buys you:** constant memory over huge or infinite sources, early
        exit without computing the rest, and pipeline composition.

        **Costs you:** single use, no `len()`, no indexing, and *deferred
        side effects* — the body runs later than the line where you wrote it,
        which interacts badly with mutation and with `try/except`.
        """),
        Demo(
            code="""
            # Early exit: only three items are ever computed.
            log = []

            def trace(n):
                log.append(n)
                return n

            first_big = next(x for x in (trace(i) for i in range(1000)) if x > 2)
            print("found:", first_big, "| computed:", log)

            # Infinite sources are fine when consumption is bounded.
            import itertools
            evens = (n for n in itertools.count() if n % 2 == 0)
            print("first 5 evens:", list(itertools.islice(evens, 5)))
            """,
        ),
        Demo(
            code="""
            # Deferred evaluation bites when the source changes underneath.
            data = [1, 2, 3]
            lazy = (x * 10 for x in data)
            eager = [x * 10 for x in data]

            data.append(4)
            data[0] = 100

            print("eager (snapshot at creation):", eager)
            print("lazy  (reads data at consumption):", list(lazy))
            """,
            explain="""
            Only the *outermost iterable* is evaluated when the genexp is
            created — and even then, `data` is captured as a reference, so
            later mutations are visible. Materialise with `list(...)` when you
            need a snapshot.
            """,
        ),
        Predict(
            code="""
            funcs_late = [lambda: i for i in range(3)]
            funcs_bound = [lambda i=i: i for i in range(3)]

            print([f() for f in funcs_late])
            print([f() for f in funcs_bound])
            """,
            answer="""
            [2, 2, 2]
            [0, 1, 2]
            """,
            explain="""
            Closures capture the **variable**, not its value at creation time.
            By the time the lambdas run, `i` is 2. The default-argument trick
            (`i=i`) evaluates `i` eagerly at definition time. `functools.partial`
            is the other standard fix.
            """,
        ),
        Text("""
        ## When *not* to use a comprehension

        - It spans more than about two lines or two `for` clauses — a loop
          reads better.
        - The body has side effects and no useful result. Never write
          `[print(x) for x in xs]`: you build a list of `None` for nothing.
        - You need `try/except` inside — comprehensions cannot contain
          statements.
        - A built-in already does it: `sum`, `any`, `all`, `min`/`max` with
          `key=`, `list(map(...))` for a bare function call.
        """),
        Demo(
            code="""
            rows = [{"n": 3}, {"n": 8}, {"n": 5}]

            print("any :", any(r["n"] > 7 for r in rows))
            print("all :", all(r["n"] > 1 for r in rows))
            print("sum :", sum(r["n"] for r in rows))
            print("max :", max(rows, key=lambda r: r["n"]))
            print("count matching:", sum(1 for r in rows if r["n"] % 2))

            # any/all short-circuit -- they stop at the first decisive element.
            seen = []
            def probe(x):
                seen.append(x)
                return x > 1
            any(probe(x) for x in [0, 1, 2, 3, 4])
            print("any() only looked at:", seen)
            """,
            explain="""
            `sum(1 for ... if ...)` is the idiomatic counter. And note that
            passing a genexp as the *sole* argument to a function needs no
            extra parentheses: `sum(x for x in xs)` is fine.
            """,
        ),
        Exercise(
            slug="pipeline",
            title="A lazy transformation pipeline",
            difficulty="medium",
            brief="""
            Build `pipeline(source, *stages)` that threads an iterable through
            a series of stages **lazily** — nothing may be computed until the
            result is iterated, and the whole thing must work on an infinite
            source.

            Each stage is a tuple:
            - `("map", fn)` — apply `fn` to each item
            - `("filter", pred)` — keep items where `pred(item)` is truthy
            - `("take", n)` — stop after `n` items

            Also write `count_calls(fn)` returning `(wrapped, counter)` where
            `counter` is a one-element list whose `[0]` holds the call count —
            the checks use it to prove your pipeline is really lazy.
            """,
            starter="""
            from itertools import count, islice


            def pipeline(source, *stages):
                ...


            def count_calls(fn):
                ...
            """,
            checks=[
                Check("maps and filters in order", lambda ns: _pl_basic(ns["pipeline"])),
                Check("take limits the output", lambda ns: _pl_take(ns["pipeline"])),
                Check("returns a lazy iterator, not a list", lambda ns: _pl_lazy_type(ns["pipeline"])),
                Check("nothing runs before iteration starts",
                      lambda ns: _pl_deferred(ns["pipeline"], ns["count_calls"])),
                Check("works on an infinite source", lambda ns: _pl_infinite(ns["pipeline"])),
                Check("computes only what take() needs",
                      lambda ns: _pl_minimal(ns["pipeline"], ns["count_calls"])),
            ],
            hints=(
                "`map` and `filter` are already lazy in Python 3; `islice` is the "
                "lazy `take`.",
                "If you write `return [...]` anywhere you have broken laziness.",
                "A `for` loop that rebinds `it = map(fn, it)` composes stages "
                "without consuming anything.",
                "Careful with late binding if you build lambdas in a loop — bind "
                "the stage argument as a default or use `functools.partial`.",
            ),
            solution="""
            from itertools import count, islice

            def pipeline(source, *stages):
                it = iter(source)
                for kind, arg in stages:
                    match kind:
                        case "map":
                            it = map(arg, it)
                        case "filter":
                            it = filter(arg, it)
                        case "take":
                            it = islice(it, arg)
                        case _:
                            raise ValueError(f"unknown stage {kind!r}")
                return it

            def count_calls(fn):
                counter = [0]
                def wrapped(x):
                    counter[0] += 1
                    return fn(x)
                return wrapped, counter
            """,
        ),
        Exercise(
            slug="chunker",
            title="Lazy chunking without itertools.batched",
            difficulty="tricky",
            brief="""
            Implement `chunks(iterable, size, *, pad=None, drop_last=False)`
            yielding **tuples** of length `size`.

            - it must be lazy: a generator, working on infinite input
            - it must consume the source **once** — no `list(iterable)`
            - a short final chunk is yielded as-is by default
            - `drop_last=True` discards a short final chunk
            - `pad=<value>` fills a short final chunk up to `size`
              (`pad` and `drop_last` are mutually exclusive → `ValueError`)
            - `size < 1` raises `ValueError`
            - an empty source yields nothing

            `itertools.batched` exists in 3.12 — the point is to write it.
            """,
            starter="""
            def chunks(iterable, size, *, pad=None, drop_last=False):
                ...
            """,
            checks=[
                Check("even split into tuples", lambda ns: _ch_even(ns["chunks"])),
                Check("short final chunk kept by default", lambda ns: _ch_short(ns["chunks"])),
                Check("drop_last discards the remainder", lambda ns: _ch_drop(ns["chunks"])),
                Check("pad fills the final chunk", lambda ns: _ch_pad(ns["chunks"])),
                Check("rejects bad arguments", lambda ns: _ch_validate(ns["chunks"])),
                Check("lazy: works on an infinite source", lambda ns: _ch_infinite(ns["chunks"])),
                Check("consumes an iterator exactly once", lambda ns: _ch_single_pass(ns["chunks"])),
                Check("empty source yields nothing", lambda ns: _ch_empty(ns["chunks"])),
            ],
            hints=(
                "Validate arguments *before* the first `yield`, or the error will "
                "not surface until someone iterates.",
                "A generator function cannot raise at call time — wrap the "
                "generator in a plain function that validates, then returns it.",
                "`iter(iterable)` once, then accumulate into a list and yield "
                "`tuple(buf)` when it reaches `size`.",
                "Do not forget the leftover buffer after the loop ends.",
            ),
            solution="""
            def chunks(iterable, size, *, pad=None, drop_last=False):
                if size < 1:
                    raise ValueError("size must be at least 1")
                if pad is not None and drop_last:
                    raise ValueError("pad and drop_last are mutually exclusive")

                def generate():
                    buf = []
                    for item in iterable:
                        buf.append(item)
                        if len(buf) == size:
                            yield tuple(buf)
                            buf = []
                    if not buf:
                        return
                    if drop_last:
                        return
                    if pad is not None:
                        buf.extend([pad] * (size - len(buf)))
                    yield tuple(buf)

                return generate()
            """,
        ),
        Text("""
        ## Takeaways

        - `[...]` materialises, `(...)` defers. Generators are one-shot.
        - Comprehensions have their own scope — no leaks, and no access to
          class-level names past the first iterable.
        - `if` after `for` filters; `if/else` before `for` maps.
        - The walrus computes once and binds outward.
        - Closures capture variables, not values — bind with a default
          argument when building callables in a loop.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _pl_basic(pipeline) -> None:
    got = list(pipeline(range(10), ("map", lambda x: x * 2), ("filter", lambda x: x > 10)))
    assert got == [12, 14, 16, 18], got


def _pl_take(pipeline) -> None:
    got = list(pipeline(range(100), ("take", 3)))
    assert got == [0, 1, 2], got
    got2 = list(pipeline(range(10), ("filter", lambda x: x % 2), ("take", 2)))
    assert got2 == [1, 3], got2


def _pl_lazy_type(pipeline) -> None:
    out = pipeline(range(5), ("map", lambda x: x))
    assert not isinstance(out, (list, tuple)), (
        f"pipeline returned an eager {type(out).__name__}; it must stay lazy"
    )
    assert hasattr(out, "__next__"), "the result must be an iterator"


def _pl_deferred(pipeline, count_calls) -> None:
    fn, counter = count_calls(lambda x: x)
    pipeline(range(100), ("map", fn))
    assert counter[0] == 0, f"{counter[0]} calls happened before iteration began"


def _pl_infinite(pipeline) -> None:
    from itertools import count

    got = list(pipeline(count(), ("map", lambda x: x * x), ("take", 4)))
    assert got == [0, 1, 4, 9], got


def _pl_minimal(pipeline, count_calls) -> None:
    from itertools import count

    fn, counter = count_calls(lambda x: x * 2)
    list(pipeline(count(), ("map", fn), ("take", 3)))
    assert counter[0] <= 4, f"computed {counter[0]} items to produce 3"


def _ch_even(chunks) -> None:
    got = list(chunks([1, 2, 3, 4], 2))
    assert got == [(1, 2), (3, 4)], got
    assert all(isinstance(c, tuple) for c in got), "chunks must be tuples"


def _ch_short(chunks) -> None:
    got = list(chunks([1, 2, 3, 4, 5], 2))
    assert got == [(1, 2), (3, 4), (5,)], got


def _ch_drop(chunks) -> None:
    got = list(chunks([1, 2, 3, 4, 5], 2, drop_last=True))
    assert got == [(1, 2), (3, 4)], got
    assert list(chunks([1], 2, drop_last=True)) == []


def _ch_pad(chunks) -> None:
    got = list(chunks([1, 2, 3, 4, 5], 3, pad=0))
    assert got == [(1, 2, 3), (4, 5, 0)], got
    assert list(chunks([1, 2, 3], 3, pad=0)) == [(1, 2, 3)], "exact fit must not pad"


def _ch_validate(chunks) -> None:
    for kwargs in ({}, {"pad": 0}):
        try:
            list(chunks([1, 2], 0, **kwargs))
        except ValueError:
            pass
        else:
            raise AssertionError("size < 1 must raise ValueError")
    try:
        chunks([1, 2], 2, pad=0, drop_last=True)
    except ValueError:
        return
    raise AssertionError("pad + drop_last must raise ValueError")


def _ch_infinite(chunks) -> None:
    from itertools import count, islice

    got = list(islice(chunks(count(), 3), 2))
    assert got == [(0, 1, 2), (3, 4, 5)], got


def _ch_single_pass(chunks) -> None:
    source = iter(range(6))
    got = list(chunks(source, 2))
    assert got == [(0, 1), (2, 3), (4, 5)], got
    assert list(source) == [], "the source iterator should be fully consumed, once"


def _ch_empty(chunks) -> None:
    assert list(chunks([], 3)) == []
    assert list(chunks([], 3, pad=0)) == [], "an empty source must not produce a padded chunk"
