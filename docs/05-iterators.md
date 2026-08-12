# 05 — Iterators and Generators

`for` is a thin wrapper over two method calls. Once you can implement the
iterator protocol by hand, generators stop being magic — they are just a
compiler-written iterator whose state is a suspended stack frame. This
lesson goes all the way to `send`, `throw`, `close`, and `yield from`,
which is also the machinery `await` is built on.

## The protocol

- **iterable** — has `__iter__()` returning an iterator
- **iterator** — has `__next__()` and an `__iter__()` returning `self`

`for x in obj:` desugars to roughly:

```python
it = iter(obj)              # calls obj.__iter__()
while True:
    try:
        x = next(it)        # calls it.__next__()
    except StopIteration:
        break
    ...body...
```

Every iterator is an iterable; the reverse is false. A `list` is an
iterable that hands out a *fresh* iterator each time — which is why
you can loop over it twice.

```python
nums = [1, 2, 3]
it1, it2 = iter(nums), iter(nums)
print("independent iterators:", next(it1), next(it1), "|", next(it2))
print("iterator is its own iterable:", iter(it1) is it1)

# An iterator, hand-rolled.
class Countdown:
    def __init__(self, start): self.start = start
    def __iter__(self):
        return CountdownIterator(self.start)     # fresh state each time

class CountdownIterator:
    def __init__(self, n): self.n = n
    def __iter__(self): return self
    def __next__(self):
        if self.n <= 0:
            raise StopIteration
        self.n -= 1
        return self.n + 1

c = Countdown(3)
print("pass 1:", list(c))
print("pass 2:", list(c), "  <- reusable because __iter__ makes a new one")
```
Splitting *iterable* from *iterator* is what makes a container
re-iterable. If a class returns `self` from `__iter__` and mutates
its own state in `__next__`, it is single-use — like a file object
or a generator.


## `iter()` has a second form

`iter(callable, sentinel)` builds an iterator that calls `callable()`
repeatedly until it returns `sentinel`. It is the neat way to drain
anything with a "read one" API.

```python
import io

stream = io.StringIO("alpha\nbeta\ngamma\n")
# Call readline() until it returns "" (EOF).
for line in iter(stream.readline, ""):
    print("line:", line.strip())

# Same trick over a queue-like object.
pending = [3, 1, 4, None, 5]
pop = iter(pending).__next__
print("until None:", list(iter(pop, None)))
```
`iter(callable, sentinel)` calls the callable with **no
arguments** over and over, stopping as soon as the result equals
the sentinel. It converts any "keep calling until you get X" API
— the shape of most C-derived I/O — into something a `for` loop
can consume directly.

Two details worth holding on to: the comparison is `==`, not
`is`, so a sentinel with a custom `__eq__` can surprise you; and
the sentinel itself is **not** yielded, nor is anything after it —
the `5` sitting behind `None` is simply never reached.

## Generators: iterators the compiler writes for you

A function containing `yield` is a **generator function**. Calling it
runs no body code at all — it returns a generator object. Each `next()`
runs to the following `yield` and suspends, keeping locals and the
instruction pointer alive.

```python
import inspect

def gen():
    print("  [body starts]")
    x = yield 1
    print("  [resumed with]", x)
    yield 2
    print("  [body ends]")

g = gen()
print("calling gen() ran nothing:", type(g).__name__, inspect.getgeneratorstate(g))
print("next ->", next(g), inspect.getgeneratorstate(g))
print("next ->", next(g))
try:
    next(g)
except StopIteration as stop:
    print("StopIteration, value =", stop.value,
          "| state:", inspect.getgeneratorstate(g))
```
States are `GEN_CREATED` → `GEN_SUSPENDED` → `GEN_RUNNING` →
`GEN_CLOSED`. `inspect.getgeneratorstate` and
`inspect.getgeneratorlocals` are excellent debugging tools that
almost nobody knows about.

```python
# `return` in a generator sets StopIteration.value -- how a
# generator reports a final result rather than a stream item.
def parse(tokens):
    collected = []
    for tok in tokens:
        if tok == "STOP":
            return len(collected)          # becomes .value
        collected.append(tok)
        yield tok.upper()
    return len(collected)

g = parse(["a", "b", "STOP", "c"])
print("yielded:", list(g))

g2 = parse(["a", "b", "STOP", "c"])
try:
    while True:
        next(g2)
except StopIteration as stop:
    print("returned value:", stop.value)
```
`list(g)` throws the return value away — only `yield from` and
manual `next()` can see it. `await` uses exactly this channel to
deliver a coroutine's result.

**Quiz.** What does calling a generator function do?

