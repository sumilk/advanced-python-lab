"""Lintly — a pluggable AST linter.

Read README.md in this directory for the full specification.

    uv run learn.py projects test lintly
"""
from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    code: str
    line: int
    col: int
    message: str
    filename: str = "<string>"

    def __lt__(self, other):
        ...

    def __str__(self):
        ...


class Rule:
    """Subclass to add a rule. Registration is automatic."""

    registry: dict = {}
    code: str = ""
    message: str = ""

    def __init_subclass__(cls, **kwargs):
        ...

    def __init__(self, config=None):
        self.config = config or {}

    def check(self, tree, context):
        """Yield Findings for `tree`. `context` carries filename and source."""
        raise NotImplementedError


# --- the built-in rules ----------------------------------------------------
# L101 mutable default   L102 bare except       L103 too complex
# L104 shadowed builtin  L105 missing docstring L106 singleton comparison
# L107 unused import


def lint(source, filename="<string>", select=None, ignore=None, config=None):
    ...


def summary(findings):
    ...
