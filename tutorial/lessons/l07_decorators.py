"""Lesson 07 — Decorators."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=7,
    slug="decorators",
    title="Decorators",
    summary="""
    A decorator is a function that takes a function and returns a
    replacement. That is the whole idea — everything else is applying it
    carefully: preserving metadata, handling arguments, stacking, decorating
    methods and classes, and keeping the wrapper introspectable.
    """,
    tags=("decorators", "closures", "functools", "metaprogramming"),
    blocks=[
        Text("""
        ## Desugaring

        ```python
        @decorate
        def f(): ...
        ```

        is exactly

        ```python
        def f(): ...
        f = decorate(f)
        ```

        The decorator runs **once**, at definition time. Whatever it returns
        is bound to the name — it need not even be callable, though it almost
        always is.
        """),
        Demo(
            code="""
            def announce(fn):
                print(f"  [decorating {fn.__name__} at import time]")
                def wrapper(*args, **kwargs):
                    print(f"  [calling {fn.__name__}]")
                    return fn(*args, **kwargs)
                return wrapper

            @announce
            def work(x):
                return x * 2

            print("definition finished")
            print("result:", work(21))
            print("what the name points at now:", work.__name__)
            """,
            explain="""
            Note the last line: the name `work` now refers to `wrapper`. That
            broken `__name__` is why `functools.wraps` exists.
            """,
        ),
        Text("""
        ## `functools.wraps` — never skip it

        `@wraps(fn)` copies `__name__`, `__doc__`, `__qualname__`,
        `__module__`, `__dict__` and `__annotations__` onto the wrapper, and
        sets `__wrapped__ = fn`. That last one is what lets
        `inspect.signature` see through the wrapper.
        """),
        Demo(
            code="""
            import functools
            import inspect

            def bare(fn):
                def wrapper(*a, **k): return fn(*a, **k)
                return wrapper

            def proper(fn):
                @functools.wraps(fn)
                def wrapper(*a, **k): return fn(*a, **k)
                return wrapper

            def target(x: int, y: int = 2) -> int:
                '''Multiply two numbers.'''
                return x * y

            b, p = bare(target), proper(target)
            print(f"{'':10} {'__name__':10} {'signature':22} doc")
            for label, fn in (("bare", b), ("wraps", p)):
                print(f"{label:10} {fn.__name__:10} {str(inspect.signature(fn)):22} {fn.__doc__}")
            print("__wrapped__ points home:", p.__wrapped__ is target)
            """,
        ),
        Question(
            prompt="Which does `functools.wraps` NOT do?",
            choices=[
                "Copy `__name__` and `__doc__`",
                "Set `__wrapped__` on the wrapper",
                "Make the wrapper accept the same arguments as the original",
                "Copy `__annotations__`",
            ],
            answer=2,
            explain="It only copies metadata. The wrapper's real signature is still "
                    "`(*args, **kwargs)` — `inspect.signature` merely *reports* the "
                    "original by following `__wrapped__`.",
        ),
        Text("""
        ## Decorators with arguments: one more layer

        `@deco(x)` means `f = deco(x)(f)`. So a parameterised decorator is a
        function returning a decorator returning a wrapper — three levels.
        """),
        Demo(
            code="""
            import functools
            import time

            def retry(times=3, delay=0.0, exceptions=(Exception,)):
                def decorate(fn):
                    @functools.wraps(fn)
                    def wrapper(*args, **kwargs):
                        last = None
                        for attempt in range(1, times + 1):
                            try:
                                return fn(*args, **kwargs)
                            except exceptions as exc:
                                last = exc
                                print(f"  attempt {attempt} failed: {exc}")
                                if attempt < times:
                                    time.sleep(delay)
                        raise last
                    return wrapper
                return decorate

            calls = []

            @retry(times=3)
            def flaky():
                calls.append(1)
                if len(calls) < 3:
                    raise ConnectionError("network hiccup")
                return "succeeded on attempt " + str(len(calls))

            print(flaky())
            """,
        ),
        Text("""
        ## Supporting both `@deco` and `@deco(...)`

        Users will inevitably write `@deco` without parentheses. Detect it:
        if the decorator is called with a single positional argument that is
        callable and no keywords, it was used bare.
        """),
        Demo(
            code="""
            import functools

            def logged(fn=None, *, prefix="LOG"):
                if fn is None:                       # called as @logged(prefix=...)
                    return functools.partial(logged, prefix=prefix)

                @functools.wraps(fn)                 # called as @logged
                def wrapper(*args, **kwargs):
                    print(f"  [{prefix}] {fn.__name__}{args}")
                    return fn(*args, **kwargs)
                return wrapper

            @logged
            def bare(x): return x

            @logged(prefix="TRACE")
            def parameterised(x): return x

            bare(1)
            parameterised(2)
            """,
            explain="""
            The keyword-only `*` is what makes this safe: `@logged` passes the
            function positionally, and `@logged(prefix=...)` can only pass
            keywords, so the two cases can never be confused.
            """,
        ),
        Predict(
            code="""
            def tag(name):
                def decorate(fn):
                    def wrapper(*a, **k):
                        return f"<{name}>{fn(*a, **k)}</{name}>"
                    return wrapper
                return decorate

            @tag("b")
            @tag("i")
            def text():
                return "hi"

            print(text())
            """,
            answer="""
            <b><i>hi</i></b>
            """,
            explain="""
            Stacked decorators apply **bottom-up**: `text = tag("b")(tag("i")(text))`.
            So `i` wraps the function first and ends up innermost, while `b`
            wraps that and ends up outermost.
            """,
        ),
        Question(
            prompt="In what order do stacked decorators apply?",
            choices=[
                "Top to bottom; the top one is innermost",
                "Bottom to top; the bottom one is innermost",
                "Alphabetically by decorator name",
                "All at once, in an undefined order",
            ],
            answer=1,
            explain="The one closest to `def` runs first and is therefore innermost; "
                    "the topmost decorator wraps everything and runs first at call time.",
        ),
        Text("""
        ## Decorating methods

        A decorator sees the plain function *before* it becomes a bound
        method, so `self` simply arrives as the first positional argument.
        The subtleties are with `classmethod`/`staticmethod`, which must be
        the **outermost** decorators, since they return descriptors, not
        functions.
        """),
        Demo(
            code="""
            import functools

            def trace(fn):
                @functools.wraps(fn)
                def wrapper(*args, **kwargs):
                    where = type(args[0]).__name__ + "." if args else ""
                    print(f"  -> {where}{fn.__name__}")
                    return fn(*args, **kwargs)
                return wrapper

            class Service:
                @trace
                def fetch(self, key):
                    return f"value-for-{key}"

                @classmethod                 # OUTERMOST
                @trace
                def build(cls, name):
                    return cls()

                @staticmethod
                @trace
                def helper(x):
                    return x + 1

                @property
                @trace
                def status(self):
                    return "ok"

            s = Service()
            print(s.fetch("a"))
            print(Service.build("svc"))
            print(Service.helper(1))
            print(s.status)
            """,
            explain="""
            Put `@classmethod` *below* `@trace` and you would be decorating a
            classmethod object — not callable — and get a `TypeError` at call
            time. Rule of thumb: descriptor-producing decorators go on top.
            """,
        ),
        Text("""
        ## Class-based decorators, and decorating classes

        - A **class as decorator** — implement `__call__`. Useful when the
          decorator needs rich state or its own methods.
        - A **decorator applied to a class** — receives and returns a class.
          `dataclass`, `total_ordering`, and registration decorators work
          this way.
        """),
        Demo(
            code="""
            import functools

            class CountCalls:
                def __init__(self, fn):
                    functools.update_wrapper(self, fn)     # the wraps equivalent
                    self.fn = fn
                    self.count = 0

                def __call__(self, *args, **kwargs):
                    self.count += 1
                    return self.fn(*args, **kwargs)

                def reset(self):
                    self.count = 0

            @CountCalls
            def ping():
                return "pong"

            ping(); ping(); ping()
            print(f"{ping.__name__} called {ping.count} times")
            ping.reset()
            print("after reset:", ping.count)
            """,
            explain="""
            One caveat: a class-based decorator on a *method* breaks binding —
            the instance is not passed, because your class is not a descriptor.
            Add `__get__` returning `functools.partial(self.__call__, obj)` if
            you need that.
            """,
        ),
        Demo(
            code="""
            # Decorating a class: a plugin registry.
            REGISTRY = {}

            def register(name):
                def decorate(cls):
                    if name in REGISTRY:
                        raise ValueError(f"duplicate plugin {name!r}")
                    REGISTRY[name] = cls
                    cls.plugin_name = name           # augment the class
                    return cls                       # return it unchanged otherwise
                return decorate

            @register("json")
            class JsonExporter:
                def export(self, data): return "{...}"

            @register("csv")
            class CsvExporter:
                def export(self, data): return "a,b,c"

            print("registry:", REGISTRY)
            print("augmented:", JsonExporter.plugin_name)
            print("still a normal class:", JsonExporter().export({}))
            """,
        ),
        Text("""
        ## The stdlib decorators worth knowing

        | decorator | what it does |
        |---|---|
        | `functools.cache` | unbounded memoisation (3.9+) |
        | `functools.lru_cache(maxsize)` | bounded memoisation with stats |
        | `functools.cached_property` | compute once per instance, store in `__dict__` |
        | `functools.singledispatch` | overload on the first argument's type |
        | `functools.total_ordering` | fill in comparison methods |
        | `contextlib.contextmanager` | generator → context manager |
        | `atexit.register` | run at interpreter shutdown |
        """),
        Demo(
            code="""
            import functools
            import time

            @functools.lru_cache(maxsize=128)
            def slow_square(n):
                time.sleep(0.01)
                return n * n

            start = time.perf_counter()
            [slow_square(i % 10) for i in range(50)]
            elapsed = time.perf_counter() - start
            print(f"50 calls in {elapsed*1000:.0f} ms (only 10 were real)")
            print("stats:", slow_square.cache_info())
            slow_square.cache_clear()
            print("after clear:", slow_square.cache_info())
            """,
            explain="""
            Caveats: arguments must be **hashable**, the cache is shared across
            all callers, and on a method it keeps `self` alive forever — a
            classic memory leak. Prefer `cached_property` on instances.
            """,
        ),
        Demo(
            code="""
            import functools

            @functools.singledispatch
            def describe(value):
                return f"some {type(value).__name__}"

            @describe.register
            def _(value: int):
                return f"the integer {value}"

            @describe.register(list)
            def _(value):
                return f"a list of {len(value)} items"

            @describe.register(str)
            def _(value):
                return f"the string {value!r}"

            for item in (42, "hi", [1, 2, 3], 3.5):
                print(" ", describe(item))
            print("registry:", sorted(c.__name__ for c in describe.registry))
            """,
            explain="""
            `singledispatch` dispatches on the runtime type of the **first**
            argument, honouring the MRO — so registering `Sequence` catches
            tuples and lists both. `singledispatchmethod` does the same for
            methods, dispatching on the first argument after `self`.
            """,
        ),
        Demo(
            code="""
            import functools

            class Dataset:
                def __init__(self, rows): self.rows = rows

                @functools.cached_property
                def summary(self):
                    print("  (computing summary -- expensive)")
                    return {"n": len(self.rows), "total": sum(self.rows)}

            d = Dataset([1, 2, 3])
            print(d.summary)
            print(d.summary, "  <- second access, no recompute")
            print("stored in the instance dict:", "summary" in d.__dict__)
            del d.__dict__["summary"]         # this is how you invalidate it
            print(d.summary)
            """,
            explain="""
            `cached_property` needs a writable `__dict__`, so it cannot be
            used with `__slots__`. It is also **not** thread-safe as of 3.12:
            two threads may both compute the value.
            """,
        ),
        Exercise(
            slug="retry",
            title="A production-grade retry decorator",
            difficulty="tricky",
            brief="""
            Write `retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None)`.

            - retries the wrapped call up to `attempts` times total
            - only catches the listed `exceptions`; anything else propagates
              immediately
            - if every attempt fails, re-raise the **last** exception
            - `backoff(attempt) -> float` is called between attempts with the
              1-based attempt number that just failed; the returned number is
              passed to a `sleep` you must call via the module-level name
              `sleep` so tests can replace it
            - `on_retry(exc, attempt)` is called after each failed attempt
              that will be retried (not after the final one)
            - `attempts < 1` raises `ValueError` at decoration time
            - metadata is preserved, and the wrapper exposes `.attempts`
            - a successful first call must not sleep at all
            """,
            starter="""
            import functools
            import time

            sleep = time.sleep     # tests monkeypatch this name


            def retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None):
                ...
            """,
            checks=[
                Check("returns immediately on success", lambda ns: _rt_success(ns)),
                Check("retries then succeeds", lambda ns: _rt_eventual(ns)),
                Check("re-raises the last exception after exhausting attempts",
                      lambda ns: _rt_exhausted(ns)),
                Check("unlisted exceptions propagate at once", lambda ns: _rt_unlisted(ns)),
                Check("backoff is consulted with 1-based attempt numbers",
                      lambda ns: _rt_backoff(ns)),
                Check("on_retry fires only between attempts", lambda ns: _rt_on_retry(ns)),
                Check("attempts < 1 rejected at decoration time", lambda ns: _rt_validate(ns)),
                Check("metadata preserved and .attempts exposed", lambda ns: _rt_meta(ns)),
            ],
            hints=(
                "Call the sleep through the module global — `sleep(...)`, not "
                "`time.sleep(...)` — so a test can swap it out.",
                "The loop shape is `for attempt in range(1, attempts + 1)` with the "
                "`raise` after the loop, or inside `if attempt == attempts`.",
                "Only sleep when another attempt will actually happen.",
                "`raise` with no argument inside `except` re-raises the current "
                "exception with its original traceback.",
            ),
            solution="""
            import functools
            import time

            sleep = time.sleep

            def retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None):
                if attempts < 1:
                    raise ValueError("attempts must be at least 1")

                def decorate(fn):
                    @functools.wraps(fn)
                    def wrapper(*args, **kwargs):
                        for attempt in range(1, attempts + 1):
                            try:
                                return fn(*args, **kwargs)
                            except exceptions as exc:
                                if attempt == attempts:
                                    raise
                                if on_retry is not None:
                                    on_retry(exc, attempt)
                                if backoff is not None:
                                    sleep(backoff(attempt))
                    wrapper.attempts = attempts
                    return wrapper
                return decorate
            """,
        ),
        Exercise(
            slug="memoize",
            title="A memoiser with TTL, key policy, and stats",
            difficulty="brutal",
            brief="""
            Write `memoize(ttl=None, key=None, maxsize=None)` — a caching
            decorator you would actually ship.

            - caches results keyed by the call arguments
            - `key(*args, **kwargs)` overrides key construction when given
            - `f(1)` and `f(x=1)` must hit the **same** cache entry by default
              (normalise the call with `inspect.signature`)
            - `ttl` in seconds; expired entries recompute. Read the clock via
              the module-level name `now` so tests can control time
            - `maxsize` evicts the **least recently used** entry when exceeded
            - `f.cache_info()` → dict with `hits`, `misses`, `size`
            - `f.cache_clear()` empties the cache and zeroes the counters
            - unhashable arguments must not crash: fall back to computing
              without caching, and count that as a miss
            """,
            starter="""
            import functools
            import inspect
            import time
            from collections import OrderedDict

            now = time.monotonic     # tests monkeypatch this name


            def memoize(ttl=None, key=None, maxsize=None):
                ...
            """,
            checks=[
                Check("caches and reports hits/misses", lambda ns: _mz_basic(ns)),
                Check("positional and keyword calls share an entry", lambda ns: _mz_normalise(ns)),
                Check("custom key function is honoured", lambda ns: _mz_key(ns)),
                Check("entries expire after the ttl", lambda ns: _mz_ttl(ns)),
                Check("maxsize evicts least-recently-used", lambda ns: _mz_lru(ns)),
                Check("cache_clear resets everything", lambda ns: _mz_clear(ns)),
                Check("unhashable arguments degrade gracefully", lambda ns: _mz_unhashable(ns)),
            ],
            hints=(
                "`sig.bind(*args, **kwargs)` + `apply_defaults()` then a tuple of "
                "`sorted(bound.arguments.items())` gives a call-style-independent key.",
                "`OrderedDict.move_to_end(k)` on a hit, and `popitem(last=False)` "
                "to evict, gives you LRU in two lines.",
                "Store `(value, stored_at)` so the TTL check is "
                "`now() - stored_at > ttl`.",
                "Wrap the key construction in `try/except TypeError` to catch "
                "unhashable arguments — and remember to still call the function.",
            ),
            solution="""
            import functools
            import inspect
            import time
            from collections import OrderedDict

            now = time.monotonic

            def memoize(ttl=None, key=None, maxsize=None):
                def decorate(fn):
                    sig = inspect.signature(fn)
                    cache = OrderedDict()
                    stats = {"hits": 0, "misses": 0}

                    def make_key(args, kwargs):
                        if key is not None:
                            return key(*args, **kwargs)
                        bound = sig.bind(*args, **kwargs)
                        bound.apply_defaults()
                        return tuple(sorted(bound.arguments.items()))

                    @functools.wraps(fn)
                    def wrapper(*args, **kwargs):
                        try:
                            cache_key = make_key(args, kwargs)
                            hash(cache_key)
                        except TypeError:
                            stats["misses"] += 1
                            return fn(*args, **kwargs)

                        if cache_key in cache:
                            value, stored_at = cache[cache_key]
                            if ttl is None or now() - stored_at <= ttl:
                                cache.move_to_end(cache_key)
                                stats["hits"] += 1
                                return value
                            del cache[cache_key]

                        stats["misses"] += 1
                        value = fn(*args, **kwargs)
                        cache[cache_key] = (value, now())
                        cache.move_to_end(cache_key)
                        if maxsize is not None and len(cache) > maxsize:
                            cache.popitem(last=False)
                        return value

                    wrapper.cache_info = lambda: {**stats, "size": len(cache)}

                    def cache_clear():
                        cache.clear()
                        stats.update(hits=0, misses=0)
                    wrapper.cache_clear = cache_clear
                    return wrapper
                return decorate
            """,
        ),
        Text("""
        ## Takeaways

        - `@d` is `f = d(f)`, run once at definition time.
        - Always `functools.wraps` — otherwise you destroy introspection.
        - Parameterised decorators are three nested functions; keyword-only
          parameters let one decorator support both call styles.
        - Stacking applies bottom-up; `classmethod`/`staticmethod` go on top.
        - Reach for `cache`, `cached_property`, `singledispatch` before
          writing your own.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
