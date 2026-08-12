"""Render the whole course to one self-contained HTML page.

Two things make this more than a text dump:

* every demo is **executed at build time** and its real stdout is baked into
  the page, so the transcript panels show what Python actually printed;
* quizzes stay interactive — multiple choice needs no interpreter, just a
  few lines of JavaScript.

    uv run learn.py site            # -> site/index.html
"""
from __future__ import annotations

import html
import re
import textwrap
from pathlib import Path
from typing import Any

from .core import Demo, Exercise, Lesson, Predict, Question, Text, run_code, version_ok
from .projects import PROJECTS
from .registry import all_lessons

LETTERS = "abcdefgh"

NOTEBOOK_COMMANDS = """uv run learn.py notebooks
uv run --with jupyterlab jupyter lab notebooks/"""

TERMINAL_COMMANDS = """uv run learn.py
uv run learn.py lesson 9
uv run learn.py quiz 20"""


# ---------------------------------------------------------------------------
# Python syntax highlighting -> HTML
# ---------------------------------------------------------------------------
KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "case", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is", "lambda",
    "match", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
}
BUILTINS = {
    "abs", "all", "any", "bool", "bytes", "callable", "classmethod", "compile",
    "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter", "float",
    "format", "frozenset", "getattr", "globals", "hasattr", "hash", "id",
    "int", "isinstance", "issubclass", "iter", "len", "list", "locals", "map",
    "max", "min", "next", "object", "open", "print", "property", "range",
    "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
}

_CODE_TOKENS = re.compile(
    r"""(?P<comment>\#[^\n]*)
      | (?P<string>[rbfuRBFU]{0,2}(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"
                                   |'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"))
      | (?P<decorator>@[A-Za-z_][\w.]*)
      | (?P<defname>(?<=\bdef\s)[A-Za-z_]\w*|(?<=\bclass\s)[A-Za-z_]\w*)
      | (?P<number>\b\d[\w.]*\b)
      | (?P<dunder>\b__\w+__\b)
      | (?P<name>\b[A-Za-z_]\w*\b)
    """,
    re.VERBOSE,
)


def highlight(code: str) -> str:
    out: list[str] = []
    position = 0
    for match in _CODE_TOKENS.finditer(code):
        out.append(html.escape(code[position:match.start()]))
        kind, text = match.lastgroup, match.group()
        escaped = html.escape(text)
        if kind == "name":
            if text in KEYWORDS:
                out.append(f'<span class="tok-kw">{escaped}</span>')
            elif text in BUILTINS:
                out.append(f'<span class="tok-bi">{escaped}</span>')
            else:
                out.append(escaped)
        else:
            out.append(f'<span class="tok-{kind}">{escaped}</span>')
        position = match.end()
    out.append(html.escape(code[position:]))
    return "".join(out)


def code_block(code: str, numbered: bool = True) -> str:
    lines = textwrap.dedent(code).strip("\n").split("\n")
    gutter = ""
    if numbered:
        gutter = ('<div class="gutter" aria-hidden="true">'
                  + "".join(f"<span>{n}</span>" for n in range(1, len(lines) + 1))
                  + "</div>")
    body = highlight("\n".join(lines))
    return (f'<div class="code{" numbered" if numbered else ""}">'
            f'{gutter}<pre><code>{body}</code></pre></div>')


# ---------------------------------------------------------------------------
# markdown-lite -> HTML
# ---------------------------------------------------------------------------
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")          # .+? so **bold with *italic* inside** works
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(match):
        placeholders.append(f'<code>{html.escape(match.group(1))}</code>')
        return f"\x00{len(placeholders) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    text = html.escape(text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)


