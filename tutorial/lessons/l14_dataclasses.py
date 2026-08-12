"""Lesson 14 — Dataclasses, enums, and structural pattern matching."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=14,
    slug="dataclasses",
    title="Dataclasses, Enums, and Pattern Matching",
    summary="""
    Three features that together replace an enormous amount of boilerplate:
    `dataclass` for data-holding classes, `Enum` for closed sets of values,
    and `match` for destructuring. Pattern matching in particular is not a
    switch statement — it is destructuring with binding, and it changes how
    you write branching code.
    """,
    tags=("dataclasses", "enums", "pattern-matching", "namedtuple"),
    blocks=[
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `field(default_factory=list)` is mandatory for mutable defaults —
            `tags: list = []` raises `ValueError` at class creation, because
            the dataclass machinery explicitly catches the classic shared
            mutable default bug for you.
            """,
        ),
        Demo(
            code="""
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
            """,
        ),
        Predict(
            code="""
            from dataclasses import dataclass

            @dataclass
            class Mutable:
                x: int

            @dataclass(frozen=True)
            class Frozen:
                x: int

            print(hash(Frozen(1)) == hash(Frozen(1)))
            try:
                hash(Mutable(1))
            except TypeError as exc:
                print("Mutable:", exc)
            try:
                Frozen(1).x = 2
            except Exception as exc:
                print(type(exc).__name__)
            """,
            answer="""
            True
            Mutable: unhashable type: 'Mutable'
            FrozenInstanceError
            """,
            explain="""
            Defining `__eq__` (which `@dataclass` does) sets `__hash__ = None`.
            `frozen=True` restores it because the fields cannot change.
            `FrozenInstanceError` is a subclass of `AttributeError`.
            """,
        ),
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
        ),
        Text("""
        ## Enums

        `Enum` members are singletons with a `name` and a `value`, safe to
        compare with `is`. Variants worth knowing:

        - `IntEnum` / `StrEnum` (3.11) — also a real `int`/`str`, for
          interoperating with APIs that demand primitives
        - `Flag` / `IntFlag` — bitwise combinable
        - `auto()` — assign values automatically
        - `@unique` — reject duplicate values (otherwise they become aliases)
        """),
        Demo(
            code="""
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
            """,
        ),
        Question(
            prompt="Why compare enum members with `is` rather than `==`?",
            choices=[
                "`==` is not defined for enums",
                "Members are singletons, so `is` is exact, faster, and immune to a subclass overriding `__eq__`",
                "`is` converts the member to its value first",
                "There is no difference at all",
            ],
            answer=1,
            explain="Each member is created once. `is` also protects you from "
                    "`IntEnum` surprises where `Status.ACTIVE == 1` is True.",
        ),
        Text("""
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
        | `a \\| b` | alternatives |
        | `pat if cond` | a guard |
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Note `int(n)` — a class pattern with one positional sub-pattern.
            It means "an int, bound to `n`", not a call. And mapping patterns
            match a **subset**: `{"type": kind}` happily matches a dict with
            ten other keys.
            """,
        ),
        Demo(
            code="""
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
            """,
        ),
        Predict(
            code="""
            def classify_seq(value):
                match value:
                    case (1, 2):
                        return "tuple 1,2"
                    case [1, 2]:
                        return "list 1,2"
                    case "12":
                        return "the string"
                    case str():
                        return "some string"
                    case _:
                        return "other"

            print(classify_seq((1, 2)))
            print(classify_seq([1, 2]))
            print(classify_seq("12"))
            """,
            answer="""
            tuple 1,2
            tuple 1,2
            the string
            """,
            explain="""
            Sequence patterns do **not** distinguish list from tuple — both
            match `(1, 2)` and `[1, 2]` identically. Strings and bytes are
            deliberately excluded from sequence patterns, so `"12"` falls
            through to the literal.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            **A bare name in a pattern is always a capture** — even an
            ALL-CAPS one that looks like a constant. Only dotted names
            (`Colours.RED`, `Status.ACTIVE`) are compared by value.

            The compiler catches the case where an irrefutable pattern is
            followed by other cases (`SyntaxError` at compile time), but it
            cannot help when the capture is *last* — there the bug is silent
            and the function matches everything.
            """,
        ),
        Question(
            prompt="In `case RED:` where `RED = 'red'` is a module-level constant, what happens?",
            choices=[
                "It compares the subject to `'red'`",
                "It matches anything and rebinds the name `RED` to the subject",
                "It raises a SyntaxError",
                "It matches only if the subject is a string",
            ],
            answer=1,
            explain="Bare names are capture patterns. Use a dotted name "
                    "(`Colour.RED`) or a literal to compare by value.",
        ),
        Exercise(
            slug="event-router",
            title="A pattern-matching event router",
            difficulty="tricky",
            brief="""
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
            """,
            starter="""
            def route(event):
                ...
            """,
            checks=[
                Check("click, list and tuple positions", lambda ns: _er_click(ns["route"])),
                Check("right-click wins over plain click", lambda ns: _er_button(ns["route"])),
                Check("key length distinguishes typed/pressed", lambda ns: _er_key(ns["route"])),
                Check("resize validates dimensions", lambda ns: _er_resize(ns["route"])),
                Check("batches recurse, empty batch handled", lambda ns: _er_batch(ns["route"])),
                Check("unknown and non-events", lambda ns: _er_fallback(ns["route"])),
                Check("extra keys never block a match", lambda ns: _er_extra(ns["route"])),
                Check("implemented with match", lambda ns: _er_uses_match(ns["route"])),
            ],
            hints=(
                "Order matters: put the more specific `{'button': 'right'}` case "
                "*before* the general click case.",
                "`case {'type': 'key', 'key': str(k)} if len(k) == 1:` combines a "
                "class pattern with a guard.",
                "For the resize validation, a guard reading "
                "`if isinstance(w, int) and w > 0 and ...` is clearest; put the "
                "invalid case immediately after.",
                "`case {'type': 'batch', 'events': [*items]}` binds the list, then "
                "recurse with a comprehension and `' | '.join(...)`.",
                "Remember `bool` is an `int`: `True` would pass a naive positive-int "
                "check.",
            ),
            solution="""
            def route(event):
                match event:
                    case {"type": "click", "pos": [x, y], "button": "right"}:
                        return f"context menu at {x},{y}"
                    case {"type": "click", "pos": [x, y]}:
                        return f"click at {x},{y}"
                    case {"type": "key", "key": str(k)} if len(k) == 1:
                        return f"typed {k}"
                    case {"type": "key", "key": str(k)}:
                        return f"pressed {k}"
                    case {"type": "resize", "size": {"w": w, "h": h}} if (
                        isinstance(w, int) and not isinstance(w, bool) and w > 0
                        and isinstance(h, int) and not isinstance(h, bool) and h > 0
                    ):
                        return f"resized to {w}x{h}"
                    case {"type": "resize"}:
                        return "invalid resize"
                    case {"type": "batch", "events": []}:
                        return "empty batch"
                    case {"type": "batch", "events": [*items]}:
                        return "batch: " + " | ".join(route(item) for item in items)
                    case {"type": kind}:
                        return f"unknown event: {kind}"
                    case _:
                        return "not an event"
            """,
        ),
        Exercise(
            slug="record-builder",
            title="A frozen record with validation and evolution",
            difficulty="brutal",
            brief="""
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
            """,
            starter="""
            class Record:
                def __init_subclass__(cls, **kwargs):
                    ...
            """,
            checks=[
                Check("positional and keyword construction", lambda ns: _rb_construct(ns["Record"])),
                Check("defaults, and required fields enforced", lambda ns: _rb_defaults(ns["Record"])),
                Check("bad field ordering rejected at class creation",
                      lambda ns: _rb_ordering(ns["Record"])),
                Check("immutability", lambda ns: _rb_frozen(ns["Record"])),
                Check("repr, equality, hashing", lambda ns: _rb_repr_eq(ns["Record"])),
                Check("evolve returns a new validated instance", lambda ns: _rb_evolve(ns["Record"])),
                Check("validate() hook runs on build and evolve", lambda ns: _rb_validate(ns["Record"])),
                Check("fields are inherited by subclasses", lambda ns: _rb_inherit(ns["Record"])),
            ],
            hints=(
                "In `__init_subclass__`, merge the parents' `_fields` with "
                "`cls.__dict__.get('__annotations__', {})` to support inheritance.",
                "Store the resolved field order on the class as a dict "
                "`{name: default_or_MISSING}`.",
                "Immutability: define `__setattr__` that raises, and write the "
                "initial values with `object.__setattr__`.",
                "`__hash__` must be defined explicitly because you define `__eq__`; "
                "`hash((type(self), *values))` works.",
                "`evolve` is just `type(self)(**{**self.asdict(), **changes})` after "
                "checking the change names.",
            ),
            solution="""
            MISSING = object()

            class Record:
                _fields: dict = {}

                def __init_subclass__(cls, **kwargs):
                    super().__init_subclass__(**kwargs)
                    fields = {}
                    for base in reversed(cls.__mro__[1:]):
                        fields.update(getattr(base, "_fields", {}))
                    for name in cls.__dict__.get("__annotations__", {}):
                        fields[name] = cls.__dict__.get(name, MISSING)

                    seen_default = None
                    for name, default in fields.items():
                        if default is not MISSING:
                            seen_default = name
                        elif seen_default is not None:
                            raise TypeError(
                                f"non-default field {name!r} follows "
                                f"default field {seen_default!r}"
                            )
                    cls._fields = fields

                def __init__(self, *args, **kwargs):
                    names = list(self._fields)
                    if len(args) > len(names):
                        raise TypeError(f"expected at most {len(names)} positional arguments")
                    values = dict(zip(names, args))
                    for key, value in kwargs.items():
                        if key not in self._fields:
                            raise TypeError(f"unexpected field {key!r}")
                        if key in values:
                            raise TypeError(f"{key!r} given twice")
                        values[key] = value

                    for name, default in self._fields.items():
                        if name not in values:
                            if default is MISSING:
                                raise TypeError(f"missing required field {name!r}")
                            values[name] = default
                        object.__setattr__(self, name, values[name])
                    self.validate()

                def validate(self):
                    pass

                def __setattr__(self, name, value):
                    raise AttributeError(f"{type(self).__name__} is immutable")

                def __delattr__(self, name):
                    raise AttributeError(f"{type(self).__name__} is immutable")

                def asdict(self):
                    return {name: getattr(self, name) for name in self._fields}

                def evolve(self, **changes):
                    unknown = set(changes) - set(self._fields)
                    if unknown:
                        raise TypeError(f"unknown field(s): {sorted(unknown)}")
                    return type(self)(**{**self.asdict(), **changes})

                def __repr__(self):
                    inner = ", ".join(f"{k}={v!r}" for k, v in self.asdict().items())
                    return f"{type(self).__name__}({inner})"

                def __eq__(self, other):
                    if type(other) is not type(self):
                        return NotImplemented
                    return self.asdict() == other.asdict()

                def __hash__(self):
                    return hash((type(self), *self.asdict().values()))
            """,
        ),
        Text("""
        ## Takeaways

        - `@dataclass(frozen=True, slots=True)` is the default choice for a
          value object; use `field(default_factory=...)` for mutables.
        - `NamedTuple` when tuple behaviour matters; `TypedDict` when it must
          stay a dict.
        - Enum members are singletons — compare with `is`, and give them
          methods.
        - `match` destructures and binds; mapping patterns match subsets.
        - A bare name in a pattern **captures**; only dotted names compare.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _er_click(route) -> None:
    assert route({"type": "click", "pos": [3, 4]}) == "click at 3,4"
    assert route({"type": "click", "pos": (3, 4)}) == "click at 3,4", (
        "a tuple position should match the same sequence pattern"
    )


def _er_button(route) -> None:
    got = route({"type": "click", "pos": [1, 2], "button": "right"})
    assert got == "context menu at 1,2", f"got {got!r} — order your cases specific-first"
    assert route({"type": "click", "pos": [1, 2], "button": "left"}) == "click at 1,2"


def _er_key(route) -> None:
    assert route({"type": "key", "key": "a"}) == "typed a"
    assert route({"type": "key", "key": "Escape"}) == "pressed Escape"


def _er_resize(route) -> None:
    assert route({"type": "resize", "size": {"w": 80, "h": 24}}) == "resized to 80x24"
    for bad in ({"w": 0, "h": 24}, {"w": -1, "h": 5}, {"w": "80", "h": 24},
                {"w": True, "h": 5}):
        got = route({"type": "resize", "size": bad})
        assert got == "invalid resize", f"size={bad} should be invalid, got {got!r}"


def _er_batch(route) -> None:
    got = route({"type": "batch", "events": [
        {"type": "click", "pos": [0, 0]},
        {"type": "key", "key": "x"},
    ]})
    assert got == "batch: click at 0,0 | typed x", got
    assert route({"type": "batch", "events": []}) == "empty batch"
    nested = route({"type": "batch", "events": [
        {"type": "batch", "events": [{"type": "key", "key": "z"}]},
    ]})
    assert nested == "batch: batch: typed z", nested


def _er_fallback(route) -> None:
    assert route({"type": "mystery"}) == "unknown event: mystery"
    for value in (42, "click", None, [1, 2], {"no_type": 1}):
        assert route(value) == "not an event", f"{value!r} -> {route(value)!r}"


def _er_extra(route) -> None:
    got = route({"type": "click", "pos": [1, 1], "timestamp": 12345, "meta": {}})
    assert got == "click at 1,1", f"extra keys should not block the match, got {got!r}"


def _er_uses_match(route) -> None:
    """Check the *bytecode*, which works even when no source file exists."""
    import dis

    opnames = {ins.opname for ins in dis.get_instructions(route)}
    match_ops = {op for op in opnames if op.startswith("MATCH_")}
    assert match_ops, (
        "this exercise is about `match` — implement it with a match statement "
        "(no MATCH_* opcodes found in the compiled function)"
    )


def _rb_models(Record):
    class User(Record):
        name: str
        age: int = 0

    return User


def _rb_construct(Record) -> None:
    User = _rb_models(Record)
    a = User(name="ada")
    b = User("ada")
    c = User("ada", 21)
    assert (a.name, a.age) == ("ada", 0)
    assert (b.name, b.age) == ("ada", 0)
    assert (c.name, c.age) == ("ada", 21)
    try:
        User("ada", name="grace")
    except TypeError:
        pass
    else:
        raise AssertionError("giving a field twice must raise TypeError")


def _rb_defaults(Record) -> None:
    User = _rb_models(Record)
    try:
        User()
    except TypeError:
        pass
    else:
        raise AssertionError("a missing required field must raise TypeError")
    try:
        User(name="a", nope=1)
    except TypeError:
        return
    raise AssertionError("an unknown field must raise TypeError")


def _rb_ordering(Record) -> None:
    try:
        class Bad(Record):
            a: int = 1
            b: int
    except TypeError:
        return
    raise AssertionError(
        "a non-default field after a defaulted one must raise TypeError at class creation"
    )


def _rb_frozen(Record) -> None:
    User = _rb_models(Record)
    u = User("ada")
    try:
        u.name = "grace"
    except AttributeError:
        return
    raise AssertionError("instances must be immutable")


def _rb_repr_eq(Record) -> None:
    User = _rb_models(Record)
    u = User("ada", 36)
    assert repr(u) == "User(name='ada', age=36)", repr(u)
    assert u == User("ada", 36)
    assert u != User("ada", 21)
    assert len({User("ada", 36), User("ada", 36)}) == 1, "instances must be hashable"

    class Other(Record):
        name: str
        age: int = 0

    assert u != Other("ada", 36), "different types must not compare equal"


def _rb_evolve(Record) -> None:
    User = _rb_models(Record)
    u = User("ada", 36)
    v = u.evolve(age=37)
    assert v == User("ada", 37) and u.age == 36, "evolve must not mutate the original"
    assert v is not u
    try:
        u.evolve(nope=1)
    except TypeError:
        return
    raise AssertionError("evolve must reject unknown fields")


def _rb_validate(Record) -> None:
    calls = []

    class Positive(Record):
        n: int

        def validate(self):
            calls.append(self.n)
            if self.n <= 0:
                raise ValueError("n must be positive")

    Positive(5)
    assert calls == [5], f"validate should run on construction, calls={calls}"
    try:
        Positive(-1)
    except ValueError:
        pass
    else:
        raise AssertionError("validate() raising must propagate from the constructor")

    p = Positive(5)
    try:
        p.evolve(n=-2)
    except ValueError:
        return
    raise AssertionError("evolve must re-run validate()")


def _rb_inherit(Record) -> None:
    class Base(Record):
        a: int

    class Child(Base):
        b: str = "x"

    c = Child(1, "y")
    assert (c.a, c.b) == (1, "y"), c
    assert list(Child._fields) == ["a", "b"], list(Child._fields)
    assert repr(c) == "Child(a=1, b='y')", repr(c)
