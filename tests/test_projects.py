"""Meta-tests for the capstone projects.

These verify the projects are *solvable* and *unsolved*: every reference
solution must pass its own suite, and every untouched starter must fail it.
Both run the real pytest suite in a subprocess so the grading path the
learner uses is the one under test.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tutorial.progress import ROOT
from tutorial.projects import PROJECTS


def run_suite(project, solutions: bool) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if solutions:
        env["TUTORIAL_SOLUTIONS"] = "1"
    else:
        env.pop("TUTORIAL_SOLUTIONS", None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(project.tests), "-m", "project",
         "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


@pytest.mark.parametrize("project", PROJECTS, ids=[p.slug for p in PROJECTS])
def test_project_files_exist(project):
    assert project.path.is_dir(), f"missing directory {project.path}"
    assert (project.path / "README.md").exists(), "every project needs a brief"
    assert project.starter.exists(), f"missing starter {project.starter}"
    assert project.tests.exists(), f"missing suite {project.tests}"
    solution = project.path.parent / "_solutions" / f"{project.slug}.py"
    assert solution.exists(), f"missing reference solution {solution}"


@pytest.mark.parametrize("project", PROJECTS, ids=[p.slug for p in PROJECTS])
def test_reference_solution_passes(project):
    completed = run_suite(project, solutions=True)
    assert completed.returncode == 0, (
        f"{project.slug}: the reference solution does not pass its own suite\n"
        + completed.stdout[-4000:]
    )


@pytest.mark.parametrize("project", PROJECTS, ids=[p.slug for p in PROJECTS])
def test_starter_does_not_pass(project):
    completed = run_suite(project, solutions=False)
    assert completed.returncode != 0, (
        f"{project.slug}: the untouched starter already passes — "
        "the suite is not testing anything"
    )


def test_every_project_is_reachable_from_the_cli():
    from tutorial.projects import find

    for project in PROJECTS:
        assert find(project.slug) is project
    assert find("no-such-project") is None
    assert find("1") is PROJECTS[0]


def test_project_metadata():
    slugs = [p.slug for p in PROJECTS]
    assert len(set(slugs)) == len(slugs), "duplicate project slug"
    for project in PROJECTS:
        assert project.title and project.blurb
        assert project.lessons, "a project should say which lessons it draws on"
        assert project.difficulty in {"medium", "hard", "brutal"}
