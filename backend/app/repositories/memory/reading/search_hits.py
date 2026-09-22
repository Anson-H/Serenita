"""Exact immutable recall origins; labels are projected under current access."""
from collections import defaultdict
import json
import math

from backend.app.schemas.memory.values import canonical_uuid

MAX_TEXT_HITS = 16
MAX_SEED_LABEL_BYTES = 16_384
MAX_RESULT_LABEL_BYTES = 65_536
MAX_PATH_HITS = 3_000
TEXT_KEYS = {'entity_id', 'name_id', 'event_id', 'path_event_id', 'entity_score'}
VECTOR_KEYS = {'binding_id', 'status_id', 'vector_id', 'space_id', 'text_hash', 'vector_hash', 'score'}


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def validate_seed_hits(step):
    """Strict cursor metadata, with no names, original text or inferred identity."""
    for route, keys, limit in (('text', TEXT_KEYS, MAX_TEXT_HITS), ('vector', VECTOR_KEYS, 1)):
        hits = step[route + '_hits']
        if type(hits) is not list or len(hits) > limit or bool(hits) != (step[route + '_rank'] is not None):
            raise ValueError('Invalid recall hit metadata')
        seen = set()
        for hit in hits:
            if type(hit) is not dict or set(hit) != keys:
                raise ValueError('Invalid recall hit fields')
            for key, value in hit.items():
                if key.endswith('_id') and not (key == 'name_id' and value is None):
                    canonical_uuid(value)
                if key.endswith('_hash') and (type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
                    raise ValueError('Invalid recall hash')
            score = hit['entity_score' if route == 'text' else 'score']
            try:
                finite = type(score) in (float, int) and math.isfinite(score)
            except OverflowError:
                finite = False
            if not finite or (route == 'text' and score <= 0) or (route == 'vector' and not -2 <= score <= 2):
                raise ValueError('Invalid recall score')
            identity = (hit['entity_id'], hit['name_id']) if route == 'text' else hit['binding_id']
            if identity in seen:
                raise ValueError('Duplicate recall hit')
            seen.add(identity)


def hit_lookup(snapshot, query):
    from backend.app.repositories.memory.indexing.index_repository import entity_terms
    return {'names': {(row['entity_id'], row['name_id']): row for row in snapshot['names']},
        'links': {(row['event_id'], row['entity_id']): row for row in snapshot['links']},
        'bindings': {row['binding_id']: row for row in snapshot['bindings']},
        'terms': set(entity_terms(query))}


def verify_hit_bindings(vectors, snapshot, lookup, hits, *, verification=None):
    groups = defaultdict(dict)
    for hit in hits:
        binding = lookup['bindings'].get(hit['binding_id'])
        if binding and binding['space_id'] in snapshot['spaces'] and binding.get('status') and binding['status']['state'] == 'confirmed':
            groups[binding['space_id']][binding['binding_id']] = binding
    verified = set()
    verification = {} if verification is None else verification
    for space_id, bindings in groups.items():
        def key(row):
            return (space_id, row['binding_id'], row['vector_id'], row['text_hash'], row['status']['vector_hash'])
        missing = [row for row in bindings.values() if key(row) not in verification]
        if missing:
            rows, _ = vectors.verify_many(snapshot['account_id'], snapshot['member_id'], missing, snapshot['spaces'][space_id])
            for row in missing:
                verification[key(row)] = row['binding_id'] in rows
        verified.update(row['binding_id'] for row in bindings.values() if verification[key(row)])
    return verified


def _text_label(hit, snapshot, names):
    entity = snapshot['entities'][hit['entity_id']]
    name = names[(hit['entity_id'], hit['name_id'])] if hit['name_id'] is not None else None
    return {**hit, 'name': name['name'] if name else entity['canonical_name'],
        **{key: entity[key] for key in ('canonical_name', 'entity_type', 'formal_resource_type', 'formal_resource_id')}}






def check_seed(repo, access, db, cutoff, identity, step, snapshot, lookup, verified):
    """An alternate name/binding cannot replace any original channel's proof."""
    from backend.app.repositories.memory.indexing.index_repository import entity_terms
    terms, links = lookup['terms'], lookup['links']
    def visible(kind, identity, **kwargs):
        row = repo._record(db, access, kind, identity, cutoff=cutoff, **kwargs)
        return row if row is not None and repo._visible(db, access, row) else None
    text_ok = bool(step['text_hits'])
    for hit in step['text_hits']:
        entity = visible('entity', hit['entity_id'])
        name = visible('entity_name', hit['entity_id'], item_id=hit['name_id']) if hit['name_id'] else entity
        link = links.get((identity, hit['entity_id']))
        actual_name = name.get('name', name.get('canonical_name')) if name else None
        if (entity is None or name is None or link is None or name['event_id'] != hit['event_id']
                or link['event_id'] != hit['path_event_id']
                or not terms.intersection(entity_terms(actual_name))):
            text_ok = False
    vector_ok = bool(step['vector_hits'])
    for hit in step['vector_hits']:
        binding = lookup['bindings'].get(hit['binding_id'])
        space = snapshot['spaces'].get(hit['space_id'])
        status = binding.get('status') if binding else None
        if (binding is None or space is None or binding['event_id'] != identity or status is None
                or status['status_id'] != hit['status_id'] or status['state'] != 'confirmed'
                or any(binding[key] != hit[key] for key in ('vector_id', 'space_id', 'text_hash', 'vector_hash'))
                or visible('vector_binding', hit['binding_id']) is None
                or visible('vector_status', hit['binding_id'], item_id=hit['status_id']) is None
                or visible('vector_space', hit['space_id']) is None):
            vector_ok = False
            continue
        if hit['binding_id'] not in verified:
            vector_ok = False
    changed = (bool(step['text_hits']) != text_ok or bool(step['vector_hits']) != vector_ok)
    return {**step, 'text_hits': step['text_hits'] if text_ok else [], 'text_rank': step['text_rank'] if text_ok else None,
        'vector_hits': step['vector_hits'] if vector_ok else [], 'vector_rank': step['vector_rank'] if vector_ok else None}, changed


def project_hits(chains, snapshot, *, lookup, ranking_event=None, ranking_hits=()):
    text, vector, semantic, seen = [], [], [], set()
    for chain in chains:
        from backend.app.repositories.memory.reading.sag_paths import project_semantic_hit
        for step in chain:
            if 'entity_hit' in step:
                hit = step['entity_hit']
                key = ('semantic', hit['binding_id'])
                if key not in seen:
                    semantic.append(project_semantic_hit(hit, snapshot, step['event_id']))
                    seen.add(key)
        seed = chain[0]
        for hit in seed['text_hits']:
            key = ('text', seed['event_id'], hit['entity_id'], hit['name_id'])
            if key not in seen:
                text.append({'seed_event_id': seed['event_id'], **_text_label(hit, snapshot, lookup['names'])})
                seen.add(key)
        for hit in seed['vector_hits']:
            key = ('vector', seed['event_id'], hit['binding_id'])
            if key not in seen:
                space = snapshot['spaces'][hit['space_id']]
                vector.append({'seed_event_id': seed['event_id'], **hit,
                    **{name: space[name] for name in ('model_id', 'model_signature', 'dimensions')}})
                seen.add(key)
        for step in chain[1:]:
            for hit in step.get('vector_hits', []):
                key = ('vector', step['event_id'], hit['binding_id'])
                if key not in seen:
                    space = snapshot['spaces'][hit['space_id']]
                    vector.append({'path_event_id': step['event_id'], **hit,
                        **{name: space[name] for name in ('model_id', 'model_signature', 'dimensions')}})
                    seen.add(key)
    for hit in ranking_hits:
        if ('vector', ranking_event, hit['binding_id']) not in seen:
            space = snapshot['spaces'][hit['space_id']]
            vector.append({'ranking_event_id': ranking_event, **hit,
                **{name: space[name] for name in ('model_id', 'model_signature', 'dimensions')}})
    return {'text': text, 'vector': vector, **({'semantic': semantic} if semantic else {})}


def ranking_evidence(repo, actor, member, cutoff, hits, snapshot, query, *, verification=None):
    from backend.app.repositories.memory.indexing.index_repository import MemoryIndexRepository
    vectors = MemoryIndexRepository(repo).vectors
    lookup = hit_lookup(snapshot, query)
    verified = verify_hit_bindings(vectors, snapshot, lookup, [hit for values in hits.values() for hit in values], verification=verification)
    accepted, changed = {}, False
    with repo._transaction(actor, member) as (access, db):
        for identity, values in hits.items():
            step = {'text_hits': [], 'text_rank': None, 'vector_hits': values,
                'vector_rank': 1 if values else None}
            live, missing = check_seed(repo, access, db, cutoff, identity, step, snapshot, lookup, verified)
            accepted[identity] = live['vector_hits']
            changed |= missing
    return accepted, changed