class _Boom(Exception):
    pass


class _Other(Exception):
    pass


def _install_fake_sleep(ns):
    """Replace the module-level `sleep` and return the list of recorded delays."""
    recorded: list[float] = []
    ns["sleep"] = recorded.append
    return recorded


def _rt_success(ns) -> None:
    retry = ns["retry"]
    slept = _install_fake_sleep(ns)
    calls = []

    @retry(attempts=3, backoff=lambda a: 1.0)
    def ok():
        calls.append(1)
        return "fine"

    assert ok() == "fine"
    assert len(calls) == 1, f"called {len(calls)} times, expected 1"
    assert slept == [], f"a successful call must not sleep, slept {slept}"


def _rt_eventual(ns) -> None:
    retry = ns["retry"]
    _install_fake_sleep(ns)
    calls = []

    @retry(attempts=3, exceptions=(_Boom,))
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _Boom("not yet")
        return "recovered"

    assert flaky() == "recovered"
    assert len(calls) == 3, f"expected 3 attempts, got {len(calls)}"


def _rt_exhausted(ns) -> None:
    retry = ns["retry"]
    _install_fake_sleep(ns)
    calls = []

    @retry(attempts=2, exceptions=(_Boom,))
    def always():
        calls.append(1)
        raise _Boom(f"failure #{len(calls)}")

    try:
        always()
    except _Boom as exc:
        assert len(calls) == 2, f"expected 2 attempts, got {len(calls)}"
        assert "failure #2" in str(exc), f"should re-raise the LAST error, got {exc}"
        return
    raise AssertionError("the final failure must propagate")