def render_markdown(source: str) -> str:
    """A small renderer covering exactly the subset the lessons use."""
    lines = textwrap.dedent(source).strip("\n").split("\n")
    out: list[str] = []
    index = 0

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            fence: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                fence.append(lines[index])
                index += 1
            index += 1
            out.append(code_block("\n".join(fence), numbered=False))
            continue

        if stripped.startswith("### "):
            out.append(f"<h4>{inline(stripped[4:])}</h4>")
            index += 1
            continue

        if stripped.startswith("## "):
            out.append(f"<h3>{inline(stripped[3:])}</h3>")
            index += 1
            continue

        if stripped.startswith("|"):
            table: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index].strip())
                index += 1
            out.append(render_table(table))
            continue

        if stripped.startswith("> "):
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue

        if re.match(r"^[-*] ", stripped):
            items, consumed = collect_list(lines, index, r"^[-*] ")
            index += consumed
            body = "".join(f"<li>{inline(item)}</li>" for item in items)
            out.append(f"<ul>{body}</ul>")
            continue

        if re.match(r"^\d+\. ", stripped):
            items, consumed = collect_list(lines, index, r"^\d+\. ")
            index += consumed
            body = "".join(f"<li>{inline(item)}</li>" for item in items)
            out.append(f"<ol>{body}</ol>")
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not re.match(
            r"^\s*(```|#{2,3} |\||> |[-*] |\d+\. )", lines[index]
        ):
            paragraph.append(lines[index].strip())
            index += 1
        out.append(f"<p>{inline(' '.join(paragraph))}</p>")

    return "\n".join(out)


def collect_list(lines: list[str], start: int, pattern: str) -> tuple[list[str], int]:
    """Gather consecutive list items, folding continuation lines into them.

    Returns the items and how many source lines were consumed — the two differ
    whenever an item wraps, which is why the caller cannot just count items.
    """
    items: list[str] = []
    index = start
    while index < len(lines):
        stripped = lines[index].strip()
        if re.match(pattern, stripped):
            items.append(re.sub(pattern, "", stripped))
        elif stripped and items and not re.match(r"^\s*(```|#{2,3} |\||> )", lines[index]):
            items[-1] += " " + stripped          # a wrapped continuation line
        else:
            break
        index += 1
    return items, index - start


