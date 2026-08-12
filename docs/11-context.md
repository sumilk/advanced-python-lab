# 11 — Context Managers

`with` is Python's answer to "this must be undone, whatever happens".
The protocol is two methods, but the details — what `__exit__` returns,
how exceptions are suppressed, reentrancy, dynamic nesting with
`ExitStack` — are where the real power and the real bugs live.

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

```python
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
```


**Quiz.** What does a `with` statement bind to the `as` target?

- a) The context manager object itself, always
- b) Whatever `__enter__` returns
- c) The result of the `with` body
- d) `None`, unless `__exit__` returns a value

<details><summary>answer</summary>

**b** — Many managers `return self`, which is why the distinction is easy to miss — but `open()` returns a file, and `lock.acquire()`-style managers often return `None`.
</details>

## `@contextmanager`: a generator with one yield

`contextlib.contextmanager` turns a generator into a manager:
everything before `yield` is setup, the yielded value becomes the `as`
target, and everything after is teardown.

The catch: if the body raises, the exception is thrown **into the
generator at the `yield`**. So a bare `yield` with cleanup after it
will *skip* the cleanup on error — you need `try/finally`.

```python
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
```

```python
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
```

## The `contextlib` toolbox

| tool | use |
|---|---|
| `suppress(*excs)` | replace an empty `except: pass` |
| `closing(obj)` | call `obj.close()` on exit |
| `redirect_stdout/stderr(f)` | temporarily capture output |
| `nullcontext(x)` | an optional manager, without branching |
| `ExitStack()` | a dynamic number of managers |
| `ContextDecorator` | a manager usable as `@decorator` |

```python
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
```

```python
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
```
`ExitStack` is the answer whenever the number of resources is not
known at compile time. It also has `callback(fn, *args)` for plain
cleanup functions and `pop_all()` to *transfer* ownership of the
cleanups elsewhere — the idiom for "commit on success".

```python
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
```

## Reentrancy and reusability

Most managers are **single-use**: `@contextmanager` generators are
exhausted after one `with`. A **reusable** manager can be entered
again after exiting; a **reentrant** one can be entered while already
active. `threading.RLock` is reentrant; `Lock` is not.

```python
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
```
The exact exception for re-entering a spent `@contextmanager` is an
implementation detail (CPython 3.12 raises `AttributeError` because
`__enter__` deletes the stored generator arguments; older versions
raise `RuntimeError`). Do not catch it — call the decorated
*function* again to get a fresh manager instead.

## `ContextDecorator` and async managers

Subclass `ContextDecorator` (or use `@contextmanager`, which already
does) and the same object works as both `with x:` and `@x`.

For `async with`, implement `__aenter__` / `__aexit__`, or use
`contextlib.asynccontextmanager`. Full coverage is in lesson 19.

```python
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
```

**Quiz.** Why must a `@contextmanager` generator wrap its `yield` in `try/finally`?

- a) For performance — it avoids re-entering the generator
- b) Because an exception in the body is thrown at the `yield`, so plain trailing code is skipped
- c) Because generators cannot use `return`
- d) It is only needed when the manager yields a value

<details><summary>answer</summary>

**b** — `contextmanager.__exit__` calls `gen.throw(exc)`. Without `try/finally`, that exception propagates straight out of the generator and your teardown never executes.
</details>

## Exercise — An atomic-write context manager `[medium]`

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
```python
import copy
from contextlib import contextmanager

rollbacks = []


@contextmanager
def atomic_write(store, key):
    ...
```

## Exercise — A reentrant, exception-safe resource pool `[brutal]`

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
```python
from contextlib import contextmanager


class Pool:
    def __init__(self, factory, size):
        ...
```

## Takeaways

- `__enter__` supplies the `as` value; `__exit__` decides whether the
  exception lives or dies.
- A truthy `__exit__` return silently swallows errors — be deliberate.
- `@contextmanager` needs `try/finally` around the `yield`.
- `ExitStack` handles a dynamic number of resources and `pop_all()`
  transfers ownership.
- Generator-based managers are single-use; write a class when you need
  reuse or reentrancy.
