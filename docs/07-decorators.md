# 07 — Decorators

A decorator is a function that takes a function and returns a
replacement. That is the whole idea — everything else is applying it
carefully: preserving metadata, handling arguments, stacking, decorating
methods and classes, and keeping the wrapper introspectable.

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

```python
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
```
Note the last line: the name `work` now refers to `wrapper`. That
broken `__name__` is why `functools.wraps` exists.

## `functools.wraps` — never skip it

`@wraps(fn)` copies `__name__`, `__doc__`, `__qualname__`,
`__module__`, `__dict__` and `__annotations__` onto the wrapper, and
sets `__wrapped__ = fn`. That last one is what lets
`inspect.signature` see through the wrapper.

```python
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
```
Look at the `bare` row: the decorated function now calls itself
`wrapper`, advertises the signature `(*a, **k)`, and has lost its
docstring entirely. Everything that reads those — `help()`, IDE
completion, pytest's fixture matching, any framework that
dispatches on parameter names — is now working from a lie.

`functools.wraps` copies `__name__`, `__doc__`, `__qualname__`,
`__module__` and `__dict__` across, and sets `__wrapped__`
pointing at the original. That last one is the load-bearing part:
the wrapper's *real* signature is still `(*a, **k)`, and
`signature()` reports the true one only because it follows
`__wrapped__` back to the source.

**Quiz.** Which does `functools.wraps` NOT do?

- a) Copy `__name__` and `__doc__`
- b) Set `__wrapped__` on the wrapper
- c) Make the wrapper accept the same arguments as the original
- d) Copy `__annotations__`

<details><summary>answer</summary>

**c** — It only copies metadata. The wrapper's real signature is still `(*args, **kwargs)` — `inspect.signature` merely *reports* the original by following `__wrapped__`.
</details>

## Decorators with arguments: one more layer

`@deco(x)` means `f = deco(x)(f)`. So a parameterised decorator is a
function returning a decorator returning a wrapper — three levels.

```python
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
```
Three layers, and each one has a job: `retry(...)` captures the
configuration and returns `decorate`; `decorate` receives the
function and returns `wrapper`; `wrapper` does the work. That is
why a parameterised decorator needs exactly one level more than a
plain one — `@retry(times=3)` *calls* `retry` first and applies
the result.

Because `times` and `delay` are closed over at decoration time,
every decorated function carries its own settings. And note
`raise last` rather than a fresh exception: when the retries are
exhausted the caller gets the real failure, with its original
message and traceback, instead of a wrapper's guess at one.

## Supporting both `@deco` and `@deco(...)`

Users will inevitably write `@deco` without parentheses. Detect it:
if the decorator is called with a single positional argument that is
callable and no keywords, it was used bare.

```python
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
```
The keyword-only `*` is what makes this safe: `@logged` passes the
function positionally, and `@logged(prefix=...)` can only pass
keywords, so the two cases can never be confused.


**Quiz.** In what order do stacked decorators apply?

- a) Top to bottom; the top one is innermost
- b) Bottom to top; the bottom one is innermost
- c) Alphabetically by decorator name
- d) All at once, in an undefined order

<details><summary>answer</summary>

**b** — The one closest to `def` runs first and is therefore innermost; the topmost decorator wraps everything and runs first at call time.
</details>

## Decorating methods

A decorator sees the plain function *before* it becomes a bound
method, so `self` simply arrives as the first positional argument.
The subtleties are with `classmethod`/`staticmethod`, which must be
the **outermost** decorators, since they return descriptors, not
functions.

```python
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
```
Put `@classmethod` *below* `@trace` and you would be decorating a
classmethod object — not callable — and get a `TypeError` at call
time. Rule of thumb: descriptor-producing decorators go on top.

## Class-based decorators, and decorating classes

- A **class as decorator** — implement `__call__`. Useful when the
  decorator needs rich state or its own methods.
- A **decorator applied to a class** — receives and returns a class.
  `dataclass`, `total_ordering`, and registration decorators work
  this way.

```python
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
```
One caveat: a class-based decorator on a *method* breaks binding —
the instance is not passed, because your class is not a descriptor.
Add `__get__` returning `functools.partial(self.__call__, obj)` if
you need that.

```python
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
```
A class decorator receives the finished class object — the body
has already executed — and whatever it returns gets bound to the
name. Here it returns the class untouched and merely records it,
which is the plugin-registry pattern: importing a module is what
makes its exporters available.

The duplicate check is the part worth copying. It runs at
**import time**, so two plugins claiming `"json"` fail loudly at
startup rather than resolving to whichever module happened to be
imported last. Lesson 10 does the same job for subclasses with
`__init_subclass__`, no decorator required.

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

```python
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
```
Caveats: arguments must be **hashable**, the cache is shared across
all callers, and on a method it keeps `self` alive forever — a
classic memory leak. Prefer `cached_property` on instances.

```python
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
```
`singledispatch` dispatches on the runtime type of the **first**
argument, honouring the MRO — so registering `Sequence` catches
tuples and lists both. `singledispatchmethod` does the same for
methods, dispatching on the first argument after `self`.

```python
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
```
`cached_property` needs a writable `__dict__`, so it cannot be
used with `__slots__`. It is also **not** thread-safe as of 3.12:
two threads may both compute the value.

## Exercise — A production-grade retry decorator `[tricky]`

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
```python
import functools
import time

sleep = time.sleep     # tests monkeypatch this name


def retry(attempts=3, exceptions=(Exception,), backoff=None, on_retry=None):
    ...
```

## Exercise — A memoiser with TTL, key policy, and stats `[brutal]`

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
```python
import functools
import inspect
import time
from collections import OrderedDict

now = time.monotonic     # tests monkeypatch this name


def memoize(ttl=None, key=None, maxsize=None):
    ...
```

## Takeaways

- `@d` is `f = d(f)`, run once at definition time.
- Always `functools.wraps` — otherwise you destroy introspection.
- Parameterised decorators are three nested functions; keyword-only
  parameters let one decorator support both call styles.
- Stacking applies bottom-up; `classmethod`/`staticmethod` go on top.
- Reach for `cache`, `cached_property`, `singledispatch` before
  writing your own.
