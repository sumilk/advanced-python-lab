"""Lesson 05 — Iterators, generators, and the coroutine machinery."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=5,
    slug="iterators",
    title="Iterators and Generators",
    summary="""
    `for` is a thin wrapper over two method calls. Once you can implement the
    iterator protocol by hand, generators stop being magic — they are just a
    compiler-written iterator whose state is a suspended stack frame. This
    lesson goes all the way to `send`, `throw`, `close`, and `yield from`,
    which is also the machinery `await` is built on.
    """,
    tags=("iterators", "generators", "coroutines", "laziness"),
    blocks=[
        Text("""
        ## The protocol

        - **iterable** — has `__iter__()` returning an iterator
        - **iterator** — has `__next__()` and an `__iter__()` returning `self`

        `for x in obj:` desugars to roughly:

        ```python
        it = iter(obj)              # calls obj.__iter__()
        while True:
            try:
                x = next(it)        # calls it.__next__()
            except StopIteration:
                break
            ...body...
        ```

        Every iterator is an iterable; the reverse is false. A `list` is an
        iterable that hands out a *fresh* iterator each time — which is why
        you can loop over it twice.
        """),
        Demo(
            code="""
            nums = [1, 2, 3]
            it1, it2 = iter(nums), iter(nums)
            print("independent iterators:", next(it1), next(it1), "|", next(it2))
            print("iterator is its own iterable:", iter(it1) is it1)

            # An iterator, hand-rolled.
            class Countdown:
                def __init__(self, start): self.start = start
                def __iter__(self):
                    return CountdownIterator(self.start)     # fresh state each time

            class CountdownIterator:
                def __init__(self, n): self.n = n
                def __iter__(self): return self
                def __next__(self):
                    if self.n <= 0:
                        raise StopIteration
                    self.n -= 1
                    return self.n + 1

            c = Countdown(3)
            print("pass 1:", list(c))
            print("pass 2:", list(c), "  <- reusable because __iter__ makes a new one")
            """,
            explain="""
            Splitting *iterable* from *iterator* is what makes a container
            re-iterable. If a class returns `self` from `__iter__` and mutates
            its own state in `__next__`, it is single-use — like a file object
            or a generator.
            """,
        ),
        Predict(
            code="""
            class OneShot:
                def __init__(self, n): self.n = n
                def __iter__(self): return self
                def __next__(self):
                    if self.n <= 0: raise StopIteration
                    self.n -= 1
                    return self.n

            s = OneShot(3)
            print(list(s))
            print(list(s))
            print(any(x > 100 for x in OneShot(3)))
            """,
            answer="""
            [2, 1, 0]
            []
            False
            """,
            explain="""
            `__iter__` returning `self` means the second `list()` resumes an
            already-exhausted iterator and gets nothing — no error, just empty.
            Silent emptiness is the signature bug of one-shot iterables.
            """,
        ),
        Text("""
        ## `iter()` has a second form

        `iter(callable, sentinel)` builds an iterator that calls `callable()`
        repeatedly until it returns `sentinel`. It is the neat way to drain
        anything with a "read one" API.
        """),
        Demo(
            code="""
            import io

            stream = io.StringIO("alpha\\nbeta\\ngamma\\n")
            # Call readline() until it returns "" (EOF).
            for line in iter(stream.readline, ""):
                print("line:", line.strip())

            # Same trick over a queue-like object.
            pending = [3, 1, 4, None, 5]
            pop = iter(pending).__next__
            print("until None:", list(iter(pop, None)))
            """,
        ),
        Text("""
        ## Generators: iterators the compiler writes for you

        A function containing `yield` is a **generator function**. Calling it
        runs no body code at all — it returns a generator object. Each `next()`
        runs to the following `yield` and suspends, keeping locals and the
        instruction pointer alive.
        """),
        Demo(
            code="""
            import inspect

            def gen():
                print("  [body starts]")
                x = yield 1
                print("  [resumed with]", x)
                yield 2
                print("  [body ends]")

            g = gen()
            print("calling gen() ran nothing:", type(g).__name__, inspect.getgeneratorstate(g))
            print("next ->", next(g), inspect.getgeneratorstate(g))
            print("next ->", next(g))
            try:
                next(g)
            except StopIteration as stop:
                print("StopIteration, value =", stop.value,
                      "| state:", inspect.getgeneratorstate(g))
            """,
            explain="""
            States are `GEN_CREATED` → `GEN_SUSPENDED` → `GEN_RUNNING` →
            `GEN_CLOSED`. `inspect.getgeneratorstate` and
            `inspect.getgeneratorlocals` are excellent debugging tools that
            almost nobody knows about.
            """,
        ),
        Demo(
            code="""
            # `return` in a generator sets StopIteration.value -- how a
            # generator reports a final result rather than a stream item.
            def parse(tokens):
                collected = []
                for tok in tokens:
                    if tok == "STOP":
                        return len(collected)          # becomes .value
                    collected.append(tok)
                    yield tok.upper()
                return len(collected)

            g = parse(["a", "b", "STOP", "c"])
            print("yielded:", list(g))

            g2 = parse(["a", "b", "STOP", "c"])
            try:
                while True:
                    next(g2)
            except StopIteration as stop:
                print("returned value:", stop.value)
            """,
            explain="""
            `list(g)` throws the return value away — only `yield from` and
            manual `next()` can see it. `await` uses exactly this channel to
            deliver a coroutine's result.
            """,
        ),
        Question(
            prompt="What does calling a generator function do?",
            choices=[
                "Runs the body until the first `yield`",
                "Runs the entire body and collects the yields into a list",
                "Runs nothing; it returns a generator object",
                "Raises unless you iterate it immediately",
            ],
            answer=2,
            explain="Not a single statement of the body executes until the first "
                    "`next()`. This is why validation in a generator function silently "
                    "does nothing until someone iterates.",
        ),
        Text("""
        ## `yield from`: delegation, not just a loop

        `yield from sub` is *almost* `for x in sub: yield x`, but it also:

        - forwards `send()` values into the sub-generator
        - forwards `throw()` exceptions into it
        - propagates `close()`
        - evaluates to the sub-generator's **return value**

        That full-duplex delegation is what made `asyncio` possible before
        `async`/`await` had syntax.
        """),
        Demo(
            code="""
            def leaf(name):
                total = 0
                while True:
                    got = yield
                    if got is None:
                        return total          # finished: report the sum
                    print(f"  {name} received {got}")
                    total += got

            def middle():
                subtotal = yield from leaf("leaf")     # captures the return value
                print("  middle saw subtotal:", subtotal)
                yield subtotal

            m = middle()
            next(m)                 # prime it
            m.send(10)
            m.send(5)
            print("final:", m.send(None))
            """,
            explain="""
            `send(x)` resumes the generator, makes the paused `yield` evaluate
            to `x`, and returns the next yielded value. `next(g)` is exactly
            `g.send(None)` — which is why a generator must be *primed* before
            you can send it a real value.
            """,
        ),
        Demo(
            code="""
            # Flattening arbitrarily nested structures -- the classic yield from.
            def flatten(obj):
                if isinstance(obj, (str, bytes)):
                    yield obj                       # strings are iterable: stop here
                    return
                try:
                    iterator = iter(obj)
                except TypeError:
                    yield obj
                    return
                for item in iterator:
                    yield from flatten(item)

            nested = [1, [2, [3, [4, [5]]]], "text", (6, {7, 8})]
            print(list(flatten(nested)))
            """,
        ),
        Text("""
        ## `throw` and `close`: exceptions travel inward

        - `g.throw(Exc)` raises `Exc` **at the paused `yield`**, so the
          generator can catch it and carry on.
        - `g.close()` throws `GeneratorExit` there. The generator must not
          yield again — doing so raises `RuntimeError`.
        - `finally` blocks in a generator run on close, which is what makes
          `@contextmanager` (lesson 11) work.
        """),
        Demo(
            code="""
            def resilient():
                results = []
                try:
                    while True:
                        try:
                            item = yield
                            results.append(item)
                        except ValueError as exc:
                            print("  caught and continuing:", exc)
                finally:
                    print("  cleanup ran, collected:", results)

            g = resilient()
            next(g)
            g.send("a")
            g.throw(ValueError("bad item"))     # generator survives
            g.send("b")
            g.close()                           # triggers the finally
            print("state after close:", g.gi_frame is None)
            """,
        ),
        Demo(
            code="""
            # Garbage collection also closes generators -- so `finally` runs
            # even if you just walk away.
            def leaky():
                try:
                    yield 1
                    yield 2
                finally:
                    print("  finally ran during cleanup")

            g = leaky()
            print("got:", next(g))
            del g                    # refcount hits zero -> close() -> finally
            print("done")
            """,
            explain="""
            Do not rely on this for releasing scarce resources: on PyPy or with
            reference cycles it may be delayed. Use a `with` block *inside* the
            generator, or `contextlib.closing`, when the cleanup matters.
            """,
        ),
        Question(
            prompt="A paused generator receives `g.close()`. What happens inside?",
            choices=[
                "`StopIteration` is raised at the paused `yield`",
                "`GeneratorExit` is raised at the paused `yield`; `finally` blocks run",
                "The frame is discarded immediately with no cleanup",
                "`__del__` is called on the generator",
            ],
            answer=1,
            explain="`GeneratorExit` inherits from `BaseException` — so a bare "
                    "`except Exception:` inside the generator will not swallow it.",
        ),
        Text("""
        ## Generator pipelines

        Chained generators form a streaming pipeline: each stage pulls one
        item at a time from the previous one. Memory stays flat regardless of
        input size, and any stage can stop the whole chain early.
        """),
        Demo(
            code="""
            def read_lines(text):
                for line in text.splitlines():
                    yield line

            def strip_comments(lines):
                for line in lines:
                    stripped = line.split("#", 1)[0].strip()
                    if stripped:
                        yield stripped

            def parse_pairs(lines):
                for line in lines:
                    key, _, value = line.partition("=")
                    yield key.strip(), value.strip()

            def coerce(pairs):
                for key, value in pairs:
                    if value.isdigit():
                        value = int(value)
                    elif value.lower() in {"true", "false"}:
                        value = value.lower() == "true"
                    yield key, value

            config_text = '''
            # server settings
            host = localhost
            port = 8080          # the http port
            debug = true

            retries = 3
            '''

            pipeline = coerce(parse_pairs(strip_comments(read_lines(config_text))))
            print(dict(pipeline))
            """,
            explain="""
            Each stage is independently testable and reusable, nothing is
            buffered, and swapping `read_lines(text)` for a file object streams
            a 100 GB config without changing another line.
            """,
        ),
        Text("""
        ## `itertools.tee`, and why you usually should not

        Need two passes over a one-shot iterator? `tee` buffers everything one
        branch has seen but the other has not. If the branches drift far apart,
        `tee` quietly holds the entire stream in memory. Often `list()` is more
        honest.
        """),
        Demo(
            code="""
            from itertools import tee

            source = iter(range(6))
            a, b = tee(source, 2)
            print("branch a:", list(a))
            print("branch b:", list(b), "  <- replayed from tee's buffer")
            print("source is exhausted:", list(source))

            # Do not touch the original after tee-ing:
            src2 = iter(range(6))
            c, d = tee(src2, 2)
            next(src2)                    # steals an item from under tee
            print("after stealing:", list(c), list(d))
            """,
        ),
        Exercise(
            slug="peekable",
            title="A peekable iterator wrapper",
            difficulty="medium",
            brief="""
            Implement `Peekable(iterable)` — an iterator that can look one item
            ahead without consuming it. This is the core primitive of every
            hand-written parser.

            - `peek()` → the next item without advancing
            - `peek(default)` → `default` instead of raising at the end
            - `peek()` at the end with no default raises `StopIteration`
            - `next(p)` returns the peeked item, then moves on
            - `bool(p)` → True while items remain (must not consume one)
            - it is an iterator: `iter(p) is p`, works in a `for` loop
            - it must never pull more than one item ahead of the consumer
            """,
            starter="""
            _MISSING = object()


            class Peekable:
                def __init__(self, iterable):
                    ...
            """,
            checks=[
                Check("peek does not advance", lambda ns: _pk_peek(ns["Peekable"])),
                Check("iterates fully and in order", lambda ns: _pk_iterate(ns["Peekable"])),
                Check("peek at the end: default and StopIteration", lambda ns: _pk_end(ns["Peekable"])),
                Check("truthiness without consuming", lambda ns: _pk_bool(ns["Peekable"])),
                Check("is a proper iterator", lambda ns: _pk_protocol(ns["Peekable"])),
                Check("reads at most one item ahead", lambda ns: _pk_lookahead(ns["Peekable"])),
                Check("handles an empty source", lambda ns: _pk_empty(ns["Peekable"])),
            ],
            hints=(
                "Keep a `_cache` slot holding either a sentinel or the buffered item.",
                "`None` is a legitimate stream value — use a unique sentinel object, "
                "not `None`, to mean 'nothing buffered'.",
                "`__bool__` is easiest as `try: self.peek() / except StopIteration: "
                "return False`. Passing your own sentinel as the *default* will not "
                "work — think about what `default is _MISSING` then evaluates to.",
                "In `__next__`, return the cached item and reset the cache *before* "
                "returning, or you will hand out the same item twice.",
            ),
            solution="""
            _MISSING = object()

            class Peekable:
                def __init__(self, iterable):
                    self._it = iter(iterable)
                    self._cache = _MISSING

                def __iter__(self):
                    return self

                def __next__(self):
                    if self._cache is not _MISSING:
                        item, self._cache = self._cache, _MISSING
                        return item
                    return next(self._it)

                def peek(self, default=_MISSING):
                    if self._cache is _MISSING:
                        try:
                            self._cache = next(self._it)
                        except StopIteration:
                            if default is _MISSING:
                                raise
                            return default
                    return self._cache

                def __bool__(self):
                    try:
                        self.peek()
                    except StopIteration:
                        return False
                    return True
            """,
        ),
        Exercise(
            slug="running-agg",
            title="A send()-driven running aggregator",
            difficulty="brutal",
            brief="""
            Write the generator `aggregator()` — a *coroutine* that consumes
            numbers via `send()` and yields the running state after each one.

            State dict: `{"count", "total", "mean", "min", "max", "error"}`.

            Protocol:
            - after priming with `next(agg)`, each `agg.send(x)` returns the
              updated state; `mean`/`min`/`max` are `None` while `count == 0`
            - sending `"reset"` clears everything back to the empty state
            - sending a non-numeric value leaves the statistics **unchanged**
              and yields a state whose `error` is `"cannot aggregate <repr>"`;
              the next good value clears `error` back to `None`
            - `bool` must be rejected as non-numeric even though
              `isinstance(True, int)` is True
            - `agg.throw(ValueError)` is caught inside: the generator yields
              its current state and keeps going
            - on `close()`, a `finally` block appends the final count to the
              module-level list `CLOSED_WITH`

            Then write `feed(agg, values)` that primes if needed, sends every
            value, and returns the last state dict.

            > **Why report the error through the yielded value instead of
            > raising it?** Because an exception that propagates *out* of a
            > generator frame terminates that generator for good — there is no
            > "raise into the caller and stay alive". `throw()` works in the
            > other direction: it raises *at* the paused `yield`, where an
            > `except` inside the body can absorb it. Keeping a coroutine
            > alive across bad input therefore means yielding the error, not
            > raising it.
            """,
            starter="""
            CLOSED_WITH = []


            def aggregator():
                ...


            def feed(agg, values):
                ...
            """,
            checks=[
                Check("running stats after each send", lambda ns: _ag_running(ns["aggregator"])),
                Check("reset clears state", lambda ns: _ag_reset(ns["aggregator"])),
                Check("bad input is reported without losing state",
                      lambda ns: _ag_bad_input(ns["aggregator"])),
                Check("throw() is absorbed and state survives", lambda ns: _ag_throw(ns["aggregator"])),
                Check("close() records the final count",
                      lambda ns: _ag_close(ns["aggregator"], ns["CLOSED_WITH"])),
                Check("feed() drives the coroutine", lambda ns: _ag_feed(ns["aggregator"], ns["feed"])),
            ],
            hints=(
                "The shape is `while True:` wrapping `try: value = yield state` "
                "with `except ValueError: continue` attached to that `try`.",
                "Build the state dict from a small closure so you never forget a key.",
                "`bool` is a subclass of `int`, so `isinstance(True, (int, float))` "
                "is True — you need an explicit `not isinstance(value, bool)`.",
                "Wrap the whole `while` in `try: ... finally: CLOSED_WITH.append(count)`; "
                "`close()` raises GeneratorExit at the yield and the finally runs.",
                "`feed` can check `inspect.getgeneratorstate(agg) == 'GEN_CREATED'` "
                "to decide whether to prime.",
            ),
            solution="""
            CLOSED_WITH = []

            def aggregator():
                count = total = 0
                lo = hi = None
                error = None

                def state():
                    return {
                        "count": count,
                        "total": total,
                        "mean": total / count if count else None,
                        "min": lo,
                        "max": hi,
                        "error": error,
                    }

                try:
                    while True:
                        try:
                            value = yield state()
                        except ValueError:
                            continue              # absorbed: loop re-yields state
                        if value == "reset":
                            count = total = 0
                            lo = hi = None
                            error = None
                            continue
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            error = f"cannot aggregate {value!r}"
                            continue              # statistics deliberately untouched
                        error = None
                        count += 1
                        total += value
                        lo = value if lo is None else min(lo, value)
                        hi = value if hi is None else max(hi, value)
                finally:
                    CLOSED_WITH.append(count)

            def feed(agg, values):
                import inspect
                if inspect.getgeneratorstate(agg) == "GEN_CREATED":
                    next(agg)
                last = None
                for value in values:
                    last = agg.send(value)
                return last
            """,
        ),
        Text("""
        ## Takeaways

        - `iter()` + `__next__()` + `StopIteration` is the whole protocol.
        - Separate the iterable from the iterator to stay re-iterable.
        - A generator function returns a generator; the body runs lazily.
        - `send`/`throw`/`close` make generators two-way; `yield from`
          forwards all three and captures the return value.
        - Pipelines of generators stream in constant memory.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _pk_peek(Peekable) -> None:
    p = Peekable([1, 2, 3])
    assert p.peek() == 1
    assert p.peek() == 1, "peek twice must give the same item"
    assert next(p) == 1
    assert p.peek() == 2


