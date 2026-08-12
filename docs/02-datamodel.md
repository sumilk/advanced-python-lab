# 02 — The Data Model — Dunder Protocols

Python has almost no privileged syntax. `len(x)`, `x[k]`, `a + b`,
`for i in x`, `with x:`, `x()` are all *dispatch* to methods with
reserved names. Learn the protocols and your own types become
indistinguishable from built-ins.

## Syntax is a call in disguise

| you write | Python calls |
|---|---|
| `len(x)` | `type(x).__len__(x)` |
| `x[k]` | `type(x).__getitem__(x, k)` |
| `a + b` | `type(a).__add__(a, b)`, then `type(b).__radd__(b, a)` |
| `for i in x` | `iter(x)` → `__iter__` or `__getitem__` |
| `x()` | `type(x).__call__(x)` |
| `print(x)` | `str(x)` → `__str__`, falling back to `__repr__` |
| `with x:` | `__enter__` / `__exit__` |
| `x.y` | `__getattribute__`, then `__getattr__` on failure |

Note the pattern: **the lookup happens on the type, not the
instance**. Assigning `obj.__len__ = ...` does nothing for `len(obj)`.

```python
class Weird:
    pass

w = Weird()
w.__len__ = lambda: 42          # instance attribute
print("attribute exists:", w.__len__())
try:
    len(w)
except TypeError as exc:
    print("but len() says:", exc)

Weird.__len__ = lambda self: 42  # on the TYPE
print("now len(w) =", len(w))
```
Implicit dunder lookup skips the instance `__dict__` entirely.
This is a deliberate optimisation *and* it keeps special methods
from being shadowed by data. It also means duck-typing a protocol
onto a single object requires patching its class.

## `__repr__` vs `__str__`

- `__repr__` — unambiguous, for developers. Ideally valid Python that
  would rebuild the object. This is what the REPL, containers, and
  debuggers show. **Always define it.**
- `__str__` — readable, for users. Defaults to `__repr__`.
- `__format__` — powers `f"{x:spec}"` and `format(x, spec)`.

```python
class Money:
    __slots__ = ("amount", "currency")

    def __init__(self, amount, currency="USD"):
        self.amount, self.currency = amount, currency

    def __repr__(self):
        return f"Money({self.amount!r}, {self.currency!r})"

    def __str__(self):
        return f"{self.amount:,.2f} {self.currency}"

    def __format__(self, spec):
        if spec == "sym":
            symbols = {"USD": "$", "EUR": "€", "INR": "₹"}
            return f"{symbols.get(self.currency, '')}{self.amount:,.2f}"
        if spec == "":
            return str(self)
        return format(self.amount, spec)      # delegate to float

m = Money(1234.5, "EUR")
print("repr :", repr(m))
print("str  :", str(m))
print("in a list:", [m])          # containers use repr
print("f-str:", f"{m}")
print("custom spec:", f"{m:sym}")
print("delegated:  ", f"{m:>12.1f}")
```
`!r` inside an f-string means "use repr". Containers *always* use
`repr` on their elements — that is why a list of objects with only
`__str__` looks like `<__main__.X object at 0x...>`.

**Quiz.** You define only `__str__` on a class. What does `print([obj])` show?

- a) Your `__str__` output
- b) The default `<Class object at 0x...>` repr
- c) A TypeError
- d) An empty list

<details><summary>answer</summary>

**b** — Containers call `repr()` on their items, and `__repr__` was not overridden. Define `__repr__` first; `__str__` is optional.
</details>

## Equality and hashing travel together

The contract, and it is a hard contract:

1. `a == b` **must** imply `hash(a) == hash(b)`
2. equality should be reflexive, symmetric, transitive
3. if you define `__eq__`, Python sets `__hash__ = None` — your class
   becomes unhashable unless you define `__hash__` too
4. hash on **immutable** parts only

Rule 3 is a safety feature: an object whose equality is value-based
but whose hash is identity-based would break every dict that holds it.

