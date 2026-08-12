"""Lesson 11 — Context managers."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=11,
    slug="context",
    title="Context Managers",
    summary="""
    `with` is Python's answer to "this must be undone, whatever happens".
    The protocol is two methods, but the details — what `__exit__` returns,
    how exceptions are suppressed, reentrancy, dynamic nesting with
    `ExitStack` — are where the real power and the real bugs live.
    """,
    tags=("context-managers", "cleanup", "contextlib", "raii"),
    blocks=[
        Text("""
        ## The protocol

        ```python
        with expr as target:
            body
        ```

        desugars to approximately:

        ```python
        mgr = expr
        value = type(mgr).__enter__(mgr)
        try:
            target = value
            body
        except BaseException as exc:
            if not type(mgr).__exit__(mgr, type(exc), exc, exc.__traceback__):
                raise
        else:
            type(mgr).__exit__(mgr, None, None, None)
        ```

        Two things to internalise:

        - `as target` binds whatever `__enter__` **returns** — not the manager
          (unless it returns `self`).
        - a **truthy** return from `__exit__` **swallows** the exception.
          Returning `True` by accident is a classic silent-failure bug.
        """),
        Demo(
            code="""
            class Trace:
                def __init__(self, name, suppress=False):
                    self.name, self.suppress = name, suppress
                def __enter__(self):
                    print(f"  enter {self.name}")
                    return f"<{self.name} resource>"
                def __exit__(self, exc_type, exc, tb):
                    print(f"  exit {self.name}: exc_type={exc_type.__name__ if exc_type else None}")
                    return self.suppress

            with Trace("normal") as resource:
                print("  body sees:", resource)

            print()
            with Trace("swallower", suppress=True):
                raise ValueError("this vanishes")
            print("execution continues -- the exception was suppressed")

            print()
            try:
                with Trace("propagator"):
                    raise ValueError("this escapes")
            except ValueError as exc:
                print("caught outside:", exc)
            """,
            explain="""
            Two things to take from the trace. `__enter__`'s **return value**
            is what `as` binds, and it need not be the manager — here it is a
            string, just as `open()` hands back the file and a lock hands back
            `None`. And `exit` runs in all three cases; that is the guarantee
            you are buying.

            The decisive part is `__exit__`'s return value: truthy
            **suppresses** the exception, anything falsy lets it propagate.
            `None` is falsy, which is why cleanup-only managers get the right
            behaviour by simply not returning. The corresponding trap is
            real — a stray `return True` at the end of an `__exit__` swallows
            every error raised in the body, and nothing anywhere reports it.
            """,
        ),
        Predict(
            code="""
            class Silent:
                def __enter__(self): return self
                def __exit__(self, *exc_info):
                    print("cleaning up")
                    return True          # <-- probably a mistake

            def compute():
                with Silent():
                    raise RuntimeError("boom")
                return "fell through"

            print(compute())
            """,
            answer="""
            cleaning up
            fell through
            """,
            explain="""
            The exception was swallowed and execution resumed **after** the
            `with` block, so the function returned normally. Unless you are
            deliberately writing a `suppress`-like manager, end `__exit__`
            with an explicit `return False` — or just no return at all.
            """,
        ),
        Question(
            prompt="What does a `with` statement bind to the `as` target?",
            choices=[
                "The context manager object itself, always",
                "Whatever `__enter__` returns",
                "The result of the `with` body",
                "`None`, unless `__exit__` returns a value",
            ],
            answer=1,
            explain="Many managers `return self`, which is why the distinction is easy "
                    "to miss — but `open()` returns a file, and `lock.acquire()`-style "
                    "managers often return `None`.",
        ),
        Text("""
        ## `@contextmanager`: a generator with one yield

        `contextlib.contextmanager` turns a generator into a manager:
        everything before `yield` is setup, the yielded value becomes the `as`
        target, and everything after is teardown.

        The catch: if the body raises, the exception is thrown **into the
        generator at the `yield`**. So a bare `yield` with cleanup after it
        will *skip* the cleanup on error — you need `try/finally`.
        """),
        Demo(
            code="""
            from contextlib import contextmanager

            @contextmanager
            def broken(name):
                print(f"  setup {name}")
                yield name
                print(f"  teardown {name}   <- skipped on error")

            @contextmanager
            def correct(name):
                print(f"  setup {name}")
                try:
                    yield name
                finally:
                    print(f"  teardown {name}   <- always runs")

            for manager in (broken, correct):
                print(manager.__name__ + ":")
                try:
                    with manager("res"):
                        raise ValueError("failure in the body")
                except ValueError:
                    print("  (exception propagated)")
                print()
            """,
            explain="""
            `broken` never prints its teardown. Under `@contextmanager` the
            exception from the body is **thrown into the generator at the
            `yield`** — the `throw` mechanism from lesson 05 — so with nothing
            to catch it the generator dies on that line and everything after
            it is skipped.

            This is why the `try/finally` is not a stylistic preference: it is
            the only thing that makes teardown happen on the failure path,
            which is the path you wrote the manager for. The rule is easy to
            apply — **if there is code after the `yield`, it belongs in a
            `finally`**.
            """,
        ),
        Demo(
            code="""
            from contextlib import contextmanager

            # Suppressing from a generator-based manager = swallow the exception.
            @contextmanager
            def tolerate(*exc_types):
                try:
                    yield
                except exc_types:
                    print("  tolerated")

            with tolerate(ZeroDivisionError):
                1 / 0
            print("continued")

            # Handing back a value and cleaning up conditionally:
            @contextmanager
            def transaction(db):
                db.append("BEGIN")
                try:
                    yield db
                except Exception:
                    db.append("ROLLBACK")
                    raise
                else:
                    db.append("COMMIT")

            log = []
            with transaction(log) as t:
                t.append("INSERT 1")
            print(log)

            log2 = []
            try:
                with transaction(log2) as t:
                    t.append("INSERT 2")
                    raise RuntimeError("constraint violated")
            except RuntimeError:
                pass
            print(log2)
            """,
            explain="""
            Since the exception surfaces *at the yield*, an ordinary `except`
            in the generator suppresses it — this is the generator-shaped
            equivalent of returning `True` from `__exit__`, and it deserves
            the same suspicion. `tolerate` catches only the types it was
            given, which is the version worth writing.

            `transaction` uses all three clauses deliberately. The rollback
            re-raises with a bare `raise`, preserving the original exception
            and traceback rather than a reconstruction. And `COMMIT` sits in
            the `else`, not after the `try` — so there is no arrangement of
            control flow in which a failed body still commits.
            """,
        ),
        Text("""
        ## The `contextlib` toolbox

        | tool | use |
        |---|---|
        | `suppress(*excs)` | replace an empty `except: pass` |
        | `closing(obj)` | call `obj.close()` on exit |
        | `redirect_stdout/stderr(f)` | temporarily capture output |
        | `nullcontext(x)` | an optional manager, without branching |
        | `ExitStack()` | a dynamic number of managers |
        | `ContextDecorator` | a manager usable as `@decorator` |
        """),
        Demo(
            code="""
            import io
            from contextlib import closing, nullcontext, redirect_stdout, suppress

            with suppress(FileNotFoundError):
                open("/definitely/not/here")
            print("suppress: no crash")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                print("this goes into the buffer")
            print("captured:", buffer.getvalue().strip())

            # nullcontext removes the if/else around an optional manager.
            def process(data, lock=None):
                with (lock or nullcontext()):
                    return sum(data)
            print("nullcontext:", process([1, 2, 3]))

            class Handle:
                def __init__(self): self.open = True
                def close(self): self.open = False; print("  closed")

            h = Handle()
            with closing(h) as handle:
                print("  using, open =", handle.open)
            print("after:", h.open)
            """,
            explain="""
            Four small tools, each replacing a shape of boilerplate:

            - `suppress(X)` is a `try/except X: pass` that cannot accidentally
              grow a body — which is what makes it safer than the long form,
              not merely shorter.
            - `redirect_stdout` reassigns `sys.stdout` for the block, the
              standard way to capture output from code you cannot change.
            - `nullcontext()` is the do-nothing manager, so an *optional*
              lock needs no `if`/`else` around the `with` and only one code
              path exists.
            - `closing(obj)` adapts any object with a `.close()` into a
              manager, for the many older APIs that never grew `__enter__`.
            """,
        ),
        Demo(
            code="""
            from contextlib import ExitStack

            class Res:
                def __init__(self, n): self.n = n
                def __enter__(self):
                    print(f"  open {self.n}")
                    if self.n == 3:
                        raise OSError(f"resource {self.n} unavailable")
                    return self
                def __exit__(self, *exc):
                    print(f"  close {self.n}")
                    return False

            # A variable number of managers, all unwound in reverse.
            with ExitStack() as stack:
                resources = [stack.enter_context(Res(n)) for n in (1, 2)]
                print("  using", [r.n for r in resources])

            print()
            print("partial failure still unwinds what succeeded:")
            try:
                with ExitStack() as stack:
                    for n in (1, 2, 3):
                        stack.enter_context(Res(n))
            except OSError as exc:
                print("  error:", exc)
            """,
            explain="""
            `ExitStack` is the answer whenever the number of resources is not
            known at compile time. It also has `callback(fn, *args)` for plain
            cleanup functions and `pop_all()` to *transfer* ownership of the
            cleanups elsewhere — the idiom for "commit on success".
            """,
        ),
        Demo(
            code="""
            from contextlib import ExitStack

            # pop_all(): keep resources open only if setup fully succeeded.
            class Conn:
                def __init__(self, n): self.n = n
                def __enter__(self): print(f"  open {self.n}"); return self
                def __exit__(self, *exc): print(f"  close {self.n}"); return False

            def open_pool(count, fail_at=None):
                with ExitStack() as stack:
                    conns = []
                    for i in range(count):
                        if i == fail_at:
                            raise RuntimeError("pool setup failed")
                        conns.append(stack.enter_context(Conn(i)))
                    return conns, stack.pop_all()      # ownership transferred out

            print("success path:")
            conns, keeper = open_pool(2)
            print("  still open:", [c.n for c in conns])
            keeper.close()

            print("failure path:")
            try:
                open_pool(3, fail_at=2)
            except RuntimeError as exc:
                print(" ", exc)
            """,
            explain="""
            `ExitStack` is for the case the `with` statement cannot express: a
            number of resources known only at runtime. Each
            `enter_context` registers a cleanup, and leaving the block unwinds
            them in reverse order.

            `pop_all()` is the subtle part, and it solves a real problem —
            all-or-nothing acquisition. On the failure path the stack is still
            armed, so the connections opened before the error are closed on
            the way out and nothing leaks. On the success path `pop_all`
            **transfers ownership** to a new stack that the function returns,
            disarming the original so the `with` block closes nothing. Note
            what that leaves behind: the caller now holds `keeper` and is
            responsible for closing it.
            """,
        ),
        Text("""
        ## Reentrancy and reusability

        Most managers are **single-use**: `@contextmanager` generators are
        exhausted after one `with`. A **reusable** manager can be entered
        again after exiting; a **reentrant** one can be entered while already
        active. `threading.RLock` is reentrant; `Lock` is not.
        """),
        Demo(
            code="""
            from contextlib import contextmanager
            import threading

            @contextmanager
            def one_shot():
                yield "value"

            manager = one_shot()
            with manager:
                pass
            try:
                with manager:          # entering the SAME manager object twice
                    pass
            except Exception as exc:
                print(f"single-use: {type(exc).__name__}: {exc}")

            # A reusable, reentrant manager written as a class:
            class Depth:
                def __init__(self): self.level = 0
                def __enter__(self):
                    self.level += 1
                    return self.level
                def __exit__(self, *exc):
                    self.level -= 1
                    return False

            d = Depth()
            with d as a, d as b:
                print("nested depth:", a, b)
            with d as c:
                print("reused later:", c)

            lock, rlock = threading.Lock(), threading.RLock()
            with rlock:
                with rlock:
                    print("RLock is reentrant")
            print("Lock is not -- a nested acquire would deadlock")
            """,
            explain="""
            The exact exception for re-entering a spent `@contextmanager` is an
            implementation detail (CPython 3.12 raises `AttributeError` because
            `__enter__` deletes the stored generator arguments; older versions
            raise `RuntimeError`). Do not catch it — call the decorated
            *function* again to get a fresh manager instead.
            """,
        ),
        Text("""
        ## `ContextDecorator` and async managers

        Subclass `ContextDecorator` (or use `@contextmanager`, which already
        does) and the same object works as both `with x:` and `@x`.

        For `async with`, implement `__aenter__` / `__aexit__`, or use
        `contextlib.asynccontextmanager`. Full coverage is in lesson 19.
        """),
        Demo(
            code="""
            import time
            from contextlib import ContextDecorator, contextmanager

            class timer(ContextDecorator):
                def __init__(self, label): self.label = label
                def __enter__(self):
                    self.start = time.perf_counter()
                    return self
                def __exit__(self, *exc):
                    self.elapsed = time.perf_counter() - self.start
                    print(f"  {self.label}: {self.elapsed*1000:.2f} ms")
                    return False

            with timer("as a block"):
                sum(range(100_000))

            @timer("as a decorator")
            def work():
                return sum(range(100_000))
            work()

            # @contextmanager gives you the same for free:
            @contextmanager
            def section(name):
                print(f"  [{name}]")
                yield

            @section("decorated")
            def go(): pass
            go()
            """,
            explain="""
            Inheriting from `ContextDecorator` gets you `__call__` for free,
            so one class serves as both a block and a decorator with no
            duplicated logic. `@contextmanager` already includes it, which is
            why `section` works in both positions without being told to.

            One caveat the timer makes concrete: as a decorator the *same
            instance* is reused for every call of the wrapped function, so
            `self.elapsed` is overwritten each time and a recursive function
            will trample it mid-flight. State that must be per-invocation
            belongs in a fresh object created inside `__enter__`, not on the
            decorator.
            """,
        ),
        Question(
            prompt="Why must a `@contextmanager` generator wrap its `yield` in `try/finally`?",
            choices=[
                "For performance — it avoids re-entering the generator",
                "Because an exception in the body is thrown at the `yield`, so plain trailing code is skipped",
                "Because generators cannot use `return`",
                "It is only needed when the manager yields a value",
            ],
            answer=1,
            explain="`contextmanager.__exit__` calls `gen.throw(exc)`. Without "
                    "`try/finally`, that exception propagates straight out of the "
                    "generator and your teardown never executes.",
        ),
        Exercise(
            slug="atomic",
            title="An atomic-write context manager",
            difficulty="medium",
            brief="""
            Write `atomic_write(store, key)` — a context manager giving
            "all-or-nothing" updates to a dict-backed store.

            - `store` is a `dict`; `key` is the entry being edited
            - `__enter__` yields a **deep copy** of `store.get(key)`, or an
              empty dict when the key is absent
            - on clean exit, the draft is written to `store[key]`
            - on any exception the store is left **completely** untouched and
              the exception propagates
            - `store[key]` must never be observable in a half-written state
            - nesting on different keys works
            - a `rollback` count is exposed: `atomic_write.rollbacks` is a
              module-level list that gets the key appended on each failure
            """,
            starter="""
            import copy
            from contextlib import contextmanager

            rollbacks = []


            @contextmanager
            def atomic_write(store, key):
                ...
            """,
            checks=[
                Check("commits on clean exit", lambda ns: _at_commit(ns)),
                Check("yields a copy, not the live object", lambda ns: _at_copy(ns)),
                Check("rolls back on exception and re-raises", lambda ns: _at_rollback(ns)),
                Check("a new key is not created on failure", lambda ns: _at_new_key(ns)),
                Check("nesting on different keys", lambda ns: _at_nesting(ns)),
                Check("rollbacks are recorded", lambda ns: _at_record(ns)),
            ],
            hints=(
                "`copy.deepcopy(store.get(key, {}))` gives you an isolated draft.",
                "`try: yield draft / except: record and re-raise / else: commit` "
                "expresses the semantics directly.",
                "Assign to `store[key]` only in the `else` branch — that is what "
                "makes the failure path a true no-op.",
                "`raise` bare inside `except` preserves the original traceback.",
            ),
            solution="""
            import copy
            from contextlib import contextmanager

            rollbacks = []

            @contextmanager
            def atomic_write(store, key):
                draft = copy.deepcopy(store.get(key, {}))
                try:
                    yield draft
                except BaseException:
                    rollbacks.append(key)
                    raise
                else:
                    store[key] = draft
            """,
        ),
        Exercise(
            slug="resource-pool",
            title="A reentrant, exception-safe resource pool",
            difficulty="brutal",
            brief="""
            Build `Pool(factory, size)` — a context-manager-based resource
            pool that is reusable, reentrant, and correct under failure.

            - `pool.acquire()` returns a **context manager**; entering it
              yields a resource, exiting returns it to the pool
            - resources are created lazily by `factory()`, at most `size` of
              them, and reused afterwards
            - acquiring when all `size` resources are checked out raises
              `RuntimeError("pool exhausted")`
            - a resource is returned even when the body raises, and the
              exception still propagates
            - nesting works: two `with pool.acquire()` blocks hold two
              distinct resources
            - `pool.stats()` → `{"created": n, "in_use": n, "available": n}`
            - `pool.close()` calls `.close()` on every created resource that
              has one, empties the pool, and is idempotent; using a closed
              pool raises `RuntimeError("pool is closed")`
            - `Pool` is itself a context manager: `with Pool(f, 2) as p:` and
              closing on exit
            """,
            starter="""
            from contextlib import contextmanager


            class Pool:
                def __init__(self, factory, size):
                    ...
            """,
            checks=[
                Check("lazily creates up to size resources", lambda ns: _rp_lazy(ns["Pool"])),
                Check("reuses returned resources", lambda ns: _rp_reuse(ns["Pool"])),
                Check("exhaustion raises RuntimeError", lambda ns: _rp_exhaust(ns["Pool"])),
                Check("returns the resource even on exception", lambda ns: _rp_exception(ns["Pool"])),
                Check("nesting holds distinct resources", lambda ns: _rp_nesting(ns["Pool"])),
                Check("stats reports accurate counts", lambda ns: _rp_stats(ns["Pool"])),
                Check("close is idempotent and blocks reuse", lambda ns: _rp_close(ns["Pool"])),
                Check("Pool works as a context manager", lambda ns: _rp_self_cm(ns["Pool"])),
            ],
            hints=(
                "Keep two collections: `_available` (a list) and `_in_use` (a set "
                "or list). `created` is just the total ever made.",
                "`@contextmanager` on an `acquire` method gives you the "
                "try/finally shape for returning the resource.",
                "Return the resource in a `finally` so an exception in the body "
                "cannot leak it.",
                "`hasattr(resource, 'close')` before calling it — the factory may "
                "produce plain objects.",
                "For the pool's own `__enter__`, return `self`; `__exit__` should "
                "call `self.close()` and return False.",
            ),
            solution="""
            from contextlib import contextmanager

            class Pool:
                def __init__(self, factory, size):
                    self.factory = factory
                    self.size = size
                    self._available = []
                    self._in_use = []
                    self._created = 0
                    self._closed = False

                @contextmanager
                def acquire(self):
                    if self._closed:
                        raise RuntimeError("pool is closed")
                    if self._available:
                        resource = self._available.pop()
                    elif self._created < self.size:
                        resource = self.factory()
                        self._created += 1
                    else:
                        raise RuntimeError("pool exhausted")

                    self._in_use.append(resource)
                    try:
                        yield resource
                    finally:
                        self._in_use.remove(resource)
                        if not self._closed:
                            self._available.append(resource)

                def stats(self):
                    return {
                        "created": self._created,
                        "in_use": len(self._in_use),
                        "available": len(self._available),
                    }

                def close(self):
                    if self._closed:
                        return
                    self._closed = True
                    for resource in [*self._available, *self._in_use]:
                        if hasattr(resource, "close"):
                            resource.close()
                    self._available.clear()

                def __enter__(self):
                    return self

                def __exit__(self, *exc_info):
                    self.close()
                    return False
            """,
        ),
        Text("""
        ## Takeaways

        - `__enter__` supplies the `as` value; `__exit__` decides whether the
          exception lives or dies.
        - A truthy `__exit__` return silently swallows errors — be deliberate.
        - `@contextmanager` needs `try/finally` around the `yield`.
        - `ExitStack` handles a dynamic number of resources and `pop_all()`
          transfers ownership.
        - Generator-based managers are single-use; write a class when you need
          reuse or reentrancy.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _at_commit(ns) -> None:
    atomic_write = ns["atomic_write"]
    store = {"user": {"name": "ada"}}
    with atomic_write(store, "user") as draft:
        draft["name"] = "grace"
        draft["role"] = "admin"
    assert store["user"] == {"name": "grace", "role": "admin"}, store


