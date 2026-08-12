"""Grading entry point shared by the terminal runner and the notebooks.

In a notebook you solve an exercise by editing a cell, then run:

    from tutorial.grader import check
    check("02-datamodel/frozen-dict")

`check` grades whatever is currently defined in the calling cell's globals,
using exactly the same Check objects the CLI uses. One source of truth.
"""
from __future__ import annotations

import inspect
from typing import Any

from .progress import Progress
from .registry import find_exercise

_PASS = "✓"
_FAIL = "✗"


class Report:
    """Result of grading, with a notebook-friendly rich display."""

    def __init__(self, title: str, rows: list[tuple[bool, str, str]]):
        self.title = title
        self.rows = rows

    @property
    def passed(self) -> int:
        return sum(1 for ok, _, _ in self.rows if ok)

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.passed == self.total

    def __bool__(self) -> bool:
        return self.complete

    def __repr__(self) -> str:
        lines = [f"{self.title}: {self.passed}/{self.total} checks pass"]
        for ok, label, detail in self.rows:
            mark = _PASS if ok else _FAIL
            lines.append(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))
        if self.complete:
            lines.append("  ★ solved")
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        colour = "#16a34a" if self.complete else "#ca8a04"
        rows = []
        for ok, label, detail in self.rows:
            mark_colour = "#16a34a" if ok else "#dc2626"
            mark = _PASS if ok else _FAIL
            extra = (f'<span style="color:#dc2626"> — {_escape(detail)}</span>'
                     if detail else "")
            rows.append(
                f'<li><span style="color:{mark_colour};font-weight:700">{mark}</span> '
                f'{_escape(label)}{extra}</li>'
            )
        banner = ("★ solved" if self.complete
                  else f"{self.passed}/{self.total} checks pass")
        return (
            f'<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
            f'border-left:4px solid {colour};padding:.5rem .9rem;margin:.3rem 0">'
            f'<div style="font-weight:700;color:{colour}">{_escape(self.title)} — {banner}</div>'
            f'<ul style="margin:.4rem 0 0;padding-left:1.2rem;line-height:1.6">'
            + "".join(rows)
            + "</ul></div>"
        )


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def check(exercise_id: str, namespace: dict[str, Any] | None = None) -> Report:
    """Grade `exercise_id` against `namespace` (defaults to the caller's globals)."""
    lesson, exercise = find_exercise(exercise_id)
    if exercise is None:
        raise LookupError(
            f"unknown exercise {exercise_id!r} — "
            "run `uv run learn.py list` to see valid ids"
        )

    if namespace is None:
        frame = inspect.currentframe()
        caller = frame.f_back if frame else None
        namespace = dict(caller.f_globals) if caller else {}
        if caller:
            namespace.update(caller.f_locals)

    rows: list[tuple[bool, str, str]] = []
    for item in exercise.checks:
        try:
            item.fn(namespace)
        except AssertionError as exc:
            rows.append((False, item.label, str(exc) or "assertion failed"))
        except KeyError as exc:
            rows.append((False, item.label, f"{exc} is not defined yet"))
        except Exception as exc:                            # noqa: BLE001
            rows.append((False, item.label, f"{type(exc).__name__}: {exc}"))
        else:
            rows.append((True, item.label, ""))

    report = Report(f"{lesson.key}/{exercise.slug}", rows)
    if report.complete:
        Progress.load().mark_exercise(f"{lesson.key}/{exercise.slug}")
    return report


def hint(exercise_id: str, n: int = 0) -> str:
    """Return the n-th hint for an exercise (0-based)."""
    _, exercise = find_exercise(exercise_id)
    if exercise is None:
        raise LookupError(f"unknown exercise {exercise_id!r}")
    if not exercise.hints:
        return "(no hints for this one)"
    n = max(0, min(n, len(exercise.hints) - 1))
    return f"hint {n + 1}/{len(exercise.hints)}: {exercise.hints[n]}"


def solution(exercise_id: str) -> str:
    """Return the reference solution source. Try the exercise first."""
    import textwrap

    _, exercise = find_exercise(exercise_id)
    if exercise is None:
        raise LookupError(f"unknown exercise {exercise_id!r}")
    return textwrap.dedent(exercise.solution).strip()
