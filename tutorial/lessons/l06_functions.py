"""Lesson 06 — Functions: signatures, scope, and closures."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=6,
    slug="functions",
    title="Functions, Scope, and Closures",
    summary="""
    Functions are objects with a rich, introspectable signature grammar and a
    precise scoping model. This lesson covers every parameter kind, the
    mutable-default trap and its real cause, LEGB resolution, closures and
    cell objects, and how to inspect and wrap a signature correctly.
    """,
    tags=("functions", "scope", "closures", "signatures"),
    blocks=[
        Text("""
        ## The full parameter grammar

        ```python
        def f(pos_only, /, standard, *args, kw_only, **kwargs):
            ...
        ```

        - everything **before `/`** is positional-only (3.8+)
        - everything **after `*`** or `*args` is keyword-only
        - `*args` collects extra positionals into a tuple
        - `**kwargs` collects extra keywords into a dict

        Positional-only parameters let you rename them later without breaking
        callers, and let `**kwargs` contain a key with the same name. That is
        why built-ins like `dict.get` use them.
        """),
        Demo(
            code="""
            def configure(source, /, mode="r", *extras, encoding="utf-8", **options):
                return {
                    "source": source, "mode": mode, "extras": extras,
                    "encoding": encoding, "options": options,
                }

            print(configure("f.txt"))
            print(configure("f.txt", "w", "x", "y", encoding="latin-1", buffer=4096))

            try:
                configure(source="f.txt")
            except TypeError as exc:
                print("positional-only:", exc)

            # Because `source` is positional-only, it may ALSO appear in **options:
            print(configure("f.txt", source="a query param"))
            """,
            explain="""
            That last line is the real motivation: without `/`, a caller who
            wants a keyword literally named `source` collides with your
            parameter. `min`, `max`, `dict.get` and friends all use `/` for
            exactly this reason.
            """,
        ),
        Text("""
        ## The mutable default argument

        Defaults are evaluated **once**, when the `def` statement executes —
        not per call. A mutable default is therefore shared state living on
        the function object, in `func.__defaults__`.
        """),
        Demo(
            code="""
            def append_bad(item, target=[]):
                target.append(item)
                return target

            print(append_bad(1))
            print(append_bad(2))
            print(append_bad(3))
            print("the default itself:", append_bad.__defaults__)

            def append_good(item, target=None):
                if target is None:
                    target = []
                target.append(item)
                return target

            print("fixed:", append_good(1), append_good(2))
            """,
        ),
        Demo(
            code="""
            import datetime

            # The same trap with a non-container: the value is frozen at def time.
            def log_bad(msg, when=datetime.datetime(2020, 1, 1)):
                return f"{when:%Y-%m-%d} {msg}"

            def log_good(msg, when=None):
                when = when or datetime.datetime.now()
                return f"{when:%Y-%m-%d} {msg}"

            print(log_bad("frozen timestamp"))
            print(log_good("evaluated per call")[:10] != "2020-01-01")

            # Occasionally the trap is a FEATURE: a per-function cache.
            def fib(n, _memo={0: 0, 1: 1}):
                if n not in _memo:
                    _memo[n] = fib(n - 1) + fib(n - 2)
                return _memo[n]

            print("fib(60) =", fib(60), "| cache size:", len(fib.__defaults__[0]))
            """,
            explain="""
            Use the deliberate version sparingly and name it with a leading
            underscore. `functools.cache` (lesson 15) says the same thing more
            clearly.
            """,
        ),
        Question(
            prompt="When is the expression in `def f(x=compute()):` evaluated?",
            choices=[
                "Every time `f` is called without `x`",
                "Once, when the `def` statement runs",
                "Once, on the first call to `f`",
                "Never — it is only a type hint",
            ],
            answer=1,
            explain="At definition time, and the result is stored in `f.__defaults__`. "
                    "That single evaluation is the whole cause of the mutable-default trap.",
        ),
        Text("""
        ## Unpacking at the call site

        `*` and `**` in a *call* are the mirror of `*args`/`**kwargs` in a
        *definition*. Since 3.5 you may use several of each in one call, and
        unpack into literals.
        """),
        Demo(
            code="""
            def show(a, b, c, d=0):
                return f"a={a} b={b} c={c} d={d}"

            args = (1, 2)
            more = {"c": 3, "d": 4}
            print(show(*args, **more))

            # Multiple unpackings, and unpacking into literals
            head, *middle, tail = [1, 2, 3, 4, 5]
            print("starred unpack:", head, middle, tail)

            merged = [*[1, 2], *(3, 4), 5]
            combined = {**{"a": 1}, **{"b": 2}, "c": 3}
            print("merged:", merged, combined)

            # Nested unpacking in a for loop
            pairs = [(1, ("a", "b")), (2, ("c", "d"))]
            for num, (first, second) in pairs:
                print(f"  {num}: {first}{second}")
            """,
        ),
        Text("""
        ## LEGB: how a name is resolved

        **L**ocal → **E**nclosing → **G**lobal → **B**uiltins.

        Crucially, whether a name is local is decided **at compile time**:
        if a function body assigns to a name anywhere, that name is local for
        the whole function — even on lines before the assignment.
        """),
        Predict(
            code="""
            x = "global"

            def read_only():
                return x

            def shadowed():
                try:
                    return x
                except UnboundLocalError as exc:
                    return f"UnboundLocalError"
                finally:
                    x = "local"          # makes x local for the WHOLE function

            print(read_only())
            print(shadowed())
            print(x)
            """,
            answer="""
            global
            UnboundLocalError
            global
            """,
            explain="""
            The compiler saw `x = "local"` and marked `x` local throughout
            `shadowed`, so the `return x` above it reads an unbound local. The
            fix is `global x` (or restructuring so you never shadow).
            """,
        ),
        Demo(
            code="""
            counter = 0

            def bump_global():
                global counter
                counter += 1

            def make_counter():
                count = 0
                def increment():
                    nonlocal count           # rebind the ENCLOSING local
                    count += 1
                    return count
                def peek():
                    return count             # reading needs no declaration
                return increment, peek

            bump_global(); bump_global()
            inc, peek = make_counter()
            inc(); inc(); inc()
            print("global:", counter, "| closure:", peek())

            # The two counters from two calls are independent.
            inc2, peek2 = make_counter()
            inc2()
            print("independent closures:", peek(), peek2())
            """,
            explain="""
            `nonlocal` targets the nearest enclosing *function* scope; it can
            never reach module level (use `global` for that) and it errors at
            compile time if no such binding exists.
            """,
        ),
        Text("""
        ## Closures are cells, and you can look inside

        A closure variable lives in a **cell object** shared between the outer
        and inner function. `func.__closure__` is a tuple of cells;
        `func.__code__.co_freevars` names them.
        """),
        Demo(
            code="""
            def outer():
                message = "hello"
                extra = [1, 2]
                def inner():
                    return message, extra
                return inner

            fn = outer()
            print("free variables:", fn.__code__.co_freevars)
            print("cells:", fn.__closure__)
            print("cell contents:", [c.cell_contents for c in fn.__closure__])

            # Cells are live: rebinding through nonlocal is visible to all readers.
            def counterish():
                n = 0
                def bump():
                    nonlocal n
                    n += 1
                def get():
                    return n
                return bump, get

            bump, get = counterish()
            bump(); bump()
            print("shared cell:", get(), "| same cell object:",
                  bump.__closure__[0] is get.__closure__[0])
            """,
        ),
        Predict(
            code="""
            def make_multipliers():
                return [lambda x: x * i for i in range(3)]

            def make_multipliers_fixed():
                return [lambda x, i=i: x * i for i in range(3)]

            print([f(10) for f in make_multipliers()])
            print([f(10) for f in make_multipliers_fixed()])
            """,
            answer="""
            [20, 20, 20]
            [0, 10, 20]
            """,
            explain="""
            All three lambdas close over the **same cell** for `i`, which holds
            2 by the time they run. The default-argument version evaluates `i`
            at each lambda's creation. `functools.partial(operator.mul, i)` is
            the cleaner idiom.
            """,
        ),
        Question(
            prompt="Inside a nested function, which keyword rebinds a variable of the *enclosing function*?",
            choices=["`global`", "`nonlocal`", "`static`", "No keyword — assignment just works"],
            answer=1,
            explain="Plain assignment creates a new local. `global` skips all the way "
                    "to module scope; `nonlocal` targets the nearest enclosing function binding.",
        ),
        Text("""
        ## Functions are objects

        They carry attributes you can read and write: `__name__`, `__doc__`,
        `__defaults__`, `__kwdefaults__`, `__annotations__`, `__dict__`,
        `__module__`, `__qualname__`, `__code__`. Understanding these is what
        makes writing correct decorators possible (next lesson).
        """),
        Demo(
            code="""
            def greet(name: str, punct: str = "!") -> str:
                '''Say hello.'''
                return f"Hello, {name}{punct}"

            greet.call_count = 0                # arbitrary attributes are allowed

            print("name       :", greet.__name__, "| qualname:", greet.__qualname__)
            print("doc        :", greet.__doc__)
            print("defaults   :", greet.__defaults__)
            print("annotations:", greet.__annotations__)
            print("attributes :", greet.__dict__)
            print("code       : argcount =", greet.__code__.co_argcount,
                  "| varnames =", greet.__code__.co_varnames)
            """,
        ),
        Text("""
        ## `inspect.signature`: the right way to introspect

        Never parse `__code__` by hand. `inspect.signature` gives you an
        object you can query, bind arguments against, and even modify.
        """),
        Demo(
            code="""
            import inspect

            def handler(request, /, timeout=30, *middleware, retries=3, **opts):
                ...

            sig = inspect.signature(handler)
            print("signature:", sig)
            for name, param in sig.parameters.items():
                print(f"  {name:12} kind={param.kind.name:20} default={param.default!r}")

            # bind() resolves a call the way Python would -- great for validation.
            bound = sig.bind("req", 5, "mw1", retries=1, verbose=True)
            bound.apply_defaults()
            print("bound:", dict(bound.arguments))

            try:
                sig.bind()                       # missing required argument
            except TypeError as exc:
                print("bind error:", exc)
            """,
            explain="""
            `sig.bind(*args, **kwargs)` is how you write a decorator that needs
            to look at a specific parameter by name regardless of whether the
            caller passed it positionally or by keyword.
            """,
        ),
        Demo(
            code="""
            import inspect
            from functools import partial

            def connect(host, port=5432, *, user, password, timeout=10):
                return f"{user}@{host}:{port} timeout={timeout}"

            # partial pre-binds arguments and produces a new callable.
            local = partial(connect, "localhost", user="admin")
            print(local(password="s3cret"))
            print("partial keeps the pieces:", local.func.__name__, local.args, local.keywords)

            # signature() understands partials and reports what's LEFT to supply.
            print("remaining signature:", inspect.signature(local))

            # partialmethod's cousin for the common "flag variant" pattern:
            debug_connect = partial(connect, timeout=1)
            print(debug_connect("db1", user="u", password="p"))
            """,
        ),
        Exercise(
            slug="validate-args",
            title="A signature-aware argument validator",
            difficulty="tricky",
            brief="""
            Write `validated(**rules)` — a decorator factory that checks
            arguments against predicates **by parameter name**, no matter how
            the caller passed them.

            - `@validated(n=lambda v: v > 0)` must reject `f(-1)`, `f(n=-1)`
              and a `-1` that arrives via a default
            - on failure raise `ValueError` whose message contains the
              parameter name and the offending value's repr
            - defaults must be validated too
            - naming a parameter that does not exist raises `TypeError` at
              **decoration** time, not call time
            - the wrapper must preserve `__name__`, `__doc__` and the
              signature (`inspect.signature` on the wrapper must equal the
              signature of the original)
            - it must work with positional-only, keyword-only, `*args` and
              `**kwargs` functions; a rule naming a `*args` or `**kwargs`
              parameter applies to *each* collected value
            """,
            starter="""
            import functools
            import inspect


            def validated(**rules):
                ...
            """,
            checks=[
                Check("rejects bad positional and keyword args",
                      lambda ns: _va_basic(ns["validated"])),
                Check("validates defaults too", lambda ns: _va_defaults(ns["validated"])),
                Check("error message names the parameter and value",
                      lambda ns: _va_message(ns["validated"])),
                Check("unknown parameter fails at decoration time",
                      lambda ns: _va_unknown(ns["validated"])),
                Check("metadata and signature preserved", lambda ns: _va_metadata(ns["validated"])),
                Check("handles keyword-only and positional-only params",
                      lambda ns: _va_kinds(ns["validated"])),
                Check("applies elementwise to *args and **kwargs",
                      lambda ns: _va_varargs(ns["validated"])),
                Check("valid calls pass through untouched", lambda ns: _va_passthrough(ns["validated"])),
            ],
            hints=(
                "`inspect.signature(fn).bind(*args, **kwargs)` then "
                "`.apply_defaults()` normalises every calling style into one dict.",
                "Check the rule names against `sig.parameters` inside the decorator "
                "body — that code runs at decoration time.",
                "`bound.arguments['args']` is a tuple and "
                "`bound.arguments['kwargs']` is a dict; look at "
                "`param.kind` to know which case you are in.",
                "`functools.wraps` copies `__name__`/`__doc__` and sets "
                "`__wrapped__`, which is what makes `inspect.signature` follow "
                "through to the original.",
            ),
            solution="""
            import functools
            import inspect

            def validated(**rules):
                def decorate(fn):
                    sig = inspect.signature(fn)
                    unknown = set(rules) - set(sig.parameters)
                    if unknown:
                        raise TypeError(
                            f"{fn.__name__}() has no parameter(s): {sorted(unknown)}"
                        )

                    @functools.wraps(fn)
                    def wrapper(*args, **kwargs):
                        bound = sig.bind(*args, **kwargs)
                        bound.apply_defaults()
                        for name, predicate in rules.items():
                            kind = sig.parameters[name].kind
                            value = bound.arguments.get(name)
                            if kind is inspect.Parameter.VAR_POSITIONAL:
                                candidates = list(value or ())
                            elif kind is inspect.Parameter.VAR_KEYWORD:
                                candidates = list((value or {}).values())
                            else:
                                candidates = [value]
                            for item in candidates:
                                if not predicate(item):
                                    raise ValueError(
                                        f"{fn.__name__}(): {name}={item!r} failed validation"
                                    )
                        return fn(*args, **kwargs)

                    return wrapper
                return decorate
            """,
        ),
        Exercise(
            slug="curry",
            title="Auto-currying with arity detection",
            difficulty="brutal",
            brief="""
            Implement `curry(fn)`: calling the result with fewer arguments than
            `fn` needs returns a new callable awaiting the rest.

            - `curry(add3)(1)(2)(3)`, `curry(add3)(1, 2)(3)` and
              `curry(add3)(1)(2, 3)` all produce the same result
            - keyword arguments work and accumulate across partial calls
            - a later call may override an earlier keyword
            - once every **required** parameter is satisfied, the function is
              invoked and the real result returned
            - parameters with defaults are *not* required: `curry(f)(1)` calls
              `f` immediately when only the defaulted parameters remain
            - a function with `*args` is called as soon as its named required
              parameters are satisfied
            - `curry` on a zero-argument function calls it on the first
              invocation: `curry(f)()` → result
            - `__name__` is preserved
            """,
            starter="""
            import functools
            import inspect


            def curry(fn):
                ...
            """,
            checks=[
                Check("one argument at a time", lambda ns: _cy_stepwise(ns["curry"])),
                Check("mixed grouping of arguments", lambda ns: _cy_grouped(ns["curry"])),
                Check("keywords accumulate and override", lambda ns: _cy_kwargs(ns["curry"])),
                Check("defaults are not required", lambda ns: _cy_defaults(ns["curry"])),
                Check("*args functions fire once named params are filled",
                      lambda ns: _cy_varargs(ns["curry"])),
                Check("zero-argument functions", lambda ns: _cy_zero(ns["curry"])),
                Check("name preserved and reusable partials",
                      lambda ns: _cy_reuse(ns["curry"])),
            ],
            hints=(
                "Try `sig.bind(*args, **kwargs)`: if it raises TypeError for "
                "*missing* arguments, you do not have enough yet.",
                "`bind_partial` never complains about missing arguments — use it "
                "to accumulate, and plain `bind` to test for completeness.",
                "Determine 'required' as parameters with no default that are not "
                "VAR_POSITIONAL or VAR_KEYWORD.",
                "Each partial call must return a *new* curried callable holding "
                "the accumulated arguments — never mutate shared state, or two "
                "branches from the same partial will contaminate each other.",
            ),
            solution="""
            import functools
            import inspect

            def curry(fn):
                sig = inspect.signature(fn)
                required = {
                    name for name, p in sig.parameters.items()
                    if p.default is inspect.Parameter.empty
                    and p.kind not in (inspect.Parameter.VAR_POSITIONAL,
                                       inspect.Parameter.VAR_KEYWORD)
                }

                def build(got_args, got_kwargs):
                    @functools.wraps(fn)
                    def collector(*args, **kwargs):
                        new_args = got_args + args
                        new_kwargs = {**got_kwargs, **kwargs}
                        bound = sig.bind_partial(*new_args, **new_kwargs)
                        if required <= set(bound.arguments):
                            return fn(*new_args, **new_kwargs)
                        return build(new_args, new_kwargs)
                    return collector

                return build((), {})
            """,
        ),
        Text("""
        ## Takeaways

        - `/` and `*` in a signature are tools, not decoration: they decide
          what callers may rename and what may collide with `**kwargs`.
        - Defaults evaluate once at `def` time — never make them mutable.
        - A name assigned anywhere in a function is local everywhere in it.
        - Closures share live cells; capture by value with a default argument
          or `partial`.
        - `inspect.signature(...).bind(...)` normalises any calling style into
          one dictionary.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _va_basic(validated) -> None:
    @validated(n=lambda v: v > 0)
    def double(n):
        return n * 2

    assert double(3) == 6
    for call in (lambda: double(-1), lambda: double(n=-1)):
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("a negative value should have been rejected")


