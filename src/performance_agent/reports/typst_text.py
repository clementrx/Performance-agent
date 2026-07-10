"""Typst text primitives: escaping and a minimal markdown-to-Typst converter.

Program bodies are agent-written markdown. Only the subset the skills produce
is converted (headings, bullets, bold); everything else is escaped plain text,
so athlete/agent content can never execute as Typst code.
"""

import re

# Order matters: backslash first, then Typst's special characters.
# "/" neutralizes // and /* */ comments (recognized anywhere in Typst markup);
# "=" and "+" neutralize line-start heading/enum syntax uniformly.
_SPECIALS = "\\#$*_@[]<>`^/=+"

# On an already-escaped line, a markdown "**" appears as "\*\*"; only complete
# open/close pairs become Typst bold — an unmatched "\*\*" stays literal.
_BOLD_PAIR = re.compile(r"\\\*\\\*(.+?)\\\*\\\*")


def escape_typst(text: str) -> str:
    """Escape every Typst-significant character in plain text.

    Line boundaries (LF, CRLF, and other Unicode line separators) collapse to
    a single space first, so escaped text can never introduce new lines and
    smuggle in Typst line-start syntax such as headings or list items.
    """
    text = " ".join(text.splitlines())
    for char in _SPECIALS:
        text = text.replace(char, "\\" + char)
    return text


def _convert_bold(line: str) -> str:
    """Convert complete markdown **bold** pairs on an ALREADY-ESCAPED line."""
    return _BOLD_PAIR.sub(r"*\1*", line)


def markdown_to_typst(markdown: str) -> str:
    """Convert the skills' markdown subset to Typst markup."""
    lines: list[str] = []
    for raw in markdown.splitlines():
        if raw.startswith("### "):
            lines.append("=== " + escape_typst(raw[4:]))
        elif raw.startswith("## "):
            lines.append("== " + escape_typst(raw[3:]))
        elif raw.startswith("# "):
            lines.append("= " + escape_typst(raw[2:]))
        elif raw.startswith("- "):
            lines.append("- " + _convert_bold(escape_typst(raw[2:])))
        else:
            lines.append(_convert_bold(escape_typst(raw)))
    return "\n".join(lines)
