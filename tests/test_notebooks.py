"""Notebook renderer checks.

Structural tests always run. Actually *executing* every generated notebook
is opt-in because it needs a kernel and takes a while:

    uv run --with nbclient --with ipykernel pytest -m notebooks
"""
from __future__ import annotations

import json

import pytest

from tutorial.core import Exercise
from tutorial.notebook import index_notebook, lesson_notebook, write_notebooks
from tutorial.registry import all_lessons

LESSONS = all_lessons()


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    dest = tmp_path_factory.mktemp("notebooks")
    written, _skipped = write_notebooks(dest)
    return written, dest


@pytest.mark.parametrize("lesson", LESSONS, ids=[les.key for les in LESSONS])
def test_notebook_is_valid_nbformat(lesson):
    nb = lesson_notebook(lesson)
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    assert nb["cells"], "empty notebook"
    for cell in nb["cells"]:
        assert cell["cell_type"] in {"markdown", "code"}
        assert isinstance(cell["source"], list)
        assert all(isinstance(line, str) for line in cell["source"])
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            assert cell["execution_count"] is None
    # round-trips through JSON exactly as nbformat expects
    json.loads(json.dumps(nb))


@pytest.mark.parametrize("lesson", LESSONS, ids=[les.key for les in LESSONS])
def test_every_exercise_gets_a_starter_and_a_check_cell(lesson):
    nb = lesson_notebook(lesson)
    sources = ["".join(c["source"]) for c in nb["cells"]]
    for ex in lesson.exercises():
        ex_id = f"{lesson.key}/{ex.slug}"
        assert any(f'check("{ex_id}")' in s for s in sources), f"no check cell for {ex_id}"
        assert any(ex.starter.strip().split("\n")[0].strip() in s for s in sources), (
            f"no starter cell for {ex_id}"
        )


@pytest.mark.parametrize("lesson", LESSONS, ids=[les.key for les in LESSONS])
def test_solutions_are_hidden_behind_details(lesson):
    """A solution may appear only inside a collapsed markdown block."""
    import textwrap

    nb = lesson_notebook(lesson)
    for ex in lesson.exercises():
        body = textwrap.dedent(ex.solution).strip()
        holders = [c for c in nb["cells"] if body in "".join(c["source"])]
        assert holders, f"{lesson.key}/{ex.slug}: solution missing from the notebook"
        for cell in holders:
            assert cell["cell_type"] == "markdown", (
                f"{lesson.key}/{ex.slug}: solution leaked into a runnable code cell"
            )
            assert "<details>" in "".join(cell["source"]), (
                f"{lesson.key}/{ex.slug}: solution must be collapsed, not inline"
            )


@pytest.mark.parametrize("lesson", LESSONS, ids=[les.key for les in LESSONS])
def test_error_demos_are_tagged(lesson):
    nb = lesson_notebook(lesson)
    tagged = sum(1 for c in nb["cells"]
                 if "raises-exception" in c["metadata"].get("tags", []))
    expected = sum(1 for b in lesson.blocks if getattr(b, "expect_error", False))
    assert tagged == expected, "expect_error demos need the raises-exception tag"


def test_index_lists_every_lesson():
    nb = index_notebook(LESSONS)
    body = "".join("".join(c["source"]) for c in nb["cells"])
    for lesson in LESSONS:
        assert f"{lesson.key}.ipynb" in body, f"{lesson.key} missing from the index"


def test_files_are_written(built):
    written, dest = built
    assert (dest / "00-START-HERE.ipynb").exists()
    assert len(written) == len(LESSONS) + 1
    for path in written:
        json.loads(path.read_text())            # each file is valid JSON


# --------------------------------------------------------------------------
# Opt-in: run every notebook in a real kernel.
# --------------------------------------------------------------------------
@pytest.mark.notebooks
@pytest.mark.parametrize("lesson", LESSONS, ids=[les.key for les in LESSONS])
def test_notebook_executes(lesson, tmp_path):
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")

    nb = nbformat.reads(json.dumps(lesson_notebook(lesson)), as_version=4)
    # The setup cell searches upward for the repo root, so execute from inside it.
    from tutorial.progress import ROOT
    workdir = ROOT / "notebooks"
    workdir.mkdir(exist_ok=True)
    client = nbclient.NotebookClient(
        nb, timeout=180, kernel_name="python3",
        resources={"metadata": {"path": str(workdir)}},
        allow_errors=False,
    )
    client.execute()


# --------------------------------------------------------------------------
# Regeneration must never destroy your work
# --------------------------------------------------------------------------
def test_generation_is_deterministic(tmp_path):
    """Byte-identical rebuilds are what makes committing notebooks/ sane."""
    first, _ = write_notebooks(tmp_path / "nb")
    before = {p.name: p.read_text() for p in first}
    second, skipped = write_notebooks(tmp_path / "nb")
    assert skipped == [], "an untouched notebook should not look edited"
    after = {p.name: p.read_text() for p in second}
    assert before == after


def test_edited_notebooks_are_not_clobbered(tmp_path):
    dest = tmp_path / "nb"
    write_notebooks(dest)
    target = next(p for p in dest.glob("*.ipynb") if p.name != "00-START-HERE.ipynb")
    mine = target.read_text().replace('"outputs": []', '"outputs": []', 1) + "\n"
    target.write_text(mine)

    written, skipped = write_notebooks(dest)
    assert target in skipped, "an edited notebook must be left alone"
    assert target not in written
    assert target.read_text() == mine, "the learner's edit was overwritten"


def test_force_overwrites(tmp_path):
    dest = tmp_path / "nb"
    write_notebooks(dest)
    target = next(p for p in dest.glob("*.ipynb") if p.name != "00-START-HERE.ipynb")
    target.write_text("clobber me\n")

    written, skipped = write_notebooks(dest, force=True)
    assert skipped == []
    assert target in written
    assert target.read_text() != "clobber me\n"