- a) Runs the body until the first `yield`
- b) Runs the entire body and collects the yields into a list
- c) Runs nothing; it returns a generator object
- d) Raises unless you iterate it immediately

<details><summary>answer</summary>

**c** — Not a single statement of the body executes until the first `next()`. This is why validation in a generator function silently does nothing until someone iterates.
</details>

## `yield from`: delegation, not just a loop

`yield from sub` is *almost* `for x in sub: yield x`, but it also:

- forwards `send()` values into the sub-generator
- forwards `throw()` exceptions into it
- propagates `close()`
- evaluates to the sub-generator's **return value**

That full-duplex delegation is what made `asyncio` possible before
`async`/`await` had syntax.

```python
def leaf(name):
    total = 0
    while True:
        got = yield
        if got is None:
            return total          # finished: report the sum
        print(f"  {name} received {got}")
        total += got

def middle():
    subtotal = yield from leaf("leaf")     # captures the return value
    print("  middle saw subtotal:", subtotal)
    yield subtotal

m = middle()
next(m)                 # prime it
m.send(10)
m.send(5)
print("final:", m.send(None))
```
`send(x)` resumes the generator, makes the paused `yield` evaluate
to `x`, and returns the next yielded value. `next(g)` is exactly
`g.send(None)` — which is why a generator must be *primed* before
you can send it a real value.

```python
# Flattening arbitrarily nested structures -- the classic yield from.
def flatten(obj):
    if isinstance(obj, (str, bytes)):
        yield obj                       # strings are iterable: stop here
        return
    try:
        iterator = iter(obj)
    except TypeError:
        yield obj
        return
    for item in iterator:
        yield from flatten(item)

nested = [1, [2, [3, [4, [5]]]], "text", (6, {7, 8})]
print(list(flatten(nested)))
```
`yield from` delegates to a sub-iterator, which is what keeps a
recursive flatten to one line — the alternative is
`for x in flatten(item): yield x` at every level.

Both guards are load-bearing. The string check comes first
because strings are iterable and a one-character string iterates
to *itself*, so recursing on one never terminates. And `iter(obj)`
in a `try` is the honest test for "is this iterable", far more
robust than an `isinstance` against a hand-written list of
container types.

Note the tail of the output: the set contributed `8, 7`. Sets have
no insertion order, so flattening one gives no ordering guarantee.

## `throw` and `close`: exceptions travel inward

- `g.throw(Exc)` raises `Exc` **at the paused `yield`**, so the
  generator can catch it and carry on.
- `g.close()` throws `GeneratorExit` there. The generator must not
  yield again — doing so raises `RuntimeError`.
- `finally` blocks in a generator run on close, which is what makes
  `@contextmanager` (lesson 11) work.

```python
def resilient():
    results = []
    try:
        while True:
            try:
                item = yield
                results.append(item)
            except ValueError as exc:
                print("  caught and continuing:", exc)
    finally:
        print("  cleanup ran, collected:", results)

g = resilient()
next(g)
g.send("a")
g.throw(ValueError("bad item"))     # generator survives
g.send("b")
g.close()                           # triggers the finally
print("state after close:", g.gi_frame is None)
```
`throw` raises the exception **at the paused `yield`**, inside the
generator's own frame — so the generator's `try/except` gets a
chance at it and, having handled it, carries straight on to accept
`"b"`. An exception thrown in is recoverable; that is the whole
point of the method.

`close()` throws `GeneratorExit` at the same spot, and that one
you must not swallow. The `finally` runs, the frame is torn down,
and `gi_frame is None` confirms the generator can never be resumed.

This is precisely the machinery behind `@contextmanager` in
lesson 11: an exception raised in a `with` body is thrown into the
generator at its `yield`, which is why the cleanup there has to
sit in a `finally`.

```python
# Garbage collection also closes generators -- so `finally` runs
# even if you just walk away.
def leaky():
    try:
        yield 1
        yield 2
    finally:
        print("  finally ran during cleanup")

g = leaky()
print("got:", next(g))
del g                    # refcount hits zero -> close() -> finally
print("done")
```
Do not rely on this for releasing scarce resources: on PyPy or with
reference cycles it may be delayed. Use a `with` block *inside* the
generator, or `contextlib.closing`, when the cleanup matters.

**Quiz.** A paused generator receives `g.close()`. What happens inside?

- a) `StopIteration` is raised at the paused `yield`
- b) `GeneratorExit` is raised at the paused `yield`; `finally` blocks run
- c) The frame is discarded immediately with no cleanup
- d) `__del__` is called on the generator

<details><summary>answer</summary>

**b** — `GeneratorExit` inherits from `BaseException` — so a bare `except Exception:` inside the generator will not swallow it.
</details>

## Generator pipelines

