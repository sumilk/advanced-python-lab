# 09 — Descriptors and Properties

Descriptors are the mechanism behind `property`, `classmethod`,
`staticmethod`, `functools.cached_property`, `__slots__`, and every ORM
field you have ever used. They are also the cleanest way to factor out
repeated attribute logic. Once you see that a plain method is *also* a
descriptor, the whole object system clicks into place.

## The protocol

A **descriptor** is any object whose *class* defines at least one of:

| method | called for |
|---|---|
| `__get__(self, obj, objtype)` | attribute read |
| `__set__(self, obj, value)` | attribute write |
| `__delete__(self, obj)` | `del obj.attr` |
| `__set_name__(self, owner, name)` | at class creation, to learn its own name |

- **data descriptor** — defines `__set__` and/or `__delete__`.
  Takes precedence over the instance `__dict__`.
- **non-data descriptor** — only `__get__`. The instance dict wins.

Descriptors only work when placed on a **class**, never on an instance.

```python
class Loud:
    def __set_name__(self, owner, name):
        print(f"  __set_name__: I live on {owner.__name__} as {name!r}")
        self.name = name
    def __get__(self, obj, objtype=None):
        print(f"  __get__(obj={obj!r}, objtype={objtype.__name__})")
        if obj is None:
            return self               # accessed on the class
        return obj.__dict__.get(self.name, "unset")
    def __set__(self, obj, value):
        print(f"  __set__({value!r})")
        obj.__dict__[self.name] = value

class Thing:
    field = Loud()

print("--- class creation happened above ---")
t = Thing()
t.field = 42
print("read:", t.field)
print("on the class:", Thing.field)
```
`__set_name__` (3.6+) is what lets a descriptor learn the attribute
name it was assigned to — before it existed, every ORM made you
write `name = Field("name")`.

When accessed on the class rather than an instance, `obj` is
`None`; returning `self` is the convention so that
`Thing.field` gives you the descriptor for introspection.


## Functions are descriptors — that is how `self` works

A plain function stored on a class is a non-data descriptor. Accessing
it through an instance calls `function.__get__(instance, cls)`, which
returns a **bound method** — a small object holding the function and
the instance. Calling it inserts the instance as the first argument.

```python
class C:
    def method(self, x): return f"method({self!r}, {x})"

c = C()
print("via instance:", type(c.method).__name__)
print("via class   :", type(C.method).__name__)
print("bound to    :", c.method.__self__ is c)
print("underlying  :", c.method.__func__ is C.method)

# Binding by hand -- exactly what attribute access does:
manual = C.method.__get__(c, C)
print("manual bind:", manual(1))

# classmethod and staticmethod are descriptors too.
print("classmethod :", type(C.__dict__.get("method")).__name__)

class D:
    @staticmethod
    def s(): return "static"
    @classmethod
    def c(cls): return f"class {cls.__name__}"
print(type(D.__dict__["s"]).__name__, "->", D.s())
print(type(D.__dict__["c"]).__name__, "->", D.c())
```

**Quiz.** Why does `obj.method` automatically receive `obj` as `self`?

- a) The interpreter special-cases attribute access on classes
- b) `function.__get__` returns a bound method that stores the instance
- c) `self` is a reserved keyword filled in by the compiler
- d) Methods are stored per instance, each capturing its own object

<details><summary>answer</summary>

**b** — Functions implement the descriptor protocol. `obj.method` is `type(obj).method.__get__(obj, type(obj))`, which produces the bound method.
</details>

## `property`: the descriptor you already use

`property` is a data descriptor implemented in C. Its constructor is
`property(fget, fset, fdel, doc)`; the `@x.setter` syntax just builds
a *new* property with one more function filled in.

```python
class Celsius:
    def __init__(self, degrees=0.0):
        self.degrees = degrees            # goes through the setter

    @property
    def degrees(self):
        return self._degrees

    @degrees.setter
    def degrees(self, value):
        if value < -273.15:
            raise ValueError("below absolute zero")
        self._degrees = float(value)

    @property
    def fahrenheit(self):                  # computed, read-only
        return self._degrees * 9 / 5 + 32

t = Celsius(25)
print(t.degrees, "C =", t.fahrenheit, "F")
t.degrees = 100
print("updated:", t.fahrenheit)

try:
    t.degrees = -300
except ValueError as exc:
    print("validated:", exc)
try:
    t.fahrenheit = 0
except AttributeError as exc:
    print("read-only:", exc)

# The equivalent without syntax sugar:
print("property is just an object:", type(Celsius.degrees).__name__,
      "| fset set:", Celsius.degrees.fset is not None)
```

