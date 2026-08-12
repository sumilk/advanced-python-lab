# 13 — Typing, Generics, and Protocols

Annotations are not enforced at runtime — they are a design tool that a
checker verifies and humans read. This lesson covers the modern syntax
(PEP 695 generics, new in 3.12), variance, `Protocol` for structural
typing, overloads, `TypedDict`, narrowing, and the runtime introspection
APIs that libraries actually use.

## Annotations do nothing at runtime

Python stores annotations and moves on. No coercion, no checking, no
cost at call time. Their value is in `mypy`/`pyright`, editors, and
libraries that *choose* to read them (pydantic, dataclasses, FastAPI).

```python
def add(a: int, b: int) -> int:
    return a + b

print("lies happily:", add("x", "y"))
print("stored:", add.__annotations__)

# Variable and class annotations
count: int = 0
names: list[str] = []

class Config:
    host: str = "localhost"
    port: int = 8080
    secret: str                       # declared, never assigned

print("class annotations:", Config.__annotations__)
print("only assigned ones exist:", hasattr(Config, "secret"))
```

## Modern syntax

Since 3.9/3.10 you rarely need the `typing` module for containers:

| old | modern |
|---|---|
| `List[int]`, `Dict[str, int]` | `list[int]`, `dict[str, int]` |
| `Optional[X]`, `Union[A, B]` | `X \| None`, `A \| B` |
| `Tuple[int, ...]` | `tuple[int, ...]` |
| `Callable[[int], str]` | `collections.abc.Callable[[int], str]` |

`from __future__ import annotations` makes *all* annotations lazy
strings, which sidesteps forward references and import cycles.

```python
from collections.abc import Callable, Iterable, Sequence

def process(
    items: Sequence[int],
    transform: Callable[[int], str],
    fallback: str | None = None,
) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for item in items:
        out.setdefault(transform(item), []).append(item)
    if fallback is not None:
        out.setdefault(fallback, [])
    return out

print(process([1, 2, 3, 4], lambda n: "even" if n % 2 == 0 else "odd"))

# A union type is a real object you can inspect and use at runtime.
MaybeInt = int | None
print("union object:", MaybeInt, "| isinstance works:", isinstance(3, int | str))
print("args:", MaybeInt.__args__)
```

## Generics, PEP 695 style (3.12+)

3.12 introduced a compact syntax with no `TypeVar` boilerplate:

```python
def first[T](items: Sequence[T]) -> T: ...
class Box[T]: ...
type Pair[T] = tuple[T, T]
```

The type parameters are scoped to the function/class, so there is no
module-level `T = TypeVar("T")` to accidentally share.

```python
from collections.abc import Sequence

def first[T](items: Sequence[T], default: T | None = None) -> T | None:
    return items[0] if items else default

class Stack[T]:
    def __init__(self) -> None:
        self._items: list[T] = []
    def push(self, item: T) -> None:
        self._items.append(item)
    def pop(self) -> T:
        return self._items.pop()
    def __len__(self) -> int:
        return len(self._items)

type Matrix[T] = list[list[T]]          # a generic type alias

s: Stack[int] = Stack()
s.push(1); s.push(2)
print("stack:", s.pop(), len(s))
print("first:", first([10, 20]), first([], default=-1))
print("type params:", Stack.__type_params__)
print("alias:", Matrix, "->", Matrix.__value__)
```
At runtime the parameters are `TypeVar` objects, reachable via
`__type_params__`. Subscription (`Stack[int]`) produces a
`types.GenericAlias`; it is checked statically and erased
dynamically — `Stack[int]() ` is just a `Stack`.

```python
# The pre-3.12 spelling, still everywhere in existing code.
from typing import Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")
Num = TypeVar("Num", int, float)          # constrained: int OR float
Comparable = TypeVar("Comparable", bound="SupportsLt")   # bounded

class Cache(Generic[K, V]):
    def __init__(self) -> None:
        self._data: dict[K, V] = {}
    def set(self, key: K, value: V) -> None:
        self._data[key] = value
    def get(self, key: K) -> V | None:
        return self._data.get(key)

def double(x: Num) -> Num:
    return x * 2

c: Cache[str, int] = Cache()
c.set("a", 1)
print("cache:", c.get("a"), c.get("zz"))
print("constrained:", double(2), double(1.5))
print("bound vs constrained: bound=any subtype, constrained=exactly one of the listed")
```

