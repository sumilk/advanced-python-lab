"""Tests for the terminal markdown-lite renderer.

The lessons are written once and rendered three ways (terminal, notebook,
site). These cover the terminal path; `test_site.py` covers the HTML one.
"""
from __future__ import annotations

import re
import textwrap

import pytest

from tutorial import ui
from tutorial.core import Demo, Exercise, Predict, Question, Text
from tutorial.registry import all_lessons

LESSONS = all_lessons()
ANSI = re.compile(r"\033\[[0-9;]*m")


def plain(md: str) -> str:
    """Render, then strip the escape sequences — what the reader actually sees."""
    return ANSI.sub("", ui.render(md))


@pytest.fixture(autouse=True)
def colour_on(monkeypatch):
    """Force colour on; otherwise output depends on whether stdout is a TTY."""
    monkeypatch.setattr(ui, "_ENABLED", True)


# ---------------------------------------------------------------------------
# inline markup
# ---------------------------------------------------------------------------
class TestInline:
    def test_basic_spans(self):
        got = ui.inline("plain **bold** *ital* `code` here")
        assert "bold" in ANSI.sub("", got)
        assert got != "plain **bold** *ital* `code` here", "nothing was styled"
        assert "**" not in ANSI.sub("", got)
        assert "`" not in ANSI.sub("", got)

    def test_asterisks_inside_a_code_span_survive(self):
        """`**kwargs` is not bold markup — eating those stars corrupts the code."""
        got = ANSI.sub("", ui.inline("`f(*args, **kwargs)` takes anything"))
        assert got == "f(*args, **kwargs) takes anything", got

    def test_two_code_spans_do_not_pair_across_each_other(self):
        got = ANSI.sub("", ui.inline("`type(self)(**{**d, **changes})` copies"))
        assert got == "type(self)(**{**d, **changes}) copies", got

    def test_italic_nested_in_bold(self):
        got = ui.inline("**Patch where it is *used*, not where defined.**")
        assert "*" not in ANSI.sub("", got), got
        assert "\033[3m" in got, "the nested italic was not styled"
        assert "\033[0m" not in got[:got.index("\033[23m")], (
            "the italic reset must not switch the surrounding bold off"
        )

    def test_bold_still_works_beside_a_kwargs_span(self):
        got = ui.inline("`__call__(cls, **kw)` → intercept **instantiation**")
        assert "**kw)" in ANSI.sub("", got), "code span was mangled"
        assert ANSI.sub("", got).endswith("intercept instantiation"), got
        assert "\033[1m" in got, "the bold span was not styled"


# ---------------------------------------------------------------------------
# block structure
# ---------------------------------------------------------------------------
class TestRender:
    def test_markup_spanning_a_line_break(self):
        """Prose is hard-wrapped in the lesson sources; spans must be rejoined."""
        assert "**" not in plain("state. **Only one thread runs\nbytecode.** So:")

    @pytest.mark.parametrize("source", [
        "- calls the factory **the\n  first time only**, then caches it",
        "3. insert it into `sys.modules` **before\n   executing it**, which is why",
        "> **Why report it through the value instead of\n> raising?** Because it is",
    ])
    def test_markup_spanning_a_line_break_in_lists_and_quotes(self, source):
        assert "**" not in plain(source), source

    def test_continuation_lines_are_joined_not_re_indented(self):
        got = plain("a paragraph that was\nhard-wrapped in the source")
        assert got == "a paragraph that was hard-wrapped in the source", got

    def test_a_blank_line_separates_paragraphs(self):
        assert plain("first para\n\nsecond para").split("\n") == [
            "first para", "", "second para",
        ]

    def test_a_list_ends_the_preceding_paragraph(self):
        got = plain("intro line\n- item one\n- item two").split("\n")
        assert got[0] == "intro line"
        assert got[1].strip().startswith("•")
        assert got[2].strip().startswith("•")

    def test_fenced_code_is_not_treated_as_prose(self):
        got = plain("```python\ndef f(a, **kw): ...\n```")
        assert "def f(a, **kw): ..." in got, got

    def test_table_rows_are_left_alone(self):
        got = plain('| `{"k": v, **rest}` | mappings |')
        assert '{"k": v, **rest}' in got, got


# ---------------------------------------------------------------------------
# wrapping
# ---------------------------------------------------------------------------
class TestFill:
    def test_wraps_on_visible_width_not_byte_length(self):
        """Escape sequences must not count toward the column budget."""
        text = ui.inline("`alpha` `bravo` `charlie` `delta` `echo` `foxtrot` `golf`")
        for line in ui.fill(text, 40).split("\n"):
            assert ui.visible_len(line) <= 40, ui.visible_len(line)
        assert len(ui.fill(text, 40).split("\n")) == 2, "wrapped far too early"

    def test_subsequent_indent_applies_from_the_second_line(self):
        got = ui.fill("word " * 30, 30, subsequent_indent="    ")
        lines = got.split("\n")
        assert not lines[0].startswith(" ")
        assert all(ln.startswith("    ") for ln in lines[1:])

    def test_empty_input(self):
        assert ui.fill("", 40) == ""


# ---------------------------------------------------------------------------
# the real corpus
# ---------------------------------------------------------------------------
def _prose_blocks():
    for lesson in LESSONS:
        for block in lesson.blocks:
            if isinstance(block, Text):
                yield lesson.key, "body", block.body
            elif isinstance(block, (Demo, Predict, Question)):
                yield lesson.key, "explain", block.explain
            elif isinstance(block, Exercise):
                yield lesson.key, "brief", block.brief
                for hint in block.hints:
                    yield lesson.key, "hint", hint


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda les: les.key)
def test_no_lesson_leaks_bold_markers_to_the_reader(lesson):
    """Every `**bold**` in the corpus must actually render.

    Code spans are dropped first: a rendered `f(**kw)` legitimately contains
    `**`, so only asterisks left over *outside* a span indicate a span the
    renderer failed to pair up — the hard-wrapped-markup bug.
    """
    for key, field, text in _prose_blocks():
        if key != lesson.key or not text:
            continue
        prose = re.sub(r"```.*?```", "", textwrap.dedent(text), flags=re.S)
        prose = re.sub(r"`[^`]+`", "CODE", prose)
        for line in plain(prose).split("\n"):
            if line.strip().startswith("|"):
                continue                    # table rows are passed through raw
            assert "**" not in line, f"{key} {field}: unrendered bold in {line!r}"