## When a property is not enough

Properties do not compose: validating ten fields the same way means
ten near-identical property pairs. A descriptor class is written once
and reused everywhere — that is the entire argument for them.

```python
class Typed:
    '''Reusable type-checked attribute.'''
    def __init__(self, expected_type, default=None):
        self.expected_type = expected_type
        self.default = default

    def __set_name__(self, owner, name):
        self.private = "_" + name
        self.public = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.private, self.default)

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(
                f"{self.public} must be {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        setattr(obj, self.private, value)

class User:
    name = Typed(str, "")
    age = Typed(int, 0)
    tags = Typed(list)

    def __init__(self, name, age):
        self.name, self.age = name, age

u = User("ada", 36)
print(u.name, u.age, "| default:", u.tags)
try:
    u.age = "thirty"
except TypeError as exc:
    print("rejected:", exc)
```
Note the storage strategy: writing to `obj._age` rather than a dict
keyed by instance. Never store per-instance state on the
*descriptor itself* — there is exactly one descriptor object shared
by every instance of the class.

```python
# The classic bug: state on the descriptor instead of the instance.
class Broken:
    def __init__(self): self.value = None
    def __get__(self, obj, objtype=None): return self.value
    def __set__(self, obj, value): self.value = value   # SHARED!

class Item:
    field = Broken()

a, b = Item(), Item()
a.field = "a's value"
b.field = "b's value"
print("a.field =", a.field, "  <- clobbered by b")
print("same descriptor object:", Item.__dict__["field"] is Item.__dict__["field"])
```

## Where to store the value

1. **Instance `__dict__` under the public name** — only safe for a
   *non-data* descriptor, or you get infinite recursion.
2. **Instance `__dict__` under a private name** (`_x`) — simple and
   debuggable. What most code does.
3. **A `WeakKeyDictionary` keyed by instance** — works with
   `__slots__`, requires hashable instances, adds indirection.

```python
import weakref

class WeakStored:
    def __set_name__(self, owner, name): self.name = name
    def __init__(self): self.data = weakref.WeakKeyDictionary()
    def __get__(self, obj, objtype=None):
        if obj is None: return self
        return self.data.get(obj)
    def __set__(self, obj, value): self.data[obj] = value

class Slotted:
    __slots__ = ("__weakref__",)        # needed for weak references
    x = WeakStored()

s = Slotted()
s.x = 42
print("works with __slots__:", s.x)
print("entries:", len(Slotted.x.data))
del s
print("after the instance dies:", len(Slotted.x.data))
```
The weak dictionary drops its entry automatically when the instance
is collected — a plain dict here would leak every object forever.

```python
# __delete__ and the full lifecycle.
class Tracked:
    def __set_name__(self, owner, name): self.private = "_" + name
    def __get__(self, obj, objtype=None):
        if obj is None: return self
        try:
            return getattr(obj, self.private)
        except AttributeError:
            raise AttributeError("value has been deleted") from None
    def __set__(self, obj, value): setattr(obj, self.private, value)
    def __delete__(self, obj):
        print("  __delete__ called")
        try:
            delattr(obj, self.private)
        except AttributeError:
            pass

class C:
    v = Tracked()

c = C()
c.v = 1
print("set:", c.v)
del c.v
try:
    c.v
except AttributeError as exc:
    print("after delete:", exc)
```

## Exercise — A configurable validating descriptor `[tricky]`

Write `Field(*, type=None, min=None, max=None, choices=None,
default=MISSING, required=True)` — one descriptor covering the
validation you actually need.

- `type` → `TypeError` on mismatch (allow `int` where `float` is
  expected, but reject `bool` for both)
- `min` / `max` → `ValueError` when out of range (inclusive)
- `choices` → `ValueError` when not a member
- reading before any assignment returns `default`, or raises
  `AttributeError` when the field is `required` and has no default
- error messages must contain the attribute's name
- each instance keeps its own value; the descriptor holds none
- accessing the field on the **class** returns the descriptor
- `del obj.field` resets it to the unset state
- validation must run in this order: type, then choices, then range
```python
MISSING = object()


class Field:
    def __init__(self, *, type=None, min=None, max=None,
                 choices=None, default=MISSING, required=True):
        ...
```

## Takeaways

- A descriptor is a class attribute implementing `__get__`/`__set__`/
  `__delete__`; `__set_name__` tells it its own name.
- Data descriptors beat the instance dict; non-data descriptors lose
  to it.
- Functions are non-data descriptors — that is the origin of `self`.
- Never keep per-instance state on the descriptor object.
- Use a property for one attribute, a descriptor class when the same
  logic repeats.