def _rt_unlisted(ns) -> None:
    retry = ns["retry"]
    _install_fake_sleep(ns)
    calls = []

    @retry(attempts=5, exceptions=(_Boom,))
    def wrong_error():
        calls.append(1)
        raise _Other("not retryable")

    try:
        wrong_error()
    except _Other:
        assert len(calls) == 1, f"unlisted exception was retried {len(calls)} times"
        return
    raise AssertionError("an unlisted exception must propagate")


def _rt_backoff(ns) -> None:
    retry = ns["retry"]
    slept = _install_fake_sleep(ns)
    seen: list[int] = []

    @retry(attempts=3, exceptions=(_Boom,), backoff=lambda attempt: seen.append(attempt) or attempt * 0.5)
    def always():
        raise _Boom("x")

    try:
        always()
    except _Boom:
        pass
    assert seen == [1, 2], f"backoff should see attempts [1, 2], saw {seen}"
    assert slept == [0.5, 1.0], f"expected sleeps [0.5, 1.0], got {slept}"


def _rt_on_retry(ns) -> None:
    retry = ns["retry"]
    _install_fake_sleep(ns)
    events = []

    @retry(attempts=3, exceptions=(_Boom,), on_retry=lambda exc, n: events.append(n))
    def always():
        raise _Boom("x")

    try:
        always()
    except _Boom:
        pass
    assert events == [1, 2], f"on_retry should fire between attempts only, got {events}"


