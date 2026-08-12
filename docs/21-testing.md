# 21 — Testing and Debugging

Tests are how you keep the freedom to change code. This lesson covers
pytest's model (plain asserts, fixtures, parametrisation, marks), the
seams that make code testable, `unittest.mock` without over-mocking,
property-based thinking, and the debugging tools — `pdb`, `breakpoint()`,
`logging`, `traceback` — that beat scattering print statements.

## Why pytest

- plain `assert`, with the expression rewritten so failures show the
  actual values
- fixtures instead of `setUp`/`tearDown` inheritance
- `parametrize` instead of loops inside a test
- a plugin for everything

The single most important habit: **one behaviour per test, named after
the behaviour**. `test_withdraw_rejects_amount_above_balance` tells you
what broke from the failure line alone.

```python
# A miniature version of pytest's assertion rewriting, to show
# what it buys you.
import ast
import textwrap

def explain_assert(source, namespace):
    tree = ast.parse(textwrap.dedent(source))
    stmt = tree.body[0]
    test = stmt.test
    left = eval(compile(ast.Expression(test.left), "<x>", "eval"), namespace)
    right = eval(compile(ast.Expression(test.comparators[0]), "<x>", "eval"),
                 namespace)
    ok = eval(compile(ast.Expression(test), "<x>", "eval"), namespace)
    return ok, left, right

ns = {"total": 7, "expected": 10}
ok, left, right = explain_assert("assert total == expected", ns)
print("passed:", ok)
print(f"  assert {left} == {right}")
print("  ^ this is why pytest needs no assertEqual family")
```

## Fixtures

A fixture is a function whose return value is injected into any test
that names it as a parameter. Scopes: `function` (default), `class`,
`module`, `package`, `session`.

```python
@pytest.fixture
def db(tmp_path):                 # fixtures can request fixtures
    conn = connect(tmp_path / "test.db")
    yield conn                    # everything after yield is teardown
    conn.close()
```

Built-ins worth knowing: `tmp_path`, `monkeypatch`, `capsys`,
`caplog`, `recwarn`, `request`.

```python
# Fixtures are just dependency injection. Here is the mechanism,
# implemented in twenty lines, so it stops looking magical.
import inspect

REGISTRY = {}

def fixture(fn):
    REGISTRY[fn.__name__] = fn
    return fn

def run_test(test_fn):
    params = inspect.signature(test_fn).parameters
    finalisers, kwargs = [], {}
    for name in params:
        produced = REGISTRY[name]()
        if inspect.isgenerator(produced):
            kwargs[name] = next(produced)
            finalisers.append(produced)
        else:
            kwargs[name] = produced
    try:
        test_fn(**kwargs)
        return "PASS"
    except AssertionError as exc:
        return f"FAIL: {exc}"
    finally:
        for gen in reversed(finalisers):
            next(gen, None)          # runs the teardown

@fixture
def numbers():
    return [1, 2, 3]

@fixture
def resource():
    print("  setup")
    yield {"open": True}
    print("  teardown")

def test_sum(numbers):
    assert sum(numbers) == 6

def test_uses_resource(resource, numbers):
    assert resource["open"]
    assert len(numbers) == 3

def test_fails(numbers):
    assert sum(numbers) == 7, "sum was 6"

for test in (test_sum, test_uses_resource, test_fails):
    print(f"{test.__name__:22} {run_test(test)}")
```
Teardown after `yield` runs even when the test fails — that is the
`finally` above. Real pytest adds scoping, caching, parametrised
fixtures and `conftest.py` discovery, but the core is exactly this.

## Parametrise instead of looping

```python
@pytest.mark.parametrize("value,expected", [
    ("", 0), ("a", 1), ("hello world", 2),
])
def test_word_count(value, expected):
    assert word_count(value) == expected
```

Each case is a **separate test**: it gets its own name, its own
failure, and one bad case does not hide the others. A loop inside one
test stops at the first failure and reports one result.

```python
# Why parametrisation beats a loop: information on failure.
def word_count(text):
    return len(text.split())

cases = [("", 0), ("a", 1), ("hello world", 2), ("  padded  ", 1),
         ("a\nb", 3)]        # deliberately wrong expectation

print("as one looping test:")
try:
    for text, expected in cases:
        assert word_count(text) == expected, f"{text!r}"
except AssertionError as exc:
    print(f"  stopped at the first failure: {exc}")

print("\nas parametrised cases:")
for text, expected in cases:
    got = word_count(text)
    status = "PASS" if got == expected else f"FAIL (got {got})"
    print(f"  word_count({text!r:14}) == {expected}  {status}")
print("\n-> every case reported; you see the whole picture at once")
```

**Quiz.** Why prefer `@pytest.mark.parametrize` over a `for` loop inside one test?

- a) It runs faster
- b) Each case becomes a separate test: independent failures, individual names, no early exit
- c) Loops are not allowed in tests
- d) It automatically generates the expected values

<details><summary>answer</summary>

