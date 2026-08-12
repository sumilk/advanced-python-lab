# 16 — Modules, Packages, and Imports

Imports look simple until a circular dependency, a shadowed stdlib name,
or a mysterious "module has no attribute" ruins an afternoon. This lesson
explains what `import` actually does, how `sys.modules` caching shapes
program behaviour, why circular imports fail *where* they do, and how to
lay a package out so none of it bites.

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

```python
import sys
import types

print("modules already loaded:", len(sys.modules))
print("first five paths:")
for entry in sys.path[:5]:
    print("   ", entry or "(cwd)")

# A module is just an object with a __dict__.
mod = types.ModuleType("synthetic")
exec("VALUE = 42\ndef greet(): return 'hi'", mod.__dict__)
sys.modules["synthetic"] = mod

import synthetic
print("imported the synthetic module:", synthetic.VALUE, synthetic.greet())
print("same object:", synthetic is mod)
del sys.modules["synthetic"]
```

```python
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
```
Module-level state is process-global singleton state. That is why
"just use a module-level dict" is the simplest singleton in
Python — and why mutable module globals make testing painful.

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

```python
import sys
import types

target = types.ModuleType("target")
exec("counter = 0\ndef report(): return f'counter={counter}'", target.__dict__)
sys.modules["target"] = target

from target import counter, report      # snapshot of counter
import target as mod

target.counter = 99                     # rebind inside the module

print("copied name  :", counter, " <- stale")
print("via module   :", mod.counter)
print("function sees:", report(), " <- reads the module global at call time")

del sys.modules["target"]
```
The function stays correct because it looks `counter` up in its
`__globals__` when called. Your imported *name* was bound once.
Import the **module** when the value may change (or when
monkeypatching in tests).

**Quiz.** You `from config import DEBUG`, then a test sets `config.DEBUG = True`. What does your name see?

- a) `True` — names are references to the module attribute
- b) The old value — `from x import y` copies the binding at import time
- c) It raises, because the module is frozen
- d) It depends on whether `DEBUG` is mutable

<details><summary>answer</summary>

**b** — Import the module (`import config`) and read `config.DEBUG` at use time, or patch the exact name the code under test uses.
</details>

## Packages, `__init__.py`, and `__all__`

A **package** is a directory Python treats as a module. With an
`__init__.py` it is a *regular* package: that file runs on first
import and its namespace is the package's namespace. Without one it
is a *namespace package* (PEP 420) — usable, but with no init hook
and split across `sys.path` entries.

`__all__` controls `from pkg import *` **and** documents the public
API. Without it, `import *` grabs every name not starting with `_`,
including your imports.

```python
import sys
import types

# Build a small package in memory to show the mechanics.
pkg = types.ModuleType("demo_pkg")
pkg.__path__ = []                       # marks it as a package
exec("__all__ = ['public']\npublic = 'exported'\n_private = 'hidden'\n"
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
```

## Circular imports

Because a module is registered in `sys.modules` *before* its body
runs, a cycle gives you a **partially initialised** module. Whether it
works depends entirely on *when* you touch the missing name:

- `import b` inside `a` — usually fine; you only need the module object
- `from b import thing` inside `a` — fails if `b` has not yet defined
  `thing` at that point
- using `b.thing` **inside a function** — always fine, because it
  resolves at call time

```python
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
```
Real fixes, in order of preference:

1. **Extract the shared thing** into a third module both import.
2. **Import the module, not the name**, and use `b.thing` inside
   functions.
3. Move the import **inside the function** that needs it.
4. `if TYPE_CHECKING:` for imports needed only by annotations.

```python
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
```

**Quiz.** Which import style survives a circular dependency most reliably?

- a) `from b import thing` at the top of the module
- b) `import b` at the top, using `b.thing` inside functions
- c) `from b import *`
- d) All import styles behave identically

<details><summary>answer</summary>

**b** — The module object exists from the moment the import starts; only its *contents* fill in later. Deferring the attribute access to call time sidesteps the ordering problem entirely.
</details>

## `__name__`, `__main__`, and the double-import trap

A module's `__name__` is its import name — except the one you ran
directly, which gets `"__main__"`. Running `python pkg/mod.py` and
also importing `pkg.mod` elsewhere loads the file **twice** under two
names, with two copies of every class. Use `python -m pkg.mod`.

```python
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
```

## Import hooks and lazy loading

`sys.meta_path` holds finders consulted in order. Adding your own lets
you import from a database, a zip, or generate modules on demand.
`importlib.util.LazyLoader` defers module execution until first
attribute access — worth knowing for CLI start-up time.

```python
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
```
This is the machinery behind import-from-zip, `.pyc`-only
distributions, pytest's assertion rewriting, and lazy imports.
You rarely write one — but knowing it exists demystifies a lot of
"how did that library do that?".

```python
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
```

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

```python
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
```

## Exercise — A lazy attribute loader with module __getattr__ `[tricky]`

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
```python
import sys
import types


def make_lazy_module(name, providers):
    ...


def unload(module):
    ...
```

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
