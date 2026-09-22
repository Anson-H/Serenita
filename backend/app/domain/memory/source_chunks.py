"""Structural source units with stable, lossless evidence positions.

Input budgets group these units later. Character offsets locate evidence only.
"""
import re

from markdown_it import MarkdownIt
from zleap.sag.modules.load.chunking.tokenizer import TokenizerTokenEstimator

_PARSER = MarkdownIt('commonmark').enable('table')


def markdown_ranges(text):
    """Keep headings with content, list items with children and tables with headers."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    starts, pending_heading = [], None
    for token in _PARSER.parse(text):
        if token.map is None or token.nesting == -1:
            continue
        if token.type == 'heading_open' and token.level == 0:
            if pending_heading is None:
                pending_heading = offsets[token.map[0]]
        elif (token.level == 0 and token.type not in {'inline', 'bullet_list_open', 'ordered_list_open'}
              or token.type == 'list_item_open' and token.level == 1):
            starts.append(pending_heading if pending_heading is not None else offsets[token.map[0]])
            pending_heading = None
    if pending_heading is not None:
        starts.append(pending_heading)
    starts = sorted({0, *starts, len(text)})
    return [(start, end) for start, end in zip(starts, starts[1:]) if end > start]


def source_fragments(sources):
    """Number structural units independently of model configuration and budgets."""
    result = []
    for identity, source in sorted(sources.items()):
        text = source['content_text']
        if not text.strip():
            continue
        units = source.get('content_units') or [{'character_start': 0, 'character_end': len(text), 'kind': 'text'}]
        offset = 0
        for unit in units:
            start, end = unit['character_start'], unit['character_end']
            if start != offset or not start < end <= len(text):
                raise ValueError('来源结构单元未完整覆盖原文。')
            offset = end
            ranges = [(0, end - start)] if unit['kind'] == 'field_group' else markdown_ranges(text[start:end])
            for left, right in ranges:
                left, right = start + left, start + right
                prefix = text[:left]
                headings = re.findall(r'^#{1,6}[ \t]+.+$', prefix, re.MULTILINE)
                result.append({'id': len(result) + 1, 'content': text[left:right], 'source_key': identity,
                    'character_start': left, 'character_end': right, 'kind': unit['kind'],
                    'section_heading': headings[-1] if headings else source.get('title', '')})
        if offset != len(text):
            raise ValueError('来源结构单元缺少末尾原文。')
    return result


def index_fragments(sources):
    result = []
    for key, source in sorted(sources.items()):
        # A heading section keeps structured item names and values together.
        units = source_fragments({key: source})
        estimate = TokenizerTokenEstimator('generic').estimate_tokens
        current = None
        for unit in units:
            if current is not None and estimate(current['content'] + unit['content']) <= 1000:
                current['content'] += unit['content']
                current['character_end'] = unit['character_end']
            else:
                current = dict(unit)
                result.append(current)
    return result
