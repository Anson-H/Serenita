"""Counts and chronology over immutable event expressions."""
from collections import defaultdict

from backend.app.schemas.memory.values import occurrence_time_bounds





def start_bounds(event):
    value = event["occurrence_time"] or {}
    if not value.get("start"):
        return None, None
    return occurrence_time_bounds({**value, "end": None})


def first_occurrences(events):
    bounds = [(event["event_id"], *start_bounds(event)) for event in events]
    known_latest = [end for _, _, end in bounds if end is not None]
    earliest_proven_upper = min(known_latest) if known_latest else None
    possible = [event_id for event_id, start, _ in bounds if start is None or earliest_proven_upper is None or start <= earliest_proven_upper]
    candidates = [(start, end) for event_id, start, end in bounds if event_id in possible]
    definite = bool(candidates) and all(start is not None and end is not None for start, end in candidates) and (
        len(candidates) == 1 or len(set(candidates)) == 1 and candidates[0][0] == candidates[0][1])
    return {"event_ids": possible, "definite": definite, "empty": not events,
            "unknown_time_event_ids": [event_id for event_id, start, end in bounds if start is None or end is None],
            "scope": "occurrence_start_with_original_precision"}


def effective_occurrence_times(events, pairs):
    """Report uncertain correction scope without interpreting free-text reasons."""
    by_id = {event['event_id']: dict(event) for event in events}
    paths = defaultdict(list)
    for pair in pairs:
        relation = pair['relation']
        if relation['relation_type'] not in {'Supersedes', 'ConflictsWith'}:
            continue
        affected = [relation['to_event_id']]
        if relation['relation_type'] == 'ConflictsWith':
            affected.append(relation['from_event_id'])
        for identity in affected:
            if identity in by_id:
                paths[identity].append({'relation_id': relation['relation_id'], 'source_event_id': relation['from_event_id']})
    for identity, basis in paths.items():
        by_id[identity]['occurrence_time'] = {'start': None, 'end': None, 'uncertainty': 'unknown',
            'unknown': ['关系未结构化标记更正或冲突的范围，需读取两端事件判断发生时间。']}
        by_id[identity]['occurrence_time_basis'] = basis
    return list(by_id.values()), [{'event_id': identity, 'reason': 'relation_scope_requires_event_reading'} for identity in paths]
