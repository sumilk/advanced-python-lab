# 17 — Memory, Reference Counting, and the GC

CPython frees most objects the instant their last reference goes away —
and runs a separate cycle collector for the rest. Understanding both
explains deterministic cleanup, why `__del__` is unreliable, where leaks
come from in a language with a garbage collector, and what `weakref`
is for.

## Reference counting

Every object carries a count of references to it. When the count hits
zero, the object is freed **immediately** — no GC pause, no delay.
That determinism is why `with open(...)` reliably closes the file even
without the `with`… in CPython. It is not guaranteed by the language,
and PyPy does not do it.

`sys.getrefcount(x)` reports one extra, for the argument itself.

```python
import sys

obj = object()
print("after creation :", sys.getrefcount(obj) - 1)

alias = obj
print("after aliasing :", sys.getrefcount(obj) - 1)

container = [obj, obj]
print("in a list twice:", sys.getrefcount(obj) - 1)

del alias, container
print("after cleanup  :", sys.getrefcount(obj) - 1)

# Freeing is immediate and observable.
class Noisy:
    def __init__(self, name): self.name = name
    def __del__(self): print(f"  freeing {self.name}")

n = Noisy("first")
print("rebinding the only reference:")
n = Noisy("second")
print("deleting:")
del n
print("done")
```
`getrefcount` reports one more than you would expect, because
passing the object to it creates a reference — hence the `- 1`
throughout. Storing it in a list twice counts twice: the
container holds a reference per slot, not per object.

The `Noisy` output shows the other half. CPython frees an object
**the instant** its count reaches zero, so "freeing first" appears
at the rebinding line, before the next statement runs. That
promptness is why files and sockets so often close on time here
without anyone thinking about it.

It is also an implementation detail, not a language guarantee.
PyPy and friends collect whenever they please, so code that relies
on this timing breaks on another interpreter — which is what `with`
is for.

## Cycles need the collector

Reference counting cannot free a cycle: each object in the loop holds
the next one's count above zero. The generational garbage collector
exists solely to find and break these.

Three generations: new objects start in gen 0, survivors are promoted.
Gen 0 is collected often and cheaply, gen 2 rarely.

```python
import gc

class Node:
    def __init__(self, name): self.name, self.ref = name, None

gc.collect()
gc.disable()

a, b = Node("a"), Node("b")
a.ref, b.ref = b, a          # a -> b -> a
del a, b                     # refcounts stay at 1 each

unreachable = gc.collect()
print("cycle objects collected:", unreachable)
print("thresholds (gen0, gen1, gen2):", gc.get_threshold())
print("counts since last collection:", gc.get_count())
print("tracked object types (sample):",
      sorted({type(o).__name__ for o in gc.get_objects()[:2000]})[:8])
gc.enable()
```
Not everything is tracked: atomic types like `int` and `str` can
never take part in a cycle, so the GC ignores them entirely.
`gc.is_tracked(x)` tells you.

```python
import gc

print("is_tracked(int)  :", gc.is_tracked(1))
print("is_tracked(str)  :", gc.is_tracked("hello"))
print("is_tracked(list) :", gc.is_tracked([]))
atoms = (1, 2)
print("is_tracked(tuple of ints):", gc.is_tracked(atoms), "at creation")
gc.collect()
print("   ...after a collection :", gc.is_tracked(atoms))
print("   ^ CPython untracks tuples proven to hold only atomics")

# gc.get_referrers / get_referents walk the object graph.
target = ["find me"]
holder = {"key": target}
referrers = [type(r).__name__ for r in gc.get_referrers(target)]
print("who points at target:", referrers)
print("what target points at:", gc.get_referents(target))
```
The cycle collector only has to examine objects that could *be* in
a cycle, so anything incapable of referencing another object —
ints, strings — is never tracked at all. That exclusion is a large
part of why collection is as cheap as it is.

The tuple line shows the refinement: a tuple holding only atomics
can also be untracked, but the runtime has to *prove* it first, so
it is tracked at creation and dropped from tracking on a later
pass. Hence `True` and then `False` from the same object.

`get_referrers` and `get_referents` walk the graph in either
direction. The first is the one you want when an object refuses to
die and you need to know what is still pointing at it.

## `__del__` is not a destructor

Problems with `__del__`:

- it runs at an unpredictable time (or never, at interpreter exit)
- exceptions inside it are printed and swallowed
- it can *resurrect* the object by storing `self` somewhere
- before 3.4 it prevented cycle collection entirely; today it works,
  but the ordering is still undefined

Use a context manager or `weakref.finalize` for cleanup that matters.

