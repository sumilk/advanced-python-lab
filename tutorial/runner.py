"""The interactive presenter: turns Lesson blocks into a terminal session."""
from __future__ import annotations

import random
import sys
import textwrap
from pathlib import Path
from typing import Any

from . import ui
from .core import (
    Check,
    Demo,
    Exercise,
    Lesson,
    Predict,
    Question,
    Text,
    run_code,
    version_ok,
)
from .progress import WORKSPACE, Progress


class Quit(Exception):
    """Raised to unwind out of a lesson back to the menu."""


# --------------------------------------------------------------------------
# Block presenters
# --------------------------------------------------------------------------
def show_text(block: Text) -> None:
    ui.p(block.body)


def show_demo(block: Demo, shared_ns: dict[str, Any]) -> None:
    print()
    print(ui.color("  ▶ live code", "bold", "magenta"))
    print(ui.code_block(block.code))

    if not version_ok(block.min_version):
        v = ".".join(map(str, block.min_version))
        print(ui.warn(f"needs Python {v}+, you are on "
                      f"{sys.version_info.major}.{sys.version_info.minor} "
                      f"— shown but not executed"))
        if block.explain:
            ui.p(block.explain)
        return

    ns = dict(shared_ns)
    if block.setup:
        run_code(block.setup, ns)
    result = run_code(block.code, ns)
    shared_ns.update({k: v for k, v in ns.items() if not k.startswith("__")})

    body: list[str] = []
    if result.stdout:
        body.extend(result.stdout.rstrip("\n").split("\n"))
    if result.failed:
        tag = "expected error" if block.expect_error else "ERROR"
        style = "yellow" if block.expect_error else "bright_red"
        if body:
            body.append("")
        body.append(ui.color(f"— {tag} —", style, "bold"))
        body.extend(result.traceback_text.rstrip("\n").split("\n")[-6:])
    if not body:
        body = [ui.color("(no output)", "grey")]

    print(ui.color("  output", "grey"))
    for line in ui.box(body, style="grey"):
        print(line)

    if block.explain:
        ui.p(block.explain)


def show_predict(block: Predict, interactive: bool) -> None:
    print()
    print(ui.color("  ❓ predict the output", "bold", "bright_yellow"))
    print(ui.code_block(block.code))
    if interactive:
        ui.ask("\n  your guess (Enter to reveal): ")
    print(ui.color("  actual:", "grey"))
    for line in ui.box(block.answer.strip("\n").split("\n"), style="green"):
        print(line)
    if block.explain:
        ui.p(block.explain)


def ask_question(q: Question, interactive: bool) -> bool:
    """Present one question. Returns True if answered correctly."""
    print()
    ui.p("### " + q.prompt)
    letters = "abcdefgh"
    for i, choice in enumerate(q.choices):
        print(f"   {ui.color(letters[i] + ')', 'cyan')} {ui.inline(choice)}")

    correct = q.correct_set()
    multi = q.answers is not None
    if not interactive:
        picked = correct
    else:
        hint = "letters, comma separated" if multi else "letter"
        while True:
            raw = ui.ask(f"\n   your answer ({hint}, or 's' to skip): ").lower()
            if raw in {"s", "skip", ""}:
                picked = set()
                break
            parts = [p.strip() for p in raw.replace(" ", ",").split(",") if p.strip()]
            if all(p in letters[: len(q.choices)] for p in parts) and parts:
                picked = {letters.index(p) for p in parts}
                break
            print(ui.warn("pick from " + ", ".join(letters[: len(q.choices)])))

    right = picked == correct
    if right:
        print(ui.ok(ui.color("correct", "bright_green", "bold")))
    else:
        want = ", ".join(letters[i] for i in sorted(correct))
        print(ui.fail(f"not quite — the answer is {ui.color(want, 'bold')}"))
    if q.explain:
        ui.p("> " + q.explain.strip().replace("\n", "\n> "))
    return right


# --------------------------------------------------------------------------
# Exercises
# --------------------------------------------------------------------------
def exercise_path(lesson_key: str, ex: Exercise) -> Path:
    return WORKSPACE / lesson_key / f"{ex.slug}.py"


def ensure_exercise_file(lesson_key: str, ex: Exercise) -> Path:
    path = exercise_path(lesson_key, ex)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        header = textwrap.dedent(f'''\
            """{ex.title}

            {textwrap.indent(textwrap.dedent(ex.brief).strip(), "            ").strip()}

            Run `python learn.py check {lesson_key}/{ex.slug}` when you are ready,
            or press 'c' in the lesson.
            """
            ''')
        path.write_text(header + "\n" + textwrap.dedent(ex.starter).strip() + "\n")
    return path


DIFFICULTY_STYLE = {
    "warmup": ("warmup", "green"),
    "medium": ("medium", "yellow"),
    "tricky": ("tricky", "bright_magenta"),
    "brutal": ("brutal", "bright_red"),
}


def run_checks(source: str, ex: Exercise, filename: str) -> tuple[int, list[str]]:
    """Execute the learner's file, then run every Check against its namespace."""
    result = run_code(source, filename=filename)
    lines: list[str] = []
    if result.failed:
        lines.append(ui.fail("your file raised before checks could run:"))
        lines.extend("    " + ln for ln in
                     result.traceback_text.rstrip("\n").split("\n")[-5:])
        return 0, lines

    passed = 0
    for check in ex.checks:
        try:
            check.fn(result.namespace)
        except AssertionError as exc:
            msg = str(exc) or "assertion failed"
            lines.append(ui.fail(f"{check.label}: {ui.color(msg, 'red')}"))
        except Exception as exc:                       # noqa: BLE001
            lines.append(ui.fail(f"{check.label}: {type(exc).__name__}: {exc}"))
        else:
            passed += 1
            lines.append(ui.ok(check.label))
    return passed, lines


