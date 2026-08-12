# Python: Intermediate → Advanced

A hands-on course covering the parts of Python that stop being obvious: the
data model, descriptors, the MRO, generators as coroutines, the GIL, asyncio,
the AST.

**22 lessons · 33 graded exercises · 45 quiz questions · 5 capstone projects**

📖 **[Read the course](https://sumilk.github.io/Python_tutorial/)** —
every code sample executed at build time, quizzes interactive.

📓 **[Browse the notebooks](https://github.com/sumilk/Python_tutorial/tree/main/notebooks)**
— [start here](https://github.com/sumilk/Python_tutorial/blob/main/notebooks/00-START-HERE.ipynb),
or read them on
[nbviewer](https://nbviewer.org/github/sumilk/Python_tutorial/tree/main/notebooks/).
To *run* them (and grade your work), clone the repo — the exercises are
graded by the package next to them:

```bash
git clone https://github.com/sumilk/Python_tutorial && cd Python_tutorial
uv run --with jupyterlab jupyter lab notebooks/
```

Everything is written once as structured data and rendered three ways —
Jupyter notebooks, an interactive terminal app, and a static site — so all
three front-ends stay in step and grade against the same test suite.

## Quick start

```bash
uv run learn.py                 # interactive terminal course
uv run learn.py notebooks       # generate notebooks/, then open in Jupyter
uv run learn.py site            # build site/index.html
uv run pytest                   # validate the whole course
```

`notebooks/` and `docs/` are checked in — they rebuild byte-for-byte
identically, so diffs stay clean. `site/` is not: it bakes executed output
into the page, so `timeit` numbers and object sizes churn on every build.

```bash
uv run learn.py notebooks       # skips notebooks you have edited
uv run learn.py notebooks --force
uv run learn.py export docs
```

No manual setup: `uv` provisions Python 3.12 and the dev dependencies on the
first run.

## The three front-ends

### Notebooks — the recommended way to work through it

```bash
uv run learn.py notebooks
uv run --with jupyterlab jupyter lab notebooks/
```

One `.ipynb` per lesson. Prose becomes markdown, demos become runnable cells,
and each exercise is an editable cell followed by a grading cell:

```python
check("09-descriptors/validated-field")
# ✓ stores and retrieves per instance
# ✓ type checking, with the int/float and bool rules
# ✗ validation order: type before range — expected TypeError
```

Hints and reference solutions sit in collapsed `<details>` blocks.
Start at `notebooks/00-START-HERE.ipynb`.

`notebooks/` is committed, so a fresh clone is usable immediately and GitHub
renders every lesson inline. Regenerating **will not overwrite work you have
done** — a notebook you have edited is skipped and reported:

```
✓ wrote 22 notebooks
! left 1 edited notebook(s) untouched:
    notebooks/05-iterators.ipynb
ℹ pass --force to overwrite them
```

### Terminal

```bash
uv run learn.py                          # menu with progress
uv run learn.py lesson 9                 # jump to one lesson
uv run learn.py list                     # curriculum + every exercise id
uv run learn.py quiz 20                  # mixed exam across all lessons
uv run learn.py check 07-decorators/retry
uv run learn.py projects                 # capstone projects
uv run learn.py reset                    # wipe progress
```

Lessons are paged, demos execute live, quizzes are answered inline, and
exercises are written to `workspace/<lesson>/<exercise>.py` for you to edit
and grade on demand.

### Static site

```bash
uv run learn.py site      # -> site/index.html, one self-contained file
```

Published at **<https://sumilk.github.io/Python_tutorial/>**.

A reading copy of the whole course. Every code sample is **executed while the
page is built**, so the output panels show real transcripts rather than
illustrations. Quizzes stay interactive; exercises are read-only there.

`.github/workflows/pages.yml` rebuilds and redeploys it on every push to
`main` — but only after `uv run pytest` passes, so a broken lesson never
reaches the published page.

`site/index.html` is fully self-contained, so `open site/index.html` is
usually all you need.

#### Serving it over HTTP

Useful when you want it on a real origin — sharing it on your LAN, or
auto-reloading while you edit a lesson.

```bash
# no dependencies at all
uv run python -m http.server -d site 8000

# with uvicorn, which adds --reload
uv add --dev uvicorn                                    # install it once
uv run uvicorn serve:app --reload --port 8000

# or without touching the project's dependencies
uv run --with uvicorn uvicorn serve:app --reload --port 8000
```

`serve.py` is a ~40-line ASGI app — no framework — that serves the `site/`
directory and refuses paths outside it. Worth a read if you have never seen
the raw ASGI protocol: `scope` is the request, `receive` pulls request
events, `send` pushes response events.

> `uvicorn` is optional. It is an ASGI server, so it cannot serve static
> files by itself; `serve.py` is the small app it runs. If you only want to
> read the site, skip both and open the file.

Progress is shared: solving an exercise in the notebook or the terminal
records it in `.progress.json` either way.

## Curriculum

| # | Lesson | Topics |
|---|---|---|
| 01 | Names, Objects, and Identity | binding vs mutation, `is` vs `==`, copying, hashability |
| 02 | The Data Model — Dunder Protocols | `__repr__`, eq/hash contract, containers, operators, `NotImplemented` |
| 03 | Sequences, Slicing, and Containers | slice assignment, sorting, dict/set internals, `collections` |
| 04 | Comprehensions and Lazy Evaluation | scoping, class-body pitfall, walrus, genexp laziness |
| 05 | Iterators and Generators | the protocol, `send`/`throw`/`close`, `yield from`, pipelines |
| 06 | Functions, Scope, and Closures | `/` and `*`, mutable defaults, LEGB, cells, `inspect.signature` |
| 07 | Decorators | `functools.wraps`, parametrised, stacking, class-based, stdlib set |
| 08 | Classes, MRO, and `super()` | attribute lookup, C3 by hand, cooperative inheritance, `__slots__` |
| 09 | Descriptors and Properties | data vs non-data, `__set_name__`, why methods bind |
| 10 | Class Creation and Metaclasses | `__prepare__`, `__init_subclass__`, ABCs, metaclass conflicts |
| 11 | Context Managers | `__exit__` return values, `@contextmanager`, `ExitStack`, reentrancy |
| 12 | Exceptions in Depth | the hierarchy, chaining, custom design, `ExceptionGroup`/`except*` |
| 13 | Typing, Generics, and Protocols | PEP 695 syntax, variance, `Protocol`, runtime introspection |
| 14 | Dataclasses, Enums, and Pattern Matching | `frozen`/`slots`, `InitVar`, `match` and the capture trap |
| 15 | The Functional Toolbox | `itertools`, `groupby`, `singledispatch`, `operator` |
| 16 | Modules, Packages, and Imports | `sys.modules`, circular imports, import hooks, layout |
| 17 | Memory, Reference Counting, and the GC | cycles, `weakref`, `tracemalloc`, interning |
| 18 | Threads, Processes, and the GIL | what the GIL locks, races, queues, `concurrent.futures` |
| 19 | Asyncio and Coroutines | tasks, `TaskGroup`, cancellation, never blocking the loop |
| 20 | Performance, Profiling, and Bytecode | `timeit`, `cProfile`, `dis`, what actually pays off |
| 21 | Testing and Debugging | fixtures, parametrise, test seams, mocking, `pdb`, logging |
| 22 | Introspection, AST, and Code Generation | `inspect`, code objects, `ast` rewriting, safe eval |

## Capstone projects

Each ships a brief, a starter, and a real pytest suite that grades it.

| project | build | lessons |
|---|---|---|
| `tinyorm` | fields as descriptors, models via metaclass, a chainable lazy query builder | 02, 09, 10, 13 |
| `resilient` | retry, circuit breaker, token-bucket rate limiter, bulkhead | 07, 11, 12, 18 |
| `streamz` | a lazy single-pass streaming pipeline with 16 operators | 04, 05, 15 |
| `scheduler` | an async DAG runner with parallelism, retries, timeouts, cancellation | 12, 18, 19 |
| `lintly` | a pluggable AST linter with 7 rules and `# noqa` support | 10, 16, 22 |

```bash
uv run learn.py projects              # list them
uv run learn.py projects show tinyorm # read the brief
uv run learn.py projects test tinyorm # grade your work
```

Edit `projects/<name>/<name>.py`. Reference solutions live in
`projects/_solutions/` — the course's own test suite runs every suite against
them to prove the projects are solvable.

## The course tests itself

```bash
uv run pytest                  # 697 tests: content, notebooks, site, projects
```

That run enforces, for every lesson:

- every demo **executes** (unless it declares `expect_error`)
- every "predict the output" answer **matches what Python actually prints**
- every exercise's reference solution passes all of its own checks
- every exercise's starter *fails* at least one check
- every quiz answer points at a real choice and carries an explanation

and, for the other front-ends: notebooks are valid nbformat with solutions
collapsed, the site is self-contained with themed tokens, and every project
is both solvable and unsolved.

Two opt-in suites:

```bash
uv run --with nbclient --with ipykernel --with nbformat pytest -m notebooks
TUTORIAL_SOLUTIONS=1 uv run pytest -m project
```

The first executes every generated notebook in a real kernel; the second
grades the reference solutions.

## Layout

```
learn.py                 CLI entry point
serve.py                 optional ASGI app for serving site/ over HTTP
tutorial/
  core.py                Lesson/Text/Demo/Question/Predict/Exercise + sandbox
  lessons/l01…l22*.py    the curriculum — content as data
  runner.py              interactive terminal presenter
  notebook.py            .ipynb renderer
  site.py                static-site renderer
  grader.py              check() — shared by notebooks and the CLI
  projects.py            capstone registry and test runner
  progress.py, ui.py, registry.py
projects/<name>/         brief, starter, grading suite
projects/_solutions/     reference solutions
tests/                   the suite that validates all of the above
notebooks/               generated + committed — deterministic, the main front-end
docs/                    generated + committed — markdown, renders on GitHub
site/                    generated, NOT committed — bakes in timings, so it churns
workspace/               your exercise files (created on demand)
```

## Adding a lesson

Drop `tutorial/lessons/l23_topic.py` exporting a `LESSON = Lesson(...)`. It is
picked up automatically by all three front-ends, and `uv run pytest` will
immediately hold it to the same standard as the rest.
