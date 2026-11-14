# 01 — Names, Objects, and Identity

Everything downstream — mutability bugs, `is` vs `==`, why default
arguments bite, how `copy` behaves — falls out of one idea: a Python
variable is a *name bound to an object*, never a box holding a value.
Get this exactly right and half of Python's "gotchas" stop being
surprising.

## Assignment binds, it does not copy

In C, `int a = b;` copies bytes into a's storage. In Python,
`a = b` makes the name `a` point at *the same object* `b` points at.
Objects live on the heap; names live in namespaces (dicts, mostly)
and are just references.

Three properties define every object:

1. **identity** — its address, never changes, read with `id()`
2. **type** — never changes (for practical purposes), read with `type()`
3. **value** — may or may not change; that is what *mutability* means

```python
a = [1, 2, 3]
b = a                 # a second name for the SAME list
b.append(4)

print("a =", a)
print("b =", b)
print("same object?", a is b, "| id match:", id(a) == id(b))

b = b + [5]           # '+' builds a NEW list, rebinds b only
print("after b = b + [5]")
print("a =", a)
print("b =", b)
print("same object?", a is b)
```
`b.append(4)` changes the list shared by `a` and `b`.
`b = b + [5]` creates a new list and binds `b` to it;
`a` still refers to the original list.

## `+=` is not sugar for `= ... + ...`

Augmented assignment calls `__iadd__` first. Mutable types implement
it in place and return `self`; immutable ones don't have it, so
Python falls back to `__add__` and rebinds. Same syntax, two
completely different outcomes.


```python
# The classic head-scratcher this produces:
t = ([1, 2], "x")
try:
    t[0] += [3]
except TypeError as exc:
    print("raised:", exc)
print("but the list changed anyway:", t)
```
`t[0] += [3]` compiles to: load `t[0]`, call `__iadd__` on it
(**succeeds**, list is mutated), then `t[0] = result` (**fails**,
tuples reject item assignment). You get the exception *and* the
mutation. Tuples are only shallowly immutable.

**Quiz.** Why does `t[0] += [3]` on `t = ([1,2], 'x')` both raise and mutate?

- a) A bug in CPython's tuple implementation
- b) `__iadd__` runs and mutates the list before the store into the tuple is attempted and rejected
- c) The list is copied, mutated, then the copy is discarded
- d) Tuples make their contents immutable, so nothing really changed

<details><summary>answer</summary>

**b** — Augmented assignment is *mutate-then-store*. The mutation has already happened by the time STORE_SUBSCR raises.
</details>

## `is` versus `==`

- `is` compares identity — *the same object?*
- `==` compares value via `__eq__` — *equivalent objects?*

Use `is` only for singletons: `None`, `True`, `False`, sentinels, and
enum members. Never for numbers or strings, no matter what you saw
work in the REPL.

```python
a = 256; b = 256
c = 257; d = 257
print("256 is 256 ->", a is b)     # small-int cache
print("257 is 257 ->", c is d)     # depends on the compiler's mood

x = "hello"; y = "hello"
print("literals interned ->", x is y)
z = "".join(["hel", "lo"])
print("built at runtime ->", x is z, "| but equal:", x == z)
```
CPython caches ints in `[-5, 256]` and interns identifier-like
string literals. These are **implementation details** — PyPy and
future CPythons may differ. Compare values with `==`.

```python
import sys

# Interning is observable, and sometimes useful on purpose:
key = sys.intern("user_id")
other = sys.intern("user" + "_id")
print("explicitly interned:", key is other)

# Identity is also how the default __eq__ behaves:
class Plain: pass
p, q = Plain(), Plain()
print("default __eq__ is identity:", p == q, p == p)
```
`object.__eq__` falls back to `is`. That is why two "equal-looking"
instances of a class you wrote compare unequal until you define
`__eq__` (lesson 02).

**Quiz.** Which comparison is *always* correct style?

- a) `if x is 0:`
- b) `if name is 'admin':`
- c) `if value is None:`
- d) `if total is 100:`

<details><summary>answer</summary>

**c** — `None` is a true singleton — there is exactly one, forever. Ints and strings only look like singletons by accident of caching.
</details>

## Mutable and immutable, and why it matters

| immutable | mutable |
|---|---|
| `int` `float` `complex` `bool` | `list` `dict` `set` `bytearray` |
| `str` `bytes` `tuple` `frozenset` | most class instances |
| `range`, `NoneType`, `Enum` members | `collections.*` containers |

Immutability buys you three things: safe sharing across threads,
hashability (so you can use it as a dict key), and the freedom for
the runtime to cache aggressively.

