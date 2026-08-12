"""Lesson 22 — Introspection, AST, and code generation."""
from __future__ import annotations

from ..core import Check, Demo, Exercise, Lesson, Predict, Question, Text

LESSON = Lesson(
    number=22,
    slug="metaprogramming",
    title="Introspection, AST, and Code Generation",
    summary="""
    The capstone lesson: Python programs that read and write Python. We cover
    the introspection API, code objects and frames, the `ast` module for
    analysing and rewriting source, safe evaluation, runtime code generation
    (how `dataclass` and `namedtuple` really work), and the judgement to know
    when *not* to do any of it.
    """,
    tags=("metaprogramming", "ast", "introspection", "codegen"),
    blocks=[
        Text("""
        ## Introspection: `inspect` and friends

        - `type(x)`, `isinstance`, `issubclass`, `dir(x)`, `vars(x)`
        - `inspect.signature`, `getsource`, `getmembers`, `getmodule`
        - `inspect.isclass/isfunction/ismethod/isgenerator/iscoroutine`
        - `inspect.currentframe()`, `inspect.stack()`
        - `__dict__`, `__mro__`, `__code__`, `__closure__`, `__annotations__`
        """),
        Demo(
            code="""
            import inspect

            class Service:
                '''A service.'''
                registry = {}

                def __init__(self, name: str, retries: int = 3):
                    self.name, self.retries = name, retries

                def run(self, *args, **kwargs) -> bool:
                    '''Do the work.'''
                    return True

                @property
                def label(self): return self.name

                @staticmethod
                def helper(): ...

            print("methods:", [n for n, _ in inspect.getmembers(Service, inspect.isfunction)])
            print("signature of __init__:", inspect.signature(Service.__init__))
            print("annotations:", Service.run.__annotations__)
            print("docstring:", inspect.getdoc(Service.run))
            print("is a property:", isinstance(inspect.getattr_static(Service, "label"), property))
            try:
                print("source lines:", len(inspect.getsource(Service).splitlines()))
            except OSError as exc:
                print("getsource   :", exc, "(this class has no source *file*)")
            """,
            explain="""
            `inspect.getattr_static` is the one to remember: it looks an
            attribute up **without** triggering descriptors, properties, or
            `__getattr__`. Essential when introspecting objects whose
            attribute access has side effects.
            """,
        ),
        Demo(
            code="""
            import inspect

            def outer():
                secret = "in outer's frame"
                return inner()

            def inner():
                frame = inspect.currentframe().f_back      # the caller's frame
                return {
                    "caller": frame.f_code.co_name,
                    "caller locals": {k: v for k, v in frame.f_locals.items()},
                    "line": frame.f_lineno,
                }

            print(outer())

            # The call stack, from the top
            def a(): return b()
            def b(): return c()
            def c(): return [f.function for f in inspect.stack()[:4]]
            print("stack:", a())
            """,
            explain="""
            Reading the caller's frame is how `logging` finds the filename and
            line number for every record. It is also a great way to build
            something unmaintainable — use it in tooling, not application
            logic.
            """,
        ),
        Text("""
        ## Code objects

        A function is a thin wrapper around a **code object** plus a closure
        and defaults. `fn.__code__` exposes everything the compiler produced.

        | attribute | meaning |
        |---|---|
        | `co_varnames` | locals, arguments first |
        | `co_argcount`, `co_kwonlyargcount`, `co_posonlyargcount` | arity |
        | `co_consts` | constants, including nested code objects |
        | `co_names` | global/attribute names referenced |
        | `co_freevars`, `co_cellvars` | closure variables |
        | `co_flags` | generator/coroutine/varargs bits |
        """),
        Demo(
            code="""
            import dis
            import inspect
            import types

            def example(a, b=2, *args, key=None, **kwargs):
                local = a + b
                return [x for x in range(local)]

            code = example.__code__
            print("argcount     :", code.co_argcount, "| kwonly:", code.co_kwonlyargcount)
            print("varnames     :", code.co_varnames)
            print("names        :", code.co_names)
            print("consts       :", [c for c in code.co_consts if not isinstance(c, types.CodeType)])
            print("nested code  :", [c.co_name for c in code.co_consts
                                     if isinstance(c, types.CodeType)])
            print("flags        :", inspect.getgeneratorstate.__module__ and
                  [f for f in ("OPTIMIZED", "NEWLOCALS", "VARARGS", "VARKEYWORDS", "GENERATOR")
                   if getattr(inspect, "CO_" + f, 0) & code.co_flags])

            # Build a function from scratch, with no def statement.
            source = "def generated(x):\\n    return x * 3\\n"
            namespace = {}
            exec(compile(source, "<generated>", "exec"), namespace)
            fn = namespace["generated"]
            print("\\ngenerated:", fn(7), "| name:", fn.__name__,
                  "| file:", fn.__code__.co_filename)
            """,
        ),
        Text("""
        ## `ast`: parse, analyse, rewrite

        `ast.parse(source)` gives you a tree you can walk, transform, and
        compile back. This is the foundation of linters, formatters, coverage
        tools, and pytest's assertion rewriting.

        - `ast.walk(tree)` — all nodes, unordered
        - `ast.NodeVisitor` — dispatch on node type
        - `ast.NodeTransformer` — same, but returns replacements
        - `ast.unparse(tree)` (3.9+) — back to source
        - `ast.dump(tree, indent=2)` — see the structure
        """),
        Demo(
            code="""
            import ast

            source = '''
            def total(items, tax=0.2):
                subtotal = sum(i["price"] for i in items)
                return subtotal * (1 + tax)
            '''

            tree = ast.parse(source)
            fn = tree.body[0]
            print("function     :", fn.name)
            print("arguments    :", [a.arg for a in fn.args.args])
            print("defaults     :", [ast.unparse(d) for d in fn.args.defaults])
            print("calls made   :", [ast.unparse(n.func) for n in ast.walk(tree)
                                     if isinstance(n, ast.Call)])
            print("names used   :", sorted({n.id for n in ast.walk(tree)
                                            if isinstance(n, ast.Name)}))
            print("\\nstructure of the return expression:")
            print(ast.dump(fn.body[-1].value, indent=2)[:220], "...")
            """,
        ),
        Demo(
            code="""
            import ast

            # A linter: find mutable default arguments.
            class MutableDefaults(ast.NodeVisitor):
                def __init__(self): self.problems = []

                def visit_FunctionDef(self, node):
                    for arg, default in zip(node.args.args[-len(node.args.defaults):]
                                            if node.args.defaults else [],
                                            node.args.defaults):
                        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                            self.problems.append((node.name, arg.arg, node.lineno))
                        elif (isinstance(default, ast.Call)
                              and isinstance(default.func, ast.Name)
                              and default.func.id in {"list", "dict", "set"}):
                            self.problems.append((node.name, arg.arg, node.lineno))
                    self.generic_visit(node)

            code = '''
            def ok(a, b=None): pass
            def bad_list(a, items=[]): pass
            def bad_dict(a, opts={}): pass
            def bad_call(a, items=list()): pass
            def nested():
                def inner(x=[]): pass
            '''

            checker = MutableDefaults()
            checker.visit(ast.parse(code))
            for name, arg, line in checker.problems:
                print(f"  line {line}: {name}() has a mutable default for {arg!r}")
            """,
        ),
        Demo(
            code="""
            import ast

            # A transformer: constant-fold and rewrite `x ** 2` into `x * x`.
            class Optimiser(ast.NodeTransformer):
                def visit_BinOp(self, node):
                    self.generic_visit(node)
                    if (isinstance(node.op, ast.Pow)
                            and isinstance(node.right, ast.Constant)
                            and node.right.value == 2):
                        return ast.BinOp(left=node.left, op=ast.Mult(), right=node.left)
                    return node

            source = "def f(x, y):\\n    return x ** 2 + y ** 2 + x ** 3\\n"
            tree = ast.parse(source)
            new_tree = ast.fix_missing_locations(Optimiser().visit(tree))
            print("before:", source.strip().splitlines()[-1].strip())
            print("after :", ast.unparse(new_tree).splitlines()[-1].strip())

            namespace = {}
            exec(compile(new_tree, "<optimised>", "exec"), namespace)
            print("still correct:", namespace["f"](3, 4))
            """,
            explain="""
            `fix_missing_locations` is mandatory after building nodes by hand:
            every node needs `lineno`/`col_offset` or `compile` raises. This
            transform is the toy version of what pytest does — it rewrites
            `assert x == y` into code that captures both sides for the error
            message.
            """,
        ),
        Question(
            prompt="What must you call after constructing new AST nodes before compiling?",
            choices=[
                "`ast.parse`",
                "`ast.fix_missing_locations(tree)`",
                "`ast.literal_eval`",
                "Nothing — locations are optional",
            ],
            answer=1,
            explain="Every node needs `lineno` and `col_offset`; the compiler raises "
                    "`TypeError: required field \"lineno\" missing` otherwise.",
        ),
        Text("""
        ## `eval`, `exec`, and safe evaluation

        `eval(expr)` evaluates an expression; `exec(stmts)` runs statements.
        Both accept explicit `globals`/`locals` dicts — but **restricting
        those is not a sandbox**. `().__class__.__bases__` reaches `object`,
        and from there its subclasses, and from there the filesystem.

        For untrusted input use `ast.literal_eval` (literals only), or parse
        with `ast` and evaluate only the node types you allow.
        """),
        Demo(
            code="""
            import ast

            print("literal_eval handles data safely:")
            for text in ("[1, 2, {'a': (3, None)}]", "{'x': True}", "3+4"):
                try:
                    print("  ", text, "->", ast.literal_eval(text))
                except ValueError as exc:
                    print("  ", text, "-> rejected:", exc)

            print("\\nand refuses anything that could execute:")
            for text in ("__import__('os').listdir('.')", "open('/etc/passwd')"):
                try:
                    ast.literal_eval(text)
                except (ValueError, SyntaxError) as exc:
                    print("  ", text[:30], "-> rejected")

            print("\\nwhy a 'restricted' eval is not a sandbox:")
            escape = "().__class__.__bases__[0].__subclasses__()"
            found = eval(escape, {"__builtins__": {}})
            print(f"   with no builtins at all, we still reached {len(found)} classes")
            """,
        ),
        Demo(
            code="""
            import ast
            import operator

            # A real safe evaluator: an allowlist of node types.
            OPS = {
                ast.Add: operator.add, ast.Sub: operator.sub,
                ast.Mult: operator.mul, ast.Div: operator.truediv,
                ast.Pow: operator.pow, ast.Mod: operator.mod,
                ast.USub: operator.neg, ast.UAdd: operator.pos,
            }

            def safe_eval(expression, variables=None):
                variables = variables or {}

                def evaluate(node):
                    match node:
                        case ast.Expression():
                            return evaluate(node.body)
                        case ast.Constant(value=v) if isinstance(v, (int, float)):
                            return v
                        case ast.Name(id=name) if name in variables:
                            return variables[name]
                        case ast.BinOp(op=op) if type(op) in OPS:
                            return OPS[type(op)](evaluate(node.left), evaluate(node.right))
                        case ast.UnaryOp(op=op) if type(op) in OPS:
                            return OPS[type(op)](evaluate(node.operand))
                        case _:
                            raise ValueError(f"not allowed: {type(node).__name__}")

                return evaluate(ast.parse(expression, mode="eval"))

            for expr in ("2 + 3 * 4", "(x + 1) ** 2", "-y / 4"):
                print(f"  {expr:14} = {safe_eval(expr, {'x': 5, 'y': 8})}")

            for bad in ("__import__('os')", "[1,2][0]", "print(1)"):
                try:
                    safe_eval(bad)
                except ValueError as exc:
                    print(f"  {bad:18} -> {exc}")
            """,
        ),
        Text("""
        ## Code generation

        `namedtuple` builds a class by formatting a source string and
        `exec`-ing it. `dataclass` builds `__init__` the same way. Why? A
        generated `__init__` with real parameter names is faster than a
        generic `**kwargs` one, and it introspects properly.
        """),
        Demo(
            code="""
            # Generate a class the way collections.namedtuple does: by
            # formatting source text and exec-ing it.
            def make_record(name, fields):
                params = ", ".join(fields)
                repr_inner = ", ".join(f"{f}={{self.{f}!r}}" for f in fields)
                comparisons = " and ".join(f"self.{f} == other.{f}" for f in fields)

                lines = [
                    f"class {name}:",
                    f"    __slots__ = {tuple(fields)!r}",
                    f"    def __init__(self, {params}):",
                    *(f"        self.{f} = {f}" for f in fields),
                    f"    def __repr__(self):",
                    f'        return f"{name}({repr_inner})"',
                    f"    def __eq__(self, other):",
                    f"        if type(other) is not type(self):",
                    f"            return NotImplemented",
                    f"        return {comparisons}",
                ]
                source = "\\n".join(lines)
                namespace = {}
                exec(source, namespace)
                cls = namespace[name]
                cls._source = source
                return cls

            Point = make_record("Point", ["x", "y"])
            p = Point(1, 2)
            print(p, "|", p == Point(1, 2), "|", p == Point(3, 4))

            import inspect
            print("real signature:", inspect.signature(Point.__init__))
            print("has __slots__ :", Point.__slots__)
            """,
            explain="""
            The generated `__init__` has *named* parameters, so
            `inspect.signature` works, IDEs autocomplete, and the call is a
            fast positional bind rather than dict unpacking. The cost is that
            the source exists only in a string — which is why generated
            classes stash it in `_source` for debugging, exactly as
            `namedtuple` does.
            """,
        ),
        Predict(
            code="""
            code = compile("result = a + b", "<gen>", "exec")
            ns = {"a": 1, "b": 2}
            exec(code, ns)
            print(ns["result"])

            expr = compile("a * b", "<gen>", "eval")
            print(eval(expr, ns))
            print(sorted(k for k in ns if not k.startswith("__")))
            """,
            answer="""
            3
            2
            ['a', 'b', 'result']
            """,
            explain="""
            `exec` with mode `"exec"` runs statements and writes into the
            namespace you gave it; `eval` with mode `"eval"` returns the value
            of a single expression and writes nothing. Both accept a
            pre-compiled code object, which is worth doing if you evaluate the
            same expression repeatedly.
            """,
        ),
        Text("""
        ## When not to do any of this

        Metaprogramming trades *write-time* cleverness for *read-time* cost.
        Every one of these techniques makes code harder to grep, harder to
        type-check, and harder for a new colleague to follow.

        Reasonable uses: frameworks, serialisation, test tooling, linters,
        DSLs with a real user base, and removing genuinely repetitive
        boilerplate across dozens of classes.

        Unreasonable uses: saving five lines; "flexibility" nobody asked for;
        anything a plain function, a decorator, or a dataclass already does.
        """),
        Question(
            prompt="You want to add a `__repr__` to 30 similar classes. What is the right tool?",
            choices=[
                "A metaclass that injects it",
                "`@dataclass`, or a small mixin — the boring, greppable option",
                "An import hook that rewrites the AST",
                "`exec` a generated class body",
            ],
            answer=1,
            explain="Reach for the least powerful tool that solves the problem. "
                    "Metaprogramming is for when the boring options genuinely cannot "
                    "express it.",
        ),
        Exercise(
            slug="code-analyser",
            title="A static analyser for Python source",
            difficulty="brutal",
            brief="""
            Write `analyse(source)` returning a report dict about a module's
            source, using `ast` — never regular expressions.

            Returned keys:
            - `functions` → list of `{"name", "lineno", "args", "returns",
              "is_async", "decorators", "complexity"}` for **top-level and
              nested** functions, in source order. `args` is every parameter
              name including `*args`/`**kwargs`; `returns` is the unparsed
              annotation or `None`; `decorators` is a list of unparsed
              decorator expressions.
            - `classes` → `{"name", "lineno", "bases", "methods"}`, methods
              being names in source order
            - `imports` → sorted list of top-level imported module names
              (`import a.b` → `"a.b"`; `from a.b import c` → `"a.b"`)
            - `mutable_defaults` → `[(function_name, arg_name)]` for list,
              dict, set literals **and** `list()`/`dict()`/`set()` calls
            - `bare_excepts` → line numbers of `except:` with no type
            - `max_depth` → the deepest nesting of `if`/`for`/`while`/`with`
              /`try` blocks anywhere in the module (0 for a flat module)

            `complexity` is cyclomatic complexity: start at 1 and add one for
            each `if`, `for`, `while`, `and`/`or` operand beyond the first,
            `except` handler, `assert`, comprehension `if`, and `match` case.
            """,
            starter="""
            import ast


            def analyse(source: str) -> dict:
                ...
            """,
            checks=[
                Check("finds functions with args and annotations", lambda ns: _ca_functions(ns)),
                Check("finds nested and async functions", lambda ns: _ca_nested(ns)),
                Check("finds classes, bases and methods", lambda ns: _ca_classes(ns)),
                Check("collects imports in both forms", lambda ns: _ca_imports(ns)),
                Check("detects mutable defaults, literals and calls",
                      lambda ns: _ca_mutable(ns)),
                Check("finds bare excepts by line", lambda ns: _ca_bare(ns)),
                Check("computes nesting depth", lambda ns: _ca_depth(ns)),
                Check("computes cyclomatic complexity", lambda ns: _ca_complexity(ns)),
                Check("handles an empty module", lambda ns: _ca_empty(ns)),
            ],
            hints=(
                "One `ast.NodeVisitor` subclass can collect everything in a single "
                "pass; keep a `self.depth` counter and bump it in the visitors for "
                "the block statements.",
                "`ast.AsyncFunctionDef` is a *different* node type from "
                "`ast.FunctionDef` — handle both, and remember `visit_AsyncFunctionDef`.",
                "For all parameter names: `args.posonlyargs + args.args + "
                "args.kwonlyargs`, plus `args.vararg` and `args.kwarg` if present.",
                "Defaults align to the *end* of `posonlyargs + args`, so zip them "
                "with `all_positional[-len(defaults):]`.",
                "For `BoolOp` complexity, add `len(node.values) - 1` — `a and b and c` "
                "is one BoolOp with three values.",
                "Track depth by incrementing before `generic_visit` and decrementing "
                "after; record the maximum as you go.",
            ),
            solution="""
            import ast

            NESTING = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                       ast.AsyncWith, ast.Try)
            MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set)
            MUTABLE_CALLS = {"list", "dict", "set"}

            def _complexity(node):
                score = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.AsyncFor,
                                          ast.While, ast.ExceptHandler, ast.Assert)):
                        score += 1
                    elif isinstance(child, ast.BoolOp):
                        score += len(child.values) - 1
                    elif isinstance(child, ast.comprehension):
                        score += len(child.ifs)
                    elif isinstance(child, ast.match_case):
                        score += 1
                return score

            def _param_names(args):
                names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
                if args.vararg:
                    names.append(args.vararg.arg)
                if args.kwarg:
                    names.append(args.kwarg.arg)
                return names

            class Analyser(ast.NodeVisitor):
                def __init__(self):
                    self.functions = []
                    self.classes = []
                    self.imports = set()
                    self.mutable_defaults = []
                    self.bare_excepts = []
                    self.depth = 0
                    self.max_depth = 0

                def _function(self, node, is_async):
                    positional = [*node.args.posonlyargs, *node.args.args]
                    defaults = node.args.defaults
                    paired = list(zip(positional[len(positional) - len(defaults):], defaults))
                    paired += [(a, d) for a, d in zip(node.args.kwonlyargs,
                                                      node.args.kw_defaults) if d]
                    for arg, default in paired:
                        if isinstance(default, MUTABLE_LITERALS) or (
                            isinstance(default, ast.Call)
                            and isinstance(default.func, ast.Name)
                            and default.func.id in MUTABLE_CALLS
                        ):
                            self.mutable_defaults.append((node.name, arg.arg))

                    self.functions.append({
                        "name": node.name,
                        "lineno": node.lineno,
                        "args": _param_names(node.args),
                        "returns": ast.unparse(node.returns) if node.returns else None,
                        "is_async": is_async,
                        "decorators": [ast.unparse(d) for d in node.decorator_list],
                        "complexity": _complexity(node),
                    })
                    self.generic_visit(node)

                def visit_FunctionDef(self, node):
                    self._function(node, False)

                def visit_AsyncFunctionDef(self, node):
                    self._function(node, True)

                def visit_ClassDef(self, node):
                    self.classes.append({
                        "name": node.name,
                        "lineno": node.lineno,
                        "bases": [ast.unparse(b) for b in node.bases],
                        "methods": [child.name for child in node.body
                                    if isinstance(child, (ast.FunctionDef,
                                                          ast.AsyncFunctionDef))],
                    })
                    self.generic_visit(node)

                def visit_Import(self, node):
                    for alias in node.names:
                        self.imports.add(alias.name)
                    self.generic_visit(node)

                def visit_ImportFrom(self, node):
                    if node.module:
                        self.imports.add(node.module)
                    self.generic_visit(node)

                def visit_ExceptHandler(self, node):
                    if node.type is None:
                        self.bare_excepts.append(node.lineno)
                    self.generic_visit(node)

                def generic_visit(self, node):
                    if isinstance(node, NESTING):
                        self.depth += 1
                        self.max_depth = max(self.max_depth, self.depth)
                        super().generic_visit(node)
                        self.depth -= 1
                    else:
                        super().generic_visit(node)

            def analyse(source: str) -> dict:
                visitor = Analyser()
                visitor.visit(ast.parse(source))
                visitor.functions.sort(key=lambda f: f["lineno"])
                return {
                    "functions": visitor.functions,
                    "classes": visitor.classes,
                    "imports": sorted(visitor.imports),
                    "mutable_defaults": visitor.mutable_defaults,
                    "bare_excepts": visitor.bare_excepts,
                    "max_depth": visitor.max_depth,
                }
            """,
        ),
        Text("""
        ## Takeaways

        - `inspect` answers almost every "what is this object?" question;
          `getattr_static` avoids triggering descriptors.
        - Functions wrap code objects; you can build them with `compile` +
          `exec`.
        - `ast` parses, analyses, and rewrites source — the basis of every
          Python dev tool.
        - Restricting `eval`'s globals is **not** a sandbox; use
          `literal_eval` or an allowlisted evaluator.
        - Reach for the least powerful tool that works. Metaprogramming is a
          cost paid by every future reader.
        """),
    ],
)


