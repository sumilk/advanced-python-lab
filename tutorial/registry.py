"""Discovers lesson modules. Each `tutorial/lessons/lNN_*.py` exposes LESSON."""
from __future__ import annotations

import importlib
import pkgutil
from functools import cache

from .core import Lesson


@cache
def all_lessons() -> tuple[Lesson, ...]:
    from . import lessons as pkg

    found: list[Lesson] = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if not mod_info.name.startswith("l"):
            continue
        module = importlib.import_module(f"{pkg.__name__}.{mod_info.name}")
        lesson = getattr(module, "LESSON", None)
        if isinstance(lesson, Lesson):
            found.append(lesson)
    return tuple(sorted(found, key=lambda les: les.number))


def find_lesson(token: str) -> Lesson | None:
    """Look a lesson up by number ('7', '07'), slug, or key ('07-descriptors')."""
    token = token.strip().lower()
    for lesson in all_lessons():
        if token in {str(lesson.number), f"{lesson.number:02d}", lesson.slug, lesson.key}:
            return lesson
    matches = [les for les in all_lessons() if token and token in les.slug]
    return matches[0] if len(matches) == 1 else None


def find_exercise(token: str):
    """Resolve 'NN-slug/exercise' or a bare exercise slug -> (Lesson, Exercise)."""
    token = token.strip().strip("/")
    lesson_part, _, ex_part = token.partition("/")
    for lesson in all_lessons():
        for ex in lesson.exercises():
            if ex_part:
                if ex.slug == ex_part and lesson_part in {lesson.key, lesson.slug,
                                                          str(lesson.number),
                                                          f"{lesson.number:02d}"}:
                    return lesson, ex
            elif ex.slug == lesson_part:
                return lesson, ex
    return None, None