```python
# Hashability tracks immutability -- for good reason.
ok = {("a", 1): "tuple key works"}
print(ok)

try:
    {["a", 1]: "nope"}
except TypeError as exc:
    print("list key ->", exc)

# Why: a mutating key would silently lose its slot.
class Sneaky:
    def __init__(self, v): self.v = v
    def __hash__(self): return hash(self.v)
    def __eq__(self, other): return self.v == other.v

k = Sneaky(1)
d = {k: "found me"}
k.v = 99                     # hash changed after insertion
print("lookup after mutating the key:", d.get(Sneaky(99), "LOST"))
print("the entry is still in there:", list(d.values()))
```
The value never left the dict — it is just parked in the bucket
for `hash(1)` while lookups now probe the bucket for `hash(99)`.
**Rule: a key's hash must never change while it is in a dict.**

## Copying: none, shallow, deep

- `b = a` — no copy at all, one object, two names.
- `a.copy()`, `list(a)`, `a[:]`, `copy.copy(a)` — **shallow**: a new
  outer container, the *same* inner objects.
- `copy.deepcopy(a)` — recursive copy, cycle-safe via a memo dict.

```python
import copy

grid = [[0] * 3 for _ in range(2)]
shallow = copy.copy(grid)
deep = copy.deepcopy(grid)

grid[0][0] = 99
print("original:", grid)
print("shallow: ", shallow, "  <- inner lists were shared")
print("deep:    ", deep)

# The classic bug this causes:
rows = [[0] * 3] * 2          # the SAME row object twice
rows[0][0] = 1
print("rows =", rows)
```
`[[0]*3] * 2` repeats a *reference*, so both rows are one object.
`[[0]*3 for _ in range(2)]` evaluates the inner list twice and
gives you two distinct rows. Always build nested structures with
a comprehension.

```python
import copy

# deepcopy handles cycles and lets classes opt out.
a = {"name": "cfg"}
a["self"] = a                       # cyclic
b = copy.deepcopy(a)
print("cycle survived:", b["self"] is b)

class Connection:
    def __init__(self, dsn): self.dsn, self.socket = dsn, object()
    def __deepcopy__(self, memo):
        # Sockets must not be duplicated -- hand back a fresh one.
        print("  custom __deepcopy__ called")
        return Connection(self.dsn)

c = Connection("db://x")
d = copy.deepcopy(c)
print("socket shared?", c.socket is d.socket)
```
`__copy__` / `__deepcopy__` / `__reduce__` let a class control
duplication. Anything holding an OS resource should define them.

**Quiz.** `board = [[None] * 3] * 3; board[1][1] = 'X'`. What is `board`?

- a) One X in the middle, as intended
- b) Three X's — one in the middle of every row
- c) A TypeError, lists are unhashable
- d) Nine X's

<details><summary>answer</summary>

**b** — `* 3` on the outer list stores three references to one row. Writing through any of them is visible through all of them.
</details>

## Function arguments: 'call by object reference'

Python is neither call-by-value nor call-by-reference in the C sense.
The *reference* is passed by value. So a function can **mutate** what
you gave it, but **rebinding** the parameter never touches your name.

```python
def modify(lst, num, dct):
    lst.append("mutated")     # visible to the caller
    num += 1                  # rebinds a local, invisible
    dct = {"replaced": True}  # rebinds a local, invisible
    return num, dct

items, count, config = [], 0, {"debug": False}
ret = modify(items, count, config)
print("items :", items)
print("count :", count, "  (returned", ret[0], ")")
print("config:", config)
```
If you want a caller to see a new value, **return it**. Mutating
arguments in place works but makes functions harder to reason
about — prefer it only when the type's whole job is to be mutated.

## Exercise — Non-destructive nested merge `[medium]`

Write `merge(base, override)` that returns a **new** dict combining
the two, recursing into nested dicts. Neither input may be modified,
and the result must not share any *mutable* sub-object with the
inputs — a later write to the result must never leak back.

Rules:
- keys only in one side are carried over
- if both values are dicts → merge recursively
- otherwise `override` wins
```python
import copy


def merge(base: dict, override: dict) -> dict:
    ...
```

## Exercise — Alias detector `[tricky]`

Write `find_aliases(container)` that scans a list and returns a list
of index-tuples for elements that are *the same object*, i.e. share
identity — not merely `==`.

`find_aliases([x, y, x, z, y])` → `[(0, 2), (1, 4)]`

- only groups of size ≥ 2 are reported
- each group is a sorted tuple of indices
- groups are ordered by their first index
- elements that appear once are omitted
- it must work for unhashable elements (`[]`, `{}`), so you cannot
  simply use the objects as dict keys
```python
def find_aliases(container: list) -> list[tuple[int, ...]]:
    ...
```

## Takeaways

- A name is a reference. Assignment rebinds; methods may mutate.
- `is` is identity, `==` is value. Reserve `is` for singletons.
- Shallow copies duplicate the container, not the contents.
- A dict key's hash must be stable for as long as it is a key.
- Passing an argument shares the object; only mutation is visible
  to the caller.