# --------------------------------------------------------------------------
# Check helpers
# --------------------------------------------------------------------------
_SAMPLE = '''
import os
import os.path
from collections import defaultdict
from typing import Any


@decorator
@other.thing(1)
def greet(name: str, *rest, punct: str = "!", **kw) -> str:
    return f"hi {name}"


async def fetch(url):
    async def inner():
        return 1
    return await inner()


class Service(Base, Mixin):
    def method_a(self): pass
    async def method_b(self): pass
    attribute = 1


def buggy(a, items=[], opts={}, cache=set(), made=list(), fine=None):
    pass


def messy(x):
    try:
        for i in range(x):
            if i > 2:
                with open("f") as fh:
                    while True:
                        break
    except:
        pass
'''


def _analysed(ns):
    return ns["analyse"](_SAMPLE)


def _ca_functions(ns) -> None:
    report = _analysed(ns)
    by_name = {f["name"]: f for f in report["functions"]}
    greet = by_name.get("greet")
    assert greet is not None, f"functions found: {sorted(by_name)}"
    assert greet["args"] == ["name", "punct", "rest", "kw"] or \
           greet["args"] == ["name", "rest", "punct", "kw"], (
        f"expected every parameter name, got {greet['args']}"
    )
    assert greet["returns"] == "str", greet["returns"]
    assert greet["is_async"] is False
    assert greet["decorators"] == ["decorator", "other.thing(1)"], greet["decorators"]


