#!/usr/bin/env python3
"""Interactive tutorial for intermediate and advanced Python.

    uv run learn.py                    # menu
    uv run learn.py lesson 7           # jump straight to a lesson
    uv run learn.py list               # curriculum overview
    uv run learn.py check 05-decorators/retry   # grade one exercise
    uv run learn.py quiz [n]           # mixed exam across every lesson
    uv run learn.py projects           # capstone projects
    uv run learn.py export docs/       # dump the whole course to markdown
    uv run learn.py reset              # wipe progress
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tutorial import ui                                        # noqa: E402
from tutorial.core import Demo, Exercise, Question, Text        # noqa: E402
from tutorial.progress import Progress                          # noqa: E402
from tutorial.registry import all_lessons, find_exercise, find_lesson  # noqa: E402
from tutorial.runner import play_lesson, quiz_only, run_checks   # noqa: E402
from tutorial.runner import ensure_exercise_file                 # noqa: E402


BANNER = r"""
   ___      _   _                   ___
  | _ \_  _| |_| |_  ___ _ _       |   \ ___ ___ _ __
  |  _/ || |  _| ' \/ _ \ ' \      | |) / -_) -_) '_ \
  |_|  \_, |\__|_||_\___/_||_|     |___/\___\___| .__/
       |__/                                     |_|