**b** — A loop reports one result and stops at the first failure, hiding how many other cases are broken.
</details>

## Test seams: design for testability

The hard part of testing is rarely the assertion — it is reaching the
code. Make the awkward things injectable:

- **time** — take a `now=time.time` parameter, or inject a clock
- **randomness** — accept a `random.Random(seed)` instance
- **I/O** — accept an open file or a `Path`, not a filename buried
  three layers down
- **network** — put it behind one small function you can replace
- **globals** — pass configuration in

Code that is hard to test is usually code with hidden dependencies.

```python
import random
import time

# Untestable: hidden dependencies on the clock and the RNG.
def make_token_bad():
    return f"{int(time.time())}-{random.randint(1000, 9999)}"

# Testable: same defaults, but both seams are injectable.
def make_token(now=time.time, rng=random):
    return f"{int(now())}-{rng.randint(1000, 9999)}"

print("production call:", make_token()[:4] + "...")

fixed_clock = lambda: 1_700_000_000
seeded = random.Random(42)
print("deterministic  :", make_token(now=fixed_clock, rng=seeded))
print("reproducible   :", make_token(now=fixed_clock, rng=random.Random(42)))

# And an expiry check becomes trivial to test at any point in time.
def is_expired(issued_at, ttl, now=time.time):
    return now() - issued_at > ttl

print("\nexpired after 61s with ttl 60:",
      is_expired(1000, 60, now=lambda: 1061))
print("not expired after 59s        :",
      is_expired(1000, 60, now=lambda: 1059))
```

## Mocking, and when not to

`unittest.mock` gives you `Mock`, `MagicMock`, `patch`, and
`create_autospec`.

Rules that keep mocks useful:

1. **Patch where it is *used*, not where it is defined.**
   `@patch("myapp.service.requests.get")`, not
   `@patch("requests.get")`.
2. Use `autospec=True` so the mock rejects calls the real object
   would reject.
3. Mock at the **boundary** (network, clock, filesystem), not your own
   internals — mocking your own code tests your mocks.
4. Assert on behaviour, not on every call.

```python
from unittest.mock import MagicMock, Mock, call, create_autospec

class EmailClient:
    def send(self, to, subject, body): ...
    def close(self): ...

def notify(client, users, subject):
    sent = 0
    for user in users:
        if user.get("email"):
            client.send(user["email"], subject, f"Hi {user['name']}")
            sent += 1
    client.close()
    return sent

client = create_autospec(EmailClient, instance=True)
users = [{"name": "ada", "email": "a@x.com"},
         {"name": "bob", "email": None},
         {"name": "cy", "email": "c@x.com"}]

sent = notify(client, users, "Welcome")
print("returned:", sent)
print("send called", client.send.call_count, "times")
print("first call:", client.send.call_args_list[0])
client.close.assert_called_once()

# autospec catches signature mistakes that a bare Mock would swallow
try:
    client.send("only@one.arg")
except TypeError as exc:
    print("\nautospec caught:", exc)

loose = Mock()
loose.send("only@one.arg")           # a plain Mock accepts anything
print("a bare Mock accepted it:", loose.send.called)
```

```python
from unittest.mock import Mock, patch
import sys
import types

# Building a module so we can demonstrate "patch where it is used".
service = types.ModuleType("service")
exec(
    "import json\n"
    "def fetch(url):\n"
    "    raise RuntimeError('real network call')\n"
    "def get_user(uid):\n"
    "    return fetch(f'/users/{uid}')\n",
    service.__dict__,
)
sys.modules["service"] = service

with patch("service.fetch", return_value={"id": 1, "name": "ada"}) as mocked:
    print("patched result:", service.get_user(1))
    mocked.assert_called_once_with("/users/1")

print("restored after the with block:", end=" ")
try:
    service.get_user(1)
except RuntimeError as exc:
    print(exc)

# side_effect: raise, or return a sequence of values
with patch("service.fetch", side_effect=[{"n": 1}, TimeoutError("slow")]):
    print("\ncall 1:", service.get_user(1))
    try:
        service.get_user(2)
    except TimeoutError as exc:
        print("call 2:", type(exc).__name__, exc)

del sys.modules["service"]
```
`patch` is a context manager *and* a decorator, and it always
restores the original — even if the test fails. `side_effect`
accepts a list (one value per call), an exception (raised), or a
function (called with the same arguments).


## Property-based testing

Instead of examples, state an **invariant** and let the machine hunt
for counterexamples. `hypothesis` is the library; the idea works with
plain `random` too.

Useful invariant shapes:

- round trip: `decode(encode(x)) == x`
- agreement with a slow, obviously-correct reference implementation
- idempotence: `f(f(x)) == f(x)`
- metamorphic: `sorted(xs + [y])` contains `sorted(xs)` as a
  subsequence

