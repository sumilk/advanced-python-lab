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
_BOLD = re.compile(r"\*\*(.+?)\*\*")          # .+? so **bold with *italic* inside** works
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_STASHED = re.compile(r"\x00(\d+)\x00")
_MARKER = re.compile(r"^[-*] |^\d+\. ")


def inline(text: str) -> str:
    """Render `code`, **bold** and *italic* spans to ANSI.

    Code spans are stashed away before the bold/italic passes and restored
    afterwards. Without that, the `**` in a span like `f(**kwargs)` is fair
    game for the bold pattern, which eats the asterisks and hands the reader
    Python that no longer parses.
    """
    stashed: list[str] = []

    def stash(match: re.Match[str]) -> str:
        stashed.append(color(match.group(1), "bright_yellow"))
        return f"\x00{len(stashed) - 1}\x00"

    def italic(match: re.Match[str]) -> str:
        # "italic off" (23) rather than a blanket RESET: an italic nested
        # inside a bold span must not switch the bold off along with itself.
        if not _ENABLED:
            return match.group(1)
        return "\033[3m{}\033[23m".format(match.group(1))

    text = _INLINE_CODE.sub(stash, text)
    text = _BOLD.sub(lambda m: color(m.group(1), "bold"), text)
    text = _ITALIC.sub(italic, text)
    return _STASHED.sub(lambda m: stashed[int(m.group(1))], text)


def fill(text: str, w: int, subsequent_indent: str = "") -> str:
    """`textwrap.fill` that measures *visible* width, so ANSI codes are free.

    Wrapping already-coloured text with textwrap counts every escape sequence
    as content and breaks lines many columns early.
    """
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current, current_len = words[0], visible_len(words[0])
    for word in words[1:]:
        word_len = visible_len(word)
        limit = w - (len(subsequent_indent) if lines else 0)
        if current_len + 1 + word_len > limit:
            lines.append(current)
            current, current_len = word, word_len
        else:
            current += " " + word
            current_len += 1 + word_len
    lines.append(current)
    return ("\n" + subsequent_indent).join(lines)


def render(md: str) -> str:
    """Render markdown-lite text to an ANSI string."""
    w = width()
    lines = textwrap.dedent(md).strip("\n").split("\n")
    out: list[str] = []
    index = 0

    def starts_block(text: str) -> bool:
        stripped = text.strip()
        return (not stripped
                or stripped.startswith(("```", "#", ">", "|"))
                or bool(_MARKER.match(stripped)))

    def paragraph(first: str) -> str:
        """Join *first* with the wrapped continuation lines that follow it.

        Inline markup is only recognised within a single string, so a
        `**bold**` span split across two source lines has to be rejoined
        before `inline()` sees it.
        """
        nonlocal index
        parts = [first]
        while index + 1 < len(lines) and not starts_block(lines[index + 1]):
            index += 1
            parts.append(lines[index].strip())
        return " ".join(parts)

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if stripped.startswith("```"):
            fence: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                fence.append(lines[index])
                index += 1
            out.append(code_block("\n".join(fence), numbers=False))
        elif not stripped:
            out.append("")
        elif stripped.startswith("### "):
            out.append(color(stripped[4:], "bold", "bright_yellow"))
        elif stripped.startswith("## "):
            out.append("")
            out.append(color("\u25b8 " + stripped[3:], "bold", "bright_cyan"))
            out.append(color("\u2500" * min(w, len(stripped) + 2), "grey"))
        elif stripped.startswith("> "):
            quote = [stripped[2:]]
            while index + 1 < len(lines) and lines[index + 1].strip().startswith(">"):
                index += 1
                quote.append(lines[index].strip()[1:].strip())
            for ln in fill(inline(" ".join(quote)), w - 4).split("\n"):
                out.append(color("\u2502 ", "yellow") + color(ln, "italic"))
        elif _MARKER.match(stripped) and stripped[0] in "-*":
            body = fill(inline(paragraph(stripped[2:])), w - 4,
                        subsequent_indent="    ")
            out.append("  " + color("\u2022", "cyan") + " " + body)
        elif _MARKER.match(stripped):
            num, _, rest = stripped.partition(". ")
            body = fill(inline(paragraph(rest)), w - 5, subsequent_indent="     ")
            out.append("  " + color(num + ".", "cyan") + " " + body)
        elif stripped.startswith("|"):
            out.append(inline(raw))
        else:
            out.append(fill(inline(paragraph(stripped)), w))
        index += 1
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