def _at_copy(ns) -> None:
    atomic_write = ns["atomic_write"]
    original = {"nested": {"n": 1}}
    store = {"k": original}
    with atomic_write(store, "k") as draft:
        assert draft is not original, "the draft must not be the live object"
        draft["nested"]["n"] = 99
        assert original["nested"]["n"] == 1, "mutating the draft leaked into the store"
    assert store["k"]["nested"]["n"] == 99


def _at_rollback(ns) -> None:
    atomic_write = ns["atomic_write"]
    store = {"user": {"name": "ada"}}
    try:
        with atomic_write(store, "user") as draft:
            draft["name"] = "corrupted"
            raise ValueError("validation failed")
    except ValueError:
        assert store == {"user": {"name": "ada"}}, f"store was modified: {store}"
        return
    raise AssertionError("the exception must propagate")


def _at_new_key(ns) -> None:
    atomic_write = ns["atomic_write"]
    store = {}
    try:
        with atomic_write(store, "fresh") as draft:
            draft["a"] = 1
            raise RuntimeError("nope")
    except RuntimeError:
        pass
    assert "fresh" not in store, f"a failed write created the key: {store}"

    with atomic_write(store, "fresh") as draft:
        draft["a"] = 1
    assert store["fresh"] == {"a": 1}, "an absent key should start as an empty dict"


