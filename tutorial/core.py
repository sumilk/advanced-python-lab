"""Content model for the tutorial.

A Lesson is a list of Blocks. Blocks are inert data; runner.py decides how
to present them. Keeping them inert means lessons can also be exported to
markdown or validated in tests without a terminal attached.
"""
from __future__ import annotations

import contextlib
import io
import sys
import textwrap
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------
@dataclass
class Text:
    """A prose block written in markdown-lite (see ui.render)."""

    body: str


@dataclass
class Demo:
    """Code that is displayed *and* executed, with its output shown.

    expect_error  -- demo intentionally raises; the traceback is the point.
    min_version   -- shown but not executed on older interpreters.
    setup         -- executed before `code` but not displayed.
    """

    code: str
    explain: str = ""
    expect_error: bool = False
    min_version: tuple[int, int] | None = None
    setup: str = ""


@dataclass
class Question:
    """A multiple-choice question. `answer` indexes `choices` (0-based).

    Questions with several correct options use `answers` instead.
    """

    prompt: str
    choices: Sequence[str]
    answer: int | None = None
    answers: Sequence[int] | None = None
    explain: str = ""

    def correct_set(self) -> set[int]:
        if self.answers is not None:
            return set(self.answers)
        return {self.answer}


@dataclass
class Predict:
    """"What does this print?" -- the learner guesses, then we run it."""

    code: str
    answer: str
    explain: str = ""


@dataclass
class Check:
    """One assertion inside an exercise. `fn` raises AssertionError to fail."""

    label: str
    fn: Callable[[dict[str, Any]], None]


@dataclass
class Exercise:
    slug: str
    title: str
    brief: str
    starter: str
    checks: list[Check]
    hints: Sequence[str] = ()
    solution: str = ""
    difficulty: str = "medium"          # warmup | medium | tricky | brutal


@dataclass
class Lesson:
    number: int
    slug: str
    title: str
    summary: str
    blocks: list[Any]
    tags: Sequence[str] = ()

    @property
    def key(self) -> str:
        return f"{self.number:02d}-{self.slug}"

    def exercises(self) -> list[Exercise]:
        return [b for b in self.blocks if isinstance(b, Exercise)]

    def questions(self) -> list[Question]:
        return [b for b in self.blocks if isinstance(b, Question)]


# --------------------------------------------------------------------------
# Execution sandbox
# --------------------------------------------------------------------------
@dataclass
class RunResult:
    stdout: str
    error: BaseException | None = None
    traceback_text: str = ""
    namespace: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.error is not None


def run_code(
    source: str,
    namespace: dict[str, Any] | None = None,
    filename: str = "<demo>",
) -> RunResult:
    """Execute *source*, capturing stdout and any exception.

    Exceptions are captured rather than propagated: a good number of these
    lessons exist precisely to show what a particular failure looks like.
    """
    source = textwrap.dedent(source).strip("\n")
    ns = namespace if namespace is not None else {}
    ns.setdefault("__name__", "__main__")
    buf = io.StringIO()
    err: BaseException | None = None
    tb_text = ""
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            # dont_inherit=True matters: compile() otherwise picks up the
            # __future__ flags of *this* module, and `from __future__ import
            # annotations` here would silently turn every annotation in every
            # lesson into a string -- which changes how dataclasses, typing
            # and InitVar behave.
            exec(compile(source, filename, "exec", dont_inherit=True), ns, ns)
    except BaseException as exc:                      # noqa: BLE001 - deliberate
        err = exc
        # Drop our own exec() frame so the traceback starts at the demo.
        tb = exc.__traceback__.tb_next if exc.__traceback__ else None
        tb_text = "".join(traceback.format_exception(type(exc), exc, tb))
    return RunResult(buf.getvalue(), err, tb_text, ns)


def version_ok(min_version: tuple[int, int] | None) -> bool:
    return min_version is None or sys.version_info[:2] >= min_version
