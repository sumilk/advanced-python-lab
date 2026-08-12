"""Lesson 09 — Descriptors and properties."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=9,
    slug="descriptors",
    title="Descriptors and Properties",
    summary="""
    Descriptors are the mechanism behind `property`, `classmethod`,
    `staticmethod`, `functools.cached_property`, `__slots__`, and every ORM
    field you have ever used. They are also the cleanest way to factor out
    repeated attribute logic. Once you see that a plain method is *also* a
    descriptor, the whole object system clicks into place.
    """,
    tags=("descriptors", "properties", "attributes", "protocols"),
    blocks=[
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `__set_name__` (3.6+) is what lets a descriptor learn the attribute
            name it was assigned to — before it existed, every ORM made you
            write `name = Field("name")`.

            When accessed on the class rather than an instance, `obj` is
            `None`; returning `self` is the convention so that
            `Thing.field` gives you the descriptor for introspection.
            """,
        ),
        Predict(
            code="""
            class NonData:
                def __get__(self, obj, objtype=None): return "from descriptor"

            class Data(NonData):
                def __set__(self, obj, value): obj.__dict__["d"] = value

            class C:
                n = NonData()
                d = Data()

            c = C()
            c.__dict__["n"] = "from instance dict"
            c.__dict__["d"] = "from instance dict"
            print(c.n)
            print(c.d)
            """,
            answer="""
            from instance dict
            from descriptor
            """,
            explain="""
            The non-data descriptor loses to the instance dict; the data
            descriptor wins. This single precedence rule is why `property`
            can enforce validation that an instance attribute cannot bypass,
            and why methods (non-data) can be shadowed per instance.
            """,
        ),
        Text("""
        ## Functions are descriptors — that is how `self` works

        A plain function stored on a class is a non-data descriptor. Accessing
        it through an instance calls `function.__get__(instance, cls)`, which
        returns a **bound method** — a small object holding the function and
        the instance. Calling it inserts the instance as the first argument.
        """),
        Demo(
            code="""
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

            # classmethod and staticmethod are descriptors too -- but
            # different ones. A plain method is stored as a bare function:
            print("in the class dict:", type(C.__dict__["method"]).__name__)

            class D:
                @staticmethod
                def s(): return "static"
                @classmethod
                def c(cls): return f"class {cls.__name__}"
            print(type(D.__dict__["s"]).__name__, "->", D.s())
            print(type(D.__dict__["c"]).__name__, "->", D.c())
            """,
            explain="""
            Through an instance you get a `method`; through the class, the
            plain `function`. A bound method is nothing more than that pair —
            `__self__` holding the instance, `__func__` the original function
            — and calling it slots `__self__` in as the first argument. The
            manual `__get__` line is not an analogy for what attribute access
            does; it is the same call.

            The class `__dict__` shows the contrast. A plain method is stored
            as a bare function, while `staticmethod` and `classmethod` are
            **different descriptor objects** wrapping one. All three work
            because each implements `__get__` its own way: the function binds
            the instance, `classmethod` binds the class, and `staticmethod`
            binds nothing and hands back the function untouched.
            """,
        ),
        Question(
            prompt="Why does `obj.method` automatically receive `obj` as `self`?",
            choices=[
                "The interpreter special-cases attribute access on classes",
                "`function.__get__` returns a bound method that stores the instance",
                "`self` is a reserved keyword filled in by the compiler",
                "Methods are stored per instance, each capturing its own object",
            ],
            answer=1,
            explain="Functions implement the descriptor protocol. `obj.method` is "
                    "`type(obj).method.__get__(obj, type(obj))`, which produces the bound method.",
        ),
        Text("""
        ## `property`: the descriptor you already use

        `property` is a data descriptor implemented in C. Its constructor is
        `property(fget, fset, fdel, doc)`; the `@x.setter` syntax just builds
        a *new* property with one more function filled in.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Note that `__init__` assigns to `self.degrees`, not
            `self._degrees` — so construction runs through the setter and
            inherits the same validation as every later write. One place
            enforces the invariant, and there is no way to build an invalid
            instance.

            `fahrenheit` is recomputed on every read and stored nowhere, so it
            cannot drift out of step with `degrees`; having no setter, it
            rejects assignment outright.

            The last line is the point of the section: `property` is an
            ordinary object with `fget`/`fset`/`fdel` attributes. `@x.setter`
            mutates nothing — it constructs a **new** property with one more
            function filled in and rebinds the name.
            """,
        ),
        Text("""
        ## When a property is not enough

        Properties do not compose: validating ten fields the same way means
        ten near-identical property pairs. A descriptor class is written once
        and reused everywhere — that is the entire argument for them.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Note the storage strategy: writing to `obj._age` rather than a dict
            keyed by instance. Never store per-instance state on the
            *descriptor itself* — there is exactly one descriptor object shared
            by every instance of the class.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            There is exactly **one** descriptor object per class attribute,
            created when the class body runs and shared by every instance ever
            made. So `self.value` inside `__set__` is class-wide storage:
            `a` and `b` wrote to the same box, and the second write won.

            The failure is quiet, which is what makes it dangerous — nothing
            raises, values simply bleed between unrelated objects, and it
            usually surfaces first under concurrency or in a long-lived
            process. Every correct descriptor keys its storage **by the
            instance**: the instance `__dict__`, a private attribute name, or
            a `WeakKeyDictionary`.
            """,
        ),
        Text("""
        ## Where to store the value

        1. **Instance `__dict__` under the public name** — only safe for a
           *non-data* descriptor, or you get infinite recursion.
        2. **Instance `__dict__` under a private name** (`_x`) — simple and
           debuggable. What most code does.
        3. **A `WeakKeyDictionary` keyed by instance** — works with
           `__slots__`, requires hashable instances, adds indirection.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            The weak dictionary drops its entry automatically when the instance
            is collected — a plain dict here would leak every object forever.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            `__delete__` completes the protocol: on a data descriptor,
            `del obj.attr` routes here instead of removing anything from the
            instance dict. Doing the work properly means the attribute returns
            to a genuinely *unset* state rather than lingering with a stale
            value.

            Two small choices carry weight. Raising `AttributeError` from
            `__get__` is what makes `hasattr()` report `False` — any other
            exception type propagates and the caller gets a crash instead of
            an answer. And `from None` suppresses the chained internal error,
            so the reader sees "value has been deleted" rather than a
            "during handling of the above exception" sandwich.
            """,
        ),
        Exercise(
            slug="validated-field",
            title="A configurable validating descriptor",
            difficulty="tricky",
            brief="""
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
            """,
            starter="""
            MISSING = object()


            class Field:
                def __init__(self, *, type=None, min=None, max=None,
                             choices=None, default=MISSING, required=True):
                    ...
            """,
            checks=[
                Check("stores and retrieves per instance", lambda ns: _fd_basic(ns)),
                Check("type checking, with the int/float and bool rules", lambda ns: _fd_type(ns)),
                Check("range checking is inclusive", lambda ns: _fd_range(ns)),
                Check("choices membership", lambda ns: _fd_choices(ns)),
                Check("defaults and required", lambda ns: _fd_default(ns)),
                Check("errors name the attribute", lambda ns: _fd_message(ns)),
                Check("class access returns the descriptor", lambda ns: _fd_class_access(ns)),
                Check("delete resets to unset", lambda ns: _fd_delete(ns)),
                Check("validation order: type before range", lambda ns: _fd_order(ns)),
            ],
            hints=(
                "`__set_name__` is where you learn the public name; derive a "
                "private one like `f'_field_{name}'` from it.",
                "`isinstance(True, int)` is True — special-case `bool` explicitly.",
                "For `type=float`, accept `int` as well: "
                "`expected = (int, float) if self.type is float else self.type`.",
                "Reading an unset required field should raise AttributeError, so "
                "`hasattr()` correctly reports False for it.",
                "Store into `obj.__dict__[self.private]` directly to avoid "
                "re-entering `__set__`.",
            ),
            solution="""
            MISSING = object()

            class Field:
                def __init__(self, *, type=None, min=None, max=None,
                             choices=None, default=MISSING, required=True):
                    self.type = type
                    self.min = min
                    self.max = max
                    self.choices = choices
                    self.default = default
                    self.required = required

                def __set_name__(self, owner, name):
                    self.name = name
                    self.private = f"_field_{name}"

                def __get__(self, obj, objtype=None):
                    if obj is None:
                        return self
                    if self.private in obj.__dict__:
                        return obj.__dict__[self.private]
                    if self.default is not MISSING:
                        return self.default
                    if self.required:
                        raise AttributeError(f"{self.name!r} has no value")
                    return None

                def __set__(self, obj, value):
                    self.validate(value)
                    obj.__dict__[self.private] = value

                def __delete__(self, obj):
                    obj.__dict__.pop(self.private, None)

                def validate(self, value):
                    if self.type is not None:
                        expected = (int, float) if self.type is float else self.type
                        if isinstance(value, bool) and self.type in (int, float):
                            raise TypeError(
                                f"{self.name} must be {self.type.__name__}, got bool"
                            )
                        if not isinstance(value, expected):
                            raise TypeError(
                                f"{self.name} must be {self.type.__name__}, "
                                f"got {builtin_type(value).__name__}"
                            )
                    if self.choices is not None and value not in self.choices:
                        raise ValueError(
                            f"{self.name} must be one of {list(self.choices)}, got {value!r}"
                        )
                    if self.min is not None and value < self.min:
                        raise ValueError(f"{self.name} must be >= {self.min}, got {value!r}")
                    if self.max is not None and value > self.max:
                        raise ValueError(f"{self.name} must be <= {self.max}, got {value!r}")

            builtin_type = type      # 'type' is shadowed by the parameter above
            """,
        ),
        Text("""
        ## Takeaways

        - A descriptor is a class attribute implementing `__get__`/`__set__`/
          `__delete__`; `__set_name__` tells it its own name.
        - Data descriptors beat the instance dict; non-data descriptors lose
          to it.
        - Functions are non-data descriptors — that is the origin of `self`.
        - Never keep per-instance state on the descriptor object.
        - Use a property for one attribute, a descriptor class when the same
          logic repeats.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _model(ns, **field_kwargs):
    Field = ns["Field"]

    class Model:
        value = Field(**field_kwargs)

    return Model


def _fd_basic(ns) -> None:
    Model = _model(ns, type=int)
    a, b = Model(), Model()
    a.value = 1
    b.value = 2
    assert (a.value, b.value) == (1, 2), "instances must not share a value"


def _fd_type(ns) -> None:
    Model = _model(ns, type=int)
    Model().value = 5
    for bad in ("5", 5.5, True):
        m = Model()
        try:
            m.value = bad
        except TypeError:
            continue
        raise AssertionError(f"{bad!r} should have been rejected for type=int")

    FloatModel = _model(ns, type=float)
    f = FloatModel()
    f.value = 1.5
    f.value = 2                          # int is acceptable where float is wanted
    assert f.value == 2
    try:
        f.value = True
    except TypeError:
        return
    raise AssertionError("bool must be rejected for type=float")


def _fd_range(ns) -> None:
    Model = _model(ns, type=int, min=0, max=10)
    m = Model()
    m.value = 0
    m.value = 10                         # inclusive on both ends
    for bad in (-1, 11):
        try:
            m.value = bad
        except ValueError:
            continue
        raise AssertionError(f"{bad} is out of range and should raise ValueError")


def _fd_choices(ns) -> None:
    Model = _model(ns, choices=("red", "green"))
    m = Model()
    m.value = "red"
    try:
        m.value = "blue"
    except ValueError:
        return
    raise AssertionError("a value outside choices must raise ValueError")


def _fd_default(ns) -> None:
    Defaulted = _model(ns, type=int, default=7)
    assert Defaulted().value == 7, "an unset field should read as its default"

    Required = _model(ns, type=int)
    m = Required()
    try:
        m.value
    except AttributeError:
        pass
    else:
        raise AssertionError("an unset required field with no default must raise AttributeError")
    assert not hasattr(m, "value"), "hasattr should report False for an unset required field"

    Optional = _model(ns, type=int, required=False)
    assert Optional().value is None, "an optional field with no default should read as None"


def _fd_message(ns) -> None:
    Field = ns["Field"]

    class Model:
        temperature = Field(type=int, min=0)

    m = Model()
    try:
        m.temperature = -5
    except ValueError as exc:
        assert "temperature" in str(exc), f"message should name the field: {exc}"
    else:
        raise AssertionError("expected ValueError")

    try:
        m.temperature = "hot"
    except TypeError as exc:
        assert "temperature" in str(exc), f"message should name the field: {exc}"
        return
    raise AssertionError("expected TypeError")


def _fd_class_access(ns) -> None:
    Field = ns["Field"]
    Model = _model(ns, type=int)
    assert isinstance(Model.value, Field), (
        "accessing the field on the class should return the descriptor itself"
    )


def _fd_delete(ns) -> None:
    Model = _model(ns, type=int, default=0)
    m = Model()
    m.value = 5
    assert m.value == 5
    del m.value
    assert m.value == 0, "after deletion the field should fall back to its default"


def _fd_order(ns) -> None:
    Model = _model(ns, type=int, min=0, max=10)
    m = Model()
    try:
        m.value = "not a number"
    except TypeError:
        return
    except ValueError:
        raise AssertionError(
            "type must be checked before range — comparing a str to an int "
            "would otherwise raise TypeError from the comparison itself"
        )
    raise AssertionError("expected TypeError")
