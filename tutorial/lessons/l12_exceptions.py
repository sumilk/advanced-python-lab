"""Lesson 12 — Exceptions in depth."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=12,
    slug="exceptions",
    title="Exceptions in Depth",
    summary="""
    Exception handling is where sloppy code becomes unmaintainable code. This
    lesson covers the hierarchy and why `BaseException` matters, the exact
    ordering rules of `try/except/else/finally`, implicit and explicit
    chaining, custom exception design, exception groups and `except*` (3.11+),
    and the traceback machinery.
    """,
    tags=("exceptions", "errors", "control-flow", "debugging"),
    blocks=[
        Text("""
        ## The hierarchy, and why `Exception` is not the top

        ```
        BaseException
        ├── SystemExit           (sys.exit)
        ├── KeyboardInterrupt    (Ctrl-C)
        ├── GeneratorExit        (generator .close())
        └── Exception            <- everything you should normally catch
            ├── ArithmeticError, LookupError, OSError, ValueError, TypeError…
            └── your own
        ```

        The three siblings of `Exception` are *control flow*, not errors.
        `except Exception:` deliberately misses them so that Ctrl-C still
        works and generators can still be closed. `except:` (bare) or
        `except BaseException:` catches them too — almost always a bug.
        """),
        Demo(
            code="""
            def risky(kind):
                if kind == "value":
                    raise ValueError("a normal error")
                if kind == "exit":
                    raise SystemExit(1)

            for kind in ("value", "exit"):
                try:
                    risky(kind)
                except Exception as exc:
                    print(f"{kind}: caught {type(exc).__name__}")
                except BaseException as exc:
                    print(f"{kind}: escaped Exception, caught {type(exc).__name__} at BaseException")

            # Ordering matters -- the FIRST matching clause wins.
            try:
                {}["missing"]
            except LookupError as exc:
                print("LookupError caught the KeyError:", type(exc).__name__)
            except KeyError:
                print("this clause is unreachable")
            """,
            explain="""
            Always order `except` clauses most-specific first. Python does not
            warn you about an unreachable clause shadowed by its own base
            class.
            """,
        ),
        Text("""
        ## `try / except / else / finally`

        - `else` runs only when **no** exception occurred — put the "rest of
          the happy path" there so the `try` block stays as small as possible.
        - `finally` runs **always**: on success, on exception, on `return`, on
          `break`, on `continue`.
        - A `return` in `finally` **discards** any in-flight exception or
          return value. Never do it.
        """),
        Predict(
            code="""
            def f():
                try:
                    return "from try"
                finally:
                    print("finally ran")

            def g():
                try:
                    raise ValueError("lost")
                finally:
                    return "from finally"          # swallows the exception

            print(f())
            print(g())
            """,
            answer="""
            finally ran
            from try
            from finally
            """,
            explain="""
            In `f`, the return value is computed, `finally` runs, then the
            function returns. In `g`, the `return` in `finally` overrides the
            propagating `ValueError` entirely — it vanishes with no trace.
            """,
        ),
        Demo(
            code="""
            def parse(text):
                try:
                    value = int(text)
                except ValueError:
                    print(f"  {text!r}: not a number")
                    return None
                else:
                    # Only runs when int() succeeded -- and errors raised HERE
                    # are not accidentally caught by the except above.
                    print(f"  {text!r}: parsed cleanly")
                    return value
                finally:
                    print(f"  {text!r}: finally")

            print("->", parse("42"))
            print("->", parse("abc"))
            """,
        ),
        Question(
            prompt="Why put code in `else` rather than at the end of the `try` block?",
            choices=[
                "It runs faster",
                "So exceptions from that code are not accidentally caught by the `except` clauses",
                "`else` is required whenever you use `except`",
                "It runs even when an exception occurred",
            ],
            answer=1,
            explain="A narrow `try` catches only what you meant to catch. Code in "
                    "`else` runs in the success path but outside the handler's reach.",
        ),
        Text("""
        ## Chaining: `__cause__`, `__context__`, `__suppress_context__`

        - Raising inside an `except` block sets `__context__` automatically →
          *"During handling of the above exception, another occurred"*.
        - `raise New() from original` sets `__cause__` → *"The above exception
          was the direct cause"*. Use it when you deliberately translate.
        - `raise New() from None` suppresses the context entirely — for when
          the internal error would only confuse the caller.
        """),
        Demo(
            code="""
            import traceback

            class ConfigError(Exception):
                pass

            def show(fn):
                try:
                    fn()
                except Exception as exc:
                    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
                    joined = "".join(lines)
                    for marker in ("During handling", "direct cause"):
                        if marker in joined:
                            print(f"  -> traceback says: '{marker}...'")
                    print(f"  __cause__={type(exc.__cause__).__name__ if exc.__cause__ else None}"
                          f"  __context__={type(exc.__context__).__name__ if exc.__context__ else None}"
                          f"  suppress={exc.__suppress_context__}")

            def implicit():
                try:
                    int("x")
                except ValueError:
                    raise ConfigError("bad config")

            def explicit():
                try:
                    int("x")
                except ValueError as exc:
                    raise ConfigError("bad config") from exc

            def suppressed():
                try:
                    int("x")
                except ValueError:
                    raise ConfigError("bad config") from None

            for name, fn in (("implicit", implicit), ("explicit", explicit),
                             ("suppressed", suppressed)):
                print(name + ":")
                show(fn)
            """,
            explain="""
            `from exc` is not cosmetic: it tells the reader *this* error was
            caused by *that* one, rather than "something else broke while I was
            handling the first thing". Libraries that translate errors should
            always use it.
            """,
        ),
        Text("""
        ## Designing your own exceptions

        - Give your package **one base class** so users can catch everything
          from you with a single clause.
        - Subclass the most specific stdlib class that fits (`ValueError`,
          `LookupError`, `OSError`) so existing handlers keep working.
        - Carry structured data as attributes, not only in the message.
        - Keep `__init__` compatible with `args` so the exception stays
          picklable — a real issue with `multiprocessing`.
        """),
        Demo(
            code="""
            class AppError(Exception):
                '''Base for everything this package raises.'''

            class ValidationError(AppError, ValueError):
                def __init__(self, field, value, reason="invalid"):
                    super().__init__(f"{field}={value!r}: {reason}")
                    self.field, self.value, self.reason = field, value, reason

            err = ValidationError("age", -1, "must be positive")
            print("message   :", err)
            print("structured:", err.field, err.value, err.reason)
            print("caught as ValueError:", isinstance(err, ValueError))
            print("caught as AppError  :", isinstance(err, AppError))

            print()
            # Reconstructability: pickle and copy rebuild an exception by
            # calling type(exc)(*exc.args). Check it yourself with __reduce__.
            class Broken(Exception):
                def __init__(self, a, b):
                    super().__init__(f"{a} and {b}")     # args is now a 1-tuple
                    self.a, self.b = a, b

            class Fixed(Exception):
                def __init__(self, a, b):
                    super().__init__(a, b)               # args == (a, b)
                    self.a, self.b = a, b
                def __str__(self): return f"{self.a} and {self.b}"

            for cls in (Broken, Fixed):
                exc = cls(1, 2)
                # __reduce__ gives (callable, args) plus optional instance state
                factory, args, *state = exc.__reduce__()
                print(f"{cls.__name__:7} args={exc.args!r}")
                try:
                    print(f"        rebuilt -> {factory(*args)}")
                except TypeError as err:
                    print(f"        rebuild FAILS -> TypeError: {err}")
            """,
            explain="""
            `BaseException.__reduce__` returns `(type(self), self.args)`, so
            anything that copies or pickles your exception calls
            `Cls(*args)`. If `__init__` passes a *formatted string* to
            `super().__init__`, `args` no longer matches the signature and the
            rebuild fails — typically deep inside `multiprocessing`, with a
            baffling traceback.
            """,
        ),
        Text("""
        ## Exception groups and `except*` (3.11+)

        When several independent operations fail — a `TaskGroup`, a batch of
        validations — you want to report *all* of them. `ExceptionGroup`
        wraps them; `except*` matches **by type across the group**, running
        each matching clause once with a sub-group.
        """),
        Demo(
            min_version=(3, 11),
            code="""
            def validate_all(record):
                errors = []
                if not record.get("name"):
                    errors.append(ValueError("name is required"))
                if record.get("age", 0) < 0:
                    errors.append(ValueError("age must be non-negative"))
                if not isinstance(record.get("tags", []), list):
                    errors.append(TypeError("tags must be a list"))
                if errors:
                    raise ExceptionGroup("validation failed", errors)
                return record

            try:
                validate_all({"name": "", "age": -5, "tags": "oops"})
            except* ValueError as group:
                print("ValueError clause saw:", [str(e) for e in group.exceptions])
            except* TypeError as group:
                print("TypeError clause saw:", [str(e) for e in group.exceptions])

            print()
            # Both clauses ran. A group can also be inspected directly:
            try:
                validate_all({"name": "", "age": -1})
            except ExceptionGroup as group:
                print("group message:", group.message)
                print("count:", len(group.exceptions))
                matched, rest = group.split(ValueError)
                print("split -> matched:", len(matched.exceptions),
                      "| rest:", rest)
            """,
            explain="""
            Key differences from plain `except`: every matching `except*`
            clause runs (not just the first), the bound name is always a
            *group*, and unmatched exceptions propagate onward in a residual
            group. `group.split(T)` and `group.subgroup(T)` let you filter
            programmatically.
            """,
        ),
        Demo(
            min_version=(3, 11),
            code="""
            # add_note (3.11) attaches context without changing the exception type.
            def load(path):
                try:
                    raise FileNotFoundError(path)
                except FileNotFoundError as exc:
                    exc.add_note(f"searched in: /etc, /usr/local/etc")
                    exc.add_note("hint: run `app init` to create it")
                    raise

            try:
                load("app.conf")
            except FileNotFoundError as exc:
                print(type(exc).__name__, exc)
                for note in exc.__notes__:
                    print("  note:", note)
            """,
        ),
        Question(
            prompt="How does `except*` differ from `except` for an ExceptionGroup?",
            choices=[
                "Only the first matching clause runs, as usual",
                "Every matching clause runs, each receiving a sub-group of the matches",
                "It catches only exceptions raised inside `async` functions",
                "It flattens the group into a single exception",
            ],
            answer=1,
            explain="`except*` is designed for concurrent failure: several unrelated "
                    "error types can be handled in one pass, each with all its instances.",
        ),
        Text("""
        ## Tracebacks and the `traceback` module

        `exc.__traceback__` is a linked list of frames. Useful tools:

        - `traceback.format_exception(exc)` → the list of strings Python
          would print
        - `traceback.print_exc()` → print the exception being handled
        - `exc.with_traceback(tb)` → attach a different traceback
        - `raise` (bare) inside `except` → re-raise preserving the traceback;
          `raise exc` **appends** the current frame instead
        """),
        Demo(
            code="""
            import traceback

            def level_three(): raise RuntimeError("deep failure")
            def level_two(): level_three()
            def level_one(): level_two()

            try:
                level_one()
            except RuntimeError as exc:
                frames = traceback.extract_tb(exc.__traceback__)
                print("frames:", [f.name for f in frames])
                print("deepest line:", frames[-1].line)
                print()
                print("".join(traceback.format_exception_only(type(exc), exc)).strip())

            # bare raise vs raise exc
            def reraise_bare():
                try:
                    level_one()
                except RuntimeError:
                    raise

            def reraise_named():
                try:
                    level_one()
                except RuntimeError as exc:
                    raise exc

            for fn in (reraise_bare, reraise_named):
                try:
                    fn()
                except RuntimeError as exc:
                    depth = len(traceback.extract_tb(exc.__traceback__))
                    print(f"{fn.__name__:16} traceback depth = {depth}")
            """,
        ),
        Text("""
        ## Anti-patterns worth naming

        - `except: pass` — swallows `KeyboardInterrupt` and every bug. Use
          `contextlib.suppress(SpecificError)`.
        - Catching broadly and re-raising a bare `Exception("failed")` —
          destroys the type and the traceback.
        - Using exceptions for ordinary control flow in hot loops — a `try` is
          cheap to *enter* but raising is not.
        - Logging *and* re-raising at every level — one entry per error is
          enough; log where you handle it.
        """),
        Demo(
            code="""
            import timeit

            data = {"present": 1}

            def with_exception():
                try:
                    return data["absent"]
                except KeyError:
                    return None

            def with_check():
                return data.get("absent")

            def happy_exception():
                try:
                    return data["present"]
                except KeyError:
                    return None

            n = 200_000
            for label, fn in (("raise+catch  ", with_exception),
                              ("dict.get     ", with_check),
                              ("try, no raise", happy_exception)):
                t = timeit.timeit(fn, number=n)
                print(f"{label}: {t/n*1e9:6.0f} ns/call")
            """,
            explain="""
            Entering a `try` is nearly free (zero-cost exceptions since 3.11).
            *Raising* costs on the order of a microsecond. "Easier to ask
            forgiveness" is idiomatic when the exception is genuinely
            exceptional; in a tight loop where failure is common, check first.
            """,
        ),
        Exercise(
            slug="error-context",
            title="An error-collecting context manager",
            difficulty="tricky",
            brief="""
            Write `collect_errors(label)` — a context manager that gathers
            multiple failures instead of stopping at the first one.

            - inside the block, `ctx.attempt(fn, *args)` runs `fn` and, if it
              raises, records the exception and returns `None`; a success
              returns the value
            - `ctx.errors` is the list of recorded exceptions
            - on exit, if anything was recorded, raise an `ExceptionGroup`
              whose message is `label` containing every recorded exception
            - if the body itself raises, that exception propagates immediately
              and no group is raised
            - `ctx.ok` → True when nothing was recorded
            - `attempt` must not swallow `KeyboardInterrupt` or `SystemExit`
            - a `catch=` argument limits which types are recorded; anything
              else propagates out of `attempt`
            """,
            starter="""
            from contextlib import contextmanager


            class Collector:
                def __init__(self, label, catch=(Exception,)):
                    ...


            @contextmanager
            def collect_errors(label, catch=(Exception,)):
                ...
            """,
            checks=[
                Check("clean block raises nothing", lambda ns: _ce_clean(ns)),
                Check("attempt returns values and None", lambda ns: _ce_values(ns)),
                Check("collected failures become an ExceptionGroup", lambda ns: _ce_group(ns)),
                Check("group message is the label", lambda ns: _ce_label(ns)),
                Check("a body exception propagates alone", lambda ns: _ce_body(ns)),
                Check("BaseException is never swallowed", lambda ns: _ce_base(ns)),
                Check("catch= narrows what is recorded", lambda ns: _ce_catch(ns)),
                Check("ok reflects the state", lambda ns: _ce_ok(ns)),
            ],
            hints=(
                "`except self.catch as exc:` inside `attempt` — and since "
                "`KeyboardInterrupt` is not an `Exception`, the default already "
                "excludes it.",
                "Raise the group *after* the `yield` returns normally, so a body "
                "exception skips it.",
                "`ExceptionGroup(label, errors)` requires a non-empty list — guard "
                "the empty case.",
                "Use `try/finally` carefully here: you want the group raised only "
                "on the success path, which is what `else` gives you.",
            ),
            solution="""
            from contextlib import contextmanager

            class Collector:
                def __init__(self, label, catch=(Exception,)):
                    self.label = label
                    self.catch = catch
                    self.errors = []

                def attempt(self, fn, *args, **kwargs):
                    try:
                        return fn(*args, **kwargs)
                    except self.catch as exc:
                        self.errors.append(exc)
                        return None

                @property
                def ok(self):
                    return not self.errors

            @contextmanager
            def collect_errors(label, catch=(Exception,)):
                collector = Collector(label, catch)
                yield collector
                if collector.errors:
                    raise ExceptionGroup(label, collector.errors)
            """,
        ),
        Text("""
        ## Takeaways

        - Catch `Exception`, not `BaseException`, and order clauses
          specific-first.
        - `else` keeps the `try` narrow; never `return` from `finally`.
        - `raise X from original` when translating; `from None` to hide noise.
        - Give your package one base exception and structured attributes.
        - `ExceptionGroup` + `except*` handle many simultaneous failures.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _ce_clean(ns) -> None:
    collect_errors = ns["collect_errors"]
    with collect_errors("nothing wrong") as ctx:
        ctx.attempt(lambda: 1)
    assert ctx.errors == [], ctx.errors


