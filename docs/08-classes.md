# 08 — Classes, MRO, and super()

Where does `obj.x` actually come from? What does `super()` really do —
and why is "call the parent class" the wrong mental model? This lesson
walks the attribute lookup chain, derives the C3 linearisation, shows how
cooperative multiple inheritance works, and measures what `__slots__`
buys you.

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

```python
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
```
Assigning to `c.shared` does not touch the class at all — it puts
an entry in *this instance's* `__dict__`, which then shadows the
class attribute for this instance only. Every other instance still
sees the original, which is what makes accidental shadowing so
hard to spot from the outside.

Even the method can be shadowed, because a plain function is a
**non-data** descriptor and loses to the instance dict. The
property survives because it is a **data** descriptor and wins —
and having no setter, it refuses the assignment outright. So if an
attribute must not be overwritten per instance, that is the
mechanism: give it a `__set__`.


## The MRO and C3 linearisation

`C.__mro__` is the ordered list of classes searched for attributes.
Python computes it with the **C3 algorithm**, which guarantees:

1. a class always precedes its parents
2. parents stay in the order you declared them
3. the result is *monotonic* — a subclass's MRO is consistent with
   every parent's MRO

When no such order exists, the `class` statement itself raises a
`TypeError`.

```python
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
```
C3 guarantees three things at once: every class appears exactly
once, a subclass always precedes its bases, and the left-to-right
order of the bases is preserved. `C` therefore lands before `A`.

The alternative matters. Under the old depth-first rule the order
would have been D B A C — so a call could reach `A`'s
implementation while `C`'s override was never consulted, even
though `C` sits between them. That silent skipping is the bug C3
exists to prevent.

And when the constraints cannot all hold, you get a `TypeError`
**at class creation** — at import, with a clear message, rather
than as mysterious dispatch behaviour much later.

```python
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
```
The rule inside `merge`: take the head of the first list that does
not appear in the *tail* of any other list. If no such head exists,
the hierarchy is inconsistent and the class cannot be created.

**Quiz.** For `class D(B, C)` where `B(A)` and `C(A)`, what is `D.__mro__`?

- a) D, B, A, C, A, object
- b) D, B, C, A, object
- c) D, C, B, A, object
- d) D, A, B, C, object

<details><summary>answer</summary>

**b** — C3 keeps A after *both* of its children, and preserves the declared order B before C. Each class appears exactly once.
</details>

## `super()` walks the MRO — it does not mean "my parent"

`super()` returns a proxy that starts searching **after the current
class in the MRO of `type(self)`**. Which class that is depends on the
*instance*, not on where the code was written. This is what makes
cooperative multiple inheritance possible.

```python
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
```
`Left.go` was written knowing nothing about `Right`, yet in a
`Both` instance its `super()` call lands on `Right.go`. Every
class in the chain runs exactly once. That is *cooperative*
inheritance — and it only works if every class calls `super()`.

```python
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
```
Each mixin plucks the keywords it understands and forwards the
rest. Break the chain — forget one `super().__init__(**kwargs)` —
and the classes after it in the MRO silently never initialise.

```python
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
```
The no-argument `super()` is shorthand: the compiler quietly
supplies the class the method was defined in and the instance.
Spelling it out as `super(B, self)` means "begin the search
**after** `B` in the MRO", which is how `C` reaches straight past
`B` to `A`.

The explicit form is required wherever the compiler cannot help —
outside a method body, as in the middle example. And note what is
being walked: the MRO of `type(self)`, not some lexical notion of
"my parent". `super(B, self)` on a `C` instance is still
traversing `C`'s MRO; it has merely been told where to start.

**Quiz.** `super()` inside a method of class `X` looks up the attribute where?

- a) In `X.__bases__[0]` — the first parent
- b) In the MRO of `type(self)`, starting after `X`
- c) In `object`, always
- d) In the class where the method was originally defined

<details><summary>answer</summary>

**b** — It is instance-dependent. The same `super()` call in `X` can reach entirely different classes depending on what the instance's class inherits from.
</details>

## Mixins

A mixin is a class designed to be *combined*, never instantiated
alone. Conventions that keep them workable:

- give them no `__init__`, or a cooperative `**kwargs` one
- depend only on a documented interface (`self.items`, `self.name`)
- list them **before** the base class: `class C(MixinA, MixinB, Base)`
- keep them small and orthogonal

```python
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
```
Both mixins are written against a `_fields` tuple that neither of
them defines — the concrete class supplies it. That is the mixin
contract in miniature: general behaviour parameterised by one
small hook, so `Point` gets a repr, ordering, equality and
hashing for two lines of declaration.

Two details in `ComparableMixin` are worth stealing. It defines
`__hash__` alongside `__eq__`, because defining `__eq__` alone
sets `__hash__` to `None` and quietly makes instances unhashable.
And it returns `NotImplemented` for a foreign type rather than
`False`, which lets Python try the other operand's reflected
comparison before concluding anything.

## `__slots__`: trading flexibility for memory

Declaring `__slots__` replaces the per-instance `__dict__` with a
fixed array of descriptors. You get lower memory and slightly faster
attribute access; you lose dynamic attributes, `__dict__`, and
(usually) `cached_property` and multiple inheritance from two slotted
classes.

```python
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
```
The saving matters at scale — a million small objects is where
this becomes real. A subclass without its own `__slots__` silently
regains a `__dict__`, undoing the benefit.

```python
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
```
Three rules, each of which quietly undoes `__slots__` when broken.

A subclass declares only its **new** slots; repeating a parent's
name allocates a second descriptor that shadows the first and
wastes the space you were trying to save.

If any class in the chain omits `__slots__` — as `C` does —
instances get a `__dict__` back and the memory benefit is gone.
This is far and away the most common way slots stop working: one
unslotted class anywhere in the hierarchy is enough.

And two bases with non-empty slots cannot be combined at all,
because their instance layouts conflict. Multiple inheritance
works only when at most one base actually declares slots.

## Exercise — Trace and validate an MRO `[medium]`

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
```python
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
```

## Exercise — A cooperative observable mixin `[brutal]`

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
```python
class Observable:
    _observed = ()

    def __init__(self, **kwargs):
        ...
```

## Takeaways

- Lookup order: data descriptors → instance dict → class MRO →
  `__getattr__`.
- `__mro__` is computed by C3 and is the single source of truth for
  both attribute lookup and `super()`.
- `super()` means "next in the MRO of `type(self)`" — cooperative,
  not parental.
- Mixins go before the base class and must forward `**kwargs`.
- `__slots__` saves real memory but is easy to lose in a subclass.
