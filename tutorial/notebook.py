"""Render lessons to Jupyter notebooks.

One .ipynb per lesson. Prose becomes markdown cells, demos become runnable
code cells, exercises become an editable starter cell followed by a
`check(...)` cell that grades it with the very same Check objects the CLI
uses -- so a notebook solution and a terminal solution are held to an
identical standard.

Notebooks are generated as raw nbformat 4.5 JSON: no jupyter dependency is
needed to *produce* them, only to run them.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from .core import Demo, Exercise, Lesson, Predict, Question, Text
from .registry import all_lessons

LETTERS = "abcdefgh"


# --------------------------------------------------------------------------
# Cell builders
# --------------------------------------------------------------------------
def md(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": _split(textwrap.dedent(source).strip("\n")),
    }


def code(source: str, *, editable: bool = True, tag: str = "") -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if tag:
        metadata["tags"] = [tag]
    if not editable:
        metadata["editable"] = False
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": [],
        "source": _split(textwrap.dedent(source).strip("\n")),
    }


def _split(text: str) -> list[str]:
    """nbformat wants a list of lines, each keeping its trailing newline."""
    lines = text.split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def _assign_ids(cells: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """nbformat 4.5 requires a unique id per cell. Keep them deterministic so
    regenerating a notebook produces a clean diff."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in prefix)
    for n, cell in enumerate(cells):
        cell["id"] = f"{safe}-{n:03d}"[:64]
    return cells


def _details(summary: str, body: str) -> str:
    return f"<details>\n<summary><b>{summary}</b></summary>\n\n{body}\n\n</details>"


# --------------------------------------------------------------------------
# Block -> cells
# --------------------------------------------------------------------------
def cells_for_block(block: Any, lesson: Lesson) -> list[dict[str, Any]]:
    match block:
        case Text():
            return [md(block.body)]

        case Demo():
            out = []
            note = ""
            if block.min_version:
                v = ".".join(map(str, block.min_version))
                note = f"> ⚠️ Requires Python {v}+\n\n"
            if block.expect_error:
                note += "> This cell **raises on purpose** — the traceback is the lesson.\n\n"
            if note:
                out.append(md(note))
            src = block.code
            if block.setup:
                src = textwrap.dedent(block.setup).strip("\n") + "\n\n" + textwrap.dedent(src).strip("\n")
            # `raises-exception` tells nbconvert/nbclient that a traceback here
            # is the expected result, not a broken notebook.
            out.append(code(src, tag="raises-exception" if block.expect_error else ""))
            if block.explain:
                out.append(md(block.explain))
            return out

        case Predict():
            return [
                md("### ❓ Predict the output\n\nRead the cell below and decide what it "
                   "prints **before** running it. Then run it."),
                code(block.code),
                md(_details(
                    "the answer, and why",
                    "```\n" + textwrap.dedent(block.answer).strip() + "\n```\n\n"
                    + textwrap.dedent(block.explain).strip(),
                )),
            ]

        case Question():
            options = "\n".join(
                f"- **{LETTERS[i]})** {choice}" for i, choice in enumerate(block.choices)
            )
            want = ", ".join(LETTERS[i] for i in sorted(block.correct_set()))
            return [md(
                f"### 🧠 Quiz\n\n{block.prompt}\n\n{options}\n\n"
                + _details("answer", f"**{want}** — {textwrap.dedent(block.explain).strip()}")
            )]

        case Exercise():
            ex_id = f"{lesson.key}/{block.slug}"
            hints = "\n".join(f"{i}. {h}" for i, h in enumerate(block.hints, 1))
            blocks = [
                md(f"---\n\n## ⚒ Exercise — {block.title}  \n"
                   f"`{ex_id}` · difficulty: **{block.difficulty}**\n\n"
                   + textwrap.dedent(block.brief).strip()
                   + "\n\nEdit the next cell, run it, then run the check cell below it."),
                code(block.starter),
                code(f'check("{ex_id}")', tag="check"),
                md(
                    (_details("hints", hints) + "\n\n" if hints else "")
                    + _details(
                        "reference solution",
                        "```python\n" + textwrap.dedent(block.solution).strip() + "\n```",
                    )
                ),
            ]
            return blocks

    return []


# --------------------------------------------------------------------------
# Lesson -> notebook
# --------------------------------------------------------------------------
PREAMBLE = '''\
# Wire the grader up. Run this cell first, every session.
import pathlib
import sys

_here = pathlib.Path.cwd()
_root = next((p for p in (_here, *_here.parents)
              if (p / "tutorial" / "grader.py").exists()), None)
if _root is None:
    raise RuntimeError("run this notebook from inside the tutorial repository")
sys.path.insert(0, str(_root))

from tutorial.grader import check, hint, solution   # noqa: E402

# A notebook kernel already owns an event loop, so asyncio.run() would refuse
# to start another one. Hand those coroutines a private loop on a worker
# thread instead, so the asyncio lessons run here exactly as they do in a
# script. (Outside a notebook this wrapper is a no-op.)
import asyncio as _asyncio                                    # noqa: E402
from concurrent.futures import ThreadPoolExecutor as _Pool    # noqa: E402

_plain_run = _asyncio.run


def _run_anywhere(coro, **kwargs):
    try:
        _asyncio.get_running_loop()
    except RuntimeError:
        return _plain_run(coro, **kwargs)
    with _Pool(1) as pool:
        return pool.submit(_plain_run, coro, **kwargs).result()


_asyncio.run = _run_anywhere

print("grader ready — Python", sys.version.split()[0])'''


