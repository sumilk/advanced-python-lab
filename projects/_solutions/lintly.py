"""Lintly — reference solution."""
from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass, field
from typing import Any

BUILTIN_NAMES = set(dir(builtins))
MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set)
MUTABLE_FACTORIES = {"list", "dict", "set"}
NOQA = re.compile(r"#\s*noqa(?::\s*(?P<codes>[A-Z0-9, ]+))?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------
@dataclass(frozen=True, order=False)
class Finding:
    code: str
    line: int
    col: int
    message: str
    filename: str = "<string>"

    def _key(self):
        return (self.filename, self.line, self.col, self.code)

    def __lt__(self, other):
        if not isinstance(other, Finding):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self):
        return f"{self.filename}:{self.line}:{self.col}: {self.code} {self.message}"


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------
class Rule:
    registry: dict[str, type[Rule]] = {}
    code: str = ""
    message: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # `abstract` must not be inherited: read it from this class only.
        if cls.__dict__.get("abstract", False):
            return
        if not getattr(cls, "code", "") or not getattr(cls, "message", ""):
            raise TypeError(f"{cls.__name__} must define both `code` and `message`")
        if cls.code in Rule.registry:
            raise ValueError(
                f"duplicate rule code {cls.code!r} "
                f"(already used by {Rule.registry[cls.code].__name__})"
            )
        Rule.registry[cls.code] = cls
        Rule.registry = dict(sorted(Rule.registry.items()))

    def __init__(self, config=None):
        self.config = config or {}

    def check(self, tree, context):
        raise NotImplementedError

    def finding(self, node, message=None, context=None):
        return Finding(
            code=self.code,
            line=getattr(node, "lineno", 1),
            col=getattr(node, "col_offset", 0),
            message=message or self.message,
            filename=(context or {}).get("filename", "<string>"),
        )


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------
def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


class MutableDefault(Rule):
    code = "L101"
    message = "mutable default argument"

    def check(self, tree, context):
        for fn in _functions(tree):
            args = fn.args
            positional = [*args.posonlyargs, *args.args]
            defaults = args.defaults
            paired = list(zip(positional[len(positional) - len(defaults):], defaults))
            paired += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults) if d]
            for arg, default in paired:
                if isinstance(default, MUTABLE_LITERALS) or (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id in MUTABLE_FACTORIES
                ):
                    yield self.finding(
                        default, f"mutable default for {arg.arg!r}", context
                    )


class BareExcept(Rule):
    code = "L102"
    message = "bare except"

    def check(self, tree, context):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                yield self.finding(node, "bare except: catches BaseException", context)


class TooComplex(Rule):
    code = "L103"
    message = "function is too complex"

    @staticmethod
    def complexity(fn):
        score = 1
        for child in ast.walk(fn):
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While,
                                  ast.ExceptHandler, ast.Assert)):
                score += 1
            elif isinstance(child, ast.BoolOp):
                score += len(child.values) - 1
            elif isinstance(child, ast.comprehension):
                score += len(child.ifs)
            elif isinstance(child, ast.match_case):
                score += 1
        return score

    def check(self, tree, context):
        limit = self.config.get("max_complexity", 10)
        for fn in _functions(tree):
            score = self.complexity(fn)
            if score > limit:
                yield self.finding(
                    fn, f"{fn.name!r} has complexity {score} (limit {limit})", context
                )


class ShadowedBuiltin(Rule):
    code = "L104"
    message = "shadows a builtin"

    def check(self, tree, context):
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id in BUILTIN_NAMES:
                    yield self.finding(node, f"{node.id!r} shadows a builtin", context)
            elif isinstance(node, ast.arg) and node.arg in BUILTIN_NAMES:
                yield self.finding(node, f"{node.arg!r} shadows a builtin", context)


class MissingDocstring(Rule):
    code = "L105"
    message = "missing docstring"

    def check(self, tree, context):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is None:
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                yield self.finding(
                    node, f"{kind} {node.name!r} has no docstring", context
                )


class SingletonComparison(Rule):
    code = "L106"
    message = "comparison to a singleton with =="

    def check(self, tree, context):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for op, comparator in zip(node.ops, node.comparators):
                if not isinstance(op, (ast.Eq, ast.NotEq)):
                    continue
                if isinstance(comparator, ast.Constant) and (
                    comparator.value is None or comparator.value is True
                    or comparator.value is False
                ):
                    verb = "==" if isinstance(op, ast.Eq) else "!="
                    yield self.finding(
                        node,
                        f"use 'is' instead of '{verb}' to compare with "
                        f"{comparator.value!r}",
                        context,
                    )


class UnusedImport(Rule):
    code = "L107"
    message = "unused import"

    def check(self, tree, context):
        bound: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    bound[name] = node
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    bound[alias.asname or alias.name] = node

        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                root = node
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    used.add(root.id)

        for name, node in bound.items():
            if name not in used:
                yield self.finding(node, f"{name!r} imported but unused", context)


# ---------------------------------------------------------------------------
# noqa handling
# ---------------------------------------------------------------------------
def noqa_map(source: str) -> dict[int, set[str] | None]:
    """line number -> set of suppressed codes, or None meaning 'all'."""
    suppressions: dict[int, set[str] | None] = {}
    for number, line in enumerate(source.splitlines(), 1):
        match = NOQA.search(line)
        if not match:
            continue
        codes = match.group("codes")
        if codes:
            suppressions[number] = {c.strip().upper() for c in codes.split(",") if c.strip()}
        else:
            suppressions[number] = None
    return suppressions


def is_suppressed(finding: Finding, suppressions) -> bool:
    if finding.line not in suppressions:
        return False
    codes = suppressions[finding.line]
    return codes is None or finding.code in codes


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def lint(source, filename="<string>", select=None, ignore=None, config=None):
    context = {"filename": filename, "source": source}

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [Finding("E999", exc.lineno or 1, (exc.offset or 1) - 1,
                        f"SyntaxError: {exc.msg}", filename)]

    codes = set(Rule.registry)
    if select is not None:
        codes &= set(select)
    elif ignore is not None:
        codes -= set(ignore)

    findings: list[Finding] = []
    for code in sorted(codes):
        rule = Rule.registry[code](config)
        findings.extend(rule.check(tree, context))

    suppressions = noqa_map(source)
    findings = [f for f in findings if not is_suppressed(f, suppressions)]
    return sorted(findings)


def summary(findings):
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.code] = counts.get(finding.code, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
