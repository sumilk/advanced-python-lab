"""Lesson 17 — Memory management, reference counting, and the GC."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=17,
    slug="memory",
    title="Memory, Reference Counting, and the GC",
    summary="""
    CPython frees most objects the instant their last reference goes away —
    and runs a separate cycle collector for the rest. Understanding both
    explains deterministic cleanup, why `__del__` is unreliable, where leaks
    come from in a language with a garbage collector, and what `weakref`
    is for.
    """,
    tags=("memory", "gc", "weakref", "refcounting"),
    blocks=[
        Text("""
        ## Reference counting

        Every object carries a count of references to it. When the count hits
        zero, the object is freed **immediately** — no GC pause, no delay.
        That determinism is why `with open(...)` reliably closes the file even
        without the `with`… in CPython. It is not guaranteed by the language,
        and PyPy does not do it.

        `sys.getrefcount(x)` reports one extra, for the argument itself.
        """),
        Demo(
            code="""
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
            """,
        ),
        Text("""
        ## Cycles need the collector

        Reference counting cannot free a cycle: each object in the loop holds
        the next one's count above zero. The generational garbage collector
        exists solely to find and break these.

        Three generations: new objects start in gen 0, survivors are promoted.
        Gen 0 is collected often and cheaply, gen 2 rarely.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            Not everything is tracked: atomic types like `int` and `str` can
            never take part in a cycle, so the GC ignores them entirely.
            `gc.is_tracked(x)` tells you.
            """,
        ),
        Demo(
            code="""
            import gc

            print("is_tracked(int)  :", gc.is_tracked(1))
            print("is_tracked(str)  :", gc.is_tracked("hello"))
            print("is_tracked(list) :", gc.is_tracked([]))
            print("is_tracked(tuple of ints):", gc.is_tracked((1, 2)))
            print("   ^ CPython untracks tuples proven to hold only atomics")

            # gc.get_referrers / get_referents walk the object graph.
            target = ["find me"]
            holder = {"key": target}
            referrers = [type(r).__name__ for r in gc.get_referrers(target)]
            print("who points at target:", referrers)
            print("what target points at:", gc.get_referents(target))
            """,
        ),
        Text("""
        ## `__del__` is not a destructor

        Problems with `__del__`:

        - it runs at an unpredictable time (or never, at interpreter exit)
        - exceptions inside it are printed and swallowed
        - it can *resurrect* the object by storing `self` somewhere
        - before 3.4 it prevented cycle collection entirely; today it works,
          but the ordering is still undefined

        Use a context manager or `weakref.finalize` for cleanup that matters.
        """),
        Demo(
            code="""
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
            """,
            explain="""
            `weakref.finalize` holds no strong reference to the object, is
            guaranteed to run at most once, runs at interpreter exit by
            default, and can be invoked early. It is strictly better than
            `__del__` for every use case.
            """,
        ),
        Question(
            prompt="Why can reference counting not free a reference cycle?",
            choices=[
                "Cycles are stored in a special region of memory",
                "Each object in the cycle is referenced by another, so no count reaches zero",
                "Reference counts are only approximate",
                "It can, but only after `gc.collect()`",
            ],
            answer=1,
            explain="Exactly — which is why CPython pairs refcounting with a "
                    "generational cycle collector.",
        ),
        Text("""
        ## `weakref`: referring without owning

        A weak reference does not keep its target alive. Uses: caches,
        observer registries, parent pointers in trees, and anywhere a strong
        reference would create a cycle or a leak.

        - `weakref.ref(obj)` — call it to get the object or `None`
        - `WeakValueDictionary` — entries vanish when the value dies
        - `WeakKeyDictionary` — attach data to objects you do not own
        - `WeakSet` — a registry that does not leak
        - `proxy` — behaves like the object, raises `ReferenceError` when dead
        """),
        Demo(
            code="""
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
            weakref.ref(temp, on_death)
            del temp
            """,
        ),
        Demo(
            code="""
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
            """,
        ),
        Text("""
        ## Measuring memory

        - `sys.getsizeof(x)` — the object's own size, **not** what it
          references. A list of a million ints reports ~8 MB, ignoring the
          ints.
        - `tracemalloc` — allocation tracking with tracebacks. The right tool
          for real leak hunting.
        - `gc.get_objects()` — everything the collector tracks, useful for
          counting instances by type.
        """),
        Demo(
            code="""
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
            """,
        ),
        Predict(
            code="""
            import sys

            a = [1, 2, 3]
            b = [a, a, a]
            print(sys.getsizeof(b) == sys.getsizeof([a, a, a]))
            print(sys.getsizeof(b) < sys.getsizeof(a) * 3)
            """,
            answer="""
            True
            True
            """,
            explain="""
            `b` holds three *pointers* to one list, so its own size is three
            pointers plus overhead — far less than three copies. `getsizeof`
            never follows references, which is exactly why it under-reports
            containers.
            """,
        ),
        Text("""
        ## Interning and small-object caches

        CPython pre-allocates `int` objects in `[-5, 256]` and interns
        identifier-like string literals at compile time. `sys.intern()` lets
        you opt in explicitly: worthwhile when you hold millions of repeated
        strings, since it collapses them to one object and makes `==` an
        O(1) pointer comparison in the common case.
        """),
        Demo(
            code="""
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
            """,
        ),
        Question(
            prompt="What does `sys.getsizeof([obj1, obj2, obj3])` measure?",
            choices=[
                "The list plus everything it contains, recursively",
                "Only the list object itself: its header plus three pointers",
                "The largest contained object",
                "Nothing meaningful — it always returns 64",
            ],
            answer=1,
            explain="It never follows references. Summing the container plus each "
                    "element (recursively, tracking ids) is the only honest way — or "
                    "just use `tracemalloc`.",
        ),
        Exercise(
            slug="object-tracker",
            title="A leak-detecting instance tracker",
            difficulty="tricky",
            brief="""
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
            """,
            starter="""
            import gc
            import weakref


            def track(cls):
                ...


            def find_leaks(cls, factory, n):
                ...
            """,
            checks=[
                Check("counts live instances", lambda ns: _ot_live(ns)),
                Check("drops the count on delete, without gc", lambda ns: _ot_drop(ns)),
                Check("total_created keeps counting", lambda ns: _ot_total(ns)),
                Check("live_instances returns the objects", lambda ns: _ot_instances(ns)),
                Check("the tracker holds no strong references", lambda ns: _ot_weak(ns)),
                Check("works with __slots__", lambda ns: _ot_slots(ns)),
                Check("reset_stats clears the total only", lambda ns: _ot_reset(ns)),
                Check("find_leaks detects a reference cycle", lambda ns: _ot_leaks(ns)),
            ],
            hints=(
                "`weakref.WeakSet` does the whole job: adding is cheap and entries "
                "disappear the moment an object is collected.",
                "Wrap `__init__` rather than `__new__` — but remember the wrapper "
                "must call the original and accept any signature.",
                "A class with `__slots__` cannot be weak-referenced unless it also "
                "declares `__weakref__`; add it by rebuilding the slots tuple.",
                "`find_leaks` should disable the GC around the loop so that only "
                "refcounting can free the objects — that is what makes a cycle "
                "visible.",
            ),
            solution="""
            import functools
            import gc
            import weakref

            def track(cls):
                if "__slots__" in cls.__dict__ and "__weakref__" not in cls.__dict__.get(
                    "__slots__", ()
                ):
                    slots = tuple(cls.__dict__["__slots__"])
                    if not any(hasattr(base, "__weakref__") for base in cls.__mro__[1:]):
                        namespace = {
                            k: v for k, v in vars(cls).items()
                            if k not in {"__dict__", "__weakref__", "__slots__"}
                            and k not in slots
                        }
                        namespace["__slots__"] = slots + ("__weakref__",)
                        cls = type(cls)(cls.__name__, cls.__bases__, namespace)

                alive = weakref.WeakSet()
                stats = {"total": 0}
                original_init = cls.__init__

                @functools.wraps(original_init)
                def __init__(self, *args, **kwargs):
                    original_init(self, *args, **kwargs)
                    alive.add(self)
                    stats["total"] += 1

                cls.__init__ = __init__
                cls.live_count = classmethod(lambda c: len(alive))
                cls.total_created = classmethod(lambda c: stats["total"])
                cls.live_instances = classmethod(lambda c: list(alive))
                cls.reset_stats = classmethod(lambda c: stats.update(total=0))
                return cls

            def find_leaks(cls, factory, n):
                gc.collect()
                before = cls.live_count()
                gc.disable()
                try:
                    for _ in range(n):
                        obj = factory()
                        del obj
                    survivors = cls.live_count() - before
                finally:
                    gc.enable()
                    gc.collect()
                return survivors
            """,
        ),
        Text("""
        ## Takeaways

        - Refcounting frees most objects instantly; the GC exists for cycles.
        - `__del__` is unpredictable — use context managers or
          `weakref.finalize`.
        - `weakref` breaks ownership cycles: parent pointers, caches,
          registries.
        - `sys.getsizeof` is shallow; `tracemalloc` is the real tool.
        - `sys.intern` collapses duplicate strings when you have millions of
          them.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _make(ns, slots=False):
    track = ns["track"]
    if slots:
        @track
        class Thing:
            __slots__ = ("v",)

            def __init__(self, v=0):
                self.v = v
    else:
        @track
        class Thing:
            def __init__(self, v=0):
                self.v = v
    return Thing


