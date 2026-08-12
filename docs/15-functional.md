# 15 — The Functional Toolbox

`itertools`, `functools` and `operator` are three small modules that
together eliminate an astonishing amount of hand-written loop code — and
run in C while doing it. This lesson is a working tour: what each tool
does, when it beats the obvious loop, and the traps (shared iterators,
grouping without sorting, `reduce` readability).

## `itertools`, by category

**Infinite:** `count(start, step)`, `cycle(iterable)`, `repeat(x, n)`

**Terminating:** `accumulate`, `chain`, `compress`, `dropwhile`,
`takewhile`, `filterfalse`, `groupby`, `islice`, `pairwise`,
`starmap`, `tee`, `zip_longest`, `batched` (3.12)

**Combinatoric:** `product`, `permutations`, `combinations`,
`combinations_with_replacement`

Every one of them is lazy, and they compose into pipelines that never
materialise an intermediate list.

```python
import itertools as it

print("count      :", list(it.islice(it.count(10, 5), 4)))
print("cycle      :", list(it.islice(it.cycle("abc"), 7)))
print("repeat     :", list(it.repeat("x", 3)))
print("accumulate :", list(it.accumulate([1, 2, 3, 4])))
print("running max:", list(it.accumulate([3, 1, 4, 1, 5], max)))
print("chain      :", list(it.chain([1, 2], "ab", (3,))))
print("from_iter  :", list(it.chain.from_iterable([[1, 2], [3, 4]])))
print("compress   :", list(it.compress("abcdef", [1, 0, 1, 0, 1, 1])))
print("takewhile  :", list(it.takewhile(lambda n: n < 3, [1, 2, 3, 1])))
print("dropwhile  :", list(it.dropwhile(lambda n: n < 3, [1, 2, 3, 1])))
print("pairwise   :", list(it.pairwise([1, 2, 3, 4])))
print("starmap    :", list(it.starmap(pow, [(2, 3), (3, 2)])))
print("zip_longest:", list(it.zip_longest("ab", "xyz", fillvalue="-")))
print("batched    :", list(it.batched("abcdefg", 3)))
```

```python
import itertools as it

print("product         :", list(it.product("ab", [1, 2])))
print("product repeat  :", list(it.product([0, 1], repeat=3))[:4], "...")
print("permutations    :", list(it.permutations("abc", 2)))
print("combinations    :", list(it.combinations("abcd", 2)))
print("with replacement:", list(it.combinations_with_replacement("ab", 2)))

# product is the flat way to write nested loops:
grid = [(r, c) for r, c in it.product(range(2), range(3))]
print("nested loops    :", grid)
```

## `groupby` groups *consecutive* runs

This is the single most misunderstood function in the module. It does
not build a mapping — it yields `(key, group)` pairs as the key
changes. **Sort by the same key first**, or you get fragments.

The group is also a lazy iterator sharing the underlying source: once
you advance to the next group, the previous one is spent.

```python
from itertools import groupby
from operator import itemgetter

rows = [
    {"dept": "eng", "name": "ada"},
    {"dept": "ops", "name": "bob"},
    {"dept": "eng", "name": "cy"},
]

print("unsorted:")
for key, group in groupby(rows, key=itemgetter("dept")):
    print("  ", key, [r["name"] for r in group])

print("sorted first:")
rows.sort(key=itemgetter("dept"))
for key, group in groupby(rows, key=itemgetter("dept")):
    print("  ", key, [r["name"] for r in group])

# The sharing trap:
groups = list(groupby("aabbb"))
print("materialised too late:", [(k, list(g)) for k, g in groups])
print("...every group is empty because the source moved on")
```
If you want a real mapping, `collections.defaultdict(list)` in a
plain loop is clearer, needs no sort, and is O(n) rather than
O(n log n). Use `groupby` for run-length work and for streaming
over already-sorted data.

**Quiz.** `groupby` on unsorted data gives you what?

- a) A correct grouping, order-independent
- b) One group per *run* of consecutive equal keys, so keys can repeat
- c) An error
- d) Groups sorted by key automatically

<details><summary>answer</summary>

**b** — It is a streaming run-detector. Sort by the same key first, or use a `defaultdict(list)`.
</details>

## `functools`

| tool | purpose |
|---|---|
| `reduce(fn, it, init)` | fold a sequence into one value |
| `partial` / `partialmethod` | pre-bind arguments |
| `cache` / `lru_cache` | memoisation |
| `cached_property` | per-instance lazy attribute |
| `singledispatch(method)` | type-based overloading |
| `wraps` / `update_wrapper` | metadata for decorators |
| `total_ordering` | derive all comparisons |
| `cmp_to_key` | adapt an old-style comparison function |

```python
from functools import cmp_to_key, partial, reduce
import operator

print("sum via reduce  :", reduce(operator.add, [1, 2, 3, 4]))
print("product         :", reduce(operator.mul, [1, 2, 3, 4]))
print("with initial    :", reduce(operator.add, [], 0))
print("flatten         :", reduce(operator.iconcat, [[1, 2], [3]], []))
print("max via reduce  :", reduce(lambda a, b: a if a > b else b, [3, 9, 2]))

# ...but prefer the built-in when one exists:
print("built-ins win   :", sum([1, 2, 3, 4]), max([3, 9, 2]))

# cmp_to_key: sorting by a rule that is not a simple key.
def compare(a, b):
    if len(a) != len(b):
        return len(a) - len(b)
    return (a > b) - (a < b)

words = ["pear", "fig", "apple", "kiwi"]
print("cmp_to_key      :", sorted(words, key=cmp_to_key(compare)))

# partial for configuration
to_binary = partial(int, base=2)
print("partial         :", to_binary("1011"))
```
`reduce` is powerful and often unreadable. Reach for it only when
no built-in fits and the operation is genuinely a fold — and
always give it an explicit initial value so an empty input does
not raise.

