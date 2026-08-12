# Lintly — a pluggable AST linter

A real linter, small enough to read in one sitting: rules register themselves
by subclassing, each walks the AST once, and findings come back sorted and
suppressible with `# noqa`.

**Lessons drawn on:** 10 (`__init_subclass__`, registries), 16 (modules),
22 (`ast`).

```python
findings = lint(source, code="app.py")
# [Finding(code='L101', line=3, col=4, message="mutable default for 'items'", ...)]
```

## Requirements

### 1. `Rule` — the plugin base

- subclassing `Rule` registers it automatically in `Rule.registry`, keyed by
  its `code`
- a subclass must define `code` (like `"L101"`) and `message`; missing either
  raises `TypeError` at class creation
- a duplicate `code` raises `ValueError` at class creation
- `abstract = True` in the class body opts a subclass out of registration
  (for intermediate base classes) and is not inherited
- every rule implements `check(tree, context) -> Iterable[Finding]`
- `Rule.registry` is ordered by code

### 2. `Finding`

A frozen, ordered value object: `code`, `line`, `col`, `message`, `filename`.

- sorts by `(filename, line, col, code)`
- `str(finding)` → `"app.py:3:4: L101 mutable default for 'items'"`

### 3. The built-in rules

| code | finds |
|---|---|
| `L101` | a mutable default argument (list/dict/set literal, or `list()`/`dict()`/`set()`) |
| `L102` | a bare `except:` |
| `L103` | a function whose cyclomatic complexity exceeds `max_complexity` (default 10) |
| `L104` | a name that shadows a builtin (assignment, parameter, or `for` target) |
| `L105` | a function or class with no docstring, ignoring names starting with `_` |
| `L106` | a comparison to a singleton with `==` (`x == None`, `== True`, `== False`) |
| `L107` | an unused import (imported name never referenced anywhere in the module) |

Each reports the **precise** line and column of the offending node.

### 4. `lint(source, filename="<string>", select=None, ignore=None, config=None)`

- returns findings **sorted**
- `select` — only these codes; `ignore` — everything but these; `select` wins
- `config` — a dict passed to rules that want it, e.g.
  `{"max_complexity": 5}`
- a `# noqa` comment on a line suppresses every finding on that line;
  `# noqa: L101,L102` suppresses only those codes
- a `SyntaxError` in the source produces a single `E999` finding at the
  reported position rather than propagating

### 5. `summary(findings)`

`dict[code, count]` ordered by descending count, then by code.

## Grading

```bash
uv run learn.py projects test lintly
```

## Hints

- `__init_subclass__` is the registration hook. Read `cls.__dict__` for
  `abstract` so the flag does not leak to grandchildren.
- Each rule can be an `ast.NodeVisitor` that appends to a list, or a plain
  `ast.walk` loop — walk is simpler and fast enough here.
- Column numbers: `node.col_offset` is 0-based, which is what the tests
  expect.
- For `L104`, `builtins.__dict__` is the list of names to check against; be
  careful to catch `ast.Name` in a `Store` context, `arg` nodes, and `for`
  targets.
- For `L107`, collect imported binding names, then subtract every `ast.Name`
  and every dotted `ast.Attribute` root used in the module. Remember
  `import a.b` binds `a`.
- Parse `# noqa` from the raw source lines, not the AST — comments are not in
  the tree. `tokenize.generate_tokens` gives you comments with positions if
  you want to be precise.
