"""Lesson 10 — Class creation, __init_subclass__, ABCs, and metaclasses."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=10,
    slug="metaclasses",
    title="Class Creation and Metaclasses",
    summary="""
    A `class` statement is executable code that calls a factory. Knowing the
    exact sequence — namespace preparation, body execution, `type.__new__`,
    `__set_name__`, `__init_subclass__` — lets you hook in at the cheapest
    level rather than reaching for a metaclass every time. We cover the
    lightweight hooks first, then ABCs, then metaclasses proper.
    """,
    tags=("metaclasses", "abc", "class-creation", "metaprogramming"),
    blocks=[
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `type(name, bases, namespace)` *is* the class factory. The `class`
            statement is syntax sugar over exactly this call.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            `__init_subclass__` is implicitly a `classmethod` and receives the
            **new subclass**, not the base. Extra keyword arguments on the
            `class` line are forwarded to it — that is a clean, documented
            configuration channel.
            """,
        ),
        Text("""
        ## `__init_subclass__`: the registry pattern, done cheaply

        Ninety per cent of the "I need a metaclass" cases are actually this:
        run some code whenever someone subclasses me.
        """),
        Demo(
            code="""
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
            """,
        ),
        Question(
            prompt="`__init_subclass__` is called with which class as its argument?",
            choices=[
                "The class that defines it",
                "The newly created subclass",
                "The metaclass",
                "`object`",
            ],
            answer=1,
            explain="It is an implicit classmethod invoked on the *parent*, receiving "
                    "the new subclass as `cls`. It does not run for the defining class itself.",
        ),
        Text("""
        ## Abstract base classes

        `abc.ABC` uses the `ABCMeta` metaclass to block instantiation until
        every `@abstractmethod` is overridden. It also supports **virtual
        subclasses** via `register`, and `__subclasshook__` for structural
        checks — which is how `isinstance(x, Iterable)` works without any
        inheritance.
        """),
        Demo(
            code="""
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
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            Note the cost: `register` and `__subclasshook__` make `isinstance`
            lie about the MRO. They are the right tool for protocol checks on
            types you do not own — but `typing.Protocol` (lesson 13) is usually
            the better modern answer.
            """,
        ),
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            Plain Python silently lets the second `timeout` win. In a large
            settings class that is a genuinely nasty bug, and `__prepare__` is
            the only hook that can see it — by the time `__new__` runs, the
            namespace is already a plain dict with one entry.
            """,
        ),
        Demo(
            code="""
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
            """,
            explain="""
            Why the metaclass rather than `__new__`? Overriding `__new__` to
            return a cached instance still calls `__init__` on it every time,
            silently re-initialising your singleton. Intercepting at
            `__call__` prevents that.
            """,
        ),
        Predict(
            code="""
            class Meta(type):
                def __call__(cls, *args, **kwargs):
                    print("meta.__call__")
                    return super().__call__(*args, **kwargs)

            class C(metaclass=Meta):
                def __new__(cls, *args):
                    print("C.__new__")
                    return super().__new__(cls)
                def __init__(self, x):
                    print("C.__init__")
                    self.x = x

            c = C(1)
            print("done", c.x)
            """,
            answer="""
            meta.__call__
            C.__new__
            C.__init__
            done 1
            """,
            explain="""
            `C(1)` is `type(C).__call__(C, 1)`. The default `type.__call__`
            then calls `C.__new__` and, if the result is an instance of `C`,
            `C.__init__`. Every instantiation goes through the metaclass.
            """,
        ),
        Question(
            prompt="You want to run code each time a class is subclassed. What is the lightest tool?",
            choices=[
                "A metaclass overriding `__new__`",
                "`__init_subclass__` on the base class",
                "A class decorator on every subclass",
                "`__set_name__`",
            ],
            answer=1,
            explain="It needs no metaclass, cannot cause metaclass conflicts, and is "
                    "inherited automatically. Metaclasses are for when you must change "
                    "*how the class object itself is built*.",
        ),
        Text("""
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
        """),
        Demo(
            code="""
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
            """,
        ),
        Exercise(
            slug="autoslots",
            title="A class decorator that adds __slots__",
            difficulty="tricky",
            brief="""
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
            """,
            starter="""
            def autoslots(cls):
                ...
            """,
            checks=[
                Check("slots are derived from annotations", lambda ns: _as_slots(ns["autoslots"])),
                Check("unknown attributes are rejected", lambda ns: _as_reject(ns["autoslots"])),
                Check("generated __init__ handles required fields", lambda ns: _as_required(ns["autoslots"])),
                Check("defaults are honoured", lambda ns: _as_defaults(ns["autoslots"])),
                Check("unknown keywords raise TypeError", lambda ns: _as_unknown(ns["autoslots"])),
                Check("methods and metadata survive", lambda ns: _as_methods(ns["autoslots"])),
                Check("an existing __init__ is left alone", lambda ns: _as_custom_init(ns["autoslots"])),
                Check("bases are preserved", lambda ns: _as_bases(ns["autoslots"])),
            ],
            hints=(
                "`dict(vars(cls))` gives you the namespace; strip `__dict__` and "
                "`__weakref__` from it or `type()` will complain about conflicts.",
                "Also remove the class-level default *values* from the namespace — "
                "a class attribute with the same name as a slot shadows the slot "
                "descriptor and raises ValueError at class creation.",
                "`cls.__dict__.get('__annotations__', {})` gets only this class's "
                "annotations, unlike `cls.__annotations__` which can inherit.",
                "Build `__init__` as a real closure over the defaults dict; there is "
                "no need to generate source text.",
            ),
            solution="""
            def autoslots(cls):
                annotations = dict(cls.__dict__.get("__annotations__", {}))
                slots = tuple(annotations)
                defaults = {name: getattr(cls, name)
                            for name in annotations if hasattr(cls, name)}

                namespace = {
                    key: value for key, value in vars(cls).items()
                    if key not in {"__dict__", "__weakref__"} and key not in annotations
                }
                namespace["__slots__"] = slots

                if "__init__" not in namespace:
                    required = [n for n in annotations if n not in defaults]

                    def __init__(self, **kwargs):
                        unknown = set(kwargs) - set(annotations)
                        if unknown:
                            raise TypeError(f"unexpected keyword(s): {sorted(unknown)}")
                        missing = [n for n in required if n not in kwargs]
                        if missing:
                            raise TypeError(f"missing required field(s): {missing}")
                        for name in annotations:
                            setattr(self, name, kwargs.get(name, defaults.get(name)))

                    namespace["__init__"] = __init__

                new_cls = type(cls)(cls.__name__, cls.__bases__, namespace)
                new_cls.__qualname__ = cls.__qualname__
                new_cls.__doc__ = cls.__doc__
                return new_cls
            """,
        ),
        Exercise(
            slug="final-meta",
            title="A metaclass enforcing @final and interfaces",
            difficulty="brutal",
            brief="""
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
            """,
            starter="""
            def final(obj):
                ...


            class StrictMeta(type):
                ...
            """,
            checks=[
                Check("final decorator marks functions and classes", lambda ns: _fm_mark(ns)),
                Check("overriding a final method raises TypeError", lambda ns: _fm_override(ns)),
                Check("legal subclassing still works", lambda ns: _fm_legal(ns)),
                Check("subclassing a final class raises TypeError", lambda ns: _fm_final_class(ns)),
                Check("requires= enforces an interface", lambda ns: _fm_requires(ns)),
                Check("inherited members satisfy requires=", lambda ns: _fm_requires_inherited(ns)),
                Check("finals() reports names across the MRO", lambda ns: _fm_finals(ns)),
                Check("error messages name the offender", lambda ns: _fm_messages(ns)),
            ],
            hints=(
                "`final` can just set an attribute: `obj.__is_final__ = True` and "
                "return `obj`.",
                "In `__new__`, walk `bases` and their `__mro__`s to collect the "
                "final names before creating the class.",
                "The `requires` keyword arrives in `**kwds` of `__new__` *and* "
                "`__init__` — accept and swallow it in both, or `type.__init__` "
                "will raise.",
                "Check `requires` after creating the class so inherited attributes "
                "count; use `hasattr(cls, name)`.",
                "Remember `__prepare__` also receives the extra keywords.",
            ),
            solution="""
            def final(obj):
                obj.__is_final__ = True
                return obj

            class StrictMeta(type):
                @classmethod
                def __prepare__(mcls, name, bases, **kwds):
                    return {}

                def __new__(mcls, name, bases, ns, **kwds):
                    requires = kwds.pop("requires", ())

                    for base in bases:
                        if getattr(base, "__is_final__", False):
                            raise TypeError(
                                f"cannot subclass final class {base.__name__!r}"
                            )

                    inherited_finals = set()
                    for base in bases:
                        for klass in base.__mro__:
                            for attr, value in vars(klass).items():
                                if getattr(value, "__is_final__", False):
                                    inherited_finals.add(attr)

                    clashes = inherited_finals & set(ns)
                    if clashes:
                        raise TypeError(
                            f"{name!r} cannot override final method(s): {sorted(clashes)}"
                        )

                    cls = super().__new__(mcls, name, bases, ns)

                    missing = [attr for attr in requires if not hasattr(cls, attr)]
                    if missing:
                        raise TypeError(f"{name!r} is missing required member(s): {missing}")
                    return cls

                def __init__(cls, name, bases, ns, **kwds):
                    kwds.pop("requires", None)
                    super().__init__(name, bases, ns)

                @staticmethod
                def finals(cls):
                    names = set()
                    for klass in cls.__mro__:
                        for attr, value in vars(klass).items():
                            if getattr(value, "__is_final__", False):
                                names.add(attr)
                    return names
            """,
        ),
        Text("""
        ## Takeaways

        - `class` = prepare namespace → run body → call the metaclass.
        - `__set_name__` and `__init_subclass__` cover most needs with no
          metaclass and no conflicts.
        - ABCs block incomplete implementations; `register` and
          `__subclasshook__` extend `isinstance` structurally.
        - A metaclass's `__call__` is the only clean place to intercept
          instantiation.
        - Metaclasses are viral — every subclass inherits yours.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _as_slots(autoslots) -> None:
    @autoslots
    class Point:
        x: int
        y: int

    assert Point.__slots__ == ("x", "y"), f"got {Point.__slots__!r}"
    p = Point(x=1, y=2)
    assert (p.x, p.y) == (1, 2)
    assert not hasattr(p, "__dict__"), "instances should have no __dict__"