```python
from functools import singledispatch, singledispatchmethod

@singledispatch
def to_json(value):
    raise TypeError(f"cannot serialise {type(value).__name__}")

@to_json.register
def _(value: int | float | bool):   # union registration works
    return str(value).lower()

@to_json.register
def _(value: str):
    return f'"{value}"'

@to_json.register
def _(value: list):
    return "[" + ",".join(to_json(v) for v in value) + "]"

@to_json.register
def _(value: dict):
    return "{" + ",".join(f'"{k}":{to_json(v)}' for k, v in value.items()) + "}"

print(to_json({"a": [1, "two", True], "b": 3.5}))

# Dispatch follows the MRO -- register an ABC to catch a family.
from collections.abc import Sequence

@singledispatch
def size(obj): return "unknown"
@size.register
def _(obj: Sequence): return f"sequence of {len(obj)}"

print(size((1, 2, 3)), "|", size([1]), "|", size(5))
```

## `operator`: functions for the syntax

Every operator has a function form, implemented in C. They are faster
than an equivalent `lambda` and, more importantly, they say what they
mean.

- `itemgetter(k)`, `itemgetter(0, 2)` (returns a tuple)
- `attrgetter("a.b")` — follows dots
- `methodcaller("strip", "x")` — calls a method with arguments
- `add`, `mul`, `lt`, `eq`, `contains`, `not_`, `truth`, `getitem`

```python
import timeit
from operator import attrgetter, itemgetter, methodcaller

pairs = [(3, "c"), (1, "a"), (2, "b")]
print("itemgetter :", sorted(pairs, key=itemgetter(0)))
print("multi      :", itemgetter(0, 1)(pairs[0]))

class Node:
    def __init__(self, name, depth): self.name, self.depth = name, depth
    class Meta: version = 2
    meta = Meta()

nodes = [Node("b", 2), Node("a", 1)]
print("attrgetter :", [n.name for n in sorted(nodes, key=attrgetter("depth"))])
print("dotted     :", attrgetter("meta.version")(nodes[0]))
print("methodcall :", list(map(methodcaller("upper"), ["a", "b"])))

data = [(i, str(i)) for i in range(2000)]
t_lambda = timeit.timeit(lambda: sorted(data, key=lambda p: p[0]), number=100)
t_getter = timeit.timeit(lambda: sorted(data, key=itemgetter(0)), number=100)
print(f"lambda {t_lambda*1000:.1f} ms vs itemgetter {t_getter*1000:.1f} ms"
      f"  ({t_lambda/t_getter:.2f}x)")
```


## Recipes worth memorising

The `itertools` docs ship a "recipes" section; these four come up
constantly.

```python
import itertools as it
from collections import deque

def take(n, iterable):
    return list(it.islice(iterable, n))

def unique_everseen(iterable, key=None):
    seen = set()
    for item in iterable:
        k = item if key is None else key(item)
        if k not in seen:
            seen.add(k)
            yield item

def sliding_window(iterable, n):
    window = deque(it.islice(iterable, n - 1), maxlen=n)
    for item in iterable:
        window.append(item)
        yield tuple(window)

def partition(predicate, iterable):
    t1, t2 = it.tee(iterable)
    return it.filterfalse(predicate, t1), filter(predicate, t2)

print("take          :", take(3, it.count()))
print("unique_everseen:", list(unique_everseen("AAAABBBCCDAABBB")))
print("by key         :", list(unique_everseen(["a", "A", "b"], key=str.lower)))
print("sliding_window :", list(sliding_window(range(5), 3)))
odd, even = partition(lambda n: n % 2 == 0, range(6))
print("partition      :", list(odd), list(even))
```

**Quiz.** Which is the right tool for `[[1,2],[3,4]]` → `[1,2,3,4]`?

- a) `itertools.product`
- b) `itertools.chain.from_iterable`
- c) `functools.reduce(operator.add, ...)`
- d) `itertools.zip_longest`

<details><summary>answer</summary>

**b** — `chain.from_iterable` is lazy and O(n). The `reduce` version is O(n²) because it builds a new list on every step.
</details>

## Exercise — Four streaming utilities `[tricky]`

Implement four lazy utilities. All must work on infinite inputs and
must not materialise the source.

`run_lengths(iterable)` → yields `(value, count)` for each run of
consecutive equal values. `"aabbbc"` → `("a",2), ("b",3), ("c",1)`.

`chunk_by(iterable, key)` → yields **lists** of consecutive items
sharing a key. `chunk_by([1,3,2,4,5], lambda n: n % 2)` →
`[1,3], [2,4], [5]`.

`interleave(*iterables)` → round-robin across the inputs, skipping
exhausted ones. `interleave("abc", "12", "")` → `a,1,b,2,c`.

`window_max(iterable, k)` → the maximum of each sliding window of
width `k`, in **O(n) total** (each element enters and leaves a
deque once — no `max()` per window). Fewer than `k` items yields
nothing.
```python
from collections import deque
from itertools import groupby, islice


def run_lengths(iterable):
    ...


def chunk_by(iterable, key):
    ...


def interleave(*iterables):
    ...


def window_max(iterable, k):
    ...
```

## Takeaways

- `itertools` composes lazily — chain stages instead of building
  intermediate lists.
- `groupby` needs sorted input and yields *shared, one-shot* groups.
- Prefer `sum`/`max`/`any` over `reduce`; keep `reduce` for real folds.
- `singledispatch` replaces `isinstance` ladders and honours the MRO.
- `operator.itemgetter`/`attrgetter` are faster and clearer than
  equivalent lambdas.