Chained generators form a streaming pipeline: each stage pulls one
item at a time from the previous one. Memory stays flat regardless of
input size, and any stage can stop the whole chain early.

```python
def read_lines(text):
    for line in text.splitlines():
        yield line

def strip_comments(lines):
    for line in lines:
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            yield stripped

def parse_pairs(lines):
    for line in lines:
        key, _, value = line.partition("=")
        yield key.strip(), value.strip()

def coerce(pairs):
    for key, value in pairs:
        if value.isdigit():
            value = int(value)
        elif value.lower() in {"true", "false"}:
            value = value.lower() == "true"
        yield key, value

config_text = '''
# server settings
host = localhost
port = 8080          # the http port
debug = true

retries = 3
'''

pipeline = coerce(parse_pairs(strip_comments(read_lines(config_text))))
print(dict(pipeline))
```
Each stage is independently testable and reusable, nothing is
buffered, and swapping `read_lines(text)` for a file object streams
a 100 GB config without changing another line.

## `itertools.tee`, and why you usually should not

Need two passes over a one-shot iterator? `tee` buffers everything one
branch has seen but the other has not. If the branches drift far apart,
`tee` quietly holds the entire stream in memory. Often `list()` is more
honest.

```python
from itertools import tee

source = iter(range(6))
a, b = tee(source, 2)
print("branch a:", list(a))
print("branch b:", list(b), "  <- replayed from tee's buffer")
print("source is exhausted:", list(source))

# Do not touch the original after tee-ing:
src2 = iter(range(6))
c, d = tee(src2, 2)
next(src2)                    # steals an item from under tee
print("after stealing:", list(c), list(d))
```
Branch `b` replayed all six items *after* `a` had consumed them,
and the source came back empty — which tells you where those items
were: in `tee`'s internal buffer. The buffer holds everything
between the furthest-ahead branch and the furthest-behind one, so
draining `a` completely before touching `b` stored the entire
stream in memory. That is the cost people forget.

The second half is the other trap: once you have tee'd an
iterator, the original is off limits. Pulling one item out from
underneath left *both* branches starting at 1, silently losing a
record.

So: use `tee` for branches consumed roughly in step. For two full
passes over something large, re-read the source or build a list on
purpose — at least then the memory cost is visible in the code.

## Exercise — A peekable iterator wrapper `[medium]`

Implement `Peekable(iterable)` — an iterator that can look one item
ahead without consuming it. This is the core primitive of every
hand-written parser.

- `peek()` → the next item without advancing
- `peek(default)` → `default` instead of raising at the end
- `peek()` at the end with no default raises `StopIteration`
- `next(p)` returns the peeked item, then moves on
- `bool(p)` → True while items remain (must not consume one)
- it is an iterator: `iter(p) is p`, works in a `for` loop
- it must never pull more than one item ahead of the consumer
```python
_MISSING = object()


class Peekable:
    def __init__(self, iterable):
        ...
```

## Exercise — A send()-driven running aggregator `[brutal]`

Write the generator `aggregator()` — a *coroutine* that consumes
numbers via `send()` and yields the running state after each one.

State dict: `{"count", "total", "mean", "min", "max", "error"}`.

Protocol:
- after priming with `next(agg)`, each `agg.send(x)` returns the
  updated state; `mean`/`min`/`max` are `None` while `count == 0`
- sending `"reset"` clears everything back to the empty state
- sending a non-numeric value leaves the statistics **unchanged**
  and yields a state whose `error` is `"cannot aggregate <repr>"`;
  the next good value clears `error` back to `None`
- `bool` must be rejected as non-numeric even though
  `isinstance(True, int)` is True
- `agg.throw(ValueError)` is caught inside: the generator yields
  its current state and keeps going
- on `close()`, a `finally` block appends the final count to the
  module-level list `CLOSED_WITH`

Then write `feed(agg, values)` that primes if needed, sends every
value, and returns the last state dict.

> **Why report the error through the yielded value instead of
> raising it?** Because an exception that propagates *out* of a
> generator frame terminates that generator for good — there is no
> "raise into the caller and stay alive". `throw()` works in the
> other direction: it raises *at* the paused `yield`, where an
> `except` inside the body can absorb it. Keeping a coroutine
> alive across bad input therefore means yielding the error, not
> raising it.
```python
CLOSED_WITH = []


def aggregator():
    ...


def feed(agg, values):
    ...
```

## Takeaways

- `iter()` + `__next__()` + `StopIteration` is the whole protocol.
- Separate the iterable from the iterator to stay re-iterable.
- A generator function returns a generator; the body runs lazily.
- `send`/`throw`/`close` make generators two-way; `yield from`
  forwards all three and captures the return value.
- Pipelines of generators stream in constant memory.
