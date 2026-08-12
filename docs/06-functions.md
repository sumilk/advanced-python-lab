# 06 — Functions, Scope, and Closures

Functions are objects with a rich, introspectable signature grammar and a
precise scoping model. This lesson covers every parameter kind, the
mutable-default trap and its real cause, LEGB resolution, closures and
cell objects, and how to inspect and wrap a signature correctly.

## The full parameter grammar

```python
def f(pos_only, /, standard, *args, kw_only, **kwargs):
    ...
```

- everything **before `/`** is positional-only (3.8+)
- everything **after `*`** or `*args` is keyword-only
- `*args` collects extra positionals into a tuple
- `**kwargs` collects extra keywords into a dict

Positional-only parameters let you rename them later without breaking
callers, and let `**kwargs` contain a key with the same name. That is
why built-ins like `dict.get` use them.

```python
def configure(source, /, mode="r", *extras, encoding="utf-8", **options):
    return {
        "source": source, "mode": mode, "extras": extras,
        "encoding": encoding, "options": options,
    }

print(configure("f.txt"))
print(configure("f.txt", "w", "x", "y", encoding="latin-1", buffer=4096))

try:
    configure(source="f.txt")
except TypeError as exc:
    print("positional-only:", exc)

# Because `source` is positional-only, it may ALSO appear in **options:
print(configure("f.txt", source="a query param"))
```
That last line is the real motivation: without `/`, a caller who
wants a keyword literally named `source` collides with your
parameter. `min`, `max`, `dict.get` and friends all use `/` for
exactly this reason.

## The mutable default argument

Defaults are evaluated **once**, when the `def` statement executes —
not per call. A mutable default is therefore shared state living on
the function object, in `func.__defaults__`.

```python
def append_bad(item, target=[]):
    target.append(item)
    return target

print(append_bad(1))
print(append_bad(2))
print(append_bad(3))
print("the default itself:", append_bad.__defaults__)

def append_good(item, target=None):
    if target is None:
        target = []
    target.append(item)
    return target

print("fixed:", append_good(1), append_good(2))
```

```python
import datetime

# The same trap with a non-container: the value is frozen at def time.
def log_bad(msg, when=datetime.datetime(2020, 1, 1)):
    return f"{when:%Y-%m-%d} {msg}"

def log_good(msg, when=None):
    when = when or datetime.datetime.now()
    return f"{when:%Y-%m-%d} {msg}"

print(log_bad("frozen timestamp"))
print(log_good("evaluated per call")[:10] != "2020-01-01")

# Occasionally the trap is a FEATURE: a per-function cache.
def fib(n, _memo={0: 0, 1: 1}):
    if n not in _memo:
        _memo[n] = fib(n - 1) + fib(n - 2)
    return _memo[n]

print("fib(60) =", fib(60), "| cache size:", len(fib.__defaults__[0]))
```
Use the deliberate version sparingly and name it with a leading
underscore. `functools.cache` (lesson 15) says the same thing more
clearly.

**Quiz.** When is the expression in `def f(x=compute()):` evaluated?

- a) Every time `f` is called without `x`
- b) Once, when the `def` statement runs
- c) Once, on the first call to `f`
- d) Never — it is only a type hint

<details><summary>answer</summary>

**b** — At definition time, and the result is stored in `f.__defaults__`. That single evaluation is the whole cause of the mutable-default trap.
</details>

## Unpacking at the call site

`*` and `**` in a *call* are the mirror of `*args`/`**kwargs` in a
*definition*. Since 3.5 you may use several of each in one call, and
unpack into literals.

```python
def show(a, b, c, d=0):
    return f"a={a} b={b} c={c} d={d}"

args = (1, 2)
more = {"c": 3, "d": 4}
print(show(*args, **more))

# Multiple unpackings, and unpacking into literals
head, *middle, tail = [1, 2, 3, 4, 5]
print("starred unpack:", head, middle, tail)

merged = [*[1, 2], *(3, 4), 5]
combined = {**{"a": 1}, **{"b": 2}, "c": 3}
print("merged:", merged, combined)

# Nested unpacking in a for loop
pairs = [(1, ("a", "b")), (2, ("c", "d"))]
for num, (first, second) in pairs:
    print(f"  {num}: {first}{second}")
```

## LEGB: how a name is resolved

**L**ocal → **E**nclosing → **G**lobal → **B**uiltins.

Crucially, whether a name is local is decided **at compile time**:
if a function body assigns to a name anywhere, that name is local for
the whole function — even on lines before the assignment.


```python
counter = 0

def bump_global():
    global counter
    counter += 1

def make_counter():
    count = 0
    def increment():
        nonlocal count           # rebind the ENCLOSING local
        count += 1
        return count
    def peek():
        return count             # reading needs no declaration
    return increment, peek

bump_global(); bump_global()
inc, peek = make_counter()
inc(); inc(); inc()
print("global:", counter, "| closure:", peek())

# The two counters from two calls are independent.
inc2, peek2 = make_counter()
inc2()
print("independent closures:", peek(), peek2())
```
`nonlocal` targets the nearest enclosing *function* scope; it can
never reach module level (use `global` for that) and it errors at
compile time if no such binding exists.

## Closures are cells, and you can look inside

A closure variable lives in a **cell object** shared between the outer
and inner function. `func.__closure__` is a tuple of cells;
`func.__code__.co_freevars` names them.

