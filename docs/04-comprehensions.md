# 04 — Comprehensions and Lazy Evaluation

Comprehensions are not just terser loops — they are a different execution
model with their own scope, their own bytecode, and (for generator
expressions) their own laziness. Knowing where the boundary sits explains
leaked variables, surprise memory use, and one-shot iterables.

## The four forms

```python
[f(x) for x in it if cond]      # list
{f(x) for x in it}              # set
{k(x): v(x) for x in it}        # dict
(f(x) for x in it)              # generator expression -- LAZY
```

The first three build the whole result immediately. The fourth builds
nothing until you iterate it. That one-character difference between
`[` and `(` is the difference between 8 GB of RAM and 200 bytes.

```python
import sys

listcomp = [x * x for x in range(100_000)]
genexp = (x * x for x in range(100_000))

print("list comp :", type(listcomp).__name__, sys.getsizeof(listcomp), "bytes")
print("genexp    :", type(genexp).__name__, sys.getsizeof(genexp), "bytes")
print("both sum to the same thing:", sum(listcomp) == sum(genexp))

# ...but the generator is now EXHAUSTED.
print("second pass over the genexp:", sum(genexp))
print("second pass over the list  :", sum(listcomp))
```
A generator is a **one-shot** iterator. Once consumed it yields
nothing more — silently, with no error. This is the single most
common generator bug: passing one to two functions and wondering
why the second saw an empty sequence.

## Comprehensions have their own scope

In Python 3, a comprehension runs in an implicit nested function.
Consequences:

- the loop variable does **not** leak into the enclosing scope
- the comprehension can read enclosing names, but assigning to one
  needs `nonlocal`/`global` (or the walrus, see below)
- at class scope, the comprehension body cannot see class-level names
  — a genuinely surprising rule

```python
x = "untouched"
squares = [x * x for x in range(4)]
print("loop var did not leak:", x, squares)

# A plain for loop DOES leak -- and that is sometimes a bug.
for y in range(4):
    pass
print("but a for loop leaks:", y)
```
The comprehension body runs in its **own implicit function
scope**, so its loop variable cannot overwrite a name you were
using — `x` survives untouched. A `for` statement has no such
scope: `y` outlives the loop, holding whatever it had on the last
iteration.

The leak is occasionally deliberate (inspecting the loop variable
after a `break`), but far more often it is how a stale name gets
silently reused fifty lines later.


**Quiz.** Inside a class body, which part of `[f(x) for x in SOURCE]` can see class-level names?

- a) All of it — class scope is a normal enclosing scope
- b) Only `SOURCE`, the outermost iterable
- c) Only the `f(x)` expression
- d) None of it

<details><summary>answer</summary>

**b** — The outermost iterable is evaluated eagerly in the enclosing scope and passed into the implicit comprehension function; the rest runs inside it.
</details>

## Nesting: loop order reads left to right

```python
[expr for a in A for b in B]     # == for a in A: for b in B: expr
```

The clauses appear in the same order you would write the nested `for`
statements. The confusing part is that the *output expression* comes
first, at the far left, even though it executes last.

```python
matrix = [[1, 2, 3], [4, 5, 6]]

flat = [cell for row in matrix for cell in row]
print("flatten:", flat)

transposed = [[row[i] for row in matrix] for i in range(3)]
print("transpose:", transposed)
print("or just:  ", [list(t) for t in zip(*matrix)])

# A later clause can depend on an earlier one.
triangle = [(i, j) for i in range(4) for j in range(i)]
print("dependent:", triangle)

# Filters attach to the loop they follow.
print("filtered:", [(i, j) for i in range(4) if i % 2 == 0
                           for j in range(3) if j > i])
```
The `for` clauses read **left to right, outermost first** —
exactly the order you would write the nested loops in. That is
also why a later clause may depend on an earlier one, as
`range(i)` does.

Filters attach to the clause they follow, and the placement
matters for cost as well as meaning: `if i % 2 == 0` is tested
once per `i` and skips the entire inner loop, while `if j > i`
is tested for every pair. Put the cheapest, most selective filter
as far left as it will go.

For the transpose, prefer the `zip(*matrix)` form underneath — it
reads better and, unlike `range(3)`, does not hard-code the width.

## Conditional expressions vs filters

- `if` **after** the `for` is a **filter** — it drops elements.
- `if/else` **before** the `for` is a **ternary** in the output
  expression — it maps every element.

You cannot filter with an `else`; you cannot map-with-default using a
trailing `if`.

```python
nums = range(6)
print("filter  :", [n for n in nums if n % 2])
print("map     :", ["odd" if n % 2 else "even" for n in nums])
print("both    :", ["big" if n > 3 else "small" for n in nums if n % 2])
```
Two different `if`s, and the output lengths give them away. An
`if` **after** the `for` is a filter — it decides whether an item
is emitted at all, so six inputs became three. An
`x if cond else y` **before** the `for` is an expression — it
always emits, it just picks which value, so six inputs stayed six.

That is also why the expression form has no bare `if`: an
expression must evaluate to something, so the `else` is
compulsory. If you catch yourself wanting to omit it, what you
actually want is a filter.

## The walrus operator `:=`

Assign inside an expression. In comprehensions it lets you compute a
value once and use it in both the filter and the output — avoiding the
classic "call the expensive function twice" pattern.

The walrus target binds in the **enclosing** scope, not the
comprehension's — one of the few ways a comprehension writes outward.