def _rt_validate(ns) -> None:
    retry = ns["retry"]
    try:
        retry(attempts=0)
    except ValueError:
        return
    raise AssertionError("attempts < 1 must raise ValueError at decoration time")


def _rt_meta(ns) -> None:
    retry = ns["retry"]

    @retry(attempts=4)
    def documented(a, b=1):
        """Docs."""
        return a + b

    assert documented.__name__ == "documented", documented.__name__
    assert documented.__doc__ == "Docs."
    assert documented.attempts == 4, f"expected .attempts == 4, got {documented.attempts!r}"
    assert documented(1) == 2


class _Clock:
    def __init__(self): self.t = 1000.0

    def __call__(self): return self.t

    def advance(self, dt): self.t += dt


def _mz_basic(ns) -> None:
    memoize = ns["memoize"]
    calls = []

    @memoize()
    def square(n):
        calls.append(n)
        return n * n

    assert square(4) == 16 and square(4) == 16
    assert calls == [4], f"function ran {len(calls)} times, expected 1"
    info = square.cache_info()
    assert info["hits"] == 1 and info["misses"] == 1, info
    assert info["size"] == 1, info


def _mz_normalise(ns) -> None:
    memoize = ns["memoize"]
    calls = []

    @memoize()
    def f(a, b=2):
        calls.append((a, b))
        return a + b

    f(1)
    f(a=1)
    f(1, 2)
    f(a=1, b=2)
    assert len(calls) == 1, (
        f"all four calls are equivalent and should share one entry; ran {len(calls)} times"
    )


