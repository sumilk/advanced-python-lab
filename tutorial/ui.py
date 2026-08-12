"""Terminal UI helpers: colour, boxes, and a tiny markdown renderer.

Everything degrades gracefully: if stdout is not a TTY, or NO_COLOR is set,
all escape sequences are dropped and the output is plain text.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap

_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

RESET = "\033[0m"
_CODES = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "grey": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
}


def color(text: str, *styles: str) -> str:
    """Wrap *text* in the given styles, e.g. color("hi", "bold", "cyan")."""
    if not _ENABLED or not styles:
        return text
    codes = ";".join(_CODES[s] for s in styles if s in _CODES)
    if not codes:
        return text
    return "\033[{}m{}{}".format(codes, text, RESET)


def width(default: int = 80, cap: int = 92) -> int:
    return min(shutil.get_terminal_size((default, 24)).columns, cap)


def visible_len(text: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def rule(char: str = "\u2500", style: str = "grey") -> str:
    return color(char * width(), style)


def title_bar(text: str, style: str = "bright_cyan") -> str:
    w = width()
    inner = " " + text.strip() + " "
    pad = max(0, w - len(inner) - 2)
    left = pad // 2
    right = pad - left
    line = "\u2550" * left + inner + "\u2550" * right
    return color("\u2554" + line + "\u2557", style)


def box(lines, style: str = "grey", pad: int = 1):
    """Render *lines* inside a light box, returning a list of strings."""
    w = width()
    inner_w = w - 2 - pad * 2
    out = [color("\u250c" + "\u2500" * (w - 2) + "\u2510", style)]
    for raw in lines:
        for chunk in (raw.split("\n") if raw else [""]):
            visible = visible_len(chunk)
            filler = " " * max(0, inner_w - visible)
            out.append(
                color("\u2502", style)
                + " " * pad
                + chunk
                + filler
                + " " * pad
                + color("\u2502", style)
            )
    out.append(color("\u2514" + "\u2500" * (w - 2) + "\u2518", style))
    return out


# --------------------------------------------------------------------------
# Syntax highlighting: deliberately small. Enough to make code readable,
# not a real lexer.
# --------------------------------------------------------------------------
_KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "match",
    "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with",
    "yield",
}
_BUILTINS = {
    "abs", "all", "any", "bool", "bytes", "callable", "classmethod", "dict",
    "dir", "divmod", "enumerate", "eval", "exec", "filter", "float", "format",
    "frozenset", "getattr", "hasattr", "hash", "id", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "object",
    "open", "print", "property", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super",
    "tuple", "type", "vars", "zip",
}

_TOKEN_RE = re.compile(
    r"""(?P<comment>\#[^\n]*)
      | (?P<string>[rbfu]{0,2}(?:'''.*?'''|\"\"\".*?\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"))
      | (?P<decorator>@[A-Za-z_][\w.]*)
      | (?P<number>\b\d[\w.]*\b)
      | (?P<name>\b[A-Za-z_]\w*\b)
    """,
    re.VERBOSE | re.DOTALL,
)


def highlight(code: str) -> str:
    if not _ENABLED:
        return code

    def repl(m):
        kind = m.lastgroup
        text = m.group()
        if kind == "comment":
            return color(text, "grey", "italic")
        if kind == "string":
            return color(text, "bright_green")
        if kind == "decorator":
            return color(text, "bright_magenta")
        if kind == "number":
            return color(text, "yellow")
        if kind == "name":
            if text in _KEYWORDS:
                return color(text, "bright_blue", "bold")
            if text in _BUILTINS:
                return color(text, "cyan")
        return text

    return _TOKEN_RE.sub(repl, code)


def code_block(code: str, numbers: bool = True, gutter: str = "\u2502") -> str:
    lines = textwrap.dedent(code).strip("\n").split("\n")
    n_w = len(str(len(lines)))
    out = []
    for i, line in enumerate(lines, 1):
        prefix = color(str(i).rjust(n_w) + " " + gutter + " ", "grey") if numbers else "    "
        out.append(prefix + highlight(line))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Markdown-lite. Supports: ## headings, - bullets, 1. lists, `code`,
# **bold**, *italic*, > quotes, fenced ``` blocks, and | tables (raw).
# --------------------------------------------------------------------------
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def inline(text: str) -> str:
    text = _INLINE_CODE.sub(lambda m: color(m.group(1), "bright_yellow"), text)
    text = _BOLD.sub(lambda m: color(m.group(1), "bold"), text)
    text = _ITALIC.sub(lambda m: color(m.group(1), "italic"), text)
    return text


def render(md: str) -> str:
    """Render markdown-lite text to an ANSI string."""
    w = width()
    out = []
    in_fence = False
    fence_buf = []
    for raw in textwrap.dedent(md).strip("\n").split("\n"):
        if raw.strip().startswith("```"):
            if in_fence:
                out.append(code_block("\n".join(fence_buf), numbers=False))
                fence_buf = []
                in_fence = False
            else:
                in_fence = True
            continue
        if in_fence:
            fence_buf.append(raw)
            continue

        stripped = raw.strip()
        if not stripped:
            out.append("")
        elif stripped.startswith("### "):
            out.append(color(stripped[4:], "bold", "bright_yellow"))
        elif stripped.startswith("## "):
            out.append("")
            out.append(color("\u25b8 " + stripped[3:], "bold", "bright_cyan"))
            out.append(color("\u2500" * min(w, len(stripped) + 2), "grey"))
        elif stripped.startswith("> "):
            body = textwrap.fill(inline(stripped[2:]), w - 4)
            for ln in body.split("\n"):
                out.append(color("\u2502 ", "yellow") + color(ln, "italic"))
        elif re.match(r"^[-*] ", stripped):
            body = textwrap.fill(
                inline(stripped[2:]), w - 4,
                subsequent_indent="    ",
            )
            out.append("  " + color("\u2022", "cyan") + " " + body[0:].lstrip())
        elif re.match(r"^\d+\. ", stripped):
            num, _, rest = stripped.partition(". ")
            body = textwrap.fill(inline(rest), w - 5, subsequent_indent="     ")
            out.append("  " + color(num + ".", "cyan") + " " + body)
        elif stripped.startswith("|"):
            out.append(inline(raw))
        else:
            out.append(textwrap.fill(inline(stripped), w))
    if fence_buf:
        out.append(code_block("\n".join(fence_buf), numbers=False))
    return "\n".join(out)


def p(md: str = "") -> None:
    print(render(md) if md else "")


def ok(msg: str) -> str:
    return color("\u2713 ", "bright_green") + msg


def fail(msg: str) -> str:
    return color("\u2717 ", "bright_red") + msg


def info(msg: str) -> str:
    return color("\u2139 ", "bright_blue") + msg


def warn(msg: str) -> str:
    return color("! ", "bright_yellow") + msg


def clear() -> None:
    if _ENABLED:
        print("\033[2J\033[H", end="")


def ask(prompt: str, default: str = "") -> str:
    """Read a line, tolerating EOF/Ctrl-C by returning the default."""
    try:
        return input(color(prompt, "bright_cyan")).strip() or default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def pause(msg: str = "Press Enter to continue \u2026") -> None:
    try:
        input(color("\n" + msg, "grey"))
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