```python
calls = []

def expensive(n):
    calls.append(n)
    return n * n

# Naive: calls expensive() twice per surviving element.
calls.clear()
naive = [expensive(n) for n in range(6) if expensive(n) > 10]
print("naive result:", naive, "| calls:", len(calls))

# Walrus: once per element.
calls.clear()
walrus = [sq for n in range(6) if (sq := expensive(n)) > 10]
print("walrus result:", walrus, "| calls:", len(calls))
print("and sq leaked out to here:", sq)
```
Reading a chunked stream is the other classic use:
`while chunk := f.read(8192):` replaces the read-before-loop
plus read-at-the-bottom dance.

**Quiz.** What does `[y := 2, y ** 2]` evaluate to?

- a) `[2, 4]`
- b) A SyntaxError
- c) `[2, 2]`
- d) `[None, 4]`

<details><summary>answer</summary>

**a** — The walrus binds `y` to 2 *and* evaluates to 2, so the second element sees `y == 2`. Legal, but do not write this in real code.
</details>

## Laziness: what it buys and what it costs

**Buys you:** constant memory over huge or infinite sources, early
exit without computing the rest, and pipeline composition.

**Costs you:** single use, no `len()`, no indexing, and *deferred
side effects* — the body runs later than the line where you wrote it,
which interacts badly with mutation and with `try/except`.

```python
# Early exit: only three items are ever computed.
log = []

def trace(n):
    log.append(n)
    return n

first_big = next(x for x in (trace(i) for i in range(1000)) if x > 2)
print("found:", first_big, "| computed:", log)

# Infinite sources are fine when consumption is bounded.
import itertools
evens = (n for n in itertools.count() if n % 2 == 0)
print("first 5 evens:", list(itertools.islice(evens, 5)))
```
`log` is the receipt: of a thousand candidates, exactly four were
ever computed. A generator expression produces values on demand,
so `next` stopped the moment the condition held — and because the
two generators are chained, no intermediate list was built at any
point.

The same property makes an infinite source usable, provided
something downstream bounds the consumption. `islice` does that
here; a bare `list(evens)` would run until you killed it.

```python
# Deferred evaluation bites when the source changes underneath.
data = [1, 2, 3]
lazy = (x * 10 for x in data)
eager = [x * 10 for x in data]

data.append(4)
data[0] = 100

print("eager (snapshot at creation):", eager)
print("lazy  (reads data at consumption):", list(lazy))
```
Only the *outermost iterable* is evaluated when the genexp is
created — and even then, `data` is captured as a reference, so
later mutations are visible. Materialise with `list(...)` when you
need a snapshot.


## When *not* to use a comprehension

- It spans more than about two lines or two `for` clauses — a loop
  reads better.
- The body has side effects and no useful result. Never write
  `[print(x) for x in xs]`: you build a list of `None` for nothing.
- You need `try/except` inside — comprehensions cannot contain
  statements.
- A built-in already does it: `sum`, `any`, `all`, `min`/`max` with
  `key=`, `list(map(...))` for a bare function call.

```python
rows = [{"n": 3}, {"n": 8}, {"n": 5}]

print("any :", any(r["n"] > 7 for r in rows))
print("all :", all(r["n"] > 1 for r in rows))
print("sum :", sum(r["n"] for r in rows))
print("max :", max(rows, key=lambda r: r["n"]))
print("count matching:", sum(1 for r in rows if r["n"] % 2))

# any/all short-circuit -- they stop at the first decisive element.
seen = []
def probe(x):
    seen.append(x)
    return x > 1
any(probe(x) for x in [0, 1, 2, 3, 4])
print("any() only looked at:", seen)
```
`sum(1 for ... if ...)` is the idiomatic counter. And note that
passing a genexp as the *sole* argument to a function needs no
extra parentheses: `sum(x for x in xs)` is fine.

## Exercise — A lazy transformation pipeline `[medium]`

Build `pipeline(source, *stages)` that threads an iterable through
a series of stages **lazily** — nothing may be computed until the
result is iterated, and the whole thing must work on an infinite
source.

Each stage is a tuple:
- `("map", fn)` — apply `fn` to each item
- `("filter", pred)` — keep items where `pred(item)` is truthy
- `("take", n)` — stop after `n` items

Also write `count_calls(fn)` returning `(wrapped, counter)` where
`counter` is a one-element list whose `[0]` holds the call count —
the checks use it to prove your pipeline is really lazy.
```python
from itertools import count, islice


def pipeline(source, *stages):
    ...


def count_calls(fn):
    ...
```

## Exercise — Lazy chunking without itertools.batched `[tricky]`

Implement `chunks(iterable, size, *, pad=None, drop_last=False)`
yielding **tuples** of length `size`.

- it must be lazy: a generator, working on infinite input
- it must consume the source **once** — no `list(iterable)`
- a short final chunk is yielded as-is by default
- `drop_last=True` discards a short final chunk
- `pad=<value>` fills a short final chunk up to `size`
  (`pad` and `drop_last` are mutually exclusive → `ValueError`)
- `size < 1` raises `ValueError`
- an empty source yields nothing

`itertools.batched` exists in 3.12 — the point is to write it.
```python
def chunks(iterable, size, *, pad=None, drop_last=False):
    ...
```

## Takeaways

- `[...]` materialises, `(...)` defers. Generators are one-shot.
- Comprehensions have their own scope — no leaks, and no access to
  class-level names past the first iterable.
- `if` after `for` filters; `if/else` before `for` maps.
- The walrus computes once and binds outward.
- Closures capture variables, not values — bind with a default
  argument when building callables in a loop.
