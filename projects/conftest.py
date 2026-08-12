"""Shared plumbing for the capstone project suites.

Each project's tests import the module under test through `load()`, which
loads it from a file path rather than by package name. That indirection is
what lets the exact same suite grade either your starter or the reference
solution:

    uv run learn.py projects test tinyorm      # grades your work
    TUTORIAL_SOLUTIONS=1 uv run pytest -m project   # grades the solutions

The second form is how the course verifies its own projects are solvable.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

PROJECTS_DIR = Path(__file__).resolve().parent
SOLUTIONS_DIR = PROJECTS_DIR / "_solutions"


def use_solutions() -> bool:
    return os.environ.get("TUTORIAL_SOLUTIONS", "").lower() in {"1", "true", "yes"}


def source_path(slug: str) -> Path:
    if use_solutions():
        return SOLUTIONS_DIR / f"{slug}.py"
    return PROJECTS_DIR / slug / f"{slug}.py"


def load(slug: str) -> ModuleType:
    """Import a project module from its file, fresh each time."""
    path = source_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"no project source at {path}")

    module_name = f"_project_{slug}_{'solution' if use_solutions() else 'work'}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def requires(module: ModuleType, *names: str) -> None:
    """Fail with a clear message when the starter has not defined something yet."""
    import pytest

    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(
            f"{module.__name__}: not implemented yet — missing {', '.join(missing)}"
        )