def _va_defaults(validated) -> None:
    @validated(n=lambda v: v > 0)
    def f(n=-5):
        return n

    try:
        f()
    except ValueError:
        return
    raise AssertionError("the default value must be validated too")


def _va_message(validated) -> None:
    @validated(width=lambda v: v > 0)
    def area(width, height):
        return width * height

    try:
        area(-3, 4)
    except ValueError as exc:
        text = str(exc)
        assert "width" in text, f"message should name the parameter: {text!r}"
        assert "-3" in text, f"message should include the value: {text!r}"
        return
    raise AssertionError("expected ValueError")


def _va_unknown(validated) -> None:
    try:
        @validated(nope=lambda v: True)
        def f(a):
            return a
    except TypeError:
        return
    raise AssertionError("an unknown parameter name must raise TypeError at decoration")


def _va_metadata(validated) -> None:
    import inspect

    @validated(a=lambda v: True)
    def documented(a, b=2):
        """Doc string."""
        return a + b

    assert documented.__name__ == "documented", f"got {documented.__name__!r}"
    assert documented.__doc__ == "Doc string."
    assert str(inspect.signature(documented)) == "(a, b=2)", (
        f"signature not preserved: {inspect.signature(documented)}"
    )


def _va_kinds(validated) -> None:
    @validated(x=lambda v: v > 0, mode=lambda v: v in {"r", "w"})
    def f(x, /, *, mode="r"):
        return x, mode

    assert f(1) == (1, "r")
    assert f(1, mode="w") == (1, "w")
    try:
        f(1, mode="z")
    except ValueError:
        pass
    else:
        raise AssertionError("keyword-only parameter was not validated")
    try:
        f(-1)
    except ValueError:
        return
    raise AssertionError("positional-only parameter was not validated")


