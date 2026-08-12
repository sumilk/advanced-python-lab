"""Self-validation of the course content.

This is the safety net that keeps a 20-lesson tutorial honest:

* every Demo actually executes (unless it declares `expect_error`)
* every Predict block's stated output matches what Python really prints
* every Exercise's reference solution passes every one of its own checks
* every Exercise starter *fails* at least one check (else it teaches nothing)
* quiz answers point at real choices

Run with:  uv run pytest -q
"""
from __future__ import annotations

import textwrap

import pytest

from tutorial.core import Demo, Exercise, Predict, Question, Text, run_code, version_ok
from tutorial.registry import all_lessons
from tutorial.runner import run_checks

LESSONS = all_lessons()


def _ids(seq):
    return [f"{les.key}#{i}" for les, i, _ in seq]


def _blocks(kind):
    return [(les, i, b) for les in LESSONS
            for i, b in enumerate(les.blocks) if isinstance(b, kind)]


def test_lessons_are_discovered():
    assert len(LESSONS) >= 1
    numbers = [les.number for les in LESSONS]
    assert numbers == sorted(numbers), "lesson numbers must be ordered"
    assert len(set(numbers)) == len(numbers), "duplicate lesson numbers"


def test_lesson_keys_unique():
    keys = [les.key for les in LESSONS]
    assert len(set(keys)) == len(keys)


def test_exercise_slugs_unique_within_lesson():
    for les in LESSONS:
        slugs = [ex.slug for ex in les.exercises()]
        assert len(set(slugs)) == len(slugs), f"duplicate exercise slug in {les.key}"


DEMOS = _blocks(Demo)


@pytest.mark.parametrize("lesson,index,demo", DEMOS, ids=_ids(DEMOS))
def test_demo_runs(lesson, index, demo: Demo):
    if not version_ok(demo.min_version):
        pytest.skip(f"needs Python {demo.min_version}")
    ns: dict = {}
    if demo.setup:
        setup = run_code(demo.setup, ns)
        assert not setup.failed, f"setup failed:\n{setup.traceback_text}"
    result = run_code(demo.code, ns)
    if demo.expect_error:
        return                       # raising is allowed, not required
    assert not result.failed, (
        f"{lesson.key} demo #{index} raised unexpectedly:\n{result.traceback_text}"
    )


PREDICTS = _blocks(Predict)


@pytest.mark.parametrize("lesson,index,block", PREDICTS, ids=_ids(PREDICTS))
def test_prediction_matches_reality(lesson, index, block: Predict):
    result = run_code(block.code)
    assert not result.failed, f"predict block raised:\n{result.traceback_text}"
    actual = textwrap.dedent(result.stdout).strip()
    claimed = textwrap.dedent(block.answer).strip()
    assert actual == claimed, (
        f"{lesson.key} Predict #{index} claims:\n{claimed}\n\nbut prints:\n{actual}"
    )


QUESTIONS = _blocks(Question)


@pytest.mark.parametrize("lesson,index,q", QUESTIONS, ids=_ids(QUESTIONS))
def test_question_well_formed(lesson, index, q: Question):
    assert len(q.choices) >= 2
    assert (q.answer is None) != (q.answers is None), "set exactly one of answer/answers"
    for idx in q.correct_set():
        assert 0 <= idx < len(q.choices), f"answer index {idx} out of range"
    assert q.explain.strip(), "every question needs an explanation"


EXERCISES = [(les, i, b) for les in LESSONS
             for i, b in enumerate(les.blocks) if isinstance(b, Exercise)]


@pytest.mark.parametrize("lesson,index,ex", EXERCISES, ids=_ids(EXERCISES))
def test_reference_solution_passes(lesson, index, ex: Exercise):
    assert ex.solution.strip(), f"{lesson.key}/{ex.slug} has no reference solution"
    source = textwrap.dedent(ex.solution)
    passed, lines = run_checks(source, ex, f"<solution {ex.slug}>")
    assert passed == len(ex.checks), (
        f"{lesson.key}/{ex.slug}: solution passes {passed}/{len(ex.checks)}\n"
        + "\n".join(lines)
    )


@pytest.mark.parametrize("lesson,index,ex", EXERCISES, ids=_ids(EXERCISES))
def test_starter_does_not_already_pass(lesson, index, ex: Exercise):
    source = textwrap.dedent(ex.starter)
    passed, _ = run_checks(source, ex, f"<starter {ex.slug}>")
    assert passed < len(ex.checks), (
        f"{lesson.key}/{ex.slug}: the starter already passes — nothing to solve"
    )


@pytest.mark.parametrize("lesson,index,ex", EXERCISES, ids=_ids(EXERCISES))
def test_exercise_metadata(lesson, index, ex: Exercise):
    assert ex.checks, "an exercise with no checks cannot be graded"
    assert ex.difficulty in {"warmup", "medium", "tricky", "brutal"}
    assert ex.brief.strip()


def test_every_lesson_has_prose_demos_quiz_and_exercise():
    for les in LESSONS:
        kinds = {type(b) for b in les.blocks}
        assert Text in kinds, f"{les.key} has no prose"
        assert Demo in kinds, f"{les.key} has no runnable demo"
        assert Question in kinds, f"{les.key} has no quiz question"
        assert Exercise in kinds, f"{les.key} has no exercise"


# --------------------------------------------------------------------------
# Cross-front-end hazards
# --------------------------------------------------------------------------
GRADER_API = {"check", "hint", "solution"}


@pytest.mark.parametrize("lesson,index,block", DEMOS + PREDICTS,
                         ids=_ids(DEMOS) + _ids(PREDICTS))
def test_demos_do_not_shadow_the_grader(lesson, index, block):
    """Notebook cells share one namespace with the grader.

    A demo that binds `check` at top level silently replaces `check(...)`,
    so the exercise cell below it grades against the wrong function.
    """
    import ast

    tree = ast.parse(textwrap.dedent(block.code))
    bound = set()
    for node in tree.body:                       # top level only
        match node:
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                bound.add(node.name)
            case ast.Assign(targets=targets):
                bound |= {t.id for t in targets if isinstance(t, ast.Name)}
            case ast.Import() | ast.ImportFrom():
                bound |= {a.asname or a.name.split(".")[0] for a in node.names}

    clash = bound & GRADER_API
    assert not clash, (
        f"{lesson.key} block #{index} binds {sorted(clash)} at module level, "
        f"which shadows the notebook grader. Rename it."
    )