def show_exercise(ex: Exercise, lesson_key: str, prog: Progress,
                  interactive: bool) -> None:
    label, style = DIFFICULTY_STYLE.get(ex.difficulty, ("medium", "yellow"))
    print()
    print(ui.color(f"  ⚒ exercise — {ex.title} ", "bold", "bright_white")
          + ui.color(f"[{label}]", style, "bold"))
    ui.p(ex.brief)

    path = ensure_exercise_file(lesson_key, ex)
    rel = path.relative_to(WORKSPACE.parent)
    print(ui.info(f"edit {ui.color(str(rel), 'bright_yellow')}"))
    slug_id = f"{lesson_key}/{ex.slug}"
    if slug_id in prog.exercises_done:
        print(ui.ok(ui.color("already solved", "green")))

    if not interactive:
        return

    hint_i = 0
    while True:
        raw = ui.ask("\n  [c]heck  [h]int  [s]olution  [r]eset  [Enter] skip → ").lower()
        if raw in {"", "n", "skip"}:
            return
        if raw.startswith("c"):
            passed, lines = run_checks(path.read_text(), ex, str(path))
            print()
            for line in lines:
                print("   " + line)
            total = len(ex.checks)
            if passed == total:
                print("\n   " + ui.color(f"★ all {total} checks pass", "bright_green", "bold"))
                prog.mark_exercise(slug_id)
                return
            print("\n   " + ui.color(f"{passed}/{total} checks pass", "yellow"))
        elif raw.startswith("h"):
            if hint_i < len(ex.hints):
                print("   " + ui.color("hint: ", "bright_yellow") + ui.inline(ex.hints[hint_i]))
                hint_i += 1
            else:
                print("   " + ui.color("no more hints — try 's' for the solution", "grey"))
        elif raw.startswith("s"):
            if not ex.solution:
                print(ui.warn("no solution recorded for this one"))
                continue
            print()
            print(ui.color("  one working solution:", "grey"))
            print(ui.code_block(textwrap.dedent(ex.solution).strip()))
        elif raw.startswith("r"):
            path.unlink(missing_ok=True)
            ensure_exercise_file(lesson_key, ex)
            print(ui.ok("starter restored"))


# --------------------------------------------------------------------------
# Lesson driver
# --------------------------------------------------------------------------
def play_lesson(lesson: Lesson, prog: Progress, interactive: bool = True,
                start_at: int = 0) -> None:
    ui.clear()
    print(ui.title_bar(f"Lesson {lesson.number:02d} — {lesson.title}"))
    ui.p(lesson.summary)
    if lesson.tags:
        print("  " + ui.color(" ".join("#" + t for t in lesson.tags), "grey"))

    shared_ns: dict[str, Any] = {}
    right = total = 0

    blocks = lesson.blocks[start_at:]
    for i, block in enumerate(blocks):
        if isinstance(block, Text):
            show_text(block)
        elif isinstance(block, Demo):
            show_demo(block, shared_ns)
        elif isinstance(block, Predict):
            show_predict(block, interactive)
        elif isinstance(block, Question):
            total += 1
            right += int(ask_question(block, interactive))
        elif isinstance(block, Exercise):
            show_exercise(block, lesson.key, prog, interactive)

        # Breathe between heavyweight blocks so output does not scroll away.
        if interactive and isinstance(block, (Demo, Predict)) and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if isinstance(nxt, (Text, Question, Exercise)):
                ui.pause()

    if total:
        pct = round(100 * right / total)
        colour = "bright_green" if pct >= 80 else "yellow" if pct >= 50 else "bright_red"
        print()
        print(ui.color(f"  quiz: {right}/{total} ({pct}%)", colour, "bold"))
        prog.record_quiz(lesson.key, right, total)

    prog.mark_read(lesson.key)
    print()
    print(ui.rule())
    print(ui.ok(ui.color(f"lesson {lesson.number:02d} complete", "bright_green", "bold")))
    solved = prog.exercise_count(lesson.key)
    n_ex = len(lesson.exercises())
    if n_ex:
        print(ui.info(f"exercises solved: {solved}/{n_ex}"))
    if interactive:
        ui.pause("Press Enter to return to the menu …")


def quiz_only(lessons: list[Lesson], prog: Progress, count: int = 12,
              seed: int | None = None) -> None:
    """A mixed quiz drawn from every lesson -- the 'exam' mode."""
    pool = [(les, q) for les in lessons for q in les.questions()]
    rng = random.Random(seed)
    rng.shuffle(pool)
    picked = pool[:count]
    ui.clear()
    print(ui.title_bar(f"Mixed quiz — {len(picked)} questions"))
    right = 0
    for n, (les, q) in enumerate(picked, 1):
        print()
        print(ui.color(f"  Q{n}/{len(picked)}", "grey")
              + ui.color(f"   (lesson {les.number:02d}: {les.title})", "grey", "italic"))
        right += int(ask_question(q, interactive=True))
    pct = round(100 * right / max(len(picked), 1))
    print()
    print(ui.rule())
    grade = ("mastery" if pct >= 90 else "solid" if pct >= 75
             else "getting there" if pct >= 50 else "worth a re-read")
    print(ui.color(f"  {right}/{len(picked)} ({pct}%) — {grade}", "bold",
                   "bright_green" if pct >= 75 else "yellow"))
    ui.pause()
