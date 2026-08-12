"""Regression tests for cross-front-end progress sharing.

The hazard these cover: the terminal runner holds one Progress for a whole
session while `grader.check()` in a notebook loads, mutates and saves on every
call. Any write that does not merge will silently discard the other one.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from tutorial.progress import Progress


@pytest.fixture
def state(tmp_path):
    return tmp_path / ".progress.json"


def test_stale_session_does_not_clobber_the_other_front_end(state):
    terminal = Progress.load(state)               # menu opens, file is empty

    for slug in ("09-descriptors/validated-field",
                 "07-decorators/retry",
                 "05-iterators/pipeline"):
        Progress.load(state).mark_exercise(slug)  # notebook grades three solves

    terminal.mark_read("02-datamodel")            # terminal finishes a lesson

    on_disk = Progress.load(state)
    assert on_disk.exercises_done == {
        "09-descriptors/validated-field",
        "07-decorators/retry",
        "05-iterators/pipeline",
    }
    assert on_disk.lessons_read == {"02-datamodel"}


def test_save_refreshes_the_live_object(state):
    """Merging only into the file would leave the terminal's progress table
    showing stale counts for the rest of the session."""
    terminal = Progress.load(state)
    Progress.load(state).mark_exercise("09-descriptors/validated-field")

    terminal.mark_read("01-objects")
    assert terminal.exercise_count("09-descriptors") == 1


def test_quiz_scores_merge_to_the_best_attempt(state):
    a, b = Progress.load(state), Progress.load(state)
    a.record_quiz("18-concurrency", 8, 10)
    b.record_quiz("18-concurrency", 5, 10)        # weaker, and written last
    assert Progress.load(state).quiz_scores["18-concurrency"] == [8, 10]


def test_reset_is_not_undone_by_the_merge(state):
    prog = Progress.load(state)
    prog.mark_exercise("07-decorators/retry")
    prog.mark_read("07-decorators")
    prog.record_quiz("07-decorators", 3, 4)

    prog.reset()

    fresh = Progress.load(state)
    assert not fresh.exercises_done
    assert not fresh.lessons_read
    assert not fresh.quiz_scores


def test_corrupt_state_file_does_not_crash(state):
    state.write_text("{ this is not json")
    prog = Progress.load(state)
    assert prog.exercises_done == set()
    prog.mark_exercise("01-objects/identity")
    assert Progress.load(state).exercises_done == {"01-objects/identity"}


@pytest.mark.parametrize("payload,expected", [
    ({"quiz_scores": {"ok": [3, 4], "bad": "nope"}}, {"ok": [3, 4]}),
    ({"quiz_scores": {"short": [1]}}, {}),
    ({"quiz_scores": {"impossible": [9, 2]}}, {}),
    ({"quiz_scores": []}, {}),
])
def test_malformed_quiz_entries_are_dropped(state, payload, expected):
    """The file lives in the repo root: expect hand edits and bad git merges."""
    state.write_text(json.dumps(payload))
    assert Progress.load(state).quiz_scores == expected


def test_non_string_entries_are_dropped(state):
    state.write_text(json.dumps({"lessons_read": ["01-objects", 7, None],
                                 "exercises_done": "not a list"}))
    prog = Progress.load(state)
    assert prog.lessons_read == {"01-objects"}
    assert prog.exercises_done == set()


def test_unwritable_location_warns_but_does_not_raise(state, capsys, monkeypatch):
    monkeypatch.setattr("tutorial.progress._warned", False)
    monkeypatch.setattr("tutorial.progress.os.replace",
                        lambda *a: (_ for _ in ()).throw(OSError("read-only file system")))
    prog = Progress.load(state)
    prog.mark_exercise("01-objects/identity")            # must not raise
    assert "could not save progress" in capsys.readouterr().err


def test_the_warning_is_printed_only_once(state, capsys, monkeypatch):
    monkeypatch.setattr("tutorial.progress._warned", False)
    monkeypatch.setattr("tutorial.progress.os.replace",
                        lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    prog = Progress.load(state)
    for n in range(5):
        prog.mark_exercise(f"01-objects/ex{n}")
    assert capsys.readouterr().err.count("could not save progress") == 1


def test_no_temp_or_lock_files_are_left_behind(state):
    Progress.load(state).mark_exercise("01-objects/identity")
    assert [p.name for p in state.parent.iterdir()] == [".progress.json"]


def test_concurrent_writers_do_not_lose_updates(state, tmp_path):
    """Six processes, forty writes each. This is the race the lock closes."""
    worker = tmp_path / "worker.py"
    worker.write_text(textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_repo_root())!r})
        from pathlib import Path
        from tutorial.progress import Progress
        for i in range(40):
            Progress.load(Path({str(state)!r})).mark_exercise(f"w{{sys.argv[1]}}/ex{{i}}")
    """))
    procs = [subprocess.Popen([sys.executable, str(worker), str(k)]) for k in range(6)]
    for proc in procs:
        assert proc.wait() == 0

    assert Progress.load(state).exercises_done == {
        f"w{k}/ex{i}" for k in range(6) for i in range(40)
    }


def _repo_root():
    from tutorial import progress
    return progress.ROOT
