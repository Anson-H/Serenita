"""Project persisted Web Tool evidence into user-facing citation text."""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit
from markdown_it import MarkdownIt

from backend.app.core.tabular_json import decode_tabular_json


_CITATION_MARKER = re.compile(r"\[cite:([^\]\r\n]+)\]")
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)")


def _is_escaped(text: str, offset: int) -> bool:
    count = 0
    while offset > 0 and text[offset - 1] == "\\":
        count += 1
        offset -= 1
    return count % 2 == 1


def _map_markdown_outside_code(content: str, transform) -> str:
    lines = content.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    protected = [(offsets[token.map[0]], offsets[token.map[1]])
                 for token in MarkdownIt().parse(content)
                 if token.type in {"fence", "code_block"} and token.map]
    cursor = 0
    output = []

    def inline(text):
        result, start = [], 0
        for match in _INLINE_CODE.finditer(text):
            if _is_escaped(text, match.start()):
                continue
            result.extend((transform(text[start:match.start()]), match.group(0)))
            start = match.end()
        return "".join(result) + transform(text[start:])

    for start, end in protected:
        output.extend((inline(content[cursor:start]), content[start:end]))
        cursor = end
    return "".join(output) + inline(content[cursor:])


def _replace_markers(content: str, replacement) -> str:
    def transform(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            if _is_escaped(text, match.start()):
                return match.group(0)
            return replacement(match.group(1))

        return _CITATION_MARKER.sub(replace, text)

    return _map_markdown_outside_code(content, transform)




def _logical_tool_output(raw_result: Any) -> dict[str, Any] | None:
    decoded = decode_tabular_json(raw_result)
    if not isinstance(decoded, dict):
        return None
    output = decoded.get("output")
    return output if isinstance(output, dict) else decoded


def _citation_source(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    citation_id = str(value.get("citation_id") or "").strip()
    url = str(value.get("url") or "").strip()
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (
        not citation_id
        or re.fullmatch(r"[\w-]+", citation_id) is None
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
    ):
        return None
    title = str(value.get("title") or parsed.hostname).strip() or parsed.hostname
    return {"citation_id": citation_id, "title": title, "url": url}


def web_citation_sources_from_events(
    events: Iterable[Any], turn_id: str
) -> dict[str, dict[str, str]]:
    """Build a trusted source registry from completed Web Tool Results."""

    sources: dict[str, dict[str, str]] = {}
    for event in events:
        if getattr(event, "type", None) != "tool/result":
            continue
        data = getattr(event, "data", None)
        if not isinstance(data, dict):
            continue
        if (
            str(data.get("turn_id") or "") != str(turn_id)
            or str(data.get("status") or "") != "completed"
        ):
            continue
        output = _logical_tool_output(data.get("result"))
        name = str(data.get("name") or "")
        candidates = (
            output.get("results")
            if name == "web_search" and output
            else output.get("pages")
            if name == "web_read" and output
            else None
        )
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            source = _citation_source(candidate)
            if source is not None:
                sources.setdefault(source["citation_id"], source)
    return sources


def _escape_markdown_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def export_web_citation_markdown(
    content: str, events: Iterable[Any], turn_id: str
) -> str:
    """Resolve internal markers to portable inline links for saved snapshots."""

    sources = web_citation_sources_from_events(events, turn_id)

    return _export_citation_markdown(content, sources)


class UnresolvedCitationError(ValueError):
    code = "REPORT_CITATION_UNRESOLVED"

    def __init__(self, citation_ids: list[str]):
        super().__init__("解读结果包含未读取来源的引用标识：" + "、".join(citation_ids))
        self.details = {"citation_ids": citation_ids}


def report_citation_markdown(content: str, observations: list[dict[str, Any]]) -> str:
    sources: dict[str, dict[str, str]] = {}
    for observation in observations:
        output = _logical_tool_output(observation.get("output"))
        if not output:
            continue
        name = observation.get("name")
        candidates = output.get("results") if name == "web_search" else output.get("pages") if name == "web_read" else None
        if isinstance(candidates, list):
            for candidate in candidates:
                source = _citation_source(candidate)
                if source:
                    sources.setdefault(source["citation_id"], source)
    return _export_citation_markdown(content, sources, strict=True)


def _export_citation_markdown(content: str, sources: dict[str, dict[str, str]], *, strict: bool = False) -> str:
    unresolved: list[str] = []
    def replacement(citation_id: str) -> str:
        source = sources.get(citation_id)
        if source is None:
            if citation_id not in unresolved:
                unresolved.append(citation_id)
            return ""
        title = _escape_markdown_label(source["title"])
        url = source["url"].replace("<", "%3C").replace(">", "%3E")
        return f"[{title}](<{url}>)"

    rendered = _replace_markers(str(content or ""), replacement)
    if strict and unresolved:
        raise UnresolvedCitationError(unresolved)
    return rendered
