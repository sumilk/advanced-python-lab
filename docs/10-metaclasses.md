# 10 — Class Creation and Metaclasses

A `class` statement is executable code that calls a factory. Knowing the
exact sequence — namespace preparation, body execution, `type.__new__`,
`__set_name__`, `__init_subclass__` — lets you hook in at the cheapest
level rather than reaching for a metaclass every time. We cover the
lightweight hooks first, then ABCs, then metaclasses proper.

## What `class` actually does

```python
class C(Base, metaclass=M, **kwds):
    <body>
```

1. determine the metaclass `M` (explicit, else the most derived
   metaclass among the bases, else `type`)
2. `ns = M.__prepare__(name, bases, **kwds)` — usually an empty dict
3. execute `<body>` with `ns` as its local namespace
4. `C = M(name, bases, ns, **kwds)` → `M.__new__` then `M.__init__`
5. inside `type.__new__`: call `__set_name__` on every descriptor in
   the namespace, then call `Base.__init_subclass__(cls=C, **kwds)`

Steps 2 and 4 are the metaclass's territory. Step 5 gives you two
hooks that need no metaclass at all — reach for those first.

```python
# Building a class with no `class` statement at all.
def greet(self):
    return f"hi, I am {self.name}"

Dynamic = type(
    "Dynamic",                                  # __name__
    (object,),                                  # __bases__
    {"greet": greet, "kind": "generated",       # namespace
     "__init__": lambda self, name: setattr(self, "name", name)},
)

d = Dynamic("ada")
print(d.greet(), "|", Dynamic.kind, "|", type(d).__name__)
print("its type is type:", type(Dynamic))
print("classes are instances of their metaclass:", isinstance(Dynamic, type))
```
`type(name, bases, namespace)` *is* the class factory. The `class`
statement is syntax sugar over exactly this call.

```python
# Watch the order of the hooks.
class Descriptor:
    def __set_name__(self, owner, name):
        print(f"  3. __set_name__ for {name!r}")

class Base:
    def __init_subclass__(cls, tag=None, **kwargs):
        print(f"  4. __init_subclass__ for {cls.__name__}, tag={tag!r}")
        super().__init_subclass__(**kwargs)
        cls.tag = tag

print("1. about to execute the class body")

class Child(Base, tag="demo"):
    print("  2. class body running")
    field = Descriptor()

print("5. class object exists:", Child, "| tag:", Child.tag)
```
`__init_subclass__` is implicitly a `classmethod` and receives the
**new subclass**, not the base. Extra keyword arguments on the
`class` line are forwarded to it — that is a clean, documented
configuration channel.

## `__init_subclass__`: the registry pattern, done cheaply

Ninety per cent of the "I need a metaclass" cases are actually this:
run some code whenever someone subclasses me.

```python
class Plugin:
    registry: dict[str, type] = {}

    def __init_subclass__(cls, /, name=None, abstract=False, **kwargs):
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        key = name or cls.__name__.lower()
        if key in Plugin.registry:
            raise ValueError(f"duplicate plugin {key!r}")
        Plugin.registry[key] = cls
        cls.plugin_name = key

class Exporter(Plugin, abstract=True):
    def run(self): raise NotImplementedError

class JsonExporter(Exporter, name="json"):
    def run(self): return "{}"

class CsvExporter(Exporter):
    def run(self): return "a,b"

print("registry:", Plugin.registry)
print("instantiate by key:", Plugin.registry["json"]().run())

try:
    class Duplicate(Exporter, name="json"): pass
except ValueError as exc:
    print("caught:", exc)
```

**Quiz.** `__init_subclass__` is called with which class as its argument?

- a) The class that defines it
- b) The newly created subclass
- c) The metaclass
- d) `object`

<details><summary>answer</summary>

**b** — It is an implicit classmethod invoked on the *parent*, receiving the new subclass as `cls`. It does not run for the defining class itself.
</details>

## Abstract base classes

`abc.ABC` uses the `ABCMeta` metaclass to block instantiation until
every `@abstractmethod` is overridden. It also supports **virtual
subclasses** via `register`, and `__subclasshook__` for structural
checks — which is how `isinstance(x, Iterable)` works without any
inheritance.

