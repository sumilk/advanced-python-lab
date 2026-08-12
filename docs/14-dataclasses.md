# 14 — Dataclasses, Enums, and Pattern Matching

Three features that together replace an enormous amount of boilerplate:
`dataclass` for data-holding classes, `Enum` for closed sets of values,
and `match` for destructuring. Pattern matching in particular is not a
switch statement — it is destructuring with binding, and it changes how
you write branching code.

## `@dataclass` generates the boilerplate

From the annotated fields it writes `__init__`, `__repr__`, `__eq__`,
and optionally ordering, hashing, and immutability. Key parameters:

| parameter | effect |
|---|---|
| `frozen=True` | immutable; makes instances hashable |
| `order=True` | generates `<`, `<=`, `>`, `>=` from field order |
| `slots=True` | adds `__slots__` (3.10+) |
| `kw_only=True` | all fields become keyword-only (3.10+) |
| `eq=False` | keep identity-based equality and hashing |

```python
from dataclasses import dataclass, field, asdict, astuple, replace, fields

@dataclass(order=True, slots=True)
class Employee:
    surname: str
    first: str
    salary: int = 0
    tags: list[str] = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

a = Employee("Lovelace", "Ada", 100)
b = Employee("Hopper", "Grace", 120)
print(a)
print("equality:", a == Employee("Lovelace", "Ada", 100))
print("ordering by field order:", sorted([a, b])[0].surname)
print("asdict:", asdict(a))
print("replace:", replace(a, salary=150))
print("field metadata:", [(f.name, f.compare) for f in fields(a)][-2:])
```
`field(default_factory=list)` is mandatory for mutable defaults —
`tags: list = []` raises `ValueError` at class creation, because
the dataclass machinery explicitly catches the classic shared
mutable default bug for you.

```python
from dataclasses import dataclass, field

# __post_init__ for derived fields and validation.
@dataclass
class Rectangle:
    width: float
    height: float
    area: float = field(init=False)          # computed, not a parameter

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("dimensions must be positive")
        self.area = self.width * self.height

r = Rectangle(3, 4)
print(r)
try:
    Rectangle(-1, 2)
except ValueError as exc:
    print("validated:", exc)

# InitVar: a constructor-only parameter that is not a field.
from dataclasses import InitVar

@dataclass
class Connection:
    host: str
    port: int = 5432
    password: InitVar[str | None] = None
    dsn: str = field(init=False)

    def __post_init__(self, password):
        auth = f":{password}@" if password else ""
        self.dsn = f"postgres://{auth}{self.host}:{self.port}"

print(Connection("db", password="s3cret"))
```


## Choosing between the record types

| | mutable | hashable | memory | ordered fields | typed |
|---|---|---|---|---|---|
| `dict` | yes | no | high | insertion | no |
| `tuple` | no | yes | lowest | positional | no |
| `NamedTuple` | no | yes | low | positional | yes |
| `dataclass` | yes | opt-in | medium | declaration | yes |
| `dataclass(slots=True)` | yes | opt-in | low | declaration | yes |
| `TypedDict` | yes | no | high | – | yes (static only) |

Rule of thumb: `NamedTuple` when it must behave like a tuple
(unpacking, indexing, legacy APIs); `dataclass(frozen=True, slots=True)`
for most value objects; a plain `dataclass` when it holds state.

```python
import sys
from dataclasses import dataclass
from typing import NamedTuple

class PointNT(NamedTuple):
    x: int
    y: int
    def distance_sq(self): return self.x ** 2 + self.y ** 2

@dataclass(frozen=True, slots=True)
class PointDC:
    x: int
    y: int

nt, dc = PointNT(3, 4), PointDC(3, 4)
print("namedtuple unpacks:", (lambda a, b: a + b)(*nt))
print("and indexes:", nt[0], "| methods work:", nt.distance_sq())
print("_replace:", nt._replace(x=10), "| _fields:", nt._fields)
print()
print("sizes -- namedtuple:", sys.getsizeof(nt),
      "| slotted dataclass:", sys.getsizeof(dc),
      "| dict:", sys.getsizeof({"x": 3, "y": 4}))
print("dataclass does NOT unpack -- that is usually a feature")
```

## Enums

`Enum` members are singletons with a `name` and a `value`, safe to
compare with `is`. Variants worth knowing:

- `IntEnum` / `StrEnum` (3.11) — also a real `int`/`str`, for
  interoperating with APIs that demand primitives
- `Flag` / `IntFlag` — bitwise combinable
- `auto()` — assign values automatically
- `@unique` — reject duplicate values (otherwise they become aliases)

