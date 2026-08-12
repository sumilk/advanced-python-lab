"""Capstone projects: multi-lesson builds graded by real pytest suites.

Each project lives in `projects/<slug>/` with three files:

    README.md            the brief
    <slug>.py            the starter you fill in
    test_<slug>.py       the grading suite

Project tests carry the `project` marker and are deselected from the normal
`uv run pytest` run, because an untouched starter is *supposed* to fail.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import ui
from .progress import ROOT

PROJECTS_DIR = ROOT / "projects"


@dataclass(frozen=True)
class Project:
    slug: str
    title: str
    blurb: str
    lessons: tuple[int, ...]
    difficulty: str
    concepts: tuple[str, ...]

    @property
    def path(self) -> Path:
        return PROJECTS_DIR / self.slug

    @property
    def starter(self) -> Path:
        return self.path / f"{self.slug}.py"

    @property
    def tests(self) -> Path:
        return self.path / f"test_{self.slug}.py"


PROJECTS: tuple[Project, ...] = (
    Project(
        slug="tinyorm",
        title="TinyORM — a declarative model layer",
        blurb="Fields as descriptors, models built by a metaclass, and a chainable "
              "query builder over an in-memory store.",
        lessons=(2, 9, 10, 13),
        difficulty="hard",
        concepts=("descriptors", "__set_name__", "metaclasses", "__init_subclass__",
                  "dunder protocols", "validation"),
    ),
    Project(
        slug="resilient",
        title="Resilient — a fault-tolerance toolkit",
        blurb="Retry with backoff, a circuit breaker, a token-bucket rate limiter and "
              "a bulkhead — each usable as a decorator and as a context manager.",
        lessons=(7, 11, 12, 18),
        difficulty="hard",
        concepts=("decorators", "context managers", "ContextDecorator",
                  "exception design", "state machines", "injectable clocks"),
    ),
    Project(
        slug="streamz",
        title="Streamz — a lazy data pipeline",
        blurb="A composable, single-pass streaming toolkit: map/filter/window/group, "
              "fan-out, and a terminal fold — all lazy, all O(1) memory.",
        lessons=(4, 5, 15),
        difficulty="medium",
        concepts=("generators", "itertools", "laziness", "operator overloading",
                  "one-shot iterators"),
    ),
    Project(
        slug="scheduler",
        title="Scheduler — an async DAG task runner",
        blurb="Run tasks with declared dependencies, maximum parallelism, retries, "
              "timeouts and cancellation. Cycle detection included.",
        lessons=(12, 18, 19),
        difficulty="hard",
        concepts=("asyncio", "TaskGroup", "topological sort", "cancellation",
                  "ExceptionGroup", "structured concurrency"),
    ),
    Project(
        slug="lintly",
        title="Lintly — a pluggable AST linter",
        blurb="A rule-registry linter over the AST: naming, complexity, mutable "
              "defaults, shadowed builtins — with noqa support and a plugin API.",
        lessons=(10, 16, 22),
        difficulty="hard",
        concepts=("ast", "NodeVisitor", "plugin registries", "__init_subclass__",
                  "source analysis"),
    ),
)


def find(slug: str) -> Project | None:
    slug = slug.strip().lower()
    exact = next((p for p in PROJECTS if p.slug == slug), None)
    if exact:
        return exact
    if slug.isdigit() and 1 <= int(slug) <= len(PROJECTS):
        return PROJECTS[int(slug) - 1]
    matches = [p for p in PROJECTS if slug and slug in p.slug]
    return matches[0] if len(matches) == 1 else None


DIFFICULTY_COLOUR = {"medium": "yellow", "hard": "bright_magenta", "brutal": "bright_red"}


def _status(project: Project) -> str:
    """A cheap heuristic: has the starter been edited at all?"""
    if not project.starter.exists():
        return ui.color("missing", "red")
    body = project.starter.read_text()
    if body.count("...") > 3:
        return ui.color("not started", "grey")
    return ui.color("in progress", "yellow")


def listing() -> None:
    print(ui.title_bar("Capstone Projects"))
    print()
    for n, project in enumerate(PROJECTS, 1):
        colour = DIFFICULTY_COLOUR.get(project.difficulty, "yellow")
        print(f"  {ui.color(str(n), 'cyan', 'bold')}. "
              + ui.color(project.title, "bold")
              + "  " + ui.color(f"[{project.difficulty}]", colour)
              + "  " + _status(project))
        ui.p("     " + project.blurb)
        print("     " + ui.color("lessons " + ", ".join(f"{n:02d}" for n in project.lessons)
                                 + " · " + " · ".join(project.concepts), "grey"))
        print()


def show(project: Project) -> None:
    ui.clear()
    print(ui.title_bar(project.title))
    readme = project.path / "README.md"
    if readme.exists():
        ui.p(readme.read_text())
    print()
    print(ui.info(f"starter: {ui.color(str(project.starter.relative_to(ROOT)), 'bright_yellow')}"))
    print(ui.info(f"tests  : {project.tests.relative_to(ROOT)}"))
    print(ui.info(f"grade  : {ui.color(f'uv run learn.py projects test {project.slug}', 'bright_yellow')}"))


def run_tests(project: Project, verbose: bool = False) -> int:
    """Grade a project by running its pytest suite in a subprocess."""
    if not project.tests.exists():
        print(ui.fail(f"no test suite at {project.tests}"))
        return 2
    print(ui.color(f"running {project.tests.relative_to(ROOT)} …", "grey"))
    print()
    argv = [sys.executable, "-m", "pytest", str(project.tests),
            "-m", "project", "--no-header", "-p", "no:cacheprovider"]
    argv.append("-v" if verbose else "-q")
    completed = subprocess.run(argv, cwd=ROOT)
    print()
    if completed.returncode == 0:
        print(ui.ok(ui.color(f"{project.title} — all tests pass", "bright_green", "bold")))
    else:
        print(ui.warn("not there yet — read the failures above"))
    return completed.returncode


def menu() -> None:
    while True:
        ui.clear()
        listing()
        print(ui.color("  commands: <number> open   t <number> test   x back", "grey"))
        raw = ui.ask("\n  > ").lower().strip()
        if raw in {"x", "q", "back", ""}:
            return
        if raw.startswith("t"):
            project = find(raw[1:].strip())
            if project is None:
                print(ui.warn("no such project"))
                ui.pause()
                continue
            run_tests(project)
            ui.pause()
            continue
        project = find(raw)
        if project is None:
            print(ui.warn("no such project"))
            ui.pause()
            continue
        show(project)
        ui.pause()


def main(argv: list[str]) -> int:
    if not argv:
        listing()
        print(ui.color("  uv run learn.py projects show <slug>", "grey"))
        print(ui.color("  uv run learn.py projects test <slug>", "grey"))
        return 0

    command, *rest = argv
    if command in {"list", "ls"}:
        listing()
        return 0
    if command in {"show", "open"}:
        project = find(rest[0]) if rest else None
        if project is None:
            print(ui.fail("usage: learn.py projects show <slug>"))
            return 2
        show(project)
        return 0
    if command in {"test", "check", "grade"}:
        if not rest:
            failures = 0
            for project in PROJECTS:
                print(ui.color(f"\n── {project.title} ", "bold"))
                failures += bool(run_tests(project))
            return 1 if failures else 0
        project = find(rest[0])
        if project is None:
            print(ui.fail(f"unknown project {rest[0]!r}"))
            return 2
        return run_tests(project, verbose="-v" in rest)

    project = find(command)
    if project is not None:
        show(project)
        return 0
    print(ui.fail(f"unknown project command {command!r}"))
    return 2