```python
class Point:
    def __init__(self, x, y):
        self.x, self.y = x, y
    def __eq__(self, other):
        if not isinstance(other, Point):
            return NotImplemented          # let the other side try
        return (self.x, self.y) == (other.x, other.y)
    def __repr__(self):
        return f"Point({self.x}, {self.y})"

print(Point(1, 2) == Point(1, 2))
print("compared to a non-Point:", Point(1, 2) == "nope")
try:
    {Point(1, 2)}
except TypeError as exc:
    print("unhashable now:", exc)

class HashablePoint(Point):
    __hash__ = lambda self: hash((self.x, self.y))

print("set dedupes:", {HashablePoint(1, 2), HashablePoint(1, 2)})
```
Returning `NotImplemented` (not `False`, and not raising) is the
correct answer for "I don't know how to compare against that".
Python then tries the reflected operation and finally falls back
to identity comparison, so `Point(1,2) == "nope"` yields `False`
without you hard-coding that decision.


## Ordering: `__lt__` and friends

Python needs `__lt__` for `sorted()`, `min()`, `max()`, and `<`.
`functools.total_ordering` fills in the rest from `__eq__` + one
ordering method — convenient, slightly slower than writing all six.

```python
from functools import total_ordering

@total_ordering
class Version:
    def __init__(self, text):
        self.parts = tuple(int(p) for p in text.split("."))
        self.text = text
    def __eq__(self, other):
        return isinstance(other, Version) and self.parts == other.parts
    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self.parts < other.parts
    def __hash__(self): return hash(self.parts)
    def __repr__(self): return f"v{self.text}"

versions = [Version(t) for t in ("1.10.0", "1.2.0", "2.0.0", "1.2.10")]
print("sorted:", sorted(versions))
print("max   :", max(versions))
print(">= came free:", Version("2.0.0") >= Version("1.2.0"))
```
Tuple comparison is lexicographic and element-wise, which makes
it the workhorse for building comparison keys: reduce your object
to a tuple of comparable fields and let tuples do the work.

## The container protocol

Implement these and your object behaves like a built-in collection:

- `__len__`, `__getitem__`, `__setitem__`, `__delitem__`
- `__contains__` (falls back to iterating if absent)
- `__iter__`, `__reversed__`

`__getitem__` alone is enough for `for`, `in`, unpacking, and even
`reversed()` (when combined with `__len__`) — a legacy protocol that
still works and still surprises people.

```python
class Grid:
    def __init__(self, w, h, fill=0):
        self.w, self.h = w, h
        self._cells = [fill] * (w * h)

    def _index(self, key):
        x, y = key                      # key is a tuple: g[1, 2]
        if not (0 <= x < self.w and 0 <= y < self.h):
            raise IndexError(f"({x}, {y}) out of bounds")
        return y * self.w + x

    def __getitem__(self, key): return self._cells[self._index(key)]
    def __setitem__(self, key, v): self._cells[self._index(key)] = v
    def __len__(self): return len(self._cells)
    def __iter__(self):
        for y in range(self.h):
            yield self._cells[y * self.w:(y + 1) * self.w]
    def __contains__(self, value): return value in self._cells
    def __repr__(self):
        return "\n".join(" ".join(str(c) for c in row) for row in self)

g = Grid(3, 2)
g[1, 0] = 7
g[2, 1] = 9
print(g)
print("len:", len(g), "| 7 in g:", 7 in g, "| rows:", list(g))
```
`g[1, 0]` passes the **tuple** `(1, 0)` as a single key — that is
all multidimensional indexing is. NumPy's `a[1:3, ::2]` is the
same trick with `slice` objects inside the tuple.