```python
from enum import Enum, Flag, IntEnum, StrEnum, auto, unique

@unique
class Status(Enum):
    PENDING = auto()
    ACTIVE = auto()
    CLOSED = auto()

    @property
    def is_terminal(self):                # enums can have behaviour
        return self is Status.CLOSED

    @classmethod
    def from_label(cls, text):
        return cls[text.upper()]

print(Status.ACTIVE, "|", Status.ACTIVE.name, Status.ACTIVE.value)
print("members are singletons:", Status.ACTIVE is Status(2),
      Status.ACTIVE is Status["ACTIVE"])
print("lookup by name :", Status["CLOSED"], "| by value:", Status(1))
print("from_label     :", Status.from_label("pending"))
print("behaviour      :", Status.CLOSED.is_terminal)
print("iteration      :", [s.name for s in Status])

class Permission(Flag):
    READ = auto()
    WRITE = auto()
    EXECUTE = auto()
    ALL = READ | WRITE | EXECUTE

perms = Permission.READ | Permission.WRITE
print()
print("flags:", perms, "| has WRITE:", Permission.WRITE in perms)
print("combined:", list(perms), "| all:", Permission.ALL)

class Colour(StrEnum):
    RED = "red"
print("StrEnum is a str:", Colour.RED.upper(), Colour.RED == "red")
```

**Quiz.** Why compare enum members with `is` rather than `==`?

- a) `==` is not defined for enums
- b) Members are singletons, so `is` is exact, faster, and immune to a subclass overriding `__eq__`
- c) `is` converts the member to its value first
- d) There is no difference at all

<details><summary>answer</summary>

**b** — Each member is created once. `is` also protects you from `IntEnum` surprises where `Status.ACTIVE == 1` is True.
</details>

## Structural pattern matching

`match` compares a *subject* against **patterns**, binding names as it
goes. The pattern kinds:

| pattern | matches |
|---|---|
| `42`, `"x"`, `None` | literal equality (`is` for None/True/False) |
| `name` | anything, and **binds** it |
| `_` | anything, binds nothing |
| `[a, b, *rest]` | sequences (not `str`/`bytes`) |
| `{"k": v, **rest}` | mappings, *partially* — extra keys are fine |
| `Point(x=0, y=y)` | class patterns, by attribute |
| `Point(0, y)` | positional, via `__match_args__` |
| `a \| b` | alternatives |
| `pat if cond` | a guard |

```python
def describe(value):
    match value:
        case 0:
            return "zero"
        case int() | float() as n if n < 0:
            return f"negative number {n}"
        case int(n):
            return f"positive int {n}"
        case [] | {}:
            return "empty container"
        case [single]:
            return f"one-element list holding {single!r}"
        case [first, *rest] if len(rest) > 2:
            return f"long list starting {first!r} (+{len(rest)})"
        case [first, *rest]:
            return f"list: {first!r} then {rest}"
        case {"type": "user", "name": str(name), **extra}:
            return f"user {name} with extras {sorted(extra)}"
        case {"type": kind}:
            return f"record of type {kind!r}"
        case str() as s:
            return f"string of length {len(s)}"
        case _:
            return f"something else: {type(value).__name__}"

samples = [
    0, -3.5, 7, [], [1], [1, 2], [1, 2, 3, 4, 5],
    {"type": "user", "name": "ada", "age": 36},
    {"type": "order"}, "hello", object(),
]
for s in samples:
    print(f"  {str(s)[:28]:30} -> {describe(s)}")
```
Note `int(n)` — a class pattern with one positional sub-pattern.
It means "an int, bound to `n`", not a call. And mapping patterns
match a **subset**: `{"type": kind}` happily matches a dict with
ten other keys.

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: int
    y: int

@dataclass
class Circle:
    centre: Point
    radius: float

def classify(shape):
    match shape:
        case Point(x=0, y=0):
            return "origin"
        case Point(x=0, y=y):
            return f"on the y-axis at {y}"
        case Point(x, y) if x == y:            # positional: __match_args__
            return f"on the diagonal at {x}"
        case Point():
            return "some point"
        case Circle(centre=Point(0, 0), radius=r):
            return f"circle centred on origin, r={r}"
        case Circle(centre=c):
            return f"circle at {c.x},{c.y}"
        case _:
            return "not a shape"

print("__match_args__:", Point.__match_args__)
for shape in (Point(0, 0), Point(0, 5), Point(3, 3), Point(1, 2),
              Circle(Point(0, 0), 2.0), Circle(Point(1, 1), 1.0), 42):
    print(f"  {str(shape)[:34]:36} -> {classify(shape)}")