def render_table(rows: list[str]) -> str:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    if len(rows) < 2:
        return ""
    header = cells(rows[0])
    body_rows = [cells(r) for r in rows[2:]]           # rows[1] is the separator
    head = "".join(f"<th>{inline(c)}</th>" for c in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
        for row in body_rows
    )
    return (f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


# ---------------------------------------------------------------------------
# Blocks -> HTML
# ---------------------------------------------------------------------------
def transcript(text: str, kind: str = "out") -> str:
    label = {"out": "output", "err": "traceback", "skip": "not run here"}[kind]
    return (f'<div class="transcript {kind}">'
            f'<div class="transcript-label">{label}</div>'
            f"<pre>{html.escape(text.rstrip())}</pre></div>")


def render_demo(block: Demo, counter: dict[str, int]) -> str:
    parts = [code_block(block.code)]

    if not version_ok(block.min_version):
        want = ".".join(map(str, block.min_version))
        parts.append(transcript(f"requires Python {want}+", "skip"))
    else:
        namespace: dict[str, Any] = {}
        if block.setup:
            run_code(block.setup, namespace)
        result = run_code(block.code, namespace)
        counter["run"] += 1
        if result.stdout.strip():
            parts.append(transcript(result.stdout))
        if result.failed:
            tail = "\n".join(result.traceback_text.rstrip().split("\n")[-6:])
            parts.append(transcript(tail, "err"))
            counter["errors" if not block.expect_error else "expected"] += 1
        elif not result.stdout.strip():
            parts.append(transcript("(no output)", "skip"))

    if block.explain:
        parts.append(f'<div class="note">{render_markdown(block.explain)}</div>')
    return f'<section class="block demo">{"".join(parts)}</section>'


def render_predict(block: Predict, index: int) -> str:
    return f"""
<section class="block predict">
  <div class="block-head"><span class="marker">predict</span>
    <span>What does this print?</span></div>
  {code_block(block.code)}
  <details class="reveal">
    <summary>Reveal the output</summary>
    {transcript(textwrap.dedent(block.answer).strip())}
    <div class="note">{render_markdown(block.explain)}</div>
  </details>
</section>"""


def render_question(block: Question, uid: str) -> str:
    correct = sorted(block.correct_set())
    options = "".join(
        f'<li><button type="button" class="option" data-index="{i}">'
        f'<span class="letter">{LETTERS[i]}</span>'
        f'<span class="option-text">{inline(choice)}</span></button></li>'
        for i, choice in enumerate(block.choices)
    )
    return f"""
<section class="block quiz" data-answer="{','.join(map(str, correct))}" id="{uid}">
  <div class="block-head"><span class="marker">quiz</span></div>
  <p class="quiz-prompt">{inline(block.prompt)}</p>
  <ul class="options">{options}</ul>
  <div class="quiz-explain" hidden>{render_markdown(block.explain)}</div>
</section>"""


def render_exercise(block: Exercise, lesson: Lesson) -> str:
    ex_id = f"{lesson.key}/{block.slug}"
    hints = "".join(f"<li>{inline(h)}</li>" for h in block.hints)
    hint_block = (f"<details class='reveal'><summary>Hints</summary>"
                  f"<ol class='hints'>{hints}</ol></details>" if hints else "")
    return f"""
<section class="block exercise">
  <div class="block-head">
    <span class="marker work">exercise</span>
    <span class="ex-title">{html.escape(block.title)}</span>
    <span class="chip {block.difficulty}">{block.difficulty}</span>
  </div>
  <div class="brief">{render_markdown(block.brief)}</div>
  <p class="run-hint">Solve it for real:
    <code>uv run learn.py check {ex_id}</code>
    or open <code>notebooks/{lesson.key}.ipynb</code>.</p>
  {code_block(block.starter, numbered=False)}
  {hint_block}
  <details class="reveal">
    <summary>Reference solution</summary>
    {code_block(block.solution, numbered=False)}
  </details>
</section>"""


def render_lesson(lesson: Lesson, counter: dict[str, int]) -> str:
    parts: list[str] = []
    quiz_index = 0
    for i, block in enumerate(lesson.blocks):
        match block:
            case Text():
                parts.append(f'<section class="block prose">'
                             f"{render_markdown(block.body)}</section>")
            case Demo():
                parts.append(render_demo(block, counter))
            case Predict():
                parts.append(render_predict(block, i))
            case Question():
                quiz_index += 1
                parts.append(render_question(block, f"{lesson.key}-q{quiz_index}"))
            case Exercise():
                parts.append(render_exercise(block, lesson))

    tags = "".join(f'<span class="tag">{t}</span>' for t in lesson.tags)
    return f"""
<article class="lesson" id="{lesson.key}" data-lesson="{lesson.key}" hidden>
  <header class="lesson-head">
    <div class="lesson-number">{lesson.number:02d}</div>
    <div>
      <h2>{html.escape(lesson.title)}</h2>
      <div class="summary">{render_markdown(lesson.summary)}</div>
      <div class="tags">{tags}</div>
    </div>
  </header>
  {"".join(parts)}
  <footer class="lesson-foot">
    <span>{len(lesson.exercises())} exercises · {len(lesson.questions())} quiz questions</span>
  </footer>
</article>"""


# ---------------------------------------------------------------------------
# Overview and projects
# ---------------------------------------------------------------------------
def render_overview(lessons: tuple[Lesson, ...], counter: dict[str, int]) -> str:
    rows = "".join(
        f'<li><button class="nav-card" data-goto="{les.key}">'
        f'<span class="num">{les.number:02d}</span>'
        f'<span class="card-body"><span class="card-title">{html.escape(les.title)}</span>'
        f'<span class="card-meta">{len(les.exercises())} exercises · '
        f'{len(les.questions())} questions</span></span></button></li>'
        for les in lessons
    )
    total_ex = sum(len(l.exercises()) for l in lessons)
    total_q = sum(len(l.questions()) for l in lessons)
    return f"""
<article class="lesson" id="overview" data-lesson="overview">
  <header class="hero">
    <div class="prompt">&gt;&gt;&gt;</div>
    <h2>Python, past the tutorial stage</h2>
    <p class="deck">Twenty-two lessons on the parts of Python that stop being
      obvious: the data model, descriptors, the MRO, generators as coroutines,
      the GIL, the AST. Every code sample on this page was executed while the
      page was built — the transcripts are real output, not illustrations.</p>
    <dl class="stats">
      <div><dt>lessons</dt><dd>{len(lessons)}</dd></div>
      <div><dt>graded exercises</dt><dd>{total_ex}</dd></div>
      <div><dt>quiz questions</dt><dd>{total_q}</dd></div>
      <div><dt>samples executed</dt><dd>{counter['run']}</dd></div>
      <div><dt>capstone projects</dt><dd>{len(PROJECTS)}</dd></div>
    </dl>
  </header>

  <section class="block prose">
    <h3>This page is the reading copy</h3>
    <p>The course is meant to be <em>run</em>. Reading gets you the ideas;
      the exercises are where they stick. Two front-ends do the actual work,
      and both grade against the same test suite:</p>
  </section>

  <div class="cards">
    <div class="feature">
      <h4>Notebooks</h4>
      <p>One <code>.ipynb</code> per lesson. Edit the exercise cell, run
        <code>check("05-iterators/peekable")</code> in the cell below it, and get a
        per-assertion pass/fail report.</p>
      {code_block(NOTEBOOK_COMMANDS, numbered=False)}
    </div>
    <div class="feature">
      <h4>Terminal</h4>
      <p>Paged lessons with live-executed demos, interactive quizzes, exercise
        files graded on demand, and progress tracked across both front-ends.</p>
      {code_block(TERMINAL_COMMANDS, numbered=False)}
    </div>
  </div>

  <section class="block prose">
    <h3>Curriculum</h3>
  </section>
  <ul class="nav-cards">{rows}</ul>
</article>"""


def render_projects() -> str:
    cards = ""
    for project in PROJECTS:
        readme = project.path / "README.md"
        brief = ""
        if readme.exists():
            body = readme.read_text().split("\n")
            brief = render_markdown("\n".join(body[1:40]))
        concepts = "".join(f'<span class="tag">{c}</span>' for c in project.concepts)
        lessons = ", ".join(f"{n:02d}" for n in project.lessons)
        cards += f"""
<section class="block project">
  <div class="block-head">
    <span class="marker work">project</span>
    <span class="ex-title">{html.escape(project.title)}</span>
    <span class="chip {project.difficulty}">{project.difficulty}</span>
  </div>
  <p class="deck">{html.escape(project.blurb)}</p>
  <div class="tags">{concepts}</div>
  <p class="run-hint">Draws on lessons {lessons} ·
    <code>uv run learn.py projects test {project.slug}</code></p>
  <details class="reveal"><summary>Full brief</summary>
    <div class="brief">{brief}</div>
  </details>
</section>"""
    return f"""
<article class="lesson" id="projects" data-lesson="projects" hidden>
  <header class="lesson-head">
    <div class="lesson-number">&#9633;</div>
    <div>
      <h2>Capstone projects</h2>
      <div class="summary"><p>Five builds that combine several lessons at
        once. Each ships a starter, a full brief, and a real pytest suite —
        25 to 46 assertions apiece — that grades your implementation.</p></div>
    </div>
  </header>
  {cards}
</article>"""


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------
CSS = """
:root{
  --ground:#f6f7f9; --surface:#eceef2; --raised:#ffffff;
  --ink:#12151b; --muted:#5a6270; --faint:#8a92a1;
  --rule:#dce0e7; --rule-soft:#e7eaef;
  --accent:#8a4b12; --accent-soft:#f3ece3; --accent-line:#c98a45;
  --pass:#0e6e5c; --pass-soft:#e4f1ed;
  --warn:#8a5a00;
  --tok-kw:#8a2f6b; --tok-str:#1c6b4a; --tok-com:#7c8593;
  --tok-num:#9a4d10; --tok-bi:#1d5a8a; --tok-dec:#7a4bb0; --tok-def:#1b3f8a;
  --shadow:0 1px 2px rgba(18,21,27,.05), 0 8px 24px -18px rgba(18,21,27,.35);
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,ui-serif,serif;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#101318; --surface:#171b22; --raised:#1b2029;
    --ink:#e4e8ef; --muted:#98a1b1; --faint:#6d7684;
    --rule:#262c36; --rule-soft:#1f242d;
    --accent:#e9a25c; --accent-soft:#26201a; --accent-line:#8a5a2a;
    --pass:#54c2a4; --pass-soft:#16241f;
    --warn:#d9a441;
    --tok-kw:#e08ac4; --tok-str:#7fd3a8; --tok-com:#6d7684;
    --tok-num:#e8a678; --tok-bi:#7fbce8; --tok-dec:#c3a2f0; --tok-def:#8fb4f5;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -20px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#101318; --surface:#171b22; --raised:#1b2029;
  --ink:#e4e8ef; --muted:#98a1b1; --faint:#6d7684;
  --rule:#262c36; --rule-soft:#1f242d;
  --accent:#e9a25c; --accent-soft:#26201a; --accent-line:#8a5a2a;
  --pass:#54c2a4; --pass-soft:#16241f;
  --warn:#d9a441;
  --tok-kw:#e08ac4; --tok-str:#7fd3a8; --tok-com:#6d7684;
  --tok-num:#e8a678; --tok-bi:#7fbce8; --tok-dec:#c3a2f0; --tok-def:#8fb4f5;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -20px rgba(0,0,0,.8);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.65;
  -webkit-font-smoothing:antialiased;
}
a{color:var(--accent)}
code{font-family:var(--mono); font-size:.86em}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px; border-radius:3px}

/* ---- shell ---- */
.shell{display:grid; grid-template-columns:280px minmax(0,1fr); min-height:100vh}
.sidebar{
  border-right:1px solid var(--rule); background:var(--surface);
  position:sticky; top:0; height:100vh; overflow-y:auto; padding:1.6rem 0 3rem;
}
.brand{padding:0 1.4rem 1.2rem; border-bottom:1px solid var(--rule)}
.brand h1{
  font-family:var(--mono); font-size:.82rem; font-weight:600;
  letter-spacing:.14em; text-transform:uppercase; margin:0 0 .3rem; color:var(--ink);
}
.brand .sub{font-size:.78rem; color:var(--muted); margin:0; line-height:1.45}
nav{padding:.9rem .7rem 0}
.nav-group{
  font-family:var(--mono); font-size:.68rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--faint); padding:.9rem .7rem .4rem;
}
nav button{
  display:flex; gap:.65rem; align-items:baseline; width:100%; text-align:left;
  background:none; border:0; cursor:pointer; color:var(--muted);
  font:inherit; font-size:.845rem; line-height:1.35;
  padding:.4rem .7rem; border-radius:5px; transition:background .12s,color .12s;
}
nav button:hover{background:var(--rule-soft); color:var(--ink)}
nav button.active{background:var(--accent-soft); color:var(--ink); font-weight:600}
nav button.active .n{color:var(--accent)}
nav button .n{
  font-family:var(--mono); font-size:.72rem; color:var(--faint);
  font-variant-numeric:tabular-nums; flex:0 0 1.4rem;
}

/* ---- main ---- */
main{padding:3.2rem 3rem 6rem; max-width:60rem}
.lesson[hidden]{display:none}
.lesson-head{display:flex; gap:1.4rem; align-items:flex-start; margin-bottom:2.4rem}
.lesson-number{
  font-family:var(--mono); font-size:2.6rem; font-weight:600; line-height:1;
  color:var(--accent-line); font-variant-numeric:tabular-nums;
  padding-top:.15rem; flex:0 0 auto;
}
.lesson-head h2{
  font-family:var(--serif); font-size:2.1rem; line-height:1.15; margin:0 0 .7rem;
  font-weight:600; text-wrap:balance; letter-spacing:-.01em;
}
.summary p{margin:0; color:var(--muted); max-width:62ch}
.tags{display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.9rem}
.tag{
  font-family:var(--mono); font-size:.68rem; letter-spacing:.04em;
  color:var(--muted); background:var(--surface); border:1px solid var(--rule);
  padding:.12rem .45rem; border-radius:3px;
}

/* ---- hero ---- */
.hero{margin-bottom:3rem}
.hero .prompt{
  font-family:var(--mono); color:var(--accent); font-size:1.1rem;
  letter-spacing:.1em; margin-bottom:.6rem;
}
.hero h2{
  font-family:var(--serif); font-size:2.9rem; line-height:1.08; margin:0 0 1rem;
  font-weight:600; letter-spacing:-.02em; text-wrap:balance; max-width:18ch;
}
.deck{color:var(--muted); max-width:64ch; font-size:1.02rem; margin:0}
.stats{
  display:flex; flex-wrap:wrap; gap:2.2rem; margin:2.2rem 0 0; padding:1.3rem 0 0;
  border-top:1px solid var(--rule);
}
.stats div{margin:0}
.stats dt{
  font-family:var(--mono); font-size:.68rem; letter-spacing:.12em;
  text-transform:uppercase; color:var(--faint);
}
.stats dd{
  margin:.15rem 0 0; font-family:var(--mono); font-size:1.5rem; font-weight:600;
  font-variant-numeric:tabular-nums; color:var(--ink);
}

/* ---- blocks ---- */
.block{margin:0 0 2.1rem}
.prose h3, .feature h4{
  font-family:var(--serif); font-size:1.32rem; font-weight:600; letter-spacing:-.005em;
  margin:2.4rem 0 .8rem; padding-bottom:.35rem; border-bottom:1px solid var(--rule);
  text-wrap:balance;
}
.prose h4{font-family:var(--sans); font-size:.95rem; font-weight:650; margin:1.6rem 0 .5rem}
.prose p, .brief p, .note p{max-width:66ch}
.prose ul, .prose ol, .brief ul, .brief ol{max-width:66ch; padding-left:1.25rem}
.prose li, .brief li{margin:.25rem 0}
blockquote{
  margin:1.1rem 0; padding:.7rem 0 .7rem 1.1rem;
  border-left:3px solid var(--accent-line); color:var(--muted); max-width:64ch;
}
.table-wrap{overflow-x:auto; margin:1.2rem 0}
table{border-collapse:collapse; font-size:.9rem; min-width:100%}
th,td{text-align:left; padding:.45rem .9rem .45rem 0; border-bottom:1px solid var(--rule-soft)}
th{
  font-family:var(--mono); font-size:.7rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--faint); border-bottom:1px solid var(--rule);
}

/* ---- code + transcript ---- */
.code{
  background:var(--raised); border:1px solid var(--rule); border-radius:7px;
  margin:1.1rem 0; overflow-x:auto; box-shadow:var(--shadow); display:flex;
}
.code.numbered .gutter{
  flex:0 0 auto; display:flex; flex-direction:column; padding:.85rem .7rem .85rem .85rem;
  border-right:1px solid var(--rule-soft); color:var(--faint);
  font-family:var(--mono); font-size:.72rem;
  text-align:right; user-select:none; font-variant-numeric:tabular-nums;
}
/* The gutter and the code must share one absolute line box, or the numbers
   drift out of step with the lines they label. */
.code.numbered .gutter span{line-height:1.33rem; display:block}
.code pre{margin:0; padding:.85rem 1.1rem; overflow-x:auto; flex:1 1 auto}
.code code{font-size:.82rem; line-height:1.33rem; white-space:pre; display:block}
.tok-kw{color:var(--tok-kw); font-weight:600}
.tok-string{color:var(--tok-str)}
.tok-comment{color:var(--tok-com); font-style:italic}
.tok-number{color:var(--tok-num)}
.tok-bi{color:var(--tok-bi)}
.tok-decorator{color:var(--tok-dec)}
.tok-defname{color:var(--tok-def); font-weight:600}
.tok-dunder{color:var(--tok-dec)}

.transcript{margin:-.4rem 0 1.1rem; border-left:3px solid var(--pass); background:var(--pass-soft);
  border-radius:0 5px 5px 0; overflow-x:auto}
.transcript.err{border-left-color:var(--accent); background:var(--accent-soft)}
.transcript.skip{border-left-color:var(--rule); background:var(--surface)}
.transcript-label{
  font-family:var(--mono); font-size:.64rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--muted); padding:.5rem .9rem 0;
}
.transcript pre{
  margin:0; padding:.25rem .9rem .7rem; font-family:var(--mono);
  font-size:.79rem; line-height:1.55; white-space:pre; color:var(--ink);
}
.note{
  font-size:.94rem; color:var(--muted); border-left:2px solid var(--rule);
  padding-left:1rem; margin:1rem 0 0;
}
.note p{margin:.4rem 0}

/* ---- markers ---- */
.block-head{display:flex; align-items:center; gap:.7rem; margin-bottom:.7rem; flex-wrap:wrap}
.marker{
  font-family:var(--mono); font-size:.66rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--accent); border:1px solid var(--accent-line); border-radius:3px;
  padding:.1rem .45rem;
}
.marker.work{color:var(--pass); border-color:var(--pass)}
.block-head span:not(.marker):not(.chip){font-size:.9rem; color:var(--muted)}
.ex-title{font-weight:600; color:var(--ink) !important; font-size:1rem !important}
.chip{
  font-family:var(--mono); font-size:.64rem; letter-spacing:.1em; text-transform:uppercase;
  padding:.1rem .45rem; border-radius:3px; background:var(--surface);
  border:1px solid var(--rule); color:var(--muted);
}
.chip.tricky{color:var(--warn); border-color:var(--warn)}
.chip.brutal,.chip.hard{color:var(--accent); border-color:var(--accent-line)}

/* ---- quiz ---- */
.quiz{
  border:1px solid var(--rule); border-radius:8px; padding:1.2rem 1.3rem;
  background:var(--surface);
}
.quiz-prompt{margin:0 0 .9rem; font-weight:550; max-width:66ch}
.options{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:.4rem}
.option{
  display:flex; gap:.7rem; align-items:baseline; width:100%; text-align:left;
  font:inherit; font-size:.92rem; cursor:pointer; padding:.5rem .75rem;
  background:var(--raised); border:1px solid var(--rule); border-radius:5px;
  color:var(--ink); transition:border-color .12s, background .12s;
}
.option:hover:not(:disabled){border-color:var(--accent-line)}
.option:disabled{cursor:default}
.option .letter{
  font-family:var(--mono); font-size:.75rem; color:var(--faint); flex:0 0 .8rem;
}
.option.right{border-color:var(--pass); background:var(--pass-soft)}
.option.right .letter{color:var(--pass)}
.option.wrong{border-color:var(--accent); background:var(--accent-soft)}
.quiz-explain{
  margin-top:.9rem; padding-top:.8rem; border-top:1px solid var(--rule);
  font-size:.92rem; color:var(--muted);
}
.quiz-explain p{margin:0; max-width:66ch}

/* ---- exercise / details ---- */
.exercise,.project{border-top:1px solid var(--rule); padding-top:1.4rem}
.run-hint{font-size:.85rem; color:var(--muted)}
.run-hint code{background:var(--surface); padding:.1rem .35rem; border-radius:3px;
  border:1px solid var(--rule)}
.reveal{margin:.9rem 0}
.reveal summary{
  cursor:pointer; font-family:var(--mono); font-size:.74rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); padding:.35rem 0; list-style:none;
  display:flex; align-items:center; gap:.45rem;
}
.reveal summary::before{content:"+"; color:var(--accent); font-weight:700}
.reveal[open] summary::before{content:"\\2212"}
.reveal summary:hover{color:var(--ink)}
.hints{font-size:.92rem; color:var(--muted); max-width:66ch}

/* ---- cards ---- */
.cards{display:grid; grid-template-columns:repeat(auto-fit,minmax(19rem,1fr)); gap:1.1rem; margin:1.4rem 0 2.4rem}
.feature{border:1px solid var(--rule); border-radius:8px; padding:1.1rem 1.2rem; background:var(--surface)}
.feature h4{margin-top:0; border:0; padding:0}
.feature p{font-size:.92rem; color:var(--muted); margin:0}
.feature .code{background:var(--ground)}
.nav-cards{list-style:none; margin:1rem 0 0; padding:0; display:grid;
  grid-template-columns:repeat(auto-fill,minmax(15rem,1fr)); gap:.5rem}
.nav-card{
  display:flex; gap:.8rem; align-items:baseline; width:100%; text-align:left;
  font:inherit; cursor:pointer; padding:.7rem .85rem; border-radius:6px;
  background:var(--surface); border:1px solid var(--rule); color:var(--ink);
  transition:border-color .12s, transform .12s;
}
.nav-card:hover{border-color:var(--accent-line); transform:translateY(-1px)}
.nav-card .num{font-family:var(--mono); font-size:.78rem; color:var(--accent);
  font-variant-numeric:tabular-nums}
.card-body{display:flex; flex-direction:column}
.card-title{font-size:.9rem; font-weight:550; line-height:1.3}
.card-meta{font-size:.75rem; color:var(--faint); font-family:var(--mono)}

.lesson-foot{
  margin-top:3rem; padding-top:1rem; border-top:1px solid var(--rule);
  font-family:var(--mono); font-size:.74rem; color:var(--faint);
  display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap;
}
.pager{display:flex; gap:.6rem}
.pager button{
  font:inherit; font-family:var(--mono); font-size:.74rem; cursor:pointer;
  background:none; border:1px solid var(--rule); color:var(--muted);
  padding:.25rem .6rem; border-radius:4px;
}
.pager button:hover{border-color:var(--accent-line); color:var(--ink)}

@media (prefers-reduced-motion:reduce){*{transition:none !important}}
@media (max-width:900px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static; height:auto; border-right:0; border-bottom:1px solid var(--rule)}
  main{padding:2rem 1.3rem 4rem}
  .hero h2{font-size:2.1rem}
  .lesson-head{gap:.9rem}
  .lesson-number{font-size:1.8rem}
}
"""

JS = """
const views = [...document.querySelectorAll('.lesson')].map(el => el.id);
const navButtons = [...document.querySelectorAll('nav button')];

function show(id, push = true) {
  if (!views.includes(id)) id = 'overview';
  document.querySelectorAll('.lesson').forEach(el => { el.hidden = el.id !== id; });
  navButtons.forEach(b => b.classList.toggle('active', b.dataset.goto === id));
  if (push && location.hash.slice(1) !== id) history.pushState(null, '', '#' + id);
  window.scrollTo({ top: 0, behavior: 'instant' });
  const pos = views.indexOf(id);
  document.querySelectorAll('.pager').forEach(p => {
    p.querySelector('[data-dir="prev"]').disabled = pos <= 0;
    p.querySelector('[data-dir="next"]').disabled = pos >= views.length - 1;
    p.dataset.pos = pos;
  });
}

document.addEventListener('click', event => {
  const nav = event.target.closest('[data-goto]');
  if (nav) { show(nav.dataset.goto); return; }

  const page = event.target.closest('.pager button');
  if (page) {
    const current = views.indexOf(document.querySelector('.lesson:not([hidden])').id);
    show(views[current + (page.dataset.dir === 'next' ? 1 : -1)]);
    return;
  }

  const option = event.target.closest('.option');
  if (option) {
    const quiz = option.closest('.quiz');
    const correct = quiz.dataset.answer.split(',');
    const chosen = option.dataset.index;
    quiz.querySelectorAll('.option').forEach(b => {
      b.disabled = true;
      if (correct.includes(b.dataset.index)) b.classList.add('right');
      else if (b === option) b.classList.add('wrong');
    });
    quiz.querySelector('.quiz-explain').hidden = false;
  }
});

window.addEventListener('popstate', () => show(location.hash.slice(1) || 'overview', false));
document.addEventListener('keydown', event => {
  if (event.target.matches('input, textarea')) return;
  const current = views.indexOf(document.querySelector('.lesson:not([hidden])').id);
  if (event.key === 'ArrowRight' && current < views.length - 1) show(views[current + 1]);
  if (event.key === 'ArrowLeft' && current > 0) show(views[current - 1]);
});

show(location.hash.slice(1) || 'overview', false);
"""


def build_site(destination: str | Path = "site/index.html") -> Path:
    lessons = all_lessons()
    counter = {"run": 0, "errors": 0, "expected": 0}

    lesson_html = "".join(render_lesson(les, counter) for les in lessons)
    overview = render_overview(lessons, counter)
    projects = render_projects()

    nav = ['<div class="nav-group">start</div>',
           '<button data-goto="overview"><span class="n">&#9670;</span>'
           '<span>Overview</span></button>',
           '<div class="nav-group">lessons</div>']
    for les in lessons:
        nav.append(
            f'<button data-goto="{les.key}"><span class="n">{les.number:02d}</span>'
            f"<span>{html.escape(les.title)}</span></button>"
        )
    nav.append('<div class="nav-group">apply</div>')
    nav.append('<button data-goto="projects"><span class="n">&#9633;</span>'
               '<span>Capstone projects</span></button>')

    pager = ('<div class="pager">'
             '<button data-dir="prev">&#8592; previous</button>'
             '<button data-dir="next">next &#8594;</button></div>')
    body = (overview + lesson_html + projects).replace(
        "</footer>", f"{pager}</footer>"
    )

    page = f"""<title>Python Past the Basics</title>
<style>{CSS}</style>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <h1>Python / advanced</h1>
      <p class="sub">{len(lessons)} lessons &middot; {counter['run']} live samples.
        Use &larr; &rarr; to move between lessons.</p>
    </div>
    <nav>{"".join(nav)}</nav>
  </aside>
  <main>{body}</main>
</div>
<script>{JS}</script>
"""

    out = Path(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    return out