```python
# __getitem__ handling both ints and slices, the way list does.
class Playlist:
    def __init__(self, songs): self.songs = list(songs)
    def __len__(self): return len(self.songs)
    def __getitem__(self, key):
        if isinstance(key, slice):
            # Returning our own type keeps slicing composable.
            return Playlist(self.songs[key])
        return self.songs[key]
    def __repr__(self): return f"Playlist({self.songs})"

p = Playlist(["a", "b", "c", "d", "e"])
print("int index :", p[2])
print("slice     :", p[1:4])
print("step slice:", p[::2])
print("negative  :", p[-1])
print("iterates via __getitem__ +  IndexError:", [s for s in p])
```
A slice arrives as a `slice(start, stop, step)` object. Passing it
straight through to the underlying list is the easy correct move;
`slice.indices(len(self))` gives you concrete numbers if you need
to loop yourself.

**Quiz.** Which single dunder is enough to make `for x in obj:` work on a class with no `__iter__`?

- a) `__next__`
- b) `__len__`
- c) `__getitem__` that raises IndexError past the end
- d) `__contains__`

<details><summary>answer</summary>

**c** — The legacy sequence protocol: `iter()` builds an iterator that calls `obj[0]`, `obj[1]`, … and stops on IndexError.
</details>

## Numeric operators and reflection

For `a + b` Python tries `type(a).__add__(a, b)`. If that returns
`NotImplemented`, it tries `type(b).__radd__(b, a)`. If *that* also
declines, you get a `TypeError`.

One exception worth knowing: if `type(b)` is a **subclass** of
`type(a)` and overrides the reflected method, `b.__radd__` is tried
*first* — so subclasses can win.

```python
class Vec:
    def __init__(self, *comps): self.c = tuple(comps)
    def __repr__(self): return f"Vec{self.c}"

    def __add__(self, other):
        if isinstance(other, Vec):
            return Vec(*(a + b for a, b in zip(self.c, other.c)))
        return NotImplemented

    def __mul__(self, k):                 # Vec * scalar
        if isinstance(k, (int, float)):
            return Vec(*(a * k for a in self.c))
        if isinstance(k, Vec):            # dot product
            return sum(a * b for a, b in zip(self.c, k.c))
        return NotImplemented

    __rmul__ = __mul__                    # scalar * Vec
    def __neg__(self): return self * -1
    def __sub__(self, o): return self + (-o)
    def __abs__(self): return sum(a * a for a in self.c) ** 0.5
    def __bool__(self): return any(self.c)
    def __eq__(self, o): return isinstance(o, Vec) and self.c == o.c

v, w = Vec(1, 2), Vec(3, 4)
print("v + w   =", v + w)
print("v - w   =", v - w)
print("3 * v   =", 3 * v, "  <- __rmul__")
print("v · w   =", v * w)
print("abs(w)  =", abs(w))
print("bool    =", bool(Vec(0, 0)), bool(v))
try:
    v + "oops"
except TypeError as exc:
    print("TypeError:", exc)
```
`3 * v` fails on `int.__mul__(3, v)`, which returns
`NotImplemented`, so Python asks `Vec.__rmul__(v, 3)`. Without
`__rmul__` you would be stuck writing `v * 3` forever.

## `__bool__` and `__len__`

Truthiness checks `__bool__` first, then `__len__` (empty = falsy),
and defaults to `True`. A common bug: a class with `__len__` that can
return 0 becomes falsy, so `if my_obj:` silently means "if non-empty".

```python
class Response:
    def __init__(self, status, items):
        self.status, self.items = status, items
    def __len__(self): return len(self.items)

empty_ok = Response(200, [])
print("status 200 but falsy:", bool(empty_ok))
print("this is why you write `if resp is not None:`")

class Fixed(Response):
    def __bool__(self): return 200 <= self.status < 300
print("with __bool__:", bool(Fixed(200, [])), bool(Fixed(500, [1])))
```
With no `__bool__`, truthiness falls back to `__len__` — so a
perfectly successful response carrying zero items is **falsy**,
and `if resp:` quietly takes the failure branch.