```


```python
# The two most common pattern-matching bugs.
source = '''
def bug(colour):
    match colour:
        case RED:          # NOT a comparison -- this CAPTURES
            return "red"
        case _:
            return "other"
'''
import textwrap
try:
    compile(textwrap.dedent(source), "<bug>", "exec")
except SyntaxError as exc:
    print("capture bug   :", exc.msg)

# With no case after it, the same pattern compiles -- and swallows
# every input, which is the bug the compiler was warning about.
RED = "red"

def still_wrong(colour):
    match colour:
        case RED:
            return f"matched, and RED is now {RED!r}"

print("silent version:", still_wrong("blue"))

class Colours:
    RED = "red"

def fixed(colour):
    match colour:
        case Colours.RED:          # a dotted name IS a value pattern
            return "really red"
        case _:
            return "not red"

print("dotted lookup :", fixed("blue"), "|", fixed("red"))

# And: a bare class pattern with a positional arg needs __match_args__
class NoArgs:
    def __init__(self, v): self.v = v
try:
    match NoArgs(1):
        case NoArgs(v):
            pass
except TypeError as exc:
    print("positional    :", exc)
```
**A bare name in a pattern is always a capture** — even an
ALL-CAPS one that looks like a constant. Only dotted names
(`Colours.RED`, `Status.ACTIVE`) are compared by value.

The compiler catches the case where an irrefutable pattern is
followed by other cases (`SyntaxError` at compile time), but it
cannot help when the capture is *last* — there the bug is silent
and the function matches everything.

**Quiz.** In `case RED:` where `RED = 'red'` is a module-level constant, what happens?

- a) It compares the subject to `'red'`
- b) It matches anything and rebinds the name `RED` to the subject
- c) It raises a SyntaxError
- d) It matches only if the subject is a string

<details><summary>answer</summary>

**b** — Bare names are capture patterns. Use a dotted name (`Colour.RED`) or a literal to compare by value.
</details>

## Exercise — A pattern-matching event router `[tricky]`

Write `route(event)` dispatching on the *shape* of an event dict
using `match`. Return a string for each case:

1. `{"type": "click", "pos": [x, y]}` → `"click at x,y"` (also
   accept a tuple for `pos`)
2. `{"type": "click", "pos": [x, y], "button": "right"}` →
   `"context menu at x,y"` — this must win over case 1
3. `{"type": "key", "key": k}` where `k` is a single character →
   `"typed k"`; longer keys → `"pressed k"`
4. `{"type": "resize", "size": {"w": w, "h": h}}` → `"resized to
   wxh"`; if either dimension is not a positive int →
   `"invalid resize"`
5. `{"type": "batch", "events": [...]}` → recursively route each
   and return `"batch: a | b | c"` (empty batch → `"empty batch"`)
6. any other dict with a `"type"` → `"unknown event: <type>"`
7. anything else → `"not an event"`

Extra keys must never prevent a match. Use `match`, not a chain of
`if`s — one of the checks inspects the source for it.
```python
def route(event):
    ...
```

## Exercise — A frozen record with validation and evolution `[brutal]`

Build `Record` — a base class giving annotated subclasses the
behaviour of a validated, immutable value object. No `dataclass`:
implement it yourself with `__init_subclass__`.

For `class User(Record): name: str; age: int = 0`:

- `User(name="ada")` and `User("ada", 21)` both work (positional
  order follows declaration order)
- fields with defaults must come after fields without, else
  `TypeError` at **class definition** time
- instances are immutable: assignment raises `AttributeError`
- `repr` → `User(name='ada', age=0)`
- `==` compares type and all fields; instances are hashable
- `.evolve(**changes)` returns a new instance with those fields
  replaced, validating unknown names with `TypeError`
- `.asdict()` → a plain dict in declaration order
- a subclass may define `validate(self)`, called after
  construction *and* after `evolve`; raising there must prevent the
  object from being used
- fields are inherited: a subclass of `User` adds to its fields
```python
class Record:
    def __init_subclass__(cls, **kwargs):
        ...
```

## Takeaways

- `@dataclass(frozen=True, slots=True)` is the default choice for a
  value object; use `field(default_factory=...)` for mutables.
- `NamedTuple` when tuple behaviour matters; `TypedDict` when it must
  stay a dict.
- Enum members are singletons — compare with `is`, and give them
  methods.
- `match` destructures and binds; mapping patterns match subsets.
- A bare name in a pattern **captures**; only dotted names compare.