"""


def print_banner() -> None:
    ui.clear()
    print(ui.color(BANNER, "bright_cyan"))
    print(ui.color("  Intermediate → Advanced Python, hands on.", "grey"))
    print(ui.color(f"  Running Python {sys.version.split()[0]}", "grey"))
    print()


def lesson_table(prog: Progress) -> None:
    lessons = all_lessons()
    print(ui.color("  #   Lesson                                  read  ex    quiz", "grey", "bold"))
    for les in lessons:
        read = ui.color("✓", "bright_green") if les.key in prog.lessons_read else ui.color("·", "grey")
        n_ex = len(les.exercises())
        done = prog.exercise_count(les.key)
        if n_ex == 0:
            ex_cell = ui.color("  – ", "grey")
        else:
            style = "bright_green" if done == n_ex else "yellow" if done else "grey"
            ex_cell = ui.color(f"{done}/{n_ex}".rjust(4), style)
        score = prog.quiz_scores.get(les.key)
        if score:
            pct = round(100 * score[0] / max(score[1], 1))
            quiz_cell = ui.color(f"{pct:>3}%", "bright_green" if pct >= 75 else "yellow")
        else:
            quiz_cell = ui.color("   –", "grey")
        title = les.title[:38].ljust(38)
        print(f"  {les.number:02d}  {title}   {read}   {ex_cell}   {quiz_cell}")

    total_ex = sum(len(les.exercises()) for les in lessons)
    done_ex = len(prog.exercises_done)
    read = len(prog.lessons_read & {les.key for les in lessons})
    print()
    print(ui.color(f"  progress: {read}/{len(lessons)} lessons · "
                   f"{done_ex}/{total_ex} exercises", "bright_cyan"))


def menu() -> None:
    prog = Progress.load()
    while True:
        print_banner()
        lesson_table(prog)
        print()
        print(ui.color("  commands: ", "grey")
              + "<number> lesson   "
              + ui.color("q", "cyan") + "uiz   "
              + ui.color("p", "cyan") + "rojects   "
              + ui.color("n", "cyan") + "ext   "
              + ui.color("r", "cyan") + "eset   "
              + ui.color("x", "cyan") + " exit")
        raw = ui.ask("\n  > ").lower()
        if raw in {"x", "exit", "quit"}:
            print(ui.color("\n  keep going. — bye\n", "grey"))
            return
        if raw in {"q", "quiz"}:
            quiz_only(list(all_lessons()), prog)
            continue
        if raw in {"p", "projects"}:
            show_projects()
            continue
        if raw in {"r", "reset"}:
            if ui.ask("  really wipe all progress? [y/N] ").lower().startswith("y"):
                prog.reset()
            continue
        if raw in {"n", "next", ""}:
            nxt = next((les for les in all_lessons() if les.key not in prog.lessons_read), None)
            if nxt is None:
                print(ui.ok("every lesson read — try 'q' for the mixed exam"))
                ui.pause()
                continue
            play_lesson(nxt, prog)
            continue
        lesson = find_lesson(raw)
        if lesson is None:
            print(ui.warn("no such lesson"))
            ui.pause()
            continue
        play_lesson(lesson, prog)


def show_projects() -> None:
    from tutorial import projects

    projects.menu()


def cmd_list() -> None:
    prog = Progress.load()
    print_banner()
    for les in all_lessons():
        print(ui.color(f"  {les.number:02d}  {les.title}", "bold"))
        print(ui.color("      " + les.summary.strip().split("\n")[0][:100], "grey"))
        for ex in les.exercises():
            print(ui.color(f"        ⚒ {les.key}/{ex.slug} — {ex.title} [{ex.difficulty}]", "grey"))
    print()
    lesson_table(prog)


def cmd_check(token: str) -> int:
    lesson, ex = find_exercise(token)
    if ex is None:
        print(ui.fail(f"unknown exercise: {token}"))
        print(ui.info("run `uv run learn.py list` to see every exercise id"))
        return 2
    path = ensure_exercise_file(lesson.key, ex)
    print(ui.color(f"  {lesson.key}/{ex.slug} — {ex.title}", "bold"))
    print(ui.color(f"  {path}", "grey"))
    print()
    passed, lines = run_checks(path.read_text(), ex, str(path))
    for line in lines:
        print("   " + line)
    total = len(ex.checks)
    print()
    if passed == total:
        print("   " + ui.color(f"★ all {total} checks pass", "bright_green", "bold"))
        Progress.load().mark_exercise(f"{lesson.key}/{ex.slug}")
        return 0
    print("   " + ui.color(f"{passed}/{total} checks pass", "yellow"))
    return 1


def cmd_export(dest: str) -> None:
    """Write the whole course out as markdown -- handy for reading offline."""
    import textwrap

    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    index = ["# Python: Intermediate → Advanced\n"]
    for les in all_lessons():
        parts = [f"# {les.number:02d} — {les.title}\n", textwrap.dedent(les.summary).strip(), ""]
        for block in les.blocks:
            match block:
                case Text():
                    parts.append(textwrap.dedent(block.body).strip())
                case Demo():
                    parts.append("```python\n" + textwrap.dedent(block.code).strip() + "\n```")
                    if block.explain:
                        parts.append(textwrap.dedent(block.explain).strip())
                case Question():
                    letters = "abcdefgh"
                    parts.append(f"**Quiz.** {block.prompt}\n")
                    parts += [f"- {letters[i]}) {c}" for i, c in enumerate(block.choices)]
                    want = ", ".join(letters[i] for i in sorted(block.correct_set()))
                    parts.append(f"\n<details><summary>answer</summary>\n\n**{want}** — "
                                 f"{textwrap.dedent(block.explain).strip()}\n</details>")
                case Exercise():
                    parts.append(f"## Exercise — {block.title} `[{block.difficulty}]`\n")
                    parts.append(textwrap.dedent(block.brief).strip())
                    parts.append("```python\n" + textwrap.dedent(block.starter).strip() + "\n```")
            parts.append("")
        (out / f"{les.key}.md").write_text("\n".join(parts))
        index.append(f"- [{les.number:02d} — {les.title}]({les.key}.md)")
    (out / "README.md").write_text("\n".join(index) + "\n")
    print(ui.ok(f"exported {len(all_lessons())} lessons to {out}/"))


def main(argv: list[str]) -> int:
    if not argv:
        try:
            menu()
        except KeyboardInterrupt:
            print()
        return 0

    cmd, *rest = argv
    match cmd:
        case "list" | "ls":
            cmd_list()
        case "lesson" | "l":
            if not rest:
                print(ui.fail("usage: learn.py lesson <number|slug>"))
                return 2
            lesson = find_lesson(rest[0])
            if lesson is None:
                print(ui.fail(f"no lesson matching {rest[0]!r}"))
                return 2
            play_lesson(lesson, Progress.load())
        case "check" | "c":
            if not rest:
                print(ui.fail("usage: learn.py check <lesson/exercise>"))
                return 2
            return cmd_check(rest[0])
        case "quiz":
            n = int(rest[0]) if rest and rest[0].isdigit() else 12
            quiz_only(list(all_lessons()), Progress.load(), count=n)
        case "projects" | "project":
            from tutorial import projects
            return projects.main(rest)
        case "export":
            cmd_export(rest[0] if rest else "docs")
        case "notebooks" | "nb":
            from tutorial.notebook import write_notebooks
            written = write_notebooks(rest[0] if rest else "notebooks")
            print(ui.ok(f"wrote {len(written)} notebooks"))
            for path in written:
                print(ui.color(f"    {path}", "grey"))
            print(ui.info("open with:  uv run --with jupyterlab jupyter lab notebooks/"))
        case "site":
            from tutorial.site import build_site
            out = build_site(rest[0] if rest else "site/index.html")
            print(ui.ok(f"wrote {out}"))
        case "reset":
            Progress.load().reset()
            print(ui.ok("progress wiped"))
        case "help" | "-h" | "--help":
            print(__doc__)
        case _:
            print(ui.fail(f"unknown command {cmd!r}"))
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)