Two rules come out of this. Define `__bool__` whenever *empty* and
*invalid* are different states for your type. And when you mean
"was I given one at all", write `if resp is not None:` — the only
test that cannot be hijacked by either protocol.

## Callables, and the attribute hooks

- `__call__` — instances behave like functions; the basis of
  stateful "function objects", decorators-as-classes, and partials.
- `__getattr__` — called **only when normal lookup fails**.
- `__getattribute__` — called for *every* attribute access. Powerful,
  easy to make infinitely recursive, rarely what you want.
- `__setattr__` / `__delattr__` — intercept writes.
- `__dir__` — what `dir()` reports.

```python
class Recorder:
    '''Records every call made through it -- a mini spy object.'''
    def __init__(self):
        object.__setattr__(self, "calls", [])

    def __getattr__(self, name):
        # Only reached for attributes that don't exist.
        if name.startswith("_"):
            raise AttributeError(name)
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return f"{name} recorded"
        return method

    def __setattr__(self, name, value):
        self.calls.append(("SET", name, value))
        object.__setattr__(self, name, value)

r = Recorder()
print(r.save(1, mode="fast"))
print(r.delete("x"))
r.threshold = 0.5
print(r.calls)
```
Note `object.__setattr__(self, "calls", [])` in `__init__`: going
through our own `__setattr__` before `calls` exists would recurse.
Any `__setattr__` override must write through `object.__setattr__`
or `self.__dict__[...]`, never `self.x = ...`.


**Quiz.** When is `__getattr__` called?

- a) On every attribute access
- b) Only when the normal lookup (instance dict, class, MRO, descriptors) fails
- c) Only for attributes starting with an underscore
- d) Only when `getattr()` is called explicitly

<details><summary>answer</summary>

**b** — It is the fallback hook. `__getattribute__` is the one that intercepts *every* access.
</details>

## Exercise — A hashable, immutable mapping `[medium]`

Build `FrozenDict`, a read-only mapping that can be used as a dict
key. Required behaviour:

- `FrozenDict(a=1, b=2)` and `FrozenDict({'a': 1})` both work
- `fd['a']`, `len(fd)`, `'a' in fd`, `iter(fd)` yields keys
- `.keys()`, `.values()`, `.items()`, `.get(key, default)`
- `fd['x'] = 1` raises `TypeError`
- `==` compares contents; order must not matter
- `hash(fd)` works, is order-independent, and equal instances hash equal
- `repr(fd)` starts with `FrozenDict(`
```python
class FrozenDict:
    def __init__(self, data=None, **kwargs):
        ...
```

## Exercise — Interval arithmetic with full operator support `[tricky]`

Implement `Interval(lo, hi)` representing the closed range `[lo, hi]`.

- `__repr__` → `Interval(1, 5)`
- `x in interval` → True when `lo <= x <= hi`
- `len(interval)` → the integer width `hi - lo` (use `int()`)
- `a + b` → `Interval(a.lo + b.lo, a.hi + b.hi)`; adding a **number**
  shifts both ends
- `a * k` and `k * a` for a number `k` scale both ends, and must
  stay ordered (`Interval(1, 3) * -1` → `Interval(-3, -1)`)
- `a & b` → overlap as a new Interval, or `None` when disjoint
- `a < b` is True when `a` lies entirely below `b` (`a.hi < b.lo`);
  `sorted()` on non-overlapping intervals must work
- `==` compares endpoints; intervals are hashable
- constructing with `lo > hi` raises `ValueError`
```python
class Interval:
    def __init__(self, lo, hi):
        ...
```

## Takeaways

- Special methods are looked up on the **type**, implicitly.
- Define `__repr__` always; `__str__` only when users see it.
- `__eq__` without `__hash__` makes the class unhashable — on purpose.
- Return `NotImplemented` from operators you can't handle, so the
  reflected operation gets a turn.
- `__getattr__` is a fallback; `__getattribute__` is a firehose.