def _ce_values(ns) -> None:
    collect_errors = ns["collect_errors"]
    try:
        with collect_errors("mixed") as ctx:
            good = ctx.attempt(lambda x: x * 2, 21)
            bad = ctx.attempt(lambda: 1 / 0)
            assert good == 42, f"a successful attempt should return its value, got {good!r}"
            assert bad is None, f"a failed attempt should return None, got {bad!r}"
    except ExceptionGroup:
        return
    raise AssertionError("the recorded failure should have produced a group")


def _ce_group(ns) -> None:
    collect_errors = ns["collect_errors"]
    try:
        with collect_errors("batch") as ctx:
            ctx.attempt(lambda: 1 / 0)
            ctx.attempt(lambda: {}["nope"])
            ctx.attempt(lambda: int("x"))
    except ExceptionGroup as group:
        kinds = sorted(type(e).__name__ for e in group.exceptions)
        assert kinds == ["KeyError", "ValueError", "ZeroDivisionError"], kinds
        assert len(ctx.errors) == 3
        return
    raise AssertionError("expected an ExceptionGroup")


def _ce_label(ns) -> None:
    collect_errors = ns["collect_errors"]
    try:
        with collect_errors("my label") as ctx:
            ctx.attempt(lambda: 1 / 0)
    except ExceptionGroup as group:
        assert group.message == "my label", f"got {group.message!r}"
        return
    raise AssertionError("expected an ExceptionGroup")


