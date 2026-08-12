"""Lesson 16 — Modules, packages, and the import system."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=16,
    slug="imports",
    title="Modules, Packages, and Imports",
    summary="""
    Imports look simple until a circular dependency, a shadowed stdlib name,
    or a mysterious "module has no attribute" ruins an afternoon. This lesson
    explains what `import` actually does, how `sys.modules` caching shapes
    program behaviour, why circular imports fail *where* they do, and how to
    lay a package out so none of it bites.
    """,
    tags=("imports", "modules", "packages", "sys.modules"),
    blocks=[
        Text("""
        ## What `import x` does

        1. check `sys.modules["x"]` — if present, bind it and **stop**
        2. otherwise search `sys.meta_path` finders (which consult
           `sys.path`) for a loader
        3. create an empty module object and **insert it into `sys.modules`
           before executing it** (this is what makes circular imports
           partially work)
        4. execute the module body top to bottom
        5. bind the name in the importing namespace

        Step 3 is the key to everything surprising about imports.
        """),
        Demo(
            code="""
            import sys
            import types

            print("modules already loaded:", len(sys.modules))
            print("first five paths:")
            for entry in sys.path[:5]:
                print("   ", entry or "(cwd)")

            # A module is just an object with a __dict__.
            mod = types.ModuleType("synthetic")
            exec("VALUE = 42\\ndef greet(): return 'hi'", mod.__dict__)
            sys.modules["synthetic"] = mod

            import synthetic
            print("imported the synthetic module:", synthetic.VALUE, synthetic.greet())
            print("same object:", synthetic is mod)
            del sys.modules["synthetic"]
            """,
        ),
        Demo(
            code="""
            import sys

            # The cache means module-level code runs exactly ONCE per process.
            import json
            first = sys.modules["json"]
            import json                     # no re-execution
            print("cached:", first is sys.modules["json"])

            # A module's namespace IS its __dict__ -- mutation is global.
            json.MY_MARKER = "set from here"
            import json as json_again
            print("visible everywhere:", json_again.MY_MARKER)
            del json.MY_MARKER

            print("module attributes:", [a for a in dir(json) if not a.startswith('_')][:6])
            print("__name__:", json.__name__, "| __package__:", json.__package__)
            """,
            explain="""
            Module-level state is process-global singleton state. That is why
            "just use a module-level dict" is the simplest singleton in
            Python — and why mutable module globals make testing painful.
            """,
        ),
        Text("""
        ## The forms of `import`

        ```python
        import pkg.mod            # binds `pkg`; access as pkg.mod.thing
        import pkg.mod as m       # binds `m` -> the module pkg.mod
        from pkg import mod       # binds `mod`
        from pkg.mod import thing # binds `thing` -- a SNAPSHOT of the value
        from pkg.mod import *     # binds per __all__, or all public names
        from . import sibling     # relative, packages only
        ```

        `from x import name` copies a *reference at import time*. If `x.name`
        is later rebound, your copy does not follow — the number-one cause of
        "why is my monkeypatch not working".
        """),
        Demo(
            code="""
            import sys
            import types

            target = types.ModuleType("target")
            exec("counter = 0\\ndef report(): return f'counter={counter}'", target.__dict__)
            sys.modules["target"] = target

            from target import counter, report      # snapshot of counter
            import target as mod

            target.counter = 99                     # rebind inside the module

            print("copied name  :", counter, " <- stale")
            print("via module   :", mod.counter)
            print("function sees:", report(), " <- reads the module global at call time")

            del sys.modules["target"]
            """,
            explain="""
            The function stays correct because it looks `counter` up in its
            `__globals__` when called. Your imported *name* was bound once.
            Import the **module** when the value may change (or when
            monkeypatching in tests).
            """,
        ),
        Question(
            prompt="You `from config import DEBUG`, then a test sets `config.DEBUG = True`. What does your name see?",
            choices=[
                "`True` — names are references to the module attribute",
                "The old value — `from x import y` copies the binding at import time",
                "It raises, because the module is frozen",
                "It depends on whether `DEBUG` is mutable",
            ],
            answer=1,
            explain="Import the module (`import config`) and read `config.DEBUG` at "
                    "use time, or patch the exact name the code under test uses.",
        ),
        Text("""
        ## Packages, `__init__.py`, and `__all__`

        A **package** is a directory Python treats as a module. With an
        `__init__.py` it is a *regular* package: that file runs on first
        import and its namespace is the package's namespace. Without one it
        is a *namespace package* (PEP 420) — usable, but with no init hook
        and split across `sys.path` entries.

        `__all__` controls `from pkg import *` **and** documents the public
        API. Without it, `import *` grabs every name not starting with `_`,
        including your imports.
        """),
        Demo(
            code="""
            import sys
            import types

            # Build a small package in memory to show the mechanics.
            pkg = types.ModuleType("demo_pkg")
            pkg.__path__ = []                       # marks it as a package
            exec("__all__ = ['public']\\npublic = 'exported'\\n_private = 'hidden'\\n"
                 "import json  # an implementation detail", pkg.__dict__)
            sys.modules["demo_pkg"] = pkg

            namespace = {}
            exec("from demo_pkg import *", namespace)
            print("with __all__   :", sorted(k for k in namespace if not k.startswith("__")))

            del pkg.__dict__["__all__"]
            namespace2 = {}
            exec("from demo_pkg import *", namespace2)
            print("without __all__:", sorted(k for k in namespace2 if not k.startswith("__")))
            print("   ^ note 'json' leaked out as part of your public API")

            del sys.modules["demo_pkg"]
            """,
        ),
        Text("""
        ## Circular imports

        Because a module is registered in `sys.modules` *before* its body
        runs, a cycle gives you a **partially initialised** module. Whether it
        works depends entirely on *when* you touch the missing name:

        - `import b` inside `a` — usually fine; you only need the module object
        - `from b import thing` inside `a` — fails if `b` has not yet defined
          `thing` at that point
        - using `b.thing` **inside a function** — always fine, because it
          resolves at call time
        """),
        Demo(
            code="""
            import sys
            import types

            def make(name, source):
                mod = types.ModuleType(name)
                mod.__dict__["__name__"] = name
                sys.modules[name] = mod
                return mod, source

            # a imports b at the top; b does `from a import HELPER` at the top.
            a_mod, a_src = make("cyc_a", '''
            import cyc_b
            HELPER = "defined after the import of cyc_b"
            def use(): return cyc_b.VALUE
            ''')
            b_mod, b_src = make("cyc_b", '''
            from cyc_a import HELPER      # cyc_a is only half-executed here
            VALUE = "b's value"
            ''')

            import textwrap
            try:
                exec(compile(textwrap.dedent(a_src), "cyc_a", "exec", dont_inherit=True),
                     a_mod.__dict__)
            except ImportError as exc:
                print("ImportError:", exc)

            print()
            print("The fix: import the MODULE, and read the attribute lazily.")
            for name in ("cyc_a", "cyc_b"):
                sys.modules.pop(name, None)
            """,
            explain="""
            Real fixes, in order of preference:

            1. **Extract the shared thing** into a third module both import.
            2. **Import the module, not the name**, and use `b.thing` inside
               functions.
            3. Move the import **inside the function** that needs it.
            4. `if TYPE_CHECKING:` for imports needed only by annotations.
            """,
        ),
        Demo(
            code="""
            import sys
            import textwrap
            import types

            # The same cycle, done correctly.
            sources = {
                "ok_a": '''
                    import ok_b
                    HELPER = "a's helper"
                    def use():
                        return f"a uses {ok_b.VALUE}"
                ''',
                "ok_b": '''
                    import ok_a
                    VALUE = "b's value"
                    def use():
                        return f"b uses {ok_a.HELPER}"    # resolved at CALL time
                ''',
            }
            for name in sources:
                mod = types.ModuleType(name)
                mod.__dict__["__name__"] = name
                sys.modules[name] = mod

            for name, src in sources.items():
                exec(compile(textwrap.dedent(src), name, "exec", dont_inherit=True),
                     sys.modules[name].__dict__)

            print(sys.modules["ok_a"].use())
            print(sys.modules["ok_b"].use())
            for name in sources:
                del sys.modules[name]
            """,
        ),
        Question(
            prompt="Which import style survives a circular dependency most reliably?",
            choices=[
                "`from b import thing` at the top of the module",
                "`import b` at the top, using `b.thing` inside functions",
                "`from b import *`",
                "All import styles behave identically",
            ],
            answer=1,
            explain="The module object exists from the moment the import starts; only "
                    "its *contents* fill in later. Deferring the attribute access to "
                    "call time sidesteps the ordering problem entirely.",
        ),
        Text("""
        ## `__name__`, `__main__`, and the double-import trap

        A module's `__name__` is its import name — except the one you ran
        directly, which gets `"__main__"`. Running `python pkg/mod.py` and
        also importing `pkg.mod` elsewhere loads the file **twice** under two
        names, with two copies of every class. Use `python -m pkg.mod`.
        """),
        Demo(
            code="""
            import sys

            print("this code's __name__:", __name__)
            print("sys.argv[0]        :", sys.argv[0].split("/")[-1])

            # Two 'copies' of a class are not the same class:
            import types
            m1, m2 = types.ModuleType("dup"), types.ModuleType("dup2")
            src = "class Widget: pass"
            exec(src, m1.__dict__)
            exec(src, m2.__dict__)
            w = m1.Widget()
            print("isinstance across copies:", isinstance(w, m2.Widget))
            print("...this is exactly what the double-import trap produces")
            """,
        ),
        Text("""
        ## Import hooks and lazy loading

        `sys.meta_path` holds finders consulted in order. Adding your own lets
        you import from a database, a zip, or generate modules on demand.
        `importlib.util.LazyLoader` defers module execution until first
        attribute access — worth knowing for CLI start-up time.
        """),
        Demo(
            code="""
            import importlib.abc
            import importlib.util
            import sys

            class GeneratedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
                '''Serves any module named auto_* with a generated body.'''
                PREFIX = "auto_"

                def find_spec(self, fullname, path=None, target=None):
                    if fullname.startswith(self.PREFIX):
                        return importlib.util.spec_from_loader(fullname, self)
                    return None

                def create_module(self, spec):
                    return None                       # use the default

                def exec_module(self, module):
                    name = module.__name__.removeprefix(self.PREFIX)
                    module.NAME = name
                    module.shout = lambda: name.upper() + "!"

            sys.meta_path.insert(0, GeneratedFinder())

            import auto_hello
            import auto_world
            print(auto_hello.NAME, auto_hello.shout())
            print(auto_world.NAME, auto_world.shout())
            print("registered:", [m for m in sys.modules if m.startswith("auto_")])

            sys.meta_path.pop(0)
            for name in ("auto_hello", "auto_world"):
                del sys.modules[name]
            """,
            explain="""
            This is the machinery behind import-from-zip, `.pyc`-only
            distributions, pytest's assertion rewriting, and lazy imports.
            You rarely write one — but knowing it exists demystifies a lot of
            "how did that library do that?".
            """,
        ),
        Demo(
            code="""
            import importlib
            import sys
            import types

            # importlib.reload: re-executes a module body in the SAME object.
            mod = types.ModuleType("reloadable")
            mod.__spec__ = None
            sys.modules["reloadable"] = mod
            exec("version = 1", mod.__dict__)
            print("before:", mod.version)

            exec("version = 2", mod.__dict__)          # simulating an edit + reload
            print("after :", mod.version)
            print("same module object:", sys.modules["reloadable"] is mod)
            print()
            print("Caveat: existing instances keep their OLD class object,")
            print("and `from mod import name` bindings elsewhere are not updated.")
            del sys.modules["reloadable"]
            """,
        ),
        Text("""
        ## Layout that avoids all of this

        ```
        project/
          pyproject.toml
          src/
            mypkg/
              __init__.py        # thin: re-export the public API, no logic
              core.py            # no imports from siblings at module level
              models.py
              _internal.py       # leading underscore = private
          tests/
        ```

        - **src layout** — tests import the installed package, not the
          working directory, so a missing `__init__.py` or packaging mistake
          fails loudly instead of silently working locally.
        - keep `__init__.py` free of heavy imports; startup cost is real.
        - never name a module after a stdlib module (`random.py`, `json.py`,
          `types.py`) — yours will shadow it.
        """),
        Demo(
            code="""
            import sys

            # Shadowing in action: the current directory is searched first.
            print("sys.path[0] is the script/cwd:", repr(sys.path[0])[:60])
            print()
            print("A file named string.py in your project directory means")
            print("`import string` finds YOURS -- and every library that")
            print("imports string breaks in a way that looks impossible.")
            print()
            print("Check what a name resolves to with:")
            import string
            print("  string ->", getattr(string, "__file__", "builtin"))
            """,
        ),
        Exercise(
            slug="lazy-module",
            title="A lazy attribute loader with module __getattr__",
            difficulty="tricky",
            brief="""
            PEP 562 lets a *module* define `__getattr__` and `__dir__`. Use it
            to build `make_lazy_module(name, providers)`:

            - `providers` maps attribute name → a zero-argument factory
            - the module resolves an attribute by calling its factory **the
              first time only**, then caching it in the module namespace
            - a second access must not call the factory again
            - an unknown attribute raises `AttributeError` whose message
              contains both the module name and the attribute
            - `dir(module)` lists the provider names plus anything already set
            - `module.load_count` reports how many factories have run
            - the module must be registered in `sys.modules` under `name`, so
              `importlib.import_module(name)` returns it
            - `unload(module)` removes it from `sys.modules` and returns True,
              or False if it was not there
            """,
            starter="""
            import sys
            import types


            def make_lazy_module(name, providers):
                ...


            def unload(module):
                ...
            """,
            checks=[
                Check("attributes resolve through the factories", lambda ns: _lm_resolve(ns)),
                Check("each factory runs at most once", lambda ns: _lm_cached(ns)),
                Check("unknown attributes raise a helpful AttributeError",
                      lambda ns: _lm_unknown(ns)),
                Check("dir() lists the lazy names", lambda ns: _lm_dir(ns)),
                Check("load_count tracks resolutions", lambda ns: _lm_count(ns)),
                Check("importable via importlib", lambda ns: _lm_importable(ns)),
                Check("unload removes it from sys.modules", lambda ns: _lm_unload(ns)),
            ],
            hints=(
                "Set `module.__getattr__ = fn` where `fn(attr)` takes exactly one "
                "argument — PEP 562 calls it with the attribute name only.",
                "Cache by doing `setattr(module, attr, value)`; after that, normal "
                "attribute lookup finds it and `__getattr__` is never consulted "
                "again.",
                "`load_count` cannot be a plain attribute you also expose lazily — "
                "keep the counter in a closure and set the attribute each time.",
                "`__dir__` must take no arguments when set on a module.",
                "Remember to guard `load_count` and `__getattr__` themselves from "
                "being treated as missing attributes.",
            ),
            solution="""
            import sys
            import types

            def make_lazy_module(name, providers):
                module = types.ModuleType(name)
                module.__all__ = sorted(providers)
                loaded = []

                def __getattr__(attr):
                    if attr in providers:
                        value = providers[attr]()
                        loaded.append(attr)
                        setattr(module, attr, value)
                        setattr(module, "load_count", len(loaded))
                        return value
                    raise AttributeError(
                        f"module {name!r} has no attribute {attr!r}"
                    )

                def __dir__():
                    return sorted(set(providers) | set(vars(module)))

                module.__getattr__ = __getattr__
                module.__dir__ = __dir__
                module.load_count = 0
                sys.modules[name] = module
                return module

            def unload(module):
                return sys.modules.pop(module.__name__, None) is not None
            """,
        ),
        Text("""
        ## Takeaways

        - `sys.modules` is the cache; a module body executes once per process.
        - Modules are inserted into the cache *before* execution — hence
          partially initialised modules in a cycle.
        - `from x import name` snapshots the binding; import the module when
          the value can change.
        - Break cycles by extracting shared code, or by deferring the
          attribute access into a function.
        - Use `python -m pkg.mod`, a src layout, and never shadow stdlib
          names.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