def _ca_nested(ns) -> None:
    report = _analysed(ns)
    names = [f["name"] for f in report["functions"]]
    assert "inner" in names, f"nested functions must be reported: {names}"
    by_name = {f["name"]: f for f in report["functions"]}
    assert by_name["fetch"]["is_async"] is True, "fetch is an async def"
    assert by_name["greet"]["lineno"] < by_name["fetch"]["lineno"], "order by line number"
    assert "method_b" in names, "methods count as functions too"


def _ca_classes(ns) -> None:
    report = _analysed(ns)
    assert len(report["classes"]) == 1, report["classes"]
    cls = report["classes"][0]
    assert cls["name"] == "Service"
    assert cls["bases"] == ["Base", "Mixin"], cls["bases"]
    assert cls["methods"] == ["method_a", "method_b"], cls["methods"]


def _ca_imports(ns) -> None:
    report = _analysed(ns)
    assert report["imports"] == ["collections", "os", "os.path", "typing"], report["imports"]


def _ca_mutable(ns) -> None:
    report = _analysed(ns)
    found = set(report["mutable_defaults"])
    expected = {("buggy", "items"), ("buggy", "opts"),
                ("buggy", "cache"), ("buggy", "made")}
    assert found == expected, f"expected {sorted(expected)}, got {sorted(found)}"