**Quiz.** What is the difference between `TypeVar('T', int, str)` and `TypeVar('T', bound=X)`?

- a) Nothing — two spellings of the same thing
- b) Constrained means T is exactly one of the listed types; bound means T is X or any subtype
- c) `bound` only works with protocols
- d) Constrained types are checked at runtime

<details><summary>answer</summary>

**b** — With constraints, a `list[int]` argument makes T = int exactly. With a bound, T can be any subclass of the bound, which is usually what you want.
</details>

## Variance in one paragraph

Given `Dog` is a `Animal`:

- **covariant** — `Sequence[Dog]` is a `Sequence[Animal]`. Safe for
  *read-only* containers.
- **contravariant** — `Callable[[Animal], None]` is a
  `Callable[[Dog], None]`. Safe for *write-only* positions.
- **invariant** — `list[Dog]` is **not** a `list[Animal]`, because you
  could append a `Cat` to it through the wider name.

The practical rule: annotate parameters with the *narrowest protocol
you actually use* — `Iterable[X]` rather than `list[X]` — and you will
stop fighting variance.

```python
from collections.abc import Iterable, Sequence

class Animal:
    def speak(self): return "..."
class Dog(Animal):
    def speak(self): return "woof"

# Iterable is covariant: a list[Dog] is an Iterable[Animal].
def chorus(animals: Iterable[Animal]) -> list[str]:
    return [a.speak() for a in animals]

dogs: list[Dog] = [Dog(), Dog()]
print(chorus(dogs), "  <- fine: we only read")

# Why list[Animal] would be unsound:
def add_a_cat(animals: list) -> None:
    animals.append(Animal())          # a checker would reject list[Animal]

add_a_cat(dogs)
print("now the list[Dog] contains:", [type(a).__name__ for a in dogs])
print("...which is exactly why list is invariant")
```

## `Protocol`: structural typing

A `Protocol` says *"anything with these members"* — no inheritance
required. This is static duck typing, and it is the right tool for
describing what your function needs from its argument.

Add `@runtime_checkable` to allow `isinstance()` — but note it only
checks *presence* of the members, not their signatures.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Closeable(Protocol):
    def close(self) -> None: ...

class Renderable(Protocol):
    width: int
    def render(self) -> str: ...

def shutdown(resource: Closeable) -> str:
    resource.close()
    return f"closed {type(resource).__name__}"

class Socket:
    def close(self): pass
class Widget:
    width = 10
    def render(self): return "<widget>"

print(shutdown(Socket()))
print("isinstance:", isinstance(Socket(), Closeable), isinstance(Widget(), Closeable))

# Protocols can have default implementations and be inherited explicitly.
class Greeter(Protocol):
    def name(self) -> str: ...
    def greet(self) -> str:
        return f"hello, {self.name()}"

class Person(Greeter):
    def name(self): return "ada"

print(Person().greet())
```
The stdlib is full of these: `SupportsInt`, `SupportsFloat`,
`SupportsIndex`, `Iterable`, `Hashable`. When you write
`def f(x: SupportsFloat)`, you are documenting *exactly* what you
require — `float(x)` — instead of over-constraining to `float`.

## `overload`, `TypedDict`, `Literal`, `Final`, `NewType`

- `@overload` declares several signatures for one implementation; the
  overload stubs are erased at runtime.
- `TypedDict` types the *shape* of a dict — still a plain dict at
  runtime.
- `Literal["a", "b"]` restricts to specific values.
- `Final` says "do not reassign"; `NewType` makes a distinct type from
  an existing one with zero runtime cost.

```python
from typing import Final, Literal, NewType, NotRequired, TypedDict, overload

UserId = NewType("UserId", int)
MAX_RETRIES: Final = 3