def _ce_body(ns) -> None:
    collect_errors = ns["collect_errors"]
    try:
        with collect_errors("body") as ctx:
            ctx.attempt(lambda: 1 / 0)
            raise RuntimeError("the body itself failed")
    except ExceptionGroup:
        raise AssertionError("a body exception must propagate as itself, not as a group")
    except RuntimeError as exc:
        assert str(exc) == "the body itself failed"
        return
    raise AssertionError("expected RuntimeError")


def _ce_base(ns) -> None:
    collect_errors = ns["collect_errors"]

    def interrupt():
        raise KeyboardInterrupt

    try:
        with collect_errors("base") as ctx:
            ctx.attempt(interrupt)
    except KeyboardInterrupt:
        return
    except ExceptionGroup:
        raise AssertionError("KeyboardInterrupt must never be recorded")
    raise AssertionError("KeyboardInterrupt should have propagated")


def _ce_catch(ns) -> None:
    collect_errors = ns["collect_errors"]
    try:
        with collect_errors("narrow", catch=(ValueError,)) as ctx:
            ctx.attempt(lambda: int("x"))          # recorded
            ctx.attempt(lambda: 1 / 0)             # must propagate
    except ZeroDivisionError:
        assert len(ctx.errors) == 1, ctx.errors
        assert isinstance(ctx.errors[0], ValueError)
        return
    raise AssertionError("an uncaught type must propagate out of attempt()")


def _ce_ok(ns) -> None:
    collect_errors = ns["collect_errors"]
    with collect_errors("fine") as ctx:
        assert ctx.ok is True
        ctx.attempt(lambda: 1)
        assert ctx.ok is True
    try:
        with collect_errors("bad") as ctx2:
            ctx2.attempt(lambda: 1 / 0)
            assert ctx2.ok is False
    except ExceptionGroup:
        pass