def _va_varargs(validated) -> None:
    @validated(nums=lambda v: isinstance(v, int), opts=lambda v: v is not None)
    def f(*nums, **opts):
        return sum(nums), len(opts)

    assert f(1, 2, 3, flag=True) == (6, 1)
    try:
        f(1, "two")
    except ValueError:
        pass
    else:
        raise AssertionError("*args values must each be validated")
    try:
        f(1, flag=None)
    except ValueError:
        return
    raise AssertionError("**kwargs values must each be validated")


def _va_passthrough(validated) -> None:
    @validated(a=lambda v: True)
    def f(a, b, c=3):
        return (a, b, c)

    assert f(1, 2) == (1, 2, 3)
    assert f(1, b=2, c=9) == (1, 2, 9)


def _cy_stepwise(curry) -> None:
    def add3(a, b, c):
        return a + b + c

    c = curry(add3)
    assert c(1)(2)(3) == 6, "stepwise currying failed"


def _cy_grouped(curry) -> None:
    def add3(a, b, c):
        return a + b + c

    c = curry(add3)
    assert c(1, 2)(3) == 6
    assert c(1)(2, 3) == 6
    assert c(1, 2, 3) == 6, "a complete call should just work"


def _cy_kwargs(curry) -> None:
    def f(a, b, c):
        return f"{a}-{b}-{c}"

    c = curry(f)
    assert c(a=1)(b=2)(c=3) == "1-2-3"
    assert c(1)(c=3)(b=2) == "1-2-3"
    assert c(a=1, b=2)(a=9, c=3) == "9-2-3", "a later keyword should override"


def _cy_defaults(curry) -> None:
    def f(a, b=10):
        return a + b

    assert curry(f)(1) == 11, "a defaulted parameter must not block the call"
    assert curry(f)(1, 2) == 3


def _cy_varargs(curry) -> None:
    def f(a, *rest):
        return (a, rest)

    assert curry(f)(1) == (1, ()), "*args should not be treated as required"
    assert curry(f)(1, 2, 3) == (1, (2, 3))


def _cy_zero(curry) -> None:
    def f():
        return "done"

    assert curry(f)() == "done"


def _cy_reuse(curry) -> None:
    def add3(a, b, c):
        return a + b + c

    c = curry(add3)
    assert c.__name__ == "add3", f"name not preserved: {c.__name__!r}"
    partial_one = c(1)
    branch_a = partial_one(2)
    branch_b = partial_one(20)
    assert branch_a(3) == 6, "a reused partial leaked state between branches"
    assert branch_b(300) == 321, "a reused partial leaked state between branches"