def _pk_iterate(Peekable) -> None:
    assert list(Peekable("abc")) == ["a", "b", "c"]
    p = Peekable([1, 2, 3])
    p.peek()
    assert list(p) == [1, 2, 3], "a peeked item must still be yielded"


def _pk_end(Peekable) -> None:
    p = Peekable([1])
    next(p)
    assert p.peek("done") == "done"
    try:
        p.peek()
    except StopIteration:
        return
    raise AssertionError("peek() past the end with no default must raise StopIteration")


def _pk_bool(Peekable) -> None:
    p = Peekable([1])
    assert bool(p) is True
    assert bool(p) is True, "bool must not consume"
    assert next(p) == 1
    assert bool(p) is False


def _pk_protocol(Peekable) -> None:
    p = Peekable([1, 2])
    assert iter(p) is p, "__iter__ must return self"
    assert [x for x in Peekable([4, 5])] == [4, 5]


def _pk_lookahead(Peekable) -> None:
    pulled = []

    def source():
        for i in range(5):
            pulled.append(i)
            yield i

    p = Peekable(source())
    p.peek()
    assert pulled == [0], f"peek pulled {pulled}, should have pulled exactly one"
    next(p)
    assert pulled == [0], f"next() after peek should not pull again, pulled {pulled}"
    next(p)
    assert pulled == [0, 1], f"pulled {pulled}"