def _as_reject(autoslots) -> None:
    @autoslots
    class Point:
        x: int

    p = Point(x=1)
    try:
        p.z = 3
    except AttributeError:
        return
    raise AssertionError("an unknown attribute must be rejected")


def _as_required(autoslots) -> None:
    @autoslots
    class Point:
        x: int
        y: int

    try:
        Point(x=1)
    except TypeError:
        return
    raise AssertionError("a missing required field must raise TypeError")


def _as_defaults(autoslots) -> None:
    @autoslots
    class Config:
        host: str
        port: int = 8080

    c = Config(host="localhost")
    assert c.port == 8080, f"default not applied, got {c.port!r}"
    assert Config(host="h", port=1).port == 1


def _as_unknown(autoslots) -> None:
    @autoslots
    class Point:
        x: int

    try:
        Point(x=1, nope=2)
    except TypeError:
        return
    raise AssertionError("an unknown keyword must raise TypeError")


def _as_methods(autoslots) -> None:
    @autoslots
    class Vec:
        """A vector."""
        x: int
        y: int

        def length_sq(self):
            return self.x ** 2 + self.y ** 2

        @property
        def as_tuple(self):
            return (self.x, self.y)

    v = Vec(x=3, y=4)
    assert v.length_sq() == 25, "methods must survive"
    assert v.as_tuple == (3, 4), "properties must survive"
    assert Vec.__name__ == "Vec", Vec.__name__
    assert Vec.__doc__ == "A vector.", repr(Vec.__doc__)


