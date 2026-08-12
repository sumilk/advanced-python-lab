"""Progress tracking, persisted as JSON next to the tutorial."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / ".progress.json"
WORKSPACE = ROOT / "workspace"


@dataclass
class Progress:
    lessons_read: set[str] = field(default_factory=set)
    exercises_done: set[str] = field(default_factory=set)
    quiz_scores: dict[str, list[int]] = field(default_factory=dict)  # key -> [right, total]
    path: Path = STATE_PATH

    # -- persistence -------------------------------------------------------
    @classmethod
    def load(cls, path: Path = STATE_PATH) -> Progress:
        if not path.exists():
            return cls(path=path)
        try:
            raw: dict[str, Any] = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return cls(path=path)
        return cls(
            lessons_read=set(raw.get("lessons_read", [])),
            exercises_done=set(raw.get("exercises_done", [])),
            quiz_scores={k: list(v) for k, v in raw.get("quiz_scores", {}).items()},
            path=path,
        )

    def save(self) -> None:
        payload = {
            "lessons_read": sorted(self.lessons_read),
            "exercises_done": sorted(self.exercises_done),
            "quiz_scores": self.quiz_scores,
        }
        try:
            self.path.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError:
            pass                      # never let bookkeeping break a lesson

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

    def reset(self) -> None:
        self.lessons_read.clear()
        self.exercises_done.clear()
        self.quiz_scores.clear()
        self.save()
