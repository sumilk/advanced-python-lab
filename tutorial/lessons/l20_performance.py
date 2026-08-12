"""Lesson 20 — Performance, profiling, and bytecode."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=20,
    slug="performance",
    title="Performance, Profiling, and Bytecode",
    summary="""
    Optimising without measuring is guessing. This lesson is about the
    measuring: `timeit` for microbenchmarks, `cProfile` for finding the
    hotspot, `dis` for understanding why one form is faster than another —
    and then the handful of optimisations that reliably pay off in CPython.
    """,
    tags=("performance", "profiling", "bytecode", "optimisation"),
    blocks=[
        Text("""
        ## Measure first, and measure correctly

        `timeit` exists because naive timing is wrong: it disables the GC,
        repeats to average out noise, and reports the **minimum** — the run
        least polluted by other activity on the machine.

        Rules for honest microbenchmarks:

        - time the smallest thing that matters, but not something the
          compiler can fold away
        - use `number=` big enough that the total is ≥ 0.1 s
        - compare `min()` of several `repeat()` runs, not the mean
        - never benchmark on the first run of a cached function
        """),
        Demo(
            code="""
            import timeit

            setup = "data = list(range(1000))"
            candidates = {
                "list comprehension": "[x * 2 for x in data]",
                "map + lambda      ": "list(map(lambda x: x * 2, data))",
                "for loop + append ": "out = []\\nfor x in data: out.append(x * 2)",
                "list(gen expr)    ": "list(x * 2 for x in data)",
            }

            results = {}
            for label, code in candidates.items():
                times = timeit.repeat(code, setup=setup, number=1000, repeat=5)
                results[label] = min(times)

            fastest = min(results.values())
            for label, t in sorted(results.items(), key=lambda kv: kv[1]):
                print(f"{label}: {t*1000:6.1f} ms   {t/fastest:.2f}x")
            """,
            explain="""
            The comprehension usually wins because it uses a dedicated
            `LIST_APPEND` opcode instead of looking up and calling the
            `.append` method on every iteration.
            """,
        ),
        Text("""
        ## `dis`: reading the bytecode

        `dis.dis(fn)` shows what the compiler actually produced. It is the
        fastest way to settle "which of these two is faster and why".
        """),
        Demo(
            code="""
            import dis

            def with_attribute_lookup(data):
                out = []
                for x in data:
                    out.append(x)          # LOAD_METHOD every iteration
                return out

            def with_local_binding(data):
                out = []
                append = out.append        # hoisted out of the loop
                for x in data:
                    append(x)
                return out

            for fn in (with_attribute_lookup, with_local_binding):
                ops = [i.opname for i in dis.get_instructions(fn)]
                print(f"{fn.__name__:24} {len(ops)} instructions, "
                      f"{ops.count('LOAD_METHOD') + ops.count('LOAD_ATTR')} attribute loads")

            print()
            print("the loop body of the first one:")
            for ins in dis.get_instructions(with_attribute_lookup):
                if ins.opname in {"LOAD_FAST", "LOAD_METHOD", "LOAD_ATTR",
                                  "CALL", "FOR_ITER"}:
                    print(f"   {ins.opname:14} {ins.argrepr}")
            """,
            explain="""
            Read those two counts carefully, because they are equal — and that
            is the lesson. Both functions contain **one** attribute load. What
            differs is *where it sits*: in the first it is inside the loop and
            executes once per item, in the second it executes once before the
            loop and the body calls a plain local.

            Static instruction counts tell you almost nothing on their own.
            The disassembly is useful for asking where an instruction sits
            relative to a loop, not for counting lines — which is why the
            hoisted version is actually the *longer* of the two.

            Note also `LOAD_ATTR` where older write-ups would say
            `LOAD_METHOD`: 3.12 merged the two, and the `NULL|self + append`
            annotation marks the specialised method form. And keep the
            perspective — this hoisting is worth doing in a demonstrably hot
            loop and nowhere else.
            """,
        ),
        Demo(
            code="""
            import dis
            import timeit

            # Constant folding: the compiler does some work for you.
            def folded(): return 60 * 60 * 24
            def literal(): return 86400

            print("folded  :", [i.argrepr for i in dis.get_instructions(folded)
                                 if i.opname.startswith("LOAD_CONST")])
            print("literal :", [i.argrepr for i in dis.get_instructions(literal)
                                 if i.opname.startswith("LOAD_CONST")])
            print("identical bytecode:", folded.__code__.co_code == literal.__code__.co_code)

            # Local variables are array slots; globals are dict lookups.
            GLOBAL_VALUE = 1

            def uses_global():
                total = 0
                for _ in range(1000):
                    total += GLOBAL_VALUE
                return total

            def uses_local(value=1):
                total = 0
                for _ in range(1000):
                    total += value
                return total

            t_global = min(timeit.repeat(uses_global, number=1000, repeat=3))
            t_local = min(timeit.repeat(uses_local, number=1000, repeat=3))
            print()
            print(f"global lookups: {t_global*1000:.1f} ms")
            print(f"local lookups : {t_local*1000:.1f} ms  ({t_global/t_local:.2f}x faster)")
            """,
            explain="""
            `LOAD_FAST` indexes an array; `LOAD_GLOBAL` hashes a string into
            the module dict (with a per-opcode cache since 3.11, which has
            narrowed the gap a lot). Hoisting a global or a method into a
            local before a hot loop is the classic micro-optimisation.
            """,
        ),
        Question(
            prompt="Why is a list comprehension typically faster than an equivalent `for` + `append`?",
            choices=[
                "It runs in C, skipping the interpreter",
                "It uses a dedicated LIST_APPEND opcode instead of repeatedly loading and calling a method",
                "It preallocates the exact final size",
                "It is compiled to a `map` call",
            ],
            answer=1,
            explain="The loop body itself is still interpreted Python. The saving is "
                    "the per-iteration attribute lookup and function call.",
        ),
        Text("""
        ## `cProfile`: find the hotspot before optimising

        A profiler tells you *where* the time goes. Read the columns:

        - `ncalls` — call count (a huge count is often the real problem)
        - `tottime` — time in the function itself, excluding sub-calls
        - `cumtime` — including sub-calls

        Sort by `tottime` to find the code to rewrite; by `cumtime` to find
        the call path to eliminate.
        """),
        Demo(
            code="""
            import cProfile
            import io
            import pstats

            def slow_membership(items, lookups):
                return sum(1 for x in lookups if x in items)   # O(n) per lookup

            def build(n):
                return [i for i in range(n)]

            def workload():
                data = build(4000)
                return slow_membership(data, range(0, 4000, 4))

            profiler = cProfile.Profile()
            profiler.enable()
            workload()
            profiler.disable()

            buffer = io.StringIO()
            stats = pstats.Stats(profiler, stream=buffer).sort_stats("tottime")
            stats.print_stats(4)

            for line in buffer.getvalue().splitlines():
                if line.strip() and not line.startswith(("   Ordered", "   Random")):
                    print(line[:96])
            """,
            explain="""
            `cProfile` adds roughly 30-100% overhead and cannot see inside C
            functions, so treat the *ratios* as meaningful and the absolute
            numbers as not. For line-level detail, `line_profiler`; for
            sampling with almost no overhead in production, `py-spy`.
            """,
        ),
        Text("""
        ## The optimisations that actually pay

        In rough order of expected return:

        1. **Better algorithm / data structure.** `set` membership instead of
           `list`; a dict index instead of a nested loop. Orders of magnitude.
        2. **Do less work.** Cache, memoise, batch, exit early, avoid
           recomputing in a loop.
        3. **Move the loop into C.** `sum`, `min`, `sorted`, `str.join`,
           `bytes`, `array`, `collections`, NumPy.
        4. **Reduce attribute lookups and function calls** in hot loops.
        5. **Use `__slots__`** when you have very many small objects.
        6. Only then: rewrite in C / Cython / Rust.
        """),
        Demo(
            code="""
            import timeit

            # 1. Algorithm: the only change that gives you 1000x.
            haystack = list(range(20_000))
            haystack_set = set(haystack)
            needles = list(range(0, 20_000, 500))

            t_list = min(timeit.repeat(
                lambda: sum(1 for n in needles if n in haystack), number=20, repeat=3))
            t_set = min(timeit.repeat(
                lambda: sum(1 for n in needles if n in haystack_set), number=20, repeat=3))
            print(f"list membership: {t_list*1000:7.2f} ms")
            print(f"set membership : {t_set*1000:7.2f} ms   ({t_list/t_set:,.0f}x)")

            # 3. String building: join vs repeated concatenation.
            words = ["chunk"] * 5000
            t_concat = min(timeit.repeat(
                lambda: "".join(words), number=200, repeat=3))

            def by_plus():
                s = ""
                for w in words:
                    s += w
                return s
            t_plus = min(timeit.repeat(by_plus, number=200, repeat=3))
            print()
            print(f"str.join       : {t_concat*1000:7.2f} ms")
            print(f"repeated +=    : {t_plus*1000:7.2f} ms   ({t_plus/t_concat:.1f}x slower)")
            """,
            explain="""
            Note the order of magnitude. Changing the *algorithm* — a set
            instead of a list — is worth several hundredfold, and no amount of
            micro-optimisation anywhere else in the function will ever reach
            that. Establish the right data structure before tuning a line.

            `join` wins for a structural reason: strings are immutable, so
            `s += w` builds an entirely new string each time and copies
            everything already accumulated, making the total work quadratic in
            the number of pieces. `join` walks the list once, adds up the
            final length, allocates a single buffer and fills it.

            Eight times rather than the thousandfold the theory predicts,
            because CPython cheats: when a string has exactly one reference it
            can sometimes resize in place. Pleasant, fragile, and gone the
            moment anything else holds a reference — do not build on it.
            """,
        ),
        Predict(
            code="""
            import timeit

            n = 100_000
            t_range = timeit.timeit(lambda: sum(range(n)), number=20)
            t_gen = timeit.timeit(lambda: sum(i for i in range(n)), number=20)
            print(t_gen > t_range * 2)
            """,
            answer="""
            True
            """,
            explain="""
            `sum(range(n))` keeps the whole loop inside C. Adding a generator
            expression forces a Python-level frame resume for every single
            element — typically 3-6x slower for doing exactly the same work.
            The lesson: never wrap a C-level iterable in a pass-through
            generator.
            """,
        ),
        Demo(
            code="""
            import sys
            import timeit
            from array import array

            # Right container for the job.
            n = 100_000
            as_list = list(range(n))
            as_array = array("i", range(n))

            print(f"list  of {n:,} ints: {sys.getsizeof(as_list)/1024:8.0f} KiB (+ the int objects)")
            print(f"array of {n:,} ints: {sys.getsizeof(as_array)/1024:8.0f} KiB (packed)")

            # But watch the trade-off: array boxes on every read.
            t_list = min(timeit.repeat(lambda: sum(as_list), number=50, repeat=3))
            t_array = min(timeit.repeat(lambda: sum(as_array), number=50, repeat=3))
            print(f"\\nsum(list) : {t_list*1000:6.1f} ms")
            print(f"sum(array): {t_array*1000:6.1f} ms  <- unboxing costs time")
            print("\\narray wins on memory; NumPy wins on both, if you can depend on it")
            """,
            explain="""
            The memory gap is wider than it looks: the list figure counts only
            its pointer array, while the hundred thousand integer objects it
            points at are charged elsewhere. The `array` stores raw machine
            ints with no per-element object at all.

            And it is slower to sum, which is the part worth understanding.
            Every read from an `array` **boxes** a fresh Python `int`, whereas
            the list's objects already exist and only need their pointers
            followed. Compactness is paid for at every access.

            That trade is precisely what NumPy removes — not by storing data
            more cleverly than `array`, but by keeping whole operations inside
            C so no element is ever boxed. Which is why `array` is a narrow
            tool for holding a lot of numbers you rarely touch one at a time.
            """,
        ),
        Text("""
        ## Where CPython 3.11+ changed the rules

        - **Zero-cost exceptions**: entering a `try` is free; only raising
          costs.
        - **Specialising adaptive interpreter** (PEP 659): hot bytecodes are
          rewritten to type-specialised versions. Consistent types in a hot
          loop now matter for speed.
        - **Inlined Python-to-Python calls**: no new C stack frame, so
          recursion and small helper functions got much cheaper.
        - Cheaper frame objects, lazily created tracebacks.

        The practical consequence: some old folklore ("function calls are
        expensive", "try/except is slow") is now much weaker. Measure on
        *your* version.
        """),
        Demo(
            code="""
            import sys
            import timeit

            print("running on", ".".join(map(str, sys.version_info[:3])))

            def helper(x): return x + 1
            def with_calls(n):
                total = 0
                for i in range(n):
                    total = helper(total)
                return total
            def inline(n):
                total = 0
                for i in range(n):
                    total = total + 1
                return total

            t_call = min(timeit.repeat(lambda: with_calls(20_000), number=20, repeat=3))
            t_inline = min(timeit.repeat(lambda: inline(20_000), number=20, repeat=3))
            print(f"with a function call: {t_call*1000:6.1f} ms")
            print(f"inlined             : {t_inline*1000:6.1f} ms")
            print(f"call overhead       : {(t_call/t_inline - 1)*100:.0f}%")

            # try/except costs nothing until something is raised
            def guarded(n):
                total = 0
                for i in range(n):
                    try:
                        total += i
                    except ValueError:
                        pass
                return total
            def unguarded(n):
                total = 0
                for i in range(n):
                    total += i
                return total

            t_guarded = min(timeit.repeat(lambda: guarded(20_000), number=20, repeat=3))
            t_plain = min(timeit.repeat(lambda: unguarded(20_000), number=20, repeat=3))
            print(f"\\ntry/except in a loop: {t_guarded/t_plain:.2f}x the plain loop")
            """,
            explain="""
            The second number retires a piece of folklore. Since 3.11,
            exception handling is **zero-cost**: entering a `try` emits no
            instructions at all, and the bookkeeping is consulted only when
            something is actually raised. Hence roughly 1.0x here. Hoisting a
            `try` out of a loop for speed is now pure obfuscation — write the
            version that reads better.

            Function calls did *not* become free. 3.11 removed the C-level
            recursion for Python-to-Python calls, which helped, but a call
            still builds a frame and still costs meaningfully against a loop
            body this small.

            The measurement habit matters more than either figure. Both of
            these changed within recent releases, so advice repeated from a
            blog post is worth exactly what `timeit` says it is on the
            interpreter you actually ship.
            """,
        ),
        Question(
            prompt="A profile shows `json.loads` at 60% cumtime, called 50,000 times. What is the best first move?",
            choices=[
                "Rewrite `json.loads` in C",
                "Find out why it is called 50,000 times and call it less — batch, cache, or parse once",
                "Add `__slots__` to the result objects",
                "Switch to threads",
            ],
            answer=1,
            explain="A huge `ncalls` is the signal. Eliminating calls beats making "
                    "each call faster, and `json` is already C.",
        ),
        Exercise(
            slug="optimise",
            title="Make it 50x faster without changing behaviour",
            difficulty="brutal",
            brief="""
            `slow_report(records, wanted_tags)` below is correct but badly
            written. Rewrite it as `fast_report` with **identical** output and
            at least a 50x speedup on the benchmark the checks run.

            The reference implementation, for behaviour you must match:

            ```python
            def slow_report(records, wanted_tags):
                result = []
                for record in records:
                    for tag in record["tags"]:
                        if tag in list(wanted_tags):          # rebuilds a list each time
                            names = ""
                            for other in records:             # O(n^2) inner scan
                                if other["group"] == record["group"]:
                                    names = names + other["name"] + ","
                            result.append({
                                "id": record["id"],
                                "tag": tag,
                                "group_members": names.rstrip(","),
                            })
                            break
                return result
            ```

            Rules:
            - the output list must be **exactly** equal, order included
            - `group_members` is a comma-joined string of the names of every
              record in the same group, **in input order**
            - a record contributes at most one entry, for the *first* of its
              tags that is wanted
            - do not mutate the inputs
            - `wanted_tags` may be any iterable, and may be large

            Write your answer as `fast_report(records, wanted_tags)`.
            """,
            starter="""
            def fast_report(records, wanted_tags):
                ...
            """,
            checks=[
                Check("matches the reference on small input", lambda ns: _op_small(ns)),
                Check("matches on records with no wanted tags", lambda ns: _op_none(ns)),
                Check("first matching tag wins", lambda ns: _op_first(ns)),
                Check("group members are in input order", lambda ns: _op_order(ns)),
                Check("matches the reference on 800 random records", lambda ns: _op_random(ns)),
                Check("inputs are not mutated", lambda ns: _op_pure(ns)),
                Check("at least 50x faster than the reference", lambda ns: _op_speed(ns)),
            ],
            hints=(
                "Three separate problems: rebuilding `list(wanted_tags)` per tag, "
                "the O(n²) inner scan, and string concatenation in a loop.",
                "Convert `wanted_tags` to a `set` once, outside every loop.",
                "Pre-compute a `dict[group] -> ','.join(names)` in a single pass "
                "before the main loop; every record in a group shares the same "
                "string.",
                "`next((t for t in record['tags'] if t in wanted), None)` finds the "
                "first wanted tag without a break-flag.",
                "Once the group strings are pre-computed, the main loop is O(n) and "
                "the whole function is two passes.",
            ),
            solution="""
            def fast_report(records, wanted_tags):
                wanted = set(wanted_tags)

                groups = {}
                for record in records:
                    groups.setdefault(record["group"], []).append(record["name"])
                joined = {group: ",".join(names) for group, names in groups.items()}

                result = []
                for record in records:
                    tag = next((t for t in record["tags"] if t in wanted), None)
                    if tag is not None:
                        result.append({
                            "id": record["id"],
                            "tag": tag,
                            "group_members": joined[record["group"]],
                        })
                return result
            """,
        ),
        Text("""
        ## Takeaways

        - Profile before optimising; `timeit` for micro, `cProfile` for macro.
        - `dis` answers "why is this form faster" definitively.
        - Algorithms and data structures beat every micro-optimisation.
        - Push loops into C: `sum`, `join`, `sorted`, `set`, `collections`.
        - Re-measure on your Python version — 3.11+ invalidated a lot of old
          advice.
        """),
    ],
)


# --------------------------------------------------------------------------
# Reference implementation and check helpers
# --------------------------------------------------------------------------
def _slow_report(records, wanted_tags):
    result = []
    for record in records:
        for tag in record["tags"]:
            if tag in list(wanted_tags):
                names = ""
                for other in records:
                    if other["group"] == record["group"]:
                        names = names + other["name"] + ","
                result.append({
                    "id": record["id"],
                    "tag": tag,
                    "group_members": names.rstrip(","),
                })
                break
    return result


def _dataset(n, seed=0):
    import random

    rng = random.Random(seed)
    tag_pool = [f"tag{i}" for i in range(12)]
    return [
        {
            "id": i,
            "name": f"name{i}",
            "group": f"g{i % 7}",
            "tags": rng.sample(tag_pool, k=rng.randint(0, 4)),
        }
        for i in range(n)
    ]


_SMALL = [
    {"id": 1, "name": "a", "group": "x", "tags": ["red", "blue"]},
    {"id": 2, "name": "b", "group": "y", "tags": ["green"]},
    {"id": 3, "name": "c", "group": "x", "tags": ["blue"]},
    {"id": 4, "name": "d", "group": "x", "tags": []},
]


def _op_small(ns) -> None:
    fast = ns["fast_report"]
    wanted = ["blue", "green"]
    got, want = fast(_SMALL, wanted), _slow_report(_SMALL, wanted)
    assert got == want, f"\nexpected {want}\ngot      {got}"


def _op_none(ns) -> None:
    fast = ns["fast_report"]
    assert fast(_SMALL, []) == [], "no wanted tags should give an empty report"
    assert fast([], ["blue"]) == []


def _op_first(ns) -> None:
    fast = ns["fast_report"]
    records = [{"id": 1, "name": "a", "group": "x", "tags": ["red", "blue", "green"]}]
    got = fast(records, ["green", "blue", "red"])
    assert len(got) == 1, got
    assert got[0]["tag"] == "red", (
        f"the first tag on the record that is wanted should win, got {got[0]['tag']!r}"
    )


def _op_order(ns) -> None:
    fast = ns["fast_report"]
    records = [
        {"id": 1, "name": "zeta", "group": "g", "tags": ["t"]},
        {"id": 2, "name": "alpha", "group": "g", "tags": ["t"]},
    ]
    got = fast(records, ["t"])
    assert got[0]["group_members"] == "zeta,alpha", (
        f"members must follow input order, got {got[0]['group_members']!r}"
    )


def _op_random(ns) -> None:
    fast = ns["fast_report"]
    records = _dataset(800, seed=7)
    wanted = ["tag1", "tag3", "tag5", "tag9"]
    got, want = fast(records, wanted), _slow_report(records, wanted)
    assert got == want, "output differs from the reference on the random dataset"


def _op_pure(ns) -> None:
    import copy

    fast = ns["fast_report"]
    records = copy.deepcopy(_SMALL)
    snapshot = copy.deepcopy(records)
    wanted = ["blue"]
    fast(records, wanted)
    assert records == snapshot, "the input records were modified"
    assert wanted == ["blue"], "the wanted_tags argument was modified"


def _op_speed(ns) -> None:
    import time

    fast = ns["fast_report"]
    records = _dataset(1400, seed=11)
    wanted = [f"tag{i}" for i in range(0, 12, 2)]

    assert fast(records, wanted) == _slow_report(records, wanted), (
        "correctness first: the output does not match the reference"
    )

    start = time.perf_counter()
    _slow_report(records, wanted)
    slow_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(5):
        fast(records, wanted)
    fast_time = (time.perf_counter() - start) / 5

    speedup = slow_time / max(fast_time, 1e-9)
    assert speedup >= 50, (
        f"only {speedup:.1f}x faster ({slow_time*1000:.0f} ms -> "
        f"{fast_time*1000:.2f} ms). Look for the O(n^2) scan and the "
        f"per-iteration list() rebuild."
    )