def _at_nesting(ns) -> None:
    atomic_write = ns["atomic_write"]
    store = {}
    with atomic_write(store, "a") as a:
        a["x"] = 1
        with atomic_write(store, "b") as b:
            b["y"] = 2
    assert store == {"a": {"x": 1}, "b": {"y": 2}}, store


def _at_record(ns) -> None:
    atomic_write = ns["atomic_write"]
    rollbacks = ns["rollbacks"]
    before = len(rollbacks)
    try:
        with atomic_write({}, "doomed"):
            raise ValueError("x")
    except ValueError:
        pass
    assert len(rollbacks) == before + 1, "the rollback was not recorded"
    assert rollbacks[-1] == "doomed", rollbacks[-1]


class _Resource:
    counter = 0

    def __init__(self):
        _Resource.counter += 1
        self.id = _Resource.counter
        self.closed = False

    def close(self):
        self.closed = True


def _factory():
    return _Resource()


def _rp_lazy(Pool) -> None:
    made = []

    def factory():
        made.append(1)
        return object()

    pool = Pool(factory, 2)
    assert made == [], "resources must be created lazily, not up front"
    with pool.acquire():
        assert len(made) == 1
    with pool.acquire():
        assert len(made) == 1, "an available resource should be reused"


def _rp_reuse(Pool) -> None:
    pool = Pool(_factory, 2)
    with pool.acquire() as r1:
        first_id = r1.id
    with pool.acquire() as r2:
        assert r2.id == first_id, "the returned resource should be handed out again"