def _as_custom_init(autoslots) -> None:
    @autoslots
    class Custom:
        x: int

        def __init__(self, x):
            self.x = x * 10

    c = Custom(5)
    assert c.x == 50, "an existing __init__ must be preserved"


def _as_bases(autoslots) -> None:
    class Base:
        def describe(self):
            return "base"

    @autoslots
    class Child(Base):
        x: int

    c = Child(x=1)
    assert isinstance(c, Base), "the original bases must be preserved"
    assert c.describe() == "base"


def _fm_mark(ns) -> None:
    final = ns["final"]

    @final
    def fn():
        return 1

    @final
    class Klass:
        pass

    assert fn() == 1, "final must return the object unchanged"
    assert getattr(fn, "__is_final__", False), "the function was not marked"
    assert getattr(Klass, "__is_final__", False), "the class was not marked"


def _fm_override(ns) -> None:
    final, StrictMeta = ns["final"], ns["StrictMeta"]

    class Base(metaclass=StrictMeta):
        @final
        def locked(self):
            return "base"

        def open_method(self):
            return "open"

    try:
        class Child(Base):
            def locked(self):
                return "override"
    except TypeError:
        return
    raise AssertionError("overriding a final method must raise TypeError")


def _fm_legal(ns) -> None:
    final, StrictMeta = ns["final"], ns["StrictMeta"]

    class Base(metaclass=StrictMeta):
        @final
        def locked(self):
            return "base"

        def open_method(self):
            return "open"

    class Child(Base):
        def open_method(self):
            return "child"

    c = Child()
    assert c.open_method() == "child"
    assert c.locked() == "base", "the final method should still be inherited"

    class GrandChild(Child):
        pass

    try:
        class Bad(GrandChild):
            def locked(self):
                return "sneaky"
    except TypeError:
        return
    raise AssertionError("finals must be enforced deep in the hierarchy too")