```python
def outer():
    message = "hello"
    extra = [1, 2]
    def inner():
        return message, extra
    return inner

fn = outer()
print("free variables:", fn.__code__.co_freevars)
print("cells:", fn.__closure__)
print("cell contents:", [c.cell_contents for c in fn.__closure__])

# Cells are live: rebinding through nonlocal is visible to all readers.
def counterish():
    n = 0
    def bump():
        nonlocal n
        n += 1
    def get():
        return n
    return bump, get

bump, get = counterish()
bump(); bump()
print("shared cell:", get(), "| same cell object:",
      bump.__closure__[0] is get.__closure__[0])
```


**Quiz.** Inside a nested function, which keyword rebinds a variable of the *enclosing function*?

- a) `global`
- b) `nonlocal`
- c) `static`
- d) No keyword — assignment just works

<details><summary>answer</summary>

**b** — Plain assignment creates a new local. `global` skips all the way to module scope; `nonlocal` targets the nearest enclosing function binding.
</details>

## Functions are objects

They carry attributes you can read and write: `__name__`, `__doc__`,
`__defaults__`, `__kwdefaults__`, `__annotations__`, `__dict__`,
`__module__`, `__qualname__`, `__code__`. Understanding these is what
makes writing correct decorators possible (next lesson).

```python
def greet(name: str, punct: str = "!") -> str:
    '''Say hello.'''
    return f"Hello, {name}{punct}"

greet.call_count = 0                # arbitrary attributes are allowed

print("name       :", greet.__name__, "| qualname:", greet.__qualname__)
print("doc        :", greet.__doc__)
print("defaults   :", greet.__defaults__)
print("annotations:", greet.__annotations__)
print("attributes :", greet.__dict__)
print("code       : argcount =", greet.__code__.co_argcount,
      "| varnames =", greet.__code__.co_varnames)
```

## `inspect.signature`: the right way to introspect

Never parse `__code__` by hand. `inspect.signature` gives you an
object you can query, bind arguments against, and even modify.

```python
import inspect

def handler(request, /, timeout=30, *middleware, retries=3, **opts):
    ...

sig = inspect.signature(handler)
print("signature:", sig)
for name, param in sig.parameters.items():
    print(f"  {name:12} kind={param.kind.name:20} default={param.default!r}")

# bind() resolves a call the way Python would -- great for validation.
bound = sig.bind("req", 5, "mw1", retries=1, verbose=True)
bound.apply_defaults()
print("bound:", dict(bound.arguments))

try:
    sig.bind()                       # missing required argument
except TypeError as exc:
    print("bind error:", exc)
```
`sig.bind(*args, **kwargs)` is how you write a decorator that needs
to look at a specific parameter by name regardless of whether the
caller passed it positionally or by keyword.

```python
import inspect
from functools import partial

def connect(host, port=5432, *, user, password, timeout=10):
    return f"{user}@{host}:{port} timeout={timeout}"

# partial pre-binds arguments and produces a new callable.
local = partial(connect, "localhost", user="admin")
print(local(password="s3cret"))
print("partial keeps the pieces:", local.func.__name__, local.args, local.keywords)

# signature() understands partials and reports what's LEFT to supply.
print("remaining signature:", inspect.signature(local))

# partialmethod's cousin for the common "flag variant" pattern:
debug_connect = partial(connect, timeout=1)
print(debug_connect("db1", user="u", password="p"))
```

## Exercise — A signature-aware argument validator `[tricky]`

Write `validated(**rules)` — a decorator factory that checks
arguments against predicates **by parameter name**, no matter how
the caller passed them.

- `@validated(n=lambda v: v > 0)` must reject `f(-1)`, `f(n=-1)`
  and a `-1` that arrives via a default
- on failure raise `ValueError` whose message contains the
  parameter name and the offending value's repr
- defaults must be validated too
- naming a parameter that does not exist raises `TypeError` at
  **decoration** time, not call time
- the wrapper must preserve `__name__`, `__doc__` and the
  signature (`inspect.signature` on the wrapper must equal the
  signature of the original)
- it must work with positional-only, keyword-only, `*args` and
  `**kwargs` functions; a rule naming a `*args` or `**kwargs`
  parameter applies to *each* collected value
```python
import functools
import inspect


def validated(**rules):
    ...
```

## Exercise — Auto-currying with arity detection `[brutal]`

Implement `curry(fn)`: calling the result with fewer arguments than
`fn` needs returns a new callable awaiting the rest.

- `curry(add3)(1)(2)(3)`, `curry(add3)(1, 2)(3)` and
  `curry(add3)(1)(2, 3)` all produce the same result
- keyword arguments work and accumulate across partial calls
- a later call may override an earlier keyword
- once every **required** parameter is satisfied, the function is
  invoked and the real result returned
- parameters with defaults are *not* required: `curry(f)(1)` calls
  `f` immediately when only the defaulted parameters remain
- a function with `*args` is called as soon as its named required
  parameters are satisfied
- `curry` on a zero-argument function calls it on the first
  invocation: `curry(f)()` → result
- `__name__` is preserved
```python
import functools
import inspect


def curry(fn):
    ...
```

## Takeaways

- `/` and `*` in a signature are tools, not decoration: they decide
  what callers may rename and what may collide with `**kwargs`.
- Defaults evaluate once at `def` time — never make them mutable.
- A name assigned anywhere in a function is local everywhere in it.
- Closures share live cells; capture by value with a default argument
  or `partial`.
- `inspect.signature(...).bind(...)` normalises any calling style into
  one dictionary.
