"""Lesson 02 — The data model: dunder protocols."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=2,
    slug="datamodel",
    title="The Data Model — Dunder Protocols",
    summary="""
    Python has almost no privileged syntax. `len(x)`, `x[k]`, `a + b`,
    `for i in x`, `with x:`, `x()` are all *dispatch* to methods with
    reserved names. Learn the protocols and your own types become
    indistinguishable from built-ins.
    """,
    tags=("dunder", "protocols", "operators"),
    blocks=[
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Implicit dunder lookup skips the instance `__dict__` entirely.
            This is a deliberate optimisation *and* it keeps special methods
            from being shadowed by data. It also means duck-typing a protocol
            onto a single object requires patching its class.
            """,
        ),
        Text("""
        ## `__repr__` vs `__str__`

        - `__repr__` — unambiguous, for developers. Ideally valid Python that
          would rebuild the object. This is what the REPL, containers, and
          debuggers show. **Always define it.**
        - `__str__` — readable, for users. Defaults to `__repr__`.
        - `__format__` — powers `f"{x:spec}"` and `format(x, spec)`.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `!r` inside an f-string means "use repr". Containers *always* use
            `repr` on their elements — that is why a list of objects with only
            `__str__` looks like `<__main__.X object at 0x...>`.
            """,
        ),
        Question(
            prompt="You define only `__str__` on a class. What does `print([obj])` show?",
            choices=[
                "Your `__str__` output",
                "The default `<Class object at 0x...>` repr",
                "A TypeError",
                "An empty list",
            ],
            answer=1,
            explain="Containers call `repr()` on their items, and `__repr__` was "
                    "not overridden. Define `__repr__` first; `__str__` is optional.",
        ),
        Text("""
        ## Equality and hashing travel together

        The contract, and it is a hard contract:

        1. `a == b` **must** imply `hash(a) == hash(b)`
        2. equality should be reflexive, symmetric, transitive
        3. if you define `__eq__`, Python sets `__hash__ = None` — your class
           becomes unhashable unless you define `__hash__` too
        4. hash on **immutable** parts only

        Rule 3 is a safety feature: an object whose equality is value-based
        but whose hash is identity-based would break every dict that holds it.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Returning `NotImplemented` (not `False`, and not raising) is the
            correct answer for "I don't know how to compare against that".
            Python then tries the reflected operation and finally falls back
            to identity comparison, so `Point(1,2) == "nope"` yields `False`
            without you hard-coding that decision.
            """,
        ),
        Predict(
            code="""
            class Case:
                def __init__(self, s): self.s = s
                def __eq__(self, o): return self.s.lower() == o.s.lower()
                def __hash__(self): return hash(self.s)     # BUG: not lowered

            a, b = Case("Hello"), Case("hello")
            print(a == b)
            print(len({a, b}))
            """,
            answer="""
            True
            2
            """,
            explain="""
            Equal objects landed in different buckets, so the set holds two
            "equal" items — the contract is broken. `__hash__` must be
            computed from exactly the same normalised data as `__eq__`:
            `hash(self.s.lower())`.
            """,
        ),
        Text("""
        ## Ordering: `__lt__` and friends

        Python needs `__lt__` for `sorted()`, `min()`, `max()`, and `<`.
        `functools.total_ordering` fills in the rest from `__eq__` + one
        ordering method — convenient, slightly slower than writing all six.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Tuple comparison is lexicographic and element-wise, which makes
            it the workhorse for building comparison keys: reduce your object
            to a tuple of comparable fields and let tuples do the work.
            """,
        ),
        Text("""
        ## The container protocol

        Implement these and your object behaves like a built-in collection:

        - `__len__`, `__getitem__`, `__setitem__`, `__delitem__`
        - `__contains__` (falls back to iterating if absent)
        - `__iter__`, `__reversed__`

        `__getitem__` alone is enough for `for`, `in`, unpacking, and even
        `reversed()` (when combined with `__len__`) — a legacy protocol that
        still works and still surprises people.
        """),
        Demo(
            code="""
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
                    return "\\n".join(" ".join(str(c) for c in row) for row in self)

            g = Grid(3, 2)
            g[1, 0] = 7
            g[2, 1] = 9
            print(g)
            print("len:", len(g), "| 7 in g:", 7 in g, "| rows:", list(g))
            """,
            explain="""
            `g[1, 0]` passes the **tuple** `(1, 0)` as a single key — that is
            all multidimensional indexing is. NumPy's `a[1:3, ::2]` is the
            same trick with `slice` objects inside the tuple.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            A slice arrives as a `slice(start, stop, step)` object. Passing it
            straight through to the underlying list is the easy correct move;
            `slice.indices(len(self))` gives you concrete numbers if you need
            to loop yourself.
            """,
        ),
        Question(
            prompt="Which single dunder is enough to make `for x in obj:` work on a class with no `__iter__`?",
            choices=[
                "`__next__`",
                "`__len__`",
                "`__getitem__` that raises IndexError past the end",
                "`__contains__`",
            ],
            answer=2,
            explain="The legacy sequence protocol: `iter()` builds an iterator that "
                    "calls `obj[0]`, `obj[1]`, … and stops on IndexError.",
        ),
        Text("""
        ## Numeric operators and reflection

        For `a + b` Python tries `type(a).__add__(a, b)`. If that returns
        `NotImplemented`, it tries `type(b).__radd__(b, a)`. If *that* also
        declines, you get a `TypeError`.

        One exception worth knowing: if `type(b)` is a **subclass** of
        `type(a)` and overrides the reflected method, `b.__radd__` is tried
        *first* — so subclasses can win.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `3 * v` fails on `int.__mul__(3, v)`, which returns
            `NotImplemented`, so Python asks `Vec.__rmul__(v, 3)`. Without
            `__rmul__` you would be stuck writing `v * 3` forever.
            """,
        ),
        Text("""
        ## `__bool__` and `__len__`

        Truthiness checks `__bool__` first, then `__len__` (empty = falsy),
        and defaults to `True`. A common bug: a class with `__len__` that can
        return 0 becomes falsy, so `if my_obj:` silently means "if non-empty".
        """),
        Demo(
            code="""
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
            """,
        ),
        Text("""
        ## Callables, and the attribute hooks

        - `__call__` — instances behave like functions; the basis of
          stateful "function objects", decorators-as-classes, and partials.
        - `__getattr__` — called **only when normal lookup fails**.
        - `__getattribute__` — called for *every* attribute access. Powerful,
          easy to make infinitely recursive, rarely what you want.
        - `__setattr__` / `__delattr__` — intercept writes.
        - `__dir__` — what `dir()` reports.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Note `object.__setattr__(self, "calls", [])` in `__init__`: going
            through our own `__setattr__` before `calls` exists would recurse.
            Any `__setattr__` override must write through `object.__setattr__`
            or `self.__dict__[...]`, never `self.x = ...`.
            """,
        ),
        Predict(
            code="""
            class Bad:
                def __getattribute__(self, name):
                    return self.__dict__[name]         # <- re-enters itself

            class Good:
                def __getattribute__(self, name):
                    return object.__getattribute__(self, name)

            b, g = Bad(), Good()
            object.__setattr__(b, "x", 1)
            g.x = 1
            try:
                print(b.x)
            except RecursionError:
                print("Bad  -> RecursionError")
            print("Good ->", g.x)
            """,
            answer="""
            Bad  -> RecursionError
            Good -> 1
            """,
            explain="""
            `self.__dict__` inside `__getattribute__` re-enters
            `__getattribute__`. The fix is `object.__getattribute__(self, name)`
            or `super().__getattribute__(name)`.
            """,
        ),
        Question(
            prompt="When is `__getattr__` called?",
            choices=[
                "On every attribute access",
                "Only when the normal lookup (instance dict, class, MRO, descriptors) fails",
                "Only for attributes starting with an underscore",
                "Only when `getattr()` is called explicitly",
            ],
            answer=1,
            explain="It is the fallback hook. `__getattribute__` is the one that "
                    "intercepts *every* access.",
        ),
        Exercise(
            slug="frozen-dict",
            title="A hashable, immutable mapping",
            difficulty="medium",
            brief="""
            Build `FrozenDict`, a read-only mapping that can be used as a dict
            key. Required behaviour:

            - `FrozenDict(a=1, b=2)` and `FrozenDict({'a': 1})` both work
            - `fd['a']`, `len(fd)`, `'a' in fd`, `iter(fd)` yields keys
            - `.keys()`, `.values()`, `.items()`, `.get(key, default)`
            - `fd['x'] = 1` raises `TypeError`
            - `==` compares contents; order must not matter
            - `hash(fd)` works, is order-independent, and equal instances hash equal
            - `repr(fd)` starts with `FrozenDict(`
            """,
            starter="""
            class FrozenDict:
                def __init__(self, data=None, **kwargs):
                    ...
            """,
            checks=[
                Check("constructs from mapping and kwargs", lambda ns: _fd_construct(ns["FrozenDict"])),
                Check("mapping reads work", lambda ns: _fd_reads(ns["FrozenDict"])),
                Check("writes raise TypeError", lambda ns: _fd_immutable(ns["FrozenDict"])),
                Check("equality ignores insertion order", lambda ns: _fd_eq(ns["FrozenDict"])),
                Check("hashable and usable as a dict key", lambda ns: _fd_hash(ns["FrozenDict"])),
                Check("repr is informative", lambda ns: _fd_repr(ns["FrozenDict"])),
                Check("unequal contents hash into distinct entries",
                      lambda ns: _fd_distinct(ns["FrozenDict"])),
            ],
            hints=(
                "Store the data in `self._data` via `object.__setattr__` if you "
                "also block attribute writes.",
                "`hash(frozenset(self._data.items()))` is order-independent.",
                "Cache the hash — recomputing it on every dict lookup is wasteful.",
                "`__setitem__` is what `fd['x'] = 1` calls.",
            ),
            solution="""
            class FrozenDict:
                def __init__(self, data=None, **kwargs):
                    combined = dict(data or {})
                    combined.update(kwargs)
                    object.__setattr__(self, "_data", combined)
                    object.__setattr__(self, "_hash", None)

                def __getitem__(self, key): return self._data[key]
                def __len__(self): return len(self._data)
                def __iter__(self): return iter(self._data)
                def __contains__(self, key): return key in self._data
                def keys(self): return self._data.keys()
                def values(self): return self._data.values()
                def items(self): return self._data.items()
                def get(self, key, default=None): return self._data.get(key, default)

                def __setitem__(self, key, value):
                    raise TypeError("FrozenDict is immutable")
                def __delitem__(self, key):
                    raise TypeError("FrozenDict is immutable")

                def __eq__(self, other):
                    if isinstance(other, FrozenDict):
                        return self._data == other._data
                    if isinstance(other, dict):
                        return self._data == other
                    return NotImplemented

                def __hash__(self):
                    if self._hash is None:
                        object.__setattr__(self, "_hash",
                                           hash(frozenset(self._data.items())))
                    return self._hash

                def __repr__(self):
                    inner = ", ".join(f"{k!r}: {v!r}" for k, v in self._data.items())
                    return f"FrozenDict({{{inner}}})"
            """,
        ),
        Exercise(
            slug="interval",
            title="Interval arithmetic with full operator support",
            difficulty="tricky",
            brief="""
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
            """,
            starter="""
            class Interval:
                def __init__(self, lo, hi):
                    ...
            """,
            checks=[
                Check("validates and reprs", lambda ns: _iv_basic(ns["Interval"])),
                Check("membership and len", lambda ns: _iv_contains(ns["Interval"])),
                Check("addition: interval and scalar", lambda ns: _iv_add(ns["Interval"])),
                Check("scaling both directions, negative-safe", lambda ns: _iv_mul(ns["Interval"])),
                Check("intersection with &", lambda ns: _iv_and(ns["Interval"])),
                Check("ordering and sorted()", lambda ns: _iv_order(ns["Interval"])),
                Check("equality and hashing", lambda ns: _iv_hash(ns["Interval"])),
            ],
            hints=(
                "For `__mul__` with a negative scalar, compute both products then "
                "`min`/`max` them.",
                "`__rmul__ = __mul__` covers `2 * iv` since scaling commutes.",
                "Return `NotImplemented` for unsupported operand types rather than "
                "raising — Python turns it into a good TypeError for you.",
                "For `&`, the overlap is `max(los)` to `min(his)`; it exists only "
                "when that range is non-empty.",
            ),
            solution="""
            from numbers import Number

            class Interval:
                __slots__ = ("lo", "hi")

                def __init__(self, lo, hi):
                    if lo > hi:
                        raise ValueError(f"lo ({lo}) must not exceed hi ({hi})")
                    object.__setattr__(self, "lo", lo)
                    object.__setattr__(self, "hi", hi)

                def __repr__(self): return f"Interval({self.lo!r}, {self.hi!r})"
                def __contains__(self, x): return self.lo <= x <= self.hi
                def __len__(self): return int(self.hi - self.lo)

                def __add__(self, other):
                    if isinstance(other, Interval):
                        return Interval(self.lo + other.lo, self.hi + other.hi)
                    if isinstance(other, Number):
                        return Interval(self.lo + other, self.hi + other)
                    return NotImplemented
                __radd__ = __add__

                def __mul__(self, k):
                    if not isinstance(k, Number):
                        return NotImplemented
                    a, b = self.lo * k, self.hi * k
                    return Interval(min(a, b), max(a, b))
                __rmul__ = __mul__

                def __and__(self, other):
                    lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
                    return Interval(lo, hi) if lo <= hi else None

                def __lt__(self, other):
                    if not isinstance(other, Interval):
                        return NotImplemented
                    return self.hi < other.lo

                def __eq__(self, other):
                    return (isinstance(other, Interval)
                            and (self.lo, self.hi) == (other.lo, other.hi))

                def __hash__(self): return hash((Interval, self.lo, self.hi))
            """,
        ),
        Text("""
        ## Takeaways

        - Special methods are looked up on the **type**, implicitly.
        - Define `__repr__` always; `__str__` only when users see it.
        - `__eq__` without `__hash__` makes the class unhashable — on purpose.
        - Return `NotImplemented` from operators you can't handle, so the
          reflected operation gets a turn.
        - `__getattr__` is a fallback; `__getattribute__` is a firehose.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _fd_construct(FD) -> None:
    assert dict(FD(a=1, b=2).items()) == {"a": 1, "b": 2}, "kwargs form failed"
    assert dict(FD({"a": 1}).items()) == {"a": 1}, "mapping form failed"
    assert dict(FD({"a": 1}, b=2).items()) == {"a": 1, "b": 2}, "combined form failed"


def _fd_reads(FD) -> None:
    fd = FD(a=1, b=2)
    assert fd["a"] == 1
    assert len(fd) == 2
    assert "b" in fd and "z" not in fd
    assert sorted(iter(fd)) == ["a", "b"], "iteration should yield keys"
    assert sorted(fd.keys()) == ["a", "b"]
    assert sorted(fd.values()) == [1, 2]
    assert fd.get("z", "dflt") == "dflt"


def _fd_immutable(FD) -> None:
    fd = FD(a=1)
    try:
        fd["b"] = 2
    except TypeError:
        return
    raise AssertionError("assignment should raise TypeError")


def _fd_eq(FD) -> None:
    assert FD(a=1, b=2) == FD(b=2, a=1), "order should not affect equality"
    assert FD(a=1) != FD(a=2)


def _fd_hash(FD) -> None:
    x, y = FD(a=1, b=2), FD(b=2, a=1)
    assert hash(x) == hash(y), "equal FrozenDicts must hash equal"
    registry = {x: "value"}
    assert registry[y] == "value", "lookup by an equal key failed"


def _fd_repr(FD) -> None:
    assert repr(FD(a=1)).startswith("FrozenDict("), f"got {repr(FD(a=1))!r}"


def _fd_distinct(FD) -> None:
    assert len({FD(a=1), FD(a=2), FD(a=1)}) == 2


def _iv_basic(Interval) -> None:
    assert repr(Interval(1, 5)) == "Interval(1, 5)", repr(Interval(1, 5))
    try:
        Interval(5, 1)
    except ValueError:
        return
    raise AssertionError("lo > hi should raise ValueError")


def _iv_contains(Interval) -> None:
    iv = Interval(1, 5)
    assert 1 in iv and 5 in iv and 3 in iv
    assert 0 not in iv and 6 not in iv
    assert len(iv) == 4, f"expected width 4, got {len(iv)}"


def _iv_add(Interval) -> None:
    assert Interval(1, 2) + Interval(10, 20) == Interval(11, 22)
    assert Interval(1, 2) + 5 == Interval(6, 7)


def _iv_mul(Interval) -> None:
    assert Interval(1, 3) * 2 == Interval(2, 6)
    assert 2 * Interval(1, 3) == Interval(2, 6), "__rmul__ missing"
    assert Interval(1, 3) * -1 == Interval(-3, -1), "negative scaling must reorder"


def _iv_and(Interval) -> None:
    assert (Interval(1, 5) & Interval(3, 9)) == Interval(3, 5)
    assert (Interval(1, 2) & Interval(8, 9)) is None, "disjoint should give None"
    assert (Interval(1, 5) & Interval(5, 9)) == Interval(5, 5), "touching endpoints overlap"


def _iv_order(Interval) -> None:
    assert Interval(1, 2) < Interval(3, 4)
    assert not (Interval(1, 5) < Interval(3, 4)), "overlapping is not 'below'"
    got = sorted([Interval(5, 6), Interval(1, 2), Interval(3, 4)])
    assert got == [Interval(1, 2), Interval(3, 4), Interval(5, 6)], got


def _iv_hash(Interval) -> None:
    assert Interval(1, 2) == Interval(1, 2)
    assert len({Interval(1, 2), Interval(1, 2), Interval(3, 4)}) == 2