```python
from abc import ABC, abstractmethod

class Storage(ABC):
    @abstractmethod
    def read(self, key): ...

    @abstractmethod
    def write(self, key, value): ...

    @property
    @abstractmethod
    def name(self): ...

    def copy_to(self, other, key):       # concrete, uses the abstracts
        other.write(key, self.read(key))

try:
    Storage()
except TypeError as exc:
    print("cannot instantiate:", exc)

class Memory(Storage):
    name = "memory"
    def __init__(self): self._data = {}
    def read(self, key): return self._data.get(key)
    def write(self, key, value): self._data[key] = value

m, n = Memory(), Memory()
m.write("k", "v")
m.copy_to(n, "k")
print("concrete method worked:", n.read("k"))
print("abstract methods:", sorted(Storage.__abstractmethods__))
```

```python
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sized

# Virtual subclasses: claim kinship without inheriting.
class Serialisable(ABC):
    @abstractmethod
    def dumps(self): ...

class LegacyThing:                 # cannot or will not inherit
    def dumps(self): return "legacy"

Serialisable.register(LegacyThing)
print("isinstance:", isinstance(LegacyThing(), Serialisable))
print("but no MRO link:", Serialisable in LegacyThing.__mro__)

# __subclasshook__: structural checks, no registration needed.
class Closeable(ABC):
    @classmethod
    def __subclasshook__(cls, other):
        if cls is Closeable:
            return any("close" in klass.__dict__ for klass in other.__mro__)
        return NotImplemented

class File:
    def close(self): pass
class Rock: pass

print("structural:", issubclass(File, Closeable), issubclass(Rock, Closeable))
print("this is how the stdlib does it:",
      isinstance([], Iterable), isinstance([], Sized))
```
Note the cost: `register` and `__subclasshook__` make `isinstance`
lie about the MRO. They are the right tool for protocol checks on
types you do not own — but `typing.Protocol` (lesson 13) is usually
the better modern answer.

## Metaclasses

A metaclass is the class of a class. Subclass `type` and override:

- `__prepare__(mcls, name, bases, **kwds)` → the namespace mapping used
  during body execution. Return an `OrderedDict`-like object to observe
  definition order or forbid redefinition.
- `__new__(mcls, name, bases, ns, **kwds)` → create and *modify* the
  class object.
- `__init__(cls, name, bases, ns, **kwds)` → configure it afterwards.
- `__call__(cls, *args, **kwargs)` → intercept **instantiation** of the
  classes it creates. This is where singletons and caching live.

```python
class Meta(type):
    @classmethod
    def __prepare__(mcls, name, bases, **kwds):
        print(f"  __prepare__({name})")
        return {}
    def __new__(mcls, name, bases, ns, **kwds):
        print(f"  __new__: creating {name} with {len(ns)} namespace entries")
        cls = super().__new__(mcls, name, bases, ns)
        cls.created_by = mcls.__name__
        return cls
    def __init__(cls, name, bases, ns, **kwds):
        print(f"  __init__: configuring {name}")
        super().__init__(name, bases, ns)
    def __call__(cls, *args, **kwargs):
        print(f"  __call__: instantiating {cls.__name__}")
        return super().__call__(*args, **kwargs)

class Widget(metaclass=Meta):
    def __init__(self, size): self.size = size

print("---")
w = Widget(3)
print("instance:", w.size, "| class attr:", Widget.created_by)
print("type(Widget) =", type(Widget).__name__)
```

```python
# __prepare__ doing real work: reject accidental redefinition.
class NoDuplicates(dict):
    def __setitem__(self, key, value):
        if key in self and not key.startswith("__"):
            raise TypeError(f"{key!r} is defined twice in this class body")
        super().__setitem__(key, value)

class StrictMeta(type):
    @classmethod
    def __prepare__(mcls, name, bases, **kwds):
        return NoDuplicates()
    def __new__(mcls, name, bases, ns, **kwds):
        return super().__new__(mcls, name, bases, dict(ns))

try:
    class Config(metaclass=StrictMeta):
        timeout = 30
        retries = 3
        timeout = 60          # a typo Python would normally accept silently
except TypeError as exc:
    print("caught:", exc)
```
Plain Python silently lets the second `timeout` win. In a large
settings class that is a genuinely nasty bug, and `__prepare__` is
the only hook that can see it — by the time `__new__` runs, the
namespace is already a plain dict with one entry.