class UserRecord(TypedDict):
    id: int
    name: str
    email: NotRequired[str]           # optional key

@overload
def lookup(key: int) -> UserRecord: ...
@overload
def lookup(key: str) -> list[UserRecord]: ...
def lookup(key):
    if isinstance(key, int):
        return {"id": key, "name": f"user{key}"}
    return [{"id": 1, "name": key}]

print("by id  :", lookup(7))
print("by name:", lookup("ada"))

uid = UserId(42)
print("NewType is just an int at runtime:", uid, type(uid).__name__)
print("TypedDict is just a dict:", type(lookup(1)).__name__)
print("required keys:", UserRecord.__required_keys__,
      "| optional:", UserRecord.__optional_keys__)

Mode = Literal["r", "w", "a"]
def open_file(path: str, mode: Mode = "r") -> str:
    return f"{path} in {mode}"
print(open_file("x.txt", "w"))
```


## Narrowing, `assert_never`, and `Self`

Checkers narrow a union as you test it: `isinstance`, `is None`,
truthiness, `in`, and `match`. `assert_never(x)` in the final `else`
makes the checker prove your handling is exhaustive — add a new
variant and the build fails.

```python
from typing import Literal, Self, assert_never

Shape = Literal["circle", "square"]

def area(shape: Shape, size: float) -> float:
    if shape == "circle":
        return 3.14159 * size ** 2
    elif shape == "square":
        return size ** 2
    else:
        assert_never(shape)      # a checker errors here if a case is missed

print(area("circle", 1), area("square", 2))

# Self: the correct return annotation for fluent APIs and factories.
class Query:
    def __init__(self): self.parts: list[str] = []
    def where(self, clause: str) -> Self:
        self.parts.append(clause)
        return self
    @classmethod
    def build(cls) -> Self:
        return cls()

class AuditedQuery(Query):
    pass

q = AuditedQuery.build().where("a = 1").where("b = 2")
print(type(q).__name__, q.parts)
```
Annotating `where` as `-> Query` would lose the subclass: a checker
would say `AuditedQuery.build().where(...)` is a plain `Query`.
`Self` preserves it.

**Quiz.** What does `@runtime_checkable` on a Protocol let `isinstance()` verify?

- a) That the object has the right method signatures
- b) Only that the named attributes/methods exist
- c) That the class explicitly inherits from the Protocol
- d) Nothing — it is a no-op at runtime

<details><summary>answer</summary>

**b** — It is a presence check only. A `close` attribute that is an int will satisfy `isinstance(x, Closeable)`.
</details>

## Exercise — A runtime validator driven by annotations `[brutal]`

Write `coerce(cls, data)` — build an instance of an annotated class
from a dict, validating and converting using **only** the
annotations.

Supported annotation forms:
- plain types: `int`, `str`, `float`, `bool`
- `X | None` (optional): `None` allowed, missing key → `None`
- `list[X]`: every element coerced to `X`
- `dict[str, X]`: every value coerced to `X`
- nested annotated classes: coerced recursively from a sub-dict

Rules:
- a class-level default makes the key optional; no default makes it
  required, and a missing required key raises `KeyError`
- a value that cannot be converted raises `TypeError` mentioning
  the field name and the expected type
- `int` fields accept `"42"` (a numeric string) and reject `"abc"`
  and `12.7`
- `bool` fields accept only real bools — never `0`/`1`/`"true"`
- unknown keys in `data` are ignored
- the result is an instance of `cls` with attributes set

You will need `typing.get_type_hints`, `get_origin`, `get_args`.
```python
from typing import get_args, get_origin, get_type_hints

MISSING = object()


def coerce(cls, data: dict):
    ...
```

## Takeaways

- Annotations are inert at runtime; their value is tooling and intent.
- Prefer `list[int]` and `X | None` over the legacy `typing` spellings.
- 3.12's `def f[T](...)` and `class C[T]` remove TypeVar boilerplate.
- Annotate parameters with the narrowest protocol you actually use.
- `Protocol` gives you duck typing a checker can verify;
  `get_type_hints`/`get_origin`/`get_args` give you it at runtime.