def _fm_final_class(ns) -> None:
    final, StrictMeta = ns["final"], ns["StrictMeta"]

    @final
    class Sealed(metaclass=StrictMeta):
        pass

    try:
        class Child(Sealed):
            pass
    except TypeError:
        return
    raise AssertionError("subclassing a final class must raise TypeError")


def _fm_requires(ns) -> None:
    StrictMeta = ns["StrictMeta"]

    try:
        class Incomplete(metaclass=StrictMeta, requires=("read", "write")):
            def read(self):
                return None
    except TypeError:
        pass
    else:
        raise AssertionError("a missing required member must raise TypeError")

    class Complete(metaclass=StrictMeta, requires=("read", "write")):
        def read(self):
            return "r"

        def write(self, v):
            return "w"

    assert Complete().read() == "r"


def _fm_requires_inherited(ns) -> None:
    StrictMeta = ns["StrictMeta"]

    class Base(metaclass=StrictMeta):
        def read(self):
            return "r"

    class Child(Base, requires=("read",)):
        pass

    assert Child().read() == "r", "an inherited member should satisfy requires="


def _fm_finals(ns) -> None:
    final, StrictMeta = ns["final"], ns["StrictMeta"]

    class Base(metaclass=StrictMeta):
        @final
        def a(self): ...
        def b(self): ...

    class Child(Base):
        @final
        def c(self): ...

    got = StrictMeta.finals(Child)
    assert got == {"a", "c"}, f"expected {{'a', 'c'}}, got {got}"


def _fm_messages(ns) -> None:
    final, StrictMeta = ns["final"], ns["StrictMeta"]

    class Base(metaclass=StrictMeta):
        @final
        def locked(self): ...

    try:
        class Child(Base):
            def locked(self): ...
    except TypeError as exc:
        assert "locked" in str(exc), f"message should name the method: {exc}"
    else:
        raise AssertionError("expected TypeError")

    @final
    class Sealed(metaclass=StrictMeta):
        pass

    try:
        class Sub(Sealed):
            pass
    except TypeError as exc:
        assert "Sealed" in str(exc), f"message should name the class: {exc}"
        return
    raise AssertionError("expected TypeError")