def _ot_live(ns) -> None:
    Thing = _make(ns)
    assert Thing.live_count() == 0, Thing.live_count()
    a, b = Thing(1), Thing(2)
    assert Thing.live_count() == 2, Thing.live_count()
    assert a.v == 1 and b.v == 2, "the original __init__ must still run"


def _ot_drop(ns) -> None:
    Thing = _make(ns)
    a = Thing()
    assert Thing.live_count() == 1
    del a
    assert Thing.live_count() == 0, (
        "refcounting alone should have dropped the count — the tracker is "
        "holding a strong reference"
    )


def _ot_total(ns) -> None:
    Thing = _make(ns)
    for _ in range(3):
        Thing()
    assert Thing.total_created() == 3, Thing.total_created()
    assert Thing.live_count() == 0, "the temporaries should all be gone"


def _ot_instances(ns) -> None:
    Thing = _make(ns)
    a = Thing(7)
    listed = Thing.live_instances()
    assert len(listed) == 1 and listed[0] is a, listed
    del listed
    del a
    assert Thing.live_instances() == []


def _ot_weak(ns) -> None:
    import sys

    Thing = _make(ns)
    a = Thing()
    # 1 for `a`, 1 for the getrefcount argument. A strong reference in the
    # tracker would push this higher.
    count = sys.getrefcount(a) - 1
    assert count == 1, f"expected a single strong reference, found {count}"


def _ot_slots(ns) -> None:
    Thing = _make(ns, slots=True)
    a = Thing(3)
    assert a.v == 3
    assert Thing.live_count() == 1
    try:
        a.other = 1
    except AttributeError:
        pass
    else:
        raise AssertionError("__slots__ must still be enforced")
    del a
    assert Thing.live_count() == 0


def _ot_reset(ns) -> None:
    Thing = _make(ns)
    keep = Thing()
    Thing()
    assert Thing.total_created() == 2
    Thing.reset_stats()
    assert Thing.total_created() == 0, Thing.total_created()
    assert Thing.live_count() == 1, "reset_stats must not forget live instances"
    del keep


def _ot_leaks(ns) -> None:
    track, find_leaks = ns["track"], ns["find_leaks"]

    @track
    class Clean:
        def __init__(self):
            self.data = [1, 2, 3]

    @track
    class Cyclic:
        def __init__(self):
            self.self_ref = self          # a cycle: refcount never reaches 0

    assert find_leaks(Clean, Clean, 10) == 0, "a clean class should leak nothing"
    leaked = find_leaks(Cyclic, Cyclic, 10)
    assert leaked == 10, f"expected all 10 cyclic instances to survive, got {leaked}"