def _mz_key(ns) -> None:
    memoize = ns["memoize"]
    calls = []

    @memoize(key=lambda user, verbose=False: user["id"])
    def load(user, verbose=False):
        calls.append(user["id"])
        return f"data-{user['id']}"

    assert load({"id": 7, "noise": 1}) == "data-7"
    assert load({"id": 7, "noise": 2}) == "data-7"
    assert calls == [7], f"custom key ignored; ran {len(calls)} times"


def _mz_ttl(ns) -> None:
    memoize = ns["memoize"]
    clock = _Clock()
    ns["now"] = clock
    calls = []

    @memoize(ttl=10)
    def f(n):
        calls.append(n)
        return n

    f(1)
    clock.advance(5)
    f(1)
    assert len(calls) == 1, "entry expired too early"
    clock.advance(6)                       # total 11 > ttl 10
    f(1)
    assert len(calls) == 2, "entry should have expired and recomputed"


def _mz_lru(ns) -> None:
    memoize = ns["memoize"]
    ns["now"] = _Clock()
    calls = []

    @memoize(maxsize=2)
    def f(n):
        calls.append(n)
        return n

    f(1); f(2)
    f(1)                     # touch 1 so 2 becomes least-recently-used
    f(3)                     # evicts 2
    assert f.cache_info()["size"] == 2, f.cache_info()
    f(1)
    assert calls == [1, 2, 3], f"1 should still be cached, calls were {calls}"
    f(2)
    assert calls == [1, 2, 3, 2], f"2 should have been evicted, calls were {calls}"


def _mz_clear(ns) -> None:
    memoize = ns["memoize"]
    ns["now"] = _Clock()
    calls = []

    @memoize()
    def f(n):
        calls.append(n)
        return n

    f(1); f(1)
    f.cache_clear()
    info = f.cache_info()
    assert info == {"hits": 0, "misses": 0, "size": 0}, info
    f(1)
    assert len(calls) == 2, "the cache was not actually emptied"


def _mz_unhashable(ns) -> None:
    memoize = ns["memoize"]
    ns["now"] = _Clock()
    calls = []

    @memoize()
    def total(items):
        calls.append(1)
        return sum(items)

    assert total([1, 2, 3]) == 6, "an unhashable argument must still work"
    assert total([1, 2, 3]) == 6
    assert len(calls) == 2, "unhashable arguments cannot be cached"
    assert total.cache_info()["misses"] == 2, total.cache_info()
