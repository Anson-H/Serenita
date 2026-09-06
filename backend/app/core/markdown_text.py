"""Derive selectable text from Markdown without changing literal content."""

from markdown_it import MarkdownIt
from markdown_it.token import Token


_MARKDOWN = MarkdownIt(
    "commonmark",
    {"tasklists": True, "strikethrough_single_tilde": True},
).enable(["table", "strikethrough"])


def _inline_text(tokens: list[Token]) -> str:
    parts: list[str] = []
    for token in tokens:
        if token.type in {"text", "code_inline", "html_inline"}:
            # ReactMarkdown displays raw HTML as literal text, not active HTML.
            parts.append(token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        # Formatting/link delimiters and images have no selectable text.
    return "".join(parts)


def markdown_selection_text(content: str) -> str:
    """Project CommonMark and GFM formatting to the text a selection contains.

    Inline formatting does not insert spaces. Blocks and table cells retain
    boundaries; callers may normalize whitespace, but must not discard it or
    remove punctuation from code, escaped text, or numeric values.
    """
    parts: list[str] = []
    for token in _MARKDOWN.parse(content):
        if token.type == "inline":
            parts.append(_inline_text(token.children or []))
        elif token.type in {"code_block", "fence", "html_block"}:
            parts.append(token.content)
    return "\n".join(parts)