```python
import weakref

class Resource:
    def __init__(self, name):
        self.name = name
    def __del__(self):
        raise RuntimeError("this exception goes nowhere useful")

r = Resource("doomed")
del r                          # the exception is printed, not raised
print("execution continues regardless")
print()

# weakref.finalize: explicit, ordered, and callable early.
class Better:
    def __init__(self, name):
        self.name = name
        self._finalizer = weakref.finalize(self, self._cleanup, name)
    @staticmethod
    def _cleanup(name):
        print(f"  cleaning up {name}")
    def close(self):
        self._finalizer()      # run now, exactly once

b = Better("explicit")
b.close()
b.close()                      # idempotent
print("alive:", b._finalizer.alive)

c = Better("automatic")
del c
```
`weakref.finalize` holds no strong reference to the object, is
guaranteed to run at most once, runs at interpreter exit by
default, and can be invoked early. It is strictly better than
`__del__` for every use case.

**Quiz.** Why can reference counting not free a reference cycle?

- a) Cycles are stored in a special region of memory
- b) Each object in the cycle is referenced by another, so no count reaches zero
- c) Reference counts are only approximate
- d) It can, but only after `gc.collect()`

<details><summary>answer</summary>

**b** — Exactly — which is why CPython pairs refcounting with a generational cycle collector.
</details>

## `weakref`: referring without owning

A weak reference does not keep its target alive. Uses: caches,
observer registries, parent pointers in trees, and anywhere a strong
reference would create a cycle or a leak.

- `weakref.ref(obj)` — call it to get the object or `None`
- `WeakValueDictionary` — entries vanish when the value dies
- `WeakKeyDictionary` — attach data to objects you do not own
- `WeakSet` — a registry that does not leak
- `proxy` — behaves like the object, raises `ReferenceError` when dead

```python
import weakref

class Data:
    def __init__(self, v): self.v = v
    def __repr__(self): return f"Data({self.v})"

d = Data(1)
ref = weakref.ref(d)
print("alive:", ref(), "| callable:", ref() is d)
del d
print("dead :", ref())

# A cache that does not keep its entries alive.
cache = weakref.WeakValueDictionary()
item = Data(2)
cache["key"] = item
print("cached:", dict(cache))
del item
print("after the last strong ref goes:", dict(cache))

# Callbacks fire when the target dies.
def on_death(reference):
    print("  callback: the object is gone")
temp = Data(3)
watcher = weakref.ref(temp, on_death)   # must be kept alive!
del temp
```
A weak reference is called like a function and returns the object,
or `None` once it is gone — so `ref()` is both the accessor and
the liveness test in one. A `WeakValueDictionary` applies that per
entry: the cache holds nothing alive, and entries vanish on their
own when the last real owner lets go. That is the correct shape
for a cache, which should never be the reason an object survives.

The `watcher =` binding is not incidental. A weakref is itself an
object, and an unstored one is collected immediately — at which
point its callback can never fire, silently. If you want the
notification, keep the reference.

```python
import weakref

# The classic leak: a parent<->child cycle.
class StrongNode:
    def __init__(self, name):
        self.name, self.children, self.parent = name, [], None
    def add(self, child):
        child.parent = self          # strong both ways -> cycle
        self.children.append(child)

class WeakNode:
    def __init__(self, name):
        self.name, self.children, self._parent = name, [], None
    def add(self, child):
        child._parent = weakref.ref(self)
        self.children.append(child)
    @property
    def parent(self):
        return self._parent() if self._parent else None

import gc
gc.collect()
gc.disable()

for cls in (StrongNode, WeakNode):
    before = len(gc.get_objects())
    root = cls("root")
    for i in range(50):
        root.add(cls(f"child{i}"))
    del root
    leaked = len([o for o in gc.get_objects() if isinstance(o, cls)])
    print(f"{cls.__name__:11}: {leaked:3} objects still alive after del")
gc.collect()
gc.enable()
print("(the strong version needs the cycle collector; the weak one does not)")
```
With the collector switched off, the difference is stark: 51
objects stranded against none. Parent and child each hold a strong
reference to the other, so neither count ever reaches zero and
refcounting alone can never free them. They are not lost — the
cycle collector will take them — but they linger until it runs.

Making the upward link weak breaks the cycle, and the whole tree
dies the moment the root does. The `parent` property hides the
difference, so callers still write `node.parent` and get an
object or `None`.

That is the rule for any bidirectional structure — trees with
parent pointers, observers holding their subject, caches keyed on
live objects: **the back-reference should be weak**. Ownership
points one way.

## Measuring memory

- `sys.getsizeof(x)` — the object's own size, **not** what it
  references. A list of a million ints reports ~8 MB, ignoring the
  ints.
- `tracemalloc` — allocation tracking with tracebacks. The right tool
  for real leak hunting.
- `gc.get_objects()` — everything the collector tracks, useful for
  counting instances by type.