```python
# __call__ on the metaclass: a singleton, correctly done.
class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class Connection(metaclass=Singleton):
    def __init__(self, dsn="default"):
        print(f"  really connecting to {dsn}")
        self.dsn = dsn

a = Connection("db://one")
b = Connection("db://two")     # __init__ does NOT run again
print("same object:", a is b, "| dsn:", b.dsn)
```
Why the metaclass rather than `__new__`? Overriding `__new__` to
return a cached instance still calls `__init__` on it every time,
silently re-initialising your singleton. Intercepting at
`__call__` prevents that.


**Quiz.** You want to run code each time a class is subclassed. What is the lightest tool?

- a) A metaclass overriding `__new__`
- b) `__init_subclass__` on the base class
- c) A class decorator on every subclass
- d) `__set_name__`

<details><summary>answer</summary>

**b** — It needs no metaclass, cannot cause metaclass conflicts, and is inherited automatically. Metaclasses are for when you must change *how the class object itself is built*.
</details>

## Metaclass conflicts, and when to just not

If two bases have different metaclasses, and neither is a subclass of
the other, the `class` statement fails. This is the practical reason
to avoid metaclasses in library code: you force every user of your
class into your metaclass hierarchy.

Decision order — pick the first that works:

1. a plain function or class decorator
2. `__init_subclass__` / `__set_name__`
3. `abc.ABC`
4. a metaclass

```python
class MetaA(type): pass
class MetaB(type): pass
class A(metaclass=MetaA): pass
class B(metaclass=MetaB): pass

try:
    class C(A, B): pass
except TypeError as exc:
    print("conflict:", exc)

# The fix: a metaclass inheriting from both.
class MetaAB(MetaA, MetaB): pass
class C(A, B, metaclass=MetaAB): pass
print("resolved:", type(C).__name__, [m.__name__ for m in type(C).__mro__[:3]])
```

## Exercise — A class decorator that adds __slots__ `[tricky]`

Write `autoslots(cls)` — a **class decorator** that rebuilds a class
with `__slots__` derived from its annotated class-level fields.

You cannot simply set `cls.__slots__` after the fact; slots only
take effect at class creation. Build a new class with `type(...)`.

- slots come from `cls.__annotations__` (its own, not inherited)
- annotated names that have a class-level *value* are defaults:
  keep them working through `__init__`
- generate an `__init__(self, **kwargs)` accepting each field as a
  keyword; fields without a default are required and raise
  `TypeError` when missing
- unknown keywords raise `TypeError`
- preserve methods, `__name__`, `__qualname__`, `__doc__`, and the
  original bases
- if the class already defines `__init__`, leave it alone
- the result must genuinely reject unknown attributes
```python
def autoslots(cls):
    ...
```

## Exercise — A metaclass enforcing @final and interfaces `[brutal]`

Write `StrictMeta`, a metaclass that enforces three rules at class
creation time, plus the `final` decorator it recognises.

1. **`@final` methods cannot be overridden.** A subclass defining a
   method marked `final` in any ancestor raises `TypeError`.
2. **Classes marked final cannot be subclassed.** `final` applied
   to a class sets a flag; subclassing raises `TypeError`.
3. **Declared interfaces must be satisfied.** A class created with
   `class C(metaclass=StrictMeta, requires=("read", "write"))`
   must define or inherit every named attribute, else `TypeError`.

Also expose `StrictMeta.finals(cls)` → the set of final method
names visible on `cls`, from anywhere in its MRO.

The error messages must name the offending method or class.
`final` must work on both functions and classes.
```python
def final(obj):
    ...


class StrictMeta(type):
    ...
```

## Takeaways

- `class` = prepare namespace → run body → call the metaclass.
- `__set_name__` and `__init_subclass__` cover most needs with no
  metaclass and no conflicts.
- ABCs block incomplete implementations; `register` and
  `__subclasshook__` extend `isinstance` structurally.
- A metaclass's `__call__` is the only clean place to intercept
  instantiation.
- Metaclasses are viral — every subclass inherits yours.
