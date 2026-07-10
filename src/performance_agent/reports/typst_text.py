"""Typst text primitives: escaping and a minimal markdown-to-Typst converter.

Program bodies are agent-written markdown. Only the subset the skills produce
is converted (headings, bullets, bold); everything else is escaped plain text,
so athlete/agent content can never execute as Typst code.
"""

# Order matters: backslash first, then Typst's special characters.
_SPECIALS = "\\#$*_@[]<>`^"


def escape_typst(text: str) -> str:
    """Escape every Typst-significant character in plain text."""
    for char in _SPECIALS:
        text = text.replace(char, "\\" + char)
    return text


def _convert_bold(line: str) -> str:
    """Convert markdown **bold** to Typst *bold* on an ALREADY-ESCAPED line."""
    # after escaping, "**" appears as "\*\*"
    return line.replace("\\*\\*", "*")


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
