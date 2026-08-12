"""Lesson 08 — Classes, attribute lookup, MRO, and super()."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=8,
    slug="classes",
    title="Classes, MRO, and super()",
    summary="""
    Where does `obj.x` actually come from? What does `super()` really do —
    and why is "call the parent class" the wrong mental model? This lesson
    walks the attribute lookup chain, derives the C3 linearisation, shows how
    cooperative multiple inheritance works, and measures what `__slots__`
    buys you.
    """,
    tags=("oop", "mro", "inheritance", "slots"),
    blocks=[
        Text("""
        ## The attribute lookup chain

        For `obj.x` (with `type(obj) is C`), Python's `object.__getattribute__`
        does roughly this:

        1. walk `type(C).__mro__` looking for `x`; if found and it is a
           **data descriptor** (has `__set__` or `__delete__`) → use it
        2. look in `obj.__dict__` → return it
        3. use the class-level `x` found in step 1 (a non-data descriptor
           like a function gets `__get__` called → bound method)
        4. fall back to `type(obj).__getattr__(obj, "x")`
        5. `AttributeError`

        Instance attributes shadow methods, but **data descriptors** (like
        `property`) beat instance attributes. That precedence is the whole
        reason properties work.
        """),
        Demo(
            code="""
            class C:
                shared = "class attribute"
                def method(self): return "method"
                @property
                def prop(self): return "property"

            c = C()
            print("from the class :", c.shared, "|", c.method(), "|", c.prop)

            c.shared = "instance wins"           # shadows the class attribute
            c.method = lambda: "instance lambda" # shadows the method too
            print("after shadowing:", c.shared, "|", c.method())

            try:
                c.prop = "cannot"                # data descriptor refuses
            except AttributeError as exc:
                print("property blocks it:", exc)

            print("instance dict:", c.__dict__)
            print("class still intact:", C.shared, C().method())
            """,
        ),
        Predict(
            code="""
            class Base:
                registry = []                 # ONE list, shared by all subclasses

            class A(Base): pass
            class B(Base): pass

            A.registry.append("from A")
            B.registry.append("from B")
            print(Base.registry)

            A.registry = ["A now has its own"]     # rebinding, not mutating
            print(Base.registry, B.registry, A.registry)
            """,
            answer="""
            ['from A', 'from B']
            ['from A', 'from B'] ['from A', 'from B'] ['A now has its own']
            """,
            explain="""
            A mutable class attribute is shared by the whole hierarchy —
            `append` hits the single object. Assignment, by contrast, creates
            a *new* attribute on `A` that shadows `Base.registry`. Per-class
            state needs `__init_subclass__` (lesson 10) or an explicit
            assignment in each subclass.
            """,
        ),
        Text("""
        ## The MRO and C3 linearisation

        `C.__mro__` is the ordered list of classes searched for attributes.
        Python computes it with the **C3 algorithm**, which guarantees:

        1. a class always precedes its parents
        2. parents stay in the order you declared them
        3. the result is *monotonic* — a subclass's MRO is consistent with
           every parent's MRO

        When no such order exists, the `class` statement itself raises a
        `TypeError`.
        """),
        Demo(
            code="""
            class A: pass
            class B(A): pass
            class C(A): pass
            class D(B, C): pass

            print("the diamond D(B, C):")
            for cls in D.__mro__:
                print("   ", cls.__name__)

            print()
            print("note C comes before A -- depth-first would have given D B A C A")

            # An impossible order is rejected at class-creation time.
            try:
                class Bad(B, A, C):     # requires A before C, but C3 needs C before A
                    pass
            except TypeError as exc:
                print("TypeError:", str(exc)[:80])
            """,
        ),
        Demo(
            code="""
            # C3 by hand: L(D) = D + merge(L(B), L(C), [B, C])
            def c3(cls):
                if cls is object:
                    return [object]
                parents = cls.__bases__
                return [cls] + merge([c3(p) for p in parents] + [list(parents)])

            def merge(sequences):
                result = []
                sequences = [list(s) for s in sequences if s]
                while sequences:
                    for seq in sequences:
                        head = seq[0]
                        if not any(head in s[1:] for s in sequences):
                            break
                    else:
                        raise TypeError("inconsistent hierarchy")
                    result.append(head)
                    for seq in sequences:
                        if seq and seq[0] == head:
                            del seq[0]
                    sequences = [s for s in sequences if s]
                return result

            class A: pass
            class B(A): pass
            class C(A): pass
            class D(B, C): pass

            print("hand-computed:", [c.__name__ for c in c3(D)])
            print("CPython's    :", [c.__name__ for c in D.__mro__])
            print("identical:", [c.__name__ for c in c3(D)] == [c.__name__ for c in D.__mro__])
            """,
            explain="""
            The rule inside `merge`: take the head of the first list that does
            not appear in the *tail* of any other list. If no such head exists,
            the hierarchy is inconsistent and the class cannot be created.
            """,
        ),
        Question(
            prompt="For `class D(B, C)` where `B(A)` and `C(A)`, what is `D.__mro__`?",
            choices=[
                "D, B, A, C, A, object",
                "D, B, C, A, object",
                "D, C, B, A, object",
                "D, A, B, C, object",
            ],
            answer=1,
            explain="C3 keeps A after *both* of its children, and preserves the "
                    "declared order B before C. Each class appears exactly once.",
        ),
        Text("""
        ## `super()` walks the MRO — it does not mean "my parent"

        `super()` returns a proxy that starts searching **after the current
        class in the MRO of `type(self)`**. Which class that is depends on the
        *instance*, not on where the code was written. This is what makes
        cooperative multiple inheritance possible.
        """),
        Demo(
            code="""
            class Base:
                def go(self): return ["Base"]

            class Left(Base):
                def go(self): return ["Left"] + super().go()

            class Right(Base):
                def go(self): return ["Right"] + super().go()

            class Both(Left, Right):
                def go(self): return ["Both"] + super().go()

            print("MRO :", [c.__name__ for c in Both.__mro__])
            print("call:", Both().go())
            print()
            print("Inside Left.go, super() resolved to Right -- not Base --")
            print("because the MRO of the *instance* is what matters:")
            print("  ", Left().go(), "<- same code, different resolution")
            """,
            explain="""
            `Left.go` was written knowing nothing about `Right`, yet in a
            `Both` instance its `super()` call lands on `Right.go`. Every
            class in the chain runs exactly once. That is *cooperative*
            inheritance — and it only works if every class calls `super()`.
            """,
        ),
        Demo(
            code="""
            # Cooperative __init__ with **kwargs is the standard pattern.
            class Base:
                def __init__(self, **kwargs):
                    print("  Base.__init__ leftover:", kwargs)
                    super().__init__()          # terminates at object

            class Timestamped(Base):
                def __init__(self, *, created="now", **kwargs):
                    self.created = created
                    print("  Timestamped consumed created")
                    super().__init__(**kwargs)

            class Named(Base):
                def __init__(self, *, name="anon", **kwargs):
                    self.name = name
                    print("  Named consumed name")
                    super().__init__(**kwargs)

            class Record(Timestamped, Named):
                pass

            r = Record(name="widget", created="2024-01-01")
            print("result:", r.name, r.created)
            """,
            explain="""
            Each mixin plucks the keywords it understands and forwards the
            rest. Break the chain — forget one `super().__init__(**kwargs)` —
            and the classes after it in the MRO silently never initialise.
            """,
        ),
        Demo(
            code="""
            # super() has an explicit two-argument form, occasionally necessary.
            class A:
                def hello(self): return "A"
            class B(A):
                def hello(self): return "B -> " + super().hello()
            class C(B):
                def hello(self):
                    skip_b = super(B, self).hello()      # start AFTER B
                    return f"C (skipping B: {skip_b})"

            print(C().hello())

            # Outside a method body you must be explicit:
            print("explicit:", super(B, C()).hello())

            # In a classmethod, pass the class:
            class D(A):
                @classmethod
                def make(cls):
                    return f"D.make -> {super().__thisclass__.__name__}"
            print(D.make())
            """,
        ),
        Question(
            prompt="`super()` inside a method of class `X` looks up the attribute where?",
            choices=[
                "In `X.__bases__[0]` — the first parent",
                "In the MRO of `type(self)`, starting after `X`",
                "In `object`, always",
                "In the class where the method was originally defined",
            ],
            answer=1,
            explain="It is instance-dependent. The same `super()` call in `X` can "
                    "reach entirely different classes depending on what the instance's "
                    "class inherits from.",
        ),
        Text("""
        ## Mixins

        A mixin is a class designed to be *combined*, never instantiated
        alone. Conventions that keep them workable:

        - give them no `__init__`, or a cooperative `**kwargs` one
        - depend only on a documented interface (`self.items`, `self.name`)
        - list them **before** the base class: `class C(MixinA, MixinB, Base)`
        - keep them small and orthogonal
        """),
        Demo(
            code="""
            class ReprMixin:
                '''Builds __repr__ from a class-level _fields tuple.'''
                _fields = ()
                def __repr__(self):
                    inner = ", ".join(f"{f}={getattr(self, f)!r}" for f in self._fields)
                    return f"{type(self).__name__}({inner})"

            class ComparableMixin:
                _fields = ()
                def _key(self): return tuple(getattr(self, f) for f in self._fields)
                def __eq__(self, other):
                    if type(other) is not type(self): return NotImplemented
                    return self._key() == other._key()
                def __hash__(self): return hash((type(self), self._key()))
                def __lt__(self, other): return self._key() < other._key()

            class Point(ReprMixin, ComparableMixin):
                _fields = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y

            pts = [Point(2, 1), Point(1, 5), Point(1, 2)]
            print("repr   :", pts[0])
            print("sorted :", sorted(pts))
            print("equal  :", Point(1, 2) == Point(1, 2))
            print("hashable:", len({Point(1, 2), Point(1, 2)}))
            """,
        ),
        Text("""
        ## `__slots__`: trading flexibility for memory

        Declaring `__slots__` replaces the per-instance `__dict__` with a
        fixed array of descriptors. You get lower memory and slightly faster
        attribute access; you lose dynamic attributes, `__dict__`, and
        (usually) `cached_property` and multiple inheritance from two slotted
        classes.
        """),
        Demo(
            code="""
            import sys

            class Loose:
                def __init__(self, x, y): self.x, self.y = x, y

            class Tight:
                __slots__ = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y

            loose, tight = Loose(1, 2), Tight(1, 2)
            loose_total = sys.getsizeof(loose) + sys.getsizeof(loose.__dict__)
            tight_total = sys.getsizeof(tight)
            print(f"with __dict__ : {loose_total:4} bytes")
            print(f"with __slots__: {tight_total:4} bytes")
            print(f"saving        : {100 * (1 - tight_total/loose_total):.0f}%")

            loose.extra = "fine"
            try:
                tight.extra = "nope"
            except AttributeError as exc:
                print("slots reject unknown attributes:", exc)

            print("slots are descriptors:", type(Tight.x).__name__)
            """,
            explain="""
            The saving matters at scale — a million small objects is where
            this becomes real. A subclass without its own `__slots__` silently
            regains a `__dict__`, undoing the benefit.
            """,
        ),
        Demo(
            code="""
            # Slots and inheritance: the rules that trip people up.
            class A:
                __slots__ = ("a",)

            class B(A):
                __slots__ = ("b",)               # do NOT repeat 'a'

            class C(A):
                pass                             # no __slots__ -> gains __dict__

            b, c = B(), C()
            b.a, b.b = 1, 2
            print("B slots work:", b.a, b.b, "| has __dict__:", hasattr(b, "__dict__"))
            c.anything = "allowed"
            print("C regained __dict__:", c.__dict__)

            # Two slotted parents with a common non-empty layout: not allowed.
            class X: __slots__ = ("v",)
            class Y: __slots__ = ("w",)
            try:
                class Z(X, Y): __slots__ = ()
            except TypeError as exc:
                print("TypeError:", exc)
            """,
        ),
        Exercise(
            slug="mro-trace",
            title="Trace and validate an MRO",
            difficulty="medium",
            brief="""
            Write two functions that reason about class hierarchies.

            `mro_names(cls)` → list of class names in `cls.__mro__` order.

            `resolve(cls, attr)` → the name of the class in the MRO that
            *provides* `attr`, or `None` if nothing does. It must report the
            class that actually holds the attribute in its `__dict__`, not
            merely one that inherits it.

            `call_chain(cls, method)` → list of class names, in MRO order,
            that define `method` in their own `__dict__`. This is the sequence
            a fully cooperative `super()` chain would visit.

            `is_cooperative(cls, method)` → True when **every** class in that
            chain except the last one actually *calls* `super()` in the
            method's body.

            > Careful: a substring search for `"super("` is not good enough —
            > a comment or a docstring mentioning `super()` would fool it, and
            > one of the checks deliberately contains exactly that. Parse the
            > source with `ast` and look for a real call node. Classes whose
            > source is unavailable (builtins, dynamically created classes)
            > count as cooperative.
            """,
            starter="""
            import ast
            import inspect
            import textwrap


            def mro_names(cls):
                ...


            def resolve(cls, attr):
                ...


            def call_chain(cls, method):
                ...


            def is_cooperative(cls, method):
                ...
            """,
            checks=[
                Check("mro_names matches __mro__", lambda ns: _mro_names(ns["mro_names"])),
                Check("resolve finds the defining class", lambda ns: _mro_resolve(ns["resolve"])),
                Check("resolve returns None for missing attributes",
                      lambda ns: _mro_missing(ns["resolve"])),
                Check("call_chain lists definers in MRO order",
                      lambda ns: _mro_chain(ns["call_chain"])),
                Check("is_cooperative spots a broken chain",
                      lambda ns: _mro_coop(ns["is_cooperative"])),
            ],
            hints=(
                "`vars(klass)` is `klass.__dict__` — use it to distinguish "
                "'defines' from 'inherits'.",
                "`cls.__mro__` is already the exact order you need; never "
                "recompute it.",
                "For the last class in a chain, calling `super()` is optional — "
                "it usually lands on `object`.",
                "`ast.walk(tree)` yields every node; you want an `ast.Call` whose "
                "`func` is an `ast.Name` with `id == 'super'`.",
                "`inspect.getsource` on a method returns it still indented — run it "
                "through `textwrap.dedent` before `ast.parse`.",
                "Wrap `inspect.getsource` in try/except (OSError, TypeError): "
                "builtins and dynamically-created classes have no source.",
            ),
            solution="""
            import ast
            import inspect
            import textwrap

            def mro_names(cls):
                return [klass.__name__ for klass in cls.__mro__]

            def resolve(cls, attr):
                for klass in cls.__mro__:
                    if attr in vars(klass):
                        return klass.__name__
                return None

            def call_chain(cls, method):
                return [klass.__name__ for klass in cls.__mro__ if method in vars(klass)]

            def calls_super(func):
                try:
                    source = textwrap.dedent(inspect.getsource(func))
                except (OSError, TypeError):
                    return True          # no source: give it the benefit of the doubt
                for node in ast.walk(ast.parse(source)):
                    if (isinstance(node, ast.Call)
                            and isinstance(node.func, ast.Name)
                            and node.func.id == "super"):
                        return True
                return False

            def is_cooperative(cls, method):
                definers = [klass for klass in cls.__mro__ if method in vars(klass)]
                return all(calls_super(vars(k)[method]) for k in definers[:-1])
            """,
        ),
        Exercise(
            slug="observable",
            title="A cooperative observable mixin",
            difficulty="brutal",
            brief="""
            Build `Observable`, a mixin that fires callbacks whenever a
            *tracked* attribute changes — and that survives multiple
            inheritance.

            - `Observable` defines `__init__(self, **kwargs)` that forwards
              leftovers via `super().__init__(**kwargs)`
            - subclasses declare `_observed = ("field", ...)`; only those
              attributes are watched
            - `obj.on_change(name, callback)` registers `callback(name, old,
              new)`; `"*"` registers for every observed attribute
            - callbacks fire **only when the value actually changes** (`!=`)
            - the first assignment (no previous value) fires with `old=None`
            - `obj.off_change(name, callback)` removes one; removing an
              unregistered callback is a no-op
            - a callback raising must not prevent the other callbacks from
              running, and must not prevent the attribute from being set;
              collect such exceptions into `obj.callback_errors`
            - listeners are **per instance**, never shared between instances
            - it must compose: `class Model(Observable, OtherBase)` must still
              run `OtherBase.__init__`
            """,
            starter="""
            class Observable:
                _observed = ()

                def __init__(self, **kwargs):
                    ...
            """,
            checks=[
                Check("fires on a tracked change", lambda ns: _ob_basic(ns["Observable"])),
                Check("ignores untracked attributes", lambda ns: _ob_untracked(ns["Observable"])),
                Check("no callback when the value is unchanged", lambda ns: _ob_nochange(ns["Observable"])),
                Check("wildcard listeners", lambda ns: _ob_wildcard(ns["Observable"])),
                Check("off_change removes, unknown removal is a no-op",
                      lambda ns: _ob_off(ns["Observable"])),
                Check("a raising callback is isolated", lambda ns: _ob_errors(ns["Observable"])),
                Check("listeners are per instance", lambda ns: _ob_isolation(ns["Observable"])),
                Check("cooperates with other bases", lambda ns: _ob_cooperative(ns["Observable"])),
            ],
            hints=(
                "Set up the listener registry with `object.__setattr__` (or write "
                "straight into `self.__dict__`) so `__setattr__` does not recurse "
                "before the registry exists.",
                "In `__setattr__`, read the old value with "
                "`getattr(self, name, None)` *before* delegating to "
                "`super().__setattr__`.",
                "Fire the callbacks *after* the value is stored, so a callback that "
                "reads the attribute sees the new value.",
                "Iterate over a copy of the callback list — a callback may register "
                "or remove listeners while you are iterating.",
                "`__init__` must call `super().__init__(**kwargs)` for the mixin to "
                "compose with another base class.",
            ),
            solution="""
            class Observable:
                _observed = ()

                def __init__(self, **kwargs):
                    object.__setattr__(self, "_listeners", {})
                    object.__setattr__(self, "callback_errors", [])
                    super().__init__(**kwargs)

                def _registry(self):
                    if "_listeners" not in self.__dict__:
                        object.__setattr__(self, "_listeners", {})
                        object.__setattr__(self, "callback_errors", [])
                    return self.__dict__["_listeners"]

                def on_change(self, name, callback):
                    self._registry().setdefault(name, []).append(callback)

                def off_change(self, name, callback):
                    listeners = self._registry().get(name, [])
                    if callback in listeners:
                        listeners.remove(callback)

                def __setattr__(self, name, value):
                    if name not in self._observed:
                        super().__setattr__(name, value)
                        return
                    old = getattr(self, name, None)
                    super().__setattr__(name, value)
                    if old == value:
                        return
                    registry = self._registry()
                    for callback in [*registry.get(name, []), *registry.get("*", [])]:
                        try:
                            callback(name, old, value)
                        except Exception as exc:
                            self.callback_errors.append(exc)
            """,
        ),
        Text("""
        ## Takeaways

        - Lookup order: data descriptors → instance dict → class MRO →
          `__getattr__`.
        - `__mro__` is computed by C3 and is the single source of truth for
          both attribute lookup and `super()`.
        - `super()` means "next in the MRO of `type(self)`" — cooperative,
          not parental.
        - Mixins go before the base class and must forward `**kwargs`.
        - `__slots__` saves real memory but is easy to lose in a subclass.
        """),
    ],
)


# --------------------------------------------------------------------------
# Fixtures and check helpers
# --------------------------------------------------------------------------
class _A:
    tag = "A"

    def go(self):
        return "A"


class _B(_A):
    def go(self):
        return "B" + super().go()


class _C(_A):
    extra = "C"

    def go(self):
        return "C" + super().go()


class _D(_B, _C):
    def go(self):
        return "D" + super().go()


class _Broken(_B, _C):
    def go(self):
        """Deliberately stops the chain.

        This docstring mentions super() on purpose: a solution that merely
        greps the source text for "super(" will wrongly call this cooperative.
        """
        return "Broken"


def _mro_names(mro_names) -> None:
    got = mro_names(_D)
    assert got == ["_D", "_B", "_C", "_A", "object"], got


def _mro_resolve(resolve) -> None:
    assert resolve(_D, "extra") == "_C", resolve(_D, "extra")
    assert resolve(_D, "tag") == "_A", resolve(_D, "tag")
    assert resolve(_D, "go") == "_D", "should report the first definer in MRO order"
    assert resolve(_B, "extra") is None, "_B does not inherit from _C"


def _mro_missing(resolve) -> None:
    assert resolve(_D, "does_not_exist") is None


def _mro_chain(call_chain) -> None:
    got = call_chain(_D, "go")
    assert got == ["_D", "_B", "_C", "_A"], got
    assert call_chain(_A, "go") == ["_A"]


def _mro_coop(is_cooperative) -> None:
    assert is_cooperative(_D, "go") is True, "_D's chain all call super()"
    assert is_cooperative(_Broken, "go") is False, "_Broken.go never calls super()"


def _ob_basic(Observable) -> None:
    class Model(Observable):
        _observed = ("name",)

    m = Model()
    events = []
    m.on_change("name", lambda n, o, v: events.append((n, o, v)))
    m.name = "first"
    assert events == [("name", None, "first")], events
    m.name = "second"
    assert events[-1] == ("name", "first", "second"), events
    assert m.name == "second"


def _ob_untracked(Observable) -> None:
    class Model(Observable):
        _observed = ("watched",)

    m = Model()
    events = []
    m.on_change("*", lambda *a: events.append(a))
    m.ignored = 1
    assert events == [], f"untracked attribute fired {events}"
    assert m.ignored == 1, "the attribute must still be set"


def _ob_nochange(Observable) -> None:
    class Model(Observable):
        _observed = ("v",)

    m = Model()
    m.v = 5
    events = []
    m.on_change("v", lambda *a: events.append(a))
    m.v = 5
    assert events == [], "an identical value must not fire a callback"
    m.v = 6
    assert len(events) == 1, events


def _ob_wildcard(Observable) -> None:
    class Model(Observable):
        _observed = ("a", "b")

    m = Model()
    seen = []
    m.on_change("*", lambda n, o, v: seen.append(n))
    m.a = 1
    m.b = 2
    assert seen == ["a", "b"], seen


def _ob_off(Observable) -> None:
    class Model(Observable):
        _observed = ("v",)

    m = Model()
    events = []
    cb = lambda n, o, v: events.append(v)
    m.on_change("v", cb)
    m.v = 1
    m.off_change("v", cb)
    m.v = 2
    assert events == [1], f"callback fired after removal: {events}"
    m.off_change("v", cb)                       # must not raise
    m.off_change("nonexistent", cb)             # must not raise


def _ob_errors(Observable) -> None:
    class Model(Observable):
        _observed = ("v",)

    m = Model()
    survived = []

    def bad(name, old, new):
        raise RuntimeError("callback exploded")

    m.on_change("v", bad)
    m.on_change("v", lambda n, o, v: survived.append(v))
    m.v = 9
    assert survived == [9], "a raising callback blocked the others"
    assert m.v == 9, "the attribute must still be set"
    assert len(m.callback_errors) == 1, m.callback_errors
    assert isinstance(m.callback_errors[0], RuntimeError)


def _ob_isolation(Observable) -> None:
    class Model(Observable):
        _observed = ("v",)

    a, b = Model(), Model()
    hits = []
    a.on_change("v", lambda *args: hits.append("a"))
    b.v = 1
    assert hits == [], "listeners leaked between instances"
    a.v = 1
    assert hits == ["a"], hits


def _ob_cooperative(Observable) -> None:
    initialised = []

    class OtherBase:
        def __init__(self, **kwargs):
            initialised.append("other")
            super().__init__(**kwargs)

    class Model(Observable, OtherBase):
        _observed = ("v",)

    m = Model()
    assert initialised == ["other"], (
        "Observable.__init__ must forward via super() so OtherBase runs"
    )
    events = []
    m.on_change("v", lambda *a: events.append(a))
    m.v = 3
    assert len(events) == 1, events