```python
import random

def encode(items):
    '''Run-length encode a list.'''
    out = []
    for item in items:
        if out and out[-1][0] == item:
            out[-1][1] += 1
        else:
            out.append([item, 1])
    return [(v, n) for v, n in out]

def decode(pairs):
    return [v for v, n in pairs for _ in range(n)]

rng = random.Random(0)
failures = []
for _ in range(400):
    length = rng.randint(0, 12)
    data = [rng.choice("aab") for _ in range(length)]
    if decode(encode(data)) != data:
        failures.append(data)

print("round-trip property held on 400 random inputs:", not failures)

# A deliberately broken variant, to show the property finding it.
def broken_encode(items):
    pairs = encode(items)
    return [(v, n) for v, n in pairs if n > 1]      # drops singletons

counterexample = next(
    (d for d in ([rng.choice("ab") for _ in range(rng.randint(1, 6))]
                 for _ in range(200))
     if decode(broken_encode(d)) != d),
    None,
)
print("counterexample for the broken version:", counterexample)
```

## Debugging beyond `print`

- `breakpoint()` — drops into `pdb` (or whatever `PYTHONBREAKPOINT`
  names). Commands: `n`ext, `s`tep, `c`ontinue, `w`here, `l`ist,
  `p`/`pp` expression, `u`p/`d`own, `b` file:line, `interact`.
- `pdb.post_mortem()` — inspect the frames of an exception *after* it
  happened. `pytest --pdb` does this automatically.
- `logging` with `%`-style lazy formatting, not f-strings, so the
  message is only rendered if the level is enabled.
- `traceback.print_stack()` — how did I get here?
- `sys.settrace` / `sys.monitoring` (3.12) — build your own tracer.

```python
import logging
import sys
import traceback

logger = logging.getLogger("demo")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def risky(n):
    logger.debug("this is never rendered: %s", expensive := "x")
    logger.info("processing %d items", n)
    try:
        return 10 / n
    except ZeroDivisionError:
        logger.exception("division failed")   # includes the traceback
        return None

risky(2)
risky(0)

print()
# post-mortem inspection without a debugger session
try:
    risky(0) or [][1]
except IndexError as exc:
    tb = exc.__traceback__
    while tb.tb_next:
        tb = tb.tb_next
    print("failed in :", tb.tb_frame.f_code.co_name)
    print("locals    :", {k: v for k, v in tb.tb_frame.f_locals.items()
                          if not k.startswith("__")})
```
`logger.info("got %s", value)` defers the string formatting until
the handler decides it will actually emit. With an f-string you
pay the formatting cost on every call, even at a level you have
turned off — measurable in hot paths and in debug logging.

```python
import sys

# A tiny call tracer -- the mechanism behind coverage tools,
# debuggers and profilers.
calls = []

def tracer(frame, event, arg):
    if event == "call" and frame.f_code.co_name in {"outer", "inner"}:
        calls.append((frame.f_code.co_name, dict(frame.f_locals)))
    return None

def inner(x): return x * 2
def outer(n): return inner(n) + inner(n + 1)

sys.settrace(tracer)
outer(5)
sys.settrace(None)

for name, local_vars in calls:
    print(f"  called {name}({local_vars})")
```

**Quiz.** Why `logger.info('value=%s', x)` rather than `logger.info(f'value={x}')`?

- a) f-strings are not supported by logging
- b) The %-form defers formatting until the record is actually emitted
- c) The %-form is easier to read
- d) There is no difference

<details><summary>answer</summary>

**b** — With an f-string the formatting happens before the call, at every call site, even when the level is disabled. It also loses the structured `record.args` that log aggregators can group on.
</details>

## Exercise — A miniature test runner `[brutal]`

Build a small test framework with `fixture`, `parametrize`, and
`run_tests` — the core of pytest in about sixty lines.

- `@fixture` registers a function by name; a test declaring a
  parameter of that name receives its value
- a **generator** fixture yields the value and its remainder is
  teardown, run even if the test fails, in reverse order
- fixtures may depend on other fixtures (resolve recursively);
  a dependency cycle raises `ValueError`
- each fixture is created at most once per test, even if two
  fixtures both require it
- `@parametrize("a,b", [(1, 2), (3, 4)])` runs the test once per
  case, filling those parameters; remaining parameters still come
  from fixtures
- `run_tests(tests)` returns a list of result dicts with keys
  `name`, `outcome` (`"pass"`/`"fail"`/`"error"`), and `message`
  — `"fail"` for `AssertionError`, `"error"` for anything else
- a parametrised test's `name` is `f"{fn.__name__}[{case}]"` where
  `case` joins the values with `-`
- a test requesting an unknown fixture is an `"error"`, not a crash
```python
import inspect

FIXTURES = {}


def fixture(fn):
    ...


def parametrize(argnames, cases):
    ...


def run_tests(tests):
    ...
```

## Takeaways

- One behaviour per test, named after the behaviour.
- Fixtures are dependency injection; teardown lives after `yield`.
- `parametrize` gives independent, individually-named cases.
- Inject the clock, the RNG, and I/O — untestable code is code with
  hidden dependencies.
- Mock at boundaries with `autospec`; a bare `MagicMock` will happily
  accept a misspelled assertion.