def lesson_notebook(lesson: Lesson) -> dict[str, Any]:
    cells: list[dict[str, Any]] = [
        md(f"# {lesson.number:02d} — {lesson.title}\n\n"
           + textwrap.dedent(lesson.summary).strip()
           + ("\n\n" + " ".join(f"`#{t}`" for t in lesson.tags) if lesson.tags else "")),
        md("<sub>Setup cell — run it once per session so `check()` works.</sub>"),
        code(PREAMBLE, tag="setup"),
    ]
    for block in lesson.blocks:
        cells.extend(cells_for_block(block, lesson))

    n_ex = len(lesson.exercises())
    cells.append(md(
        "---\n\n### ✅ Lesson complete\n\n"
        f"Exercises in this lesson: **{n_ex}**. "
        "Check your standing across the whole course with:\n\n"
        "```\nuv run learn.py list\n```"
    ))

    return {
        "cells": _assign_ids(cells, lesson.key),
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
            "tutorial": {"lesson": lesson.key, "title": lesson.title},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def index_notebook(lessons: tuple[Lesson, ...]) -> dict[str, Any]:
    rows = "\n".join(
        f"| {les.number:02d} | [{les.title}]({les.key}.ipynb) | "
        f"{len(les.exercises())} | {len(les.questions())} | "
        + " ".join(f"`{t}`" for t in les.tags) + " |"
        for les in lessons
    )
    total_ex = sum(len(les.exercises()) for les in lessons)
    total_q = sum(len(les.questions()) for les in lessons)
    return {
        "cells": _assign_ids([
            md("# Advanced Python Lab\n\n"
               "A hands-on course. Every lesson is a notebook: read, run the cells, "
               "change them, break them, then solve the exercises in place.\n\n"
               "**How to use a lesson notebook**\n\n"
               "1. Run the setup cell at the top (it wires up `check`).\n"
               "2. Run each demo cell and *read the output* — then edit it and re-run.\n"
               "3. Exercise cells are yours to fill in; the cell right after grades it.\n"
               "4. Hints and reference solutions are in collapsed `<details>` blocks."),
            md(f"## Curriculum\n\n"
               f"| # | Lesson | Exercises | Quiz Qs | Topics |\n|---|---|---|---|---|\n{rows}\n\n"
               f"**{len(lessons)} lessons · {total_ex} graded exercises · {total_q} quiz questions**"),
            md("## Other ways to take this course\n\n"
               "```bash\n"
               "uv run learn.py            # interactive terminal version\n"
               "uv run learn.py quiz 20    # mixed exam across every lesson\n"
               "uv run learn.py projects   # capstone projects\n"
               "uv run pytest              # validate the whole course\n"
               "```"),
            md("### Track your progress\n\nProgress is shared across the notebook and "
               "terminal front-ends — solving an exercise in either records it."),
            code("import sys, pathlib\n"
                 "_h = pathlib.Path.cwd()\n"
                 "sys.path.insert(0, str(next(p for p in (_h, *_h.parents)\n"
                 "                            if (p / 'tutorial').is_dir())))\n"
                 "from tutorial.progress import Progress\n"
                 "from tutorial.registry import all_lessons\n"
                 "\n"
                 "p = Progress.load()\n"
                 "for les in all_lessons():\n"
                 "    done = p.exercise_count(les.key)\n"
                 "    total = len(les.exercises())\n"
                 "    bar = '█' * done + '·' * (total - done)\n"
                 "    print(f'{les.number:02d} {les.title:<42} {bar} {done}/{total}')"),
        ], "index"),
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def serialise(notebook: dict[str, Any]) -> str:
    return json.dumps(notebook, indent=1) + "\n"


def write_notebooks(
    dest: str | Path = "notebooks", force: bool = False
) -> tuple[list[Path], list[Path]]:
    """Generate the notebooks, returning (written, skipped).

    A notebook whose content differs from what we would generate is assumed
    to contain your work and is **left alone** — these files are where you
    solve the exercises, and regenerating the course must never silently
    delete that. `force=True` overwrites regardless.

    Generation is deterministic (cell ids included), so an untouched notebook
    compares equal and is rewritten harmlessly.
    """
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    lessons = all_lessons()

    targets: list[tuple[Path, dict[str, Any]]] = [
        (out / "00-START-HERE.ipynb", index_notebook(lessons)),
        *((out / f"{les.key}.ipynb", lesson_notebook(les)) for les in lessons),
    ]

    written: list[Path] = []
    skipped: list[Path] = []
    for path, notebook in targets:
        payload = serialise(notebook)
        if not force and path.exists() and path.read_text() != payload:
            skipped.append(path)
            continue
        path.write_text(payload)
        written.append(path)
    return written, skipped