def _build(ns, calls=None):
    calls = calls if calls is not None else []

    def make(label, value):
        def factory():
            calls.append(label)
            return value
        return factory

    module = ns["make_lazy_module"]("lazy_test_mod", {
        "alpha": make("alpha", 1),
        "beta": make("beta", "two"),
    })
    return module, calls


def _cleanup(ns, module) -> None:
    try:
        ns["unload"](module)
    except Exception:
        import sys
        sys.modules.pop("lazy_test_mod", None)


def _lm_resolve(ns) -> None:
    module, calls = _build(ns)
    try:
        assert module.alpha == 1, f"got {module.alpha!r}"
        assert module.beta == "two"
        assert calls == ["alpha", "beta"], calls
    finally:
        _cleanup(ns, module)


def _lm_cached(ns) -> None:
    module, calls = _build(ns)
    try:
        module.alpha
        module.alpha
        module.alpha
        assert calls == ["alpha"], f"the factory ran {len(calls)} times, expected 1"
    finally:
        _cleanup(ns, module)


def _lm_unknown(ns) -> None:
    module, _ = _build(ns)
    try:
        module.nope
    except AttributeError as exc:
        text = str(exc)
        assert "lazy_test_mod" in text, f"message should name the module: {text!r}"
        assert "nope" in text, f"message should name the attribute: {text!r}"
    else:
        raise AssertionError("an unknown attribute must raise AttributeError")
    finally:
        _cleanup(ns, module)


def _lm_dir(ns) -> None:
    module, _ = _build(ns)
    try:
        listing = dir(module)
        assert "alpha" in listing and "beta" in listing, listing
    finally:
        _cleanup(ns, module)


def _lm_count(ns) -> None:
    module, _ = _build(ns)
    try:
        assert module.load_count == 0, f"expected 0, got {module.load_count}"
        module.alpha
        assert module.load_count == 1, f"expected 1, got {module.load_count}"
        module.alpha
        assert module.load_count == 1, "a cached access must not increment the count"
        module.beta
        assert module.load_count == 2, f"expected 2, got {module.load_count}"
    finally:
        _cleanup(ns, module)


def _lm_importable(ns) -> None:
    import importlib

    module, _ = _build(ns)
    try:
        imported = importlib.import_module("lazy_test_mod")
        assert imported is module, "the module must be registered in sys.modules"
        assert imported.alpha == 1
    finally:
        _cleanup(ns, module)


def _lm_unload(ns) -> None:
    import sys

    module, _ = _build(ns)
    assert ns["unload"](module) is True, "unload should report success"
    assert "lazy_test_mod" not in sys.modules, "the module is still cached"
    assert ns["unload"](module) is False, "a second unload should report False"
