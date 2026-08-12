"""Progress tracking, persisted as JSON next to the tutorial.

The file is shared by every front-end: the terminal runner holds a Progress
for a whole session, while `grader.check()` in a notebook loads, mutates and
saves on each call. A blind dump of in-memory state would therefore let a
long-lived terminal session overwrite everything a notebook recorded while it
was open. Writes are merges: reload, union, then replace atomically.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / ".progress.json"
WORKSPACE = ROOT / "workspace"

_LOCK_TIMEOUT = 2.0          # seconds; bookkeeping must never block a lesson
_LOCK_POLL = 0.02


@dataclass
class Progress:
    lessons_read: set[str] = field(default_factory=set)
    exercises_done: set[str] = field(default_factory=set)
    quiz_scores: dict[str, list[int]] = field(default_factory=dict)  # key -> [right, total]
    path: Path = STATE_PATH

    # -- persistence -------------------------------------------------------
    @classmethod
    def _read(cls, path: Path) -> Progress:
        """Parse the file, or return an empty Progress if it is absent/corrupt."""
        if not path.exists():
            return cls(path=path)
        try:
            raw: dict[str, Any] = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return cls(path=path)
        if not isinstance(raw, dict):
            return cls(path=path)
        return cls(
            lessons_read=_str_set(raw.get("lessons_read")),
            exercises_done=_str_set(raw.get("exercises_done")),
            quiz_scores=_quiz_scores(raw.get("quiz_scores")),
            path=path,
        )

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> Progress:
        return cls._read(path)

    def absorb(self, other: Progress) -> None:
        """Fold *other* into self. Union the sets, keep the better quiz score."""
        self.lessons_read |= other.lessons_read
        self.exercises_done |= other.exercises_done
        for key, (right, total) in other.quiz_scores.items():
            mine = self.quiz_scores.get(key)
            if mine is None or right / max(total, 1) > mine[0] / max(mine[1], 1):
                self.quiz_scores[key] = [right, total]

    def save(self, merge: bool = True) -> None:
        """Persist. By default the on-disk state is folded in first.

        merge=False is for `reset`, which must be able to shrink the file.
        """
        with _lock(self.path):
            if merge:
                self.absorb(Progress._read(self.path))
            payload = {
                "lessons_read": sorted(self.lessons_read),
                "exercises_done": sorted(self.exercises_done),
                "quiz_scores": {k: self.quiz_scores[k] for k in sorted(self.quiz_scores)},
            }
            _atomic_write(self.path, json.dumps(payload, indent=2) + "\n")

    # -- mutations ---------------------------------------------------------
    def mark_read(self, lesson_key: str) -> None:
        self.lessons_read.add(lesson_key)
        self.save()

    def mark_exercise(self, slug: str) -> None:
        self.exercises_done.add(slug)
        self.save()

    def record_quiz(self, lesson_key: str, right: int, total: int) -> None:
        prev = self.quiz_scores.get(lesson_key, [0, 0])
        # Keep the best attempt; re-taking a quiz should never look worse.
        if right / max(total, 1) >= prev[0] / max(prev[1], 1):
            self.quiz_scores[lesson_key] = [right, total]
        self.save()

    # -- queries -----------------------------------------------------------
    def exercise_count(self, lesson_key: str) -> int:
        return sum(1 for s in self.exercises_done if s.startswith(lesson_key + "/"))

    def refresh(self) -> None:
        """Pull in anything another front-end has recorded since we loaded."""
        self.absorb(Progress._read(self.path))

    def reset(self) -> None:
        self.lessons_read.clear()
        self.exercises_done.clear()
        self.quiz_scores.clear()
        self.save(merge=False)


# --------------------------------------------------------------------------
# Reading a file we do not control
# --------------------------------------------------------------------------
# .progress.json sits in the repo root, so it gets hand-edited, half-merged by
# git, and copied between machines. Anything malformed is dropped rather than
# allowed to crash a lesson.
def _str_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _quiz_scores(value: Any) -> dict[str, list[int]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[int]] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or isinstance(entry, (str, bytes)):
            continue
        try:
            right, total = entry
        except (TypeError, ValueError):
            continue
        if isinstance(right, int) and isinstance(total, int) and 0 <= right <= total:
            out[key] = [right, total]
    return out


# --------------------------------------------------------------------------
# File plumbing
# --------------------------------------------------------------------------
_warned = False


def _warn_once(detail: str) -> None:
    """Say something the first time a write fails, then stay quiet.

    Silently losing progress is worse than a line of noise, but a warning on
    every single `check()` would be its own problem.
    """
    global _warned
    if not _warned:
        _warned = True
        print(f"could not save progress ({detail}) — solutions will not persist",
              file=sys.stderr)


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename over the target.

    os.replace is atomic on POSIX and Windows, so a reader never sees a
    half-written file even if we die mid-write.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        _warn_once(str(exc))      # never let bookkeeping break a lesson


class _lock:
    """A best-effort inter-process lock: an exclusively-created sibling file.

    It closes the read-merge-write race between a notebook kernel and a
    terminal session. If the lock cannot be taken within the timeout we
    proceed anyway -- a lost update is bad, a hung tutorial is worse.
    """

    def __init__(self, target: Path):
        self.path = target.with_suffix(target.suffix + ".lock")
        self.held = False

    def __enter__(self) -> _lock:
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if _stale(self.path) or time.monotonic() > deadline:
                    self.path.unlink(missing_ok=True)
                    continue
                time.sleep(_LOCK_POLL)
                continue
            except OSError:
                return self                     # unwritable dir; carry on unlocked
            os.close(fd)
            self.held = True
            return self

    def __exit__(self, *exc: object) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)


def _stale(path: Path, max_age: float = 30.0) -> bool:
    """A lock left behind by a killed process should not wedge the course."""
    try:
        return time.time() - path.stat().st_mtime > max_age
    except OSError:
        return True