def _pk_empty(Peekable) -> None:
    p = Peekable([])
    assert not p
    assert p.peek(None) is None
    assert list(p) == []


def _ag_running(aggregator) -> None:
    agg = aggregator()
    primed = next(agg)
    assert primed["count"] == 0 and primed["mean"] is None, f"initial state wrong: {primed}"
    s1 = agg.send(10)
    assert s1 == {"count": 1, "total": 10, "mean": 10.0, "min": 10,
                  "max": 10, "error": None}, s1
    s2 = agg.send(20)
    assert s2["count"] == 2 and s2["total"] == 30 and s2["mean"] == 15.0, s2
    s3 = agg.send(-5)
    assert s3["min"] == -5 and s3["max"] == 20, s3
    agg.close()


def _ag_reset(aggregator) -> None:
    agg = aggregator()
    next(agg)
    agg.send(5)
    cleared = agg.send("reset")
    assert cleared == {"count": 0, "total": 0, "mean": None, "min": None,
                       "max": None, "error": None}, cleared
    after = agg.send(3)
    assert after["count"] == 1 and after["total"] == 3, after
    agg.close()


def _ag_bad_input(aggregator) -> None:
    agg = aggregator()
    next(agg)
    agg.send(4)
    bad = agg.send("nonsense")
    assert bad["error"] == "cannot aggregate 'nonsense'", f"error not reported: {bad}"
    assert bad["count"] == 1 and bad["total"] == 4, f"statistics were disturbed: {bad}"

    rejected = agg.send(True)
    assert rejected["error"] is not None, "bool must be rejected as non-numeric"
    assert rejected["count"] == 1, "a rejected bool must not be counted"

    good = agg.send(6)
    assert good["error"] is None, "a good value should clear the error"
    assert good["count"] == 2 and good["total"] == 10, good
    agg.close()


def _ag_throw(aggregator) -> None:
    agg = aggregator()
    next(agg)
    agg.send(7)
    state = agg.throw(ValueError("transient"))
    assert state["count"] == 1 and state["total"] == 7, f"state lost on throw: {state}"
    assert agg.send(3)["count"] == 2, "generator should continue after throw"
    agg.close()


def _ag_close(aggregator, closed_with) -> None:
    before = len(closed_with)
    agg = aggregator()
    next(agg)
    agg.send(1)
    agg.send(2)
    agg.close()
    assert len(closed_with) == before + 1, "close() should append exactly one entry"
    assert closed_with[-1] == 2, f"expected final count 2, recorded {closed_with[-1]}"


def _ag_feed(aggregator, feed) -> None:
    agg = aggregator()
    last = feed(agg, [1, 2, 3])
    assert last["count"] == 3 and last["total"] == 6 and last["mean"] == 2.0, last
    agg2 = aggregator()
    next(agg2)                       # already primed: feed must not double-prime
    last2 = feed(agg2, [4])
    assert last2["count"] == 1, f"feed mishandled an already-primed generator: {last2}"
    agg.close()
    agg2.close()