def _ca_bare(ns) -> None:
    report = _analysed(ns)
    assert len(report["bare_excepts"]) == 1, report["bare_excepts"]
    line = report["bare_excepts"][0]
    assert _SAMPLE.splitlines()[line - 1].strip() == "except:", (
        f"line {line} is {_SAMPLE.splitlines()[line - 1]!r}"
    )


def _ca_depth(ns) -> None:
    report = _analysed(ns)
    # messy(): try > for > if > with > while  == 5
    assert report["max_depth"] == 5, f"expected 5, got {report['max_depth']}"
    flat = ns["analyse"]("x = 1\ndef f():\n    return 2\n")
    assert flat["max_depth"] == 0, f"a flat module has depth 0, got {flat['max_depth']}"


def _ca_complexity(ns) -> None:
    analyse = ns["analyse"]
    simple = analyse("def f():\n    return 1\n")["functions"][0]
    assert simple["complexity"] == 1, f"a straight-line function is 1, got {simple['complexity']}"

    branchy = analyse(
        "def f(x):\n"
        "    if x and x > 1:\n"          # +1 if, +1 boolop
        "        for i in x:\n"          # +1
        "            pass\n"
        "    try:\n"
        "        pass\n"
        "    except ValueError:\n"       # +1
        "        pass\n"
        "    return [i for i in x if i]\n"   # +1 comprehension if
    )["functions"][0]
    assert branchy["complexity"] == 6, (
        f"expected 6 (1 + if + and + for + except + comp-if), "
        f"got {branchy['complexity']}"
    )


def _ca_empty(ns) -> None:
    report = ns["analyse"]("")
    assert report["functions"] == []
    assert report["classes"] == []
    assert report["imports"] == []
    assert report["mutable_defaults"] == []
    assert report["bare_excepts"] == []
    assert report["max_depth"] == 0
