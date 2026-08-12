"""Tests for the static-site renderer."""
from __future__ import annotations

import re

import pytest

from tutorial import site
from tutorial.projects import PROJECTS
from tutorial.registry import all_lessons

LESSONS = all_lessons()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "index.html"
    site.build_site(out)
    return out.read_text()


# ---------------------------------------------------------------------------
# markdown-lite
# ---------------------------------------------------------------------------
class TestMarkdown:
    def test_headings(self):
        assert site.render_markdown("## Title") == "<h3>Title</h3>"
        assert site.render_markdown("### Sub") == "<h4>Sub</h4>"

    def test_inline_formatting(self):
        got = site.render_markdown("plain **bold** *ital* `code` here")
        assert "<strong>bold</strong>" in got
        assert "<em>ital</em>" in got
        assert "<code>code</code>" in got

    def test_code_spans_are_not_double_escaped(self):
        got = site.render_markdown("call `type(x).__len__(x)` now")
        assert "<code>type(x).__len__(x)</code>" in got, got

    def test_html_in_prose_is_escaped(self):
        got = site.render_markdown("a < b and <script>alert(1)</script>")
        assert "<script>" not in got
        assert "&lt;script&gt;" in got

    def test_wrapped_list_items_stay_single(self):
        got = site.render_markdown("- one that wraps\n  onto a second line\n- two")
        assert got.count("<li>") == 2, got
        assert "<li></li>" not in got
        assert "wraps onto a second line" in got

    def test_numbered_list(self):
        got = site.render_markdown("1. first\n2. second")
        assert got.startswith("<ol>") and got.count("<li>") == 2

    def test_table(self):
        got = site.render_markdown("| a | b |\n|---|---|\n| 1 | 2 |")
        assert "<table>" in got and "<th>a</th>" in got and "<td>2</td>" in got
        assert 'class="table-wrap"' in got, "wide tables need their own scroll box"

    def test_blockquote_and_fence(self):
        assert "<blockquote>" in site.render_markdown("> note this")
        got = site.render_markdown("```\nx = 1\n```")
        assert 'class="code' in got


# ---------------------------------------------------------------------------
# Highlighting
# ---------------------------------------------------------------------------
class TestHighlight:
    def test_keywords_builtins_strings_comments(self):
        got = site.highlight('def f():\n    return len("hi")  # note')
        assert 'class="tok-kw"' in got
        assert 'class="tok-bi"' in got
        assert 'class="tok-string"' in got
        assert 'class="tok-comment"' in got

    def test_escapes_html(self):
        got = site.highlight('x = a < b and "<i>"')
        assert "<i>" not in got.replace('<span class="tok-string">', "")
        assert "&lt;" in got

    def test_gutter_line_count_matches(self):
        block = site.code_block("a = 1\nb = 2\nc = 3")
        gutter = re.search(r'<div class="gutter"[^>]*>(.*?)</div>', block, re.S).group(1)
        assert re.findall(r"<span>(\d+)</span>", gutter) == ["1", "2", "3"]

    def test_unnumbered_blocks_have_no_gutter(self):
        assert "gutter" not in site.code_block("a = 1", numbered=False)


# ---------------------------------------------------------------------------
# Whole page
# ---------------------------------------------------------------------------
class TestPage:
    def test_every_lesson_and_project_is_present(self, page):
        for lesson in LESSONS:
            assert f'id="{lesson.key}"' in page, f"{lesson.key} missing"
            assert f'data-goto="{lesson.key}"' in page, f"{lesson.key} not in the nav"
        assert 'id="projects"' in page
        for project in PROJECTS:
            assert project.title.split("—")[0].strip() in page

    def test_has_a_title(self, page):
        assert "<title>" in page
        assert re.search(r"<title>[^<]{3,60}</title>", page)

    def test_quizzes_carry_their_answers(self, page):
        quizzes = re.findall(r'class="block quiz" data-answer="([^"]*)"', page)
        expected = sum(len(les.questions()) for les in LESSONS)
        assert len(quizzes) == expected, f"{len(quizzes)} quizzes, expected {expected}"
        assert all(a and all(p.isdigit() for p in a.split(",")) for a in quizzes)

    def test_demo_output_is_baked_in(self, page):
        assert page.count('class="transcript') > 100, (
            "demo transcripts should be pre-computed into the page"
        )
        assert "a = [1, 2, 3, 4]" in page, "lesson 01's real output should be present"

    def test_solutions_are_collapsed(self, page):
        """Every exercise section must hide its solution behind a details."""
        sections = re.findall(r'<section class="block exercise">(.*?)</section>',
                              page, re.S)
        total_exercises = sum(len(les.exercises()) for les in LESSONS)
        assert len(sections) == total_exercises, (
            f"{len(sections)} exercise sections, expected {total_exercises}"
        )
        for body in sections:
            assert "<summary>Reference solution</summary>" in body
            head, _, tail = body.partition("<summary>Reference solution</summary>")
            assert head.rstrip().endswith("<details class=\"reveal\">"), (
                "the solution must sit inside the collapsed details, not before it"
            )

    def test_theme_tokens_defined_for_all_three_states(self, page):
        assert ":root{" in page.replace(" ", "")
        assert 'prefers-color-scheme:dark' in page.replace(" ", "")
        assert ':root[data-theme="dark"]' in page.replace(" ", "")
        assert ':root:not([data-theme="light"])' in page.replace(" ", "")

    def test_body_paints_its_own_background(self, page):
        body_rule = re.search(r"body\{([^}]*)\}", page.replace(" ", "").replace("\n", ""))
        assert body_rule and "background:var(--ground)" in body_rule.group(1), (
            "a transparent body borrows the host page's theme"
        )

    def test_no_external_requests(self, page):
        for pattern in ("http://", "https://", "//cdn", "<img"):
            assert pattern not in page, f"the page must be self-contained ({pattern})"

    def test_self_contained_and_reasonably_sized(self, page):
        assert "<style>" in page and "<script>" in page
        assert len(page.encode()) < 16 * 1024 * 1024

    def test_no_escape_sequences_leak_into_prose(self, page):
        """A literal \\n outside a code sample means an f-string was mis-escaped."""
        prose = re.sub(r"<pre>.*?</pre>", "", page, flags=re.S)
        prose = re.sub(r"<code>.*?</code>", "", prose, flags=re.S)
        prose = prose.split("<script>")[0].split("<style>")[1].split("</style>")[1]
        leaks = re.findall(r".{30}\\n.{30}", prose)
        assert not leaks, f"literal escape sequences in prose: {leaks[:3]}"