def _rp_exhaust(Pool) -> None:
    pool = Pool(_factory, 1)
    with pool.acquire():
        try:
            with pool.acquire():
                pass
        except RuntimeError as exc:
            assert "exhaust" in str(exc).lower(), str(exc)
            return
        raise AssertionError("acquiring beyond size must raise RuntimeError")


def _rp_exception(Pool) -> None:
    pool = Pool(_factory, 1)
    try:
        with pool.acquire():
            raise ValueError("body failed")
    except ValueError:
        pass
    else:
        raise AssertionError("the exception must propagate")
    assert pool.stats()["in_use"] == 0, "the resource leaked after an exception"
    with pool.acquire():
        pass


def _rp_nesting(Pool) -> None:
    pool = Pool(_factory, 2)
    with pool.acquire() as a, pool.acquire() as b:
        assert a is not b, "nested acquires must yield distinct resources"
        assert pool.stats()["in_use"] == 2, pool.stats()
    assert pool.stats()["in_use"] == 0


def _rp_stats(Pool) -> None:
    pool = Pool(_factory, 3)
    assert pool.stats() == {"created": 0, "in_use": 0, "available": 0}, pool.stats()
    with pool.acquire():
        assert pool.stats() == {"created": 1, "in_use": 1, "available": 0}, pool.stats()
    assert pool.stats() == {"created": 1, "in_use": 0, "available": 1}, pool.stats()


def _rp_close(Pool) -> None:
    pool = Pool(_factory, 2)
    with pool.acquire() as r:
        held = r
    pool.close()
    assert held.closed, "close() must close the pooled resources"
    pool.close()                          # idempotent: must not raise
    try:
        with pool.acquire():
            pass
    except RuntimeError as exc:
        assert "closed" in str(exc).lower(), str(exc)
        return
    raise AssertionError("using a closed pool must raise RuntimeError")


def _rp_self_cm(Pool) -> None:
    with Pool(_factory, 2) as pool:
        with pool.acquire() as r:
            held = r
        assert pool.stats()["created"] == 1
    assert held.closed, "leaving the Pool's own with-block should close it"