```python
import sys
import tracemalloc

small = [1, 2, 3]
nested = [[0] * 1000 for _ in range(10)]
print("shallow size of nested:", sys.getsizeof(nested), "bytes")
print("real size:", sys.getsizeof(nested)
      + sum(sys.getsizeof(row) for row in nested), "bytes")

tracemalloc.start()
snapshot_before = tracemalloc.take_snapshot()
hog = [dict(index=i, payload="x" * 50) for i in range(2000)]
snapshot_after = tracemalloc.take_snapshot()

top = snapshot_after.compare_to(snapshot_before, "lineno")[0]
print()
print("largest allocation since the first snapshot:")
print(f"  {top.size_diff/1024:.1f} KiB in {top.count_diff} blocks")
current, peak = tracemalloc.get_traced_memory()
print(f"  current {current/1024:.0f} KiB, peak {peak/1024:.0f} KiB")
tracemalloc.stop()
del hog
```
The first two lines are the trap: `getsizeof` reports the list's
own bookkeeping and nothing about the ten rows it points at, so
184 bytes is off by a factor of four hundred. Summing one level
deeper gets closer, and for anything genuinely nested you would
need to recurse — and remember shared objects, which naive
recursion counts twice.

`tracemalloc` is the tool that answers the real question. Take a
snapshot, do the work, take another, and `compare_to` ranks the
growth **by the line of code responsible**. That is what turns "we
are using too much memory" into a file and a line number.

`peak` matters as much as `current`: a transient list that is
built and discarded never shows up in a final measurement, but it
is exactly what triggers the out-of-memory kill.


## Interning and small-object caches

CPython pre-allocates `int` objects in `[-5, 256]` and interns
identifier-like string literals at compile time. `sys.intern()` lets
you opt in explicitly: worthwhile when you hold millions of repeated
strings, since it collapses them to one object and makes `==` an
O(1) pointer comparison in the common case.

```python
import sys

# A realistic win: repeated keys parsed from data.
raw_keys = [f"field_{i % 20}" for i in range(50_000)]
distinct_plain = len({id(k) for k in raw_keys})
interned = [sys.intern(k) for k in raw_keys]
distinct_interned = len({id(k) for k in interned})

print("distinct string objects, plain   :", distinct_plain)
print("distinct string objects, interned:", distinct_interned)
saved = (distinct_plain - distinct_interned) * sys.getsizeof(raw_keys[0])
print(f"approximate saving: {saved/1024:.0f} KiB")

print()
a, b = 100, 100
big1, big2 = 10 ** 6, 10 ** 6
print("small ints are shared:", a is b, "| large ones are not:", big1 is big2)
print("empty containers are never shared:", [] is [], {} is {})
```
Fifty thousand equal strings, fifty thousand distinct objects —
until `intern` collapses them to twenty. This is the one case
where interning is worth doing deliberately: keys parsed out of
JSON or CSV, where the same handful of field names is rebuilt for
every record. The strings compare equal either way; you are paying
for storage you do not need.

It also speeds up comparison, since interned strings can settle
equality by identity before falling back to comparing characters.

The bottom lines are the reminder from lesson 01: small integers
and literal strings are shared by the runtime, larger ones are
not, and containers never are. Convenient to know, never something
to write code against.

**Quiz.** What does `sys.getsizeof([obj1, obj2, obj3])` measure?

- a) The list plus everything it contains, recursively
- b) Only the list object itself: its header plus three pointers
- c) The largest contained object
- d) Nothing meaningful — it always returns 64

<details><summary>answer</summary>

**b** — It never follows references. Summing the container plus each element (recursively, tracking ids) is the only honest way — or just use `tracemalloc`.
</details>

## Exercise — A leak-detecting instance tracker `[tricky]`

Write `track(cls)` — a class decorator that counts live instances
**without keeping any of them alive**.

- `cls.live_count()` → how many instances are currently alive
- `cls.total_created()` → how many have ever been made
- `cls.live_instances()` → a list of the live objects
- deleting an instance must drop `live_count` with no `gc.collect()`
  needed (refcounting alone)
- tracking must not interfere with `__init__`, inheritance, or the
  class's own attributes
- `cls.reset_stats()` zeroes the total but leaves live objects
  tracked
- it must work on classes that define `__slots__`

Then write `find_leaks(cls, factory, n)` which creates and drops
`n` instances via `factory()` and returns how many survived — a
direct cycle-leak detector.
```python
import gc
import weakref


def track(cls):
    ...


def find_leaks(cls, factory, n):
    ...
```

## Takeaways

- Refcounting frees most objects instantly; the GC exists for cycles.
- `__del__` is unpredictable — use context managers or
  `weakref.finalize`.
- `weakref` breaks ownership cycles: parent pointers, caches,
  registries.
- `sys.getsizeof` is shallow; `tracemalloc` is the real tool.
- `sys.intern` collapses duplicate strings when you have millions of
  them.
