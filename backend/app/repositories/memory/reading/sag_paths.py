"""Exact SAG name/role vector evidence for paths and signed continuations."""
from collections import defaultdict
import math

from backend.app.domain.memory.scores import sag_score
from backend.app.core.errors import SerenitaError
from backend.app.repositories.memory.indexing.semantic_index_repository import MemorySemanticIndexRepository, require_binding
from backend.app.schemas.memory.values import canonical_uuid


SEMANTIC_HIT_KEYS = {'binding_id', 'vector_id', 'space_id', 'text_hash', 'vector_hash', 'event_id',
    'index_kind', 'status_id', 'cosine_score', 'sag_score', 'entity_id', 'name_id'}


def validate_semantic_hit(hit, kind):
    if type(hit) is not dict or set(hit) != SEMANTIC_HIT_KEYS or hit['index_kind'] != kind:
        raise ValueError('Invalid SAG vector evidence fields')
    for key, value in hit.items():
        if key.endswith('_id') and value is not None:
            canonical_uuid(value)
        if key.endswith('_hash') and (type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
            raise ValueError('Invalid SAG vector digest')
    nullable = {'name_id'}
    if any(hit[key] is None for key in SEMANTIC_HIT_KEYS if key.endswith('_id') and key not in nullable):
        raise ValueError('Missing SAG vector identity')
    if kind == 'entity_role' and hit['name_id'] is not None:
        raise ValueError('Invalid SAG vector target')
    try:
        valid_score = (type(hit['cosine_score']) in (int, float) and type(hit['sag_score']) in (int, float)
            and math.isfinite(hit['cosine_score']) and -1.000001 <= hit['cosine_score'] <= 1.000001
            and math.isfinite(hit['sag_score']) and abs(sag_score(hit['cosine_score']) - hit['sag_score']) <= 1e-9)
    except OverflowError:
        valid_score = False
    if not valid_score:
        raise ValueError('Invalid SAG score conversion')


def semantic_hits(paths):
    return [step['entity_hit'] for steps in paths.values() for step in steps
        if step['route'] in {'entity_seed', 'entity_vector'}]


def verified_semantic_bindings(repo, actor, member, cutoff, hits, snapshot):
    """Verify exact physical rows, never substitute a newer index for a hit."""
    semantic = MemorySemanticIndexRepository(repo)
    bindings = {row['binding_id']: row for row in semantic.snapshot(actor, member, cutoff)['bindings']}
    groups = defaultdict(dict)
    for hit in hits:
        binding = bindings.get(hit['binding_id'])
        if binding is None or not binding['status'] or binding['status']['state'] != 'confirmed':
            continue
        if binding['status']['status_id'] != hit['status_id']:
            continue
        keys = SEMANTIC_HIT_KEYS - {'status_id', 'cosine_score', 'sag_score'}
        if any(binding[key] != hit[key] for key in keys):
            continue
        if binding['space_id'] not in snapshot['spaces']:
            continue
        groups[binding['space_id']][binding['binding_id']] = binding
    verified = set()
    for space_id, rows in groups.items():
        actual, _ = semantic.vectors.verify_many(snapshot['account_id'], member, list(rows.values()), snapshot['spaces'][space_id])
        verified.update(actual)
    return verified


def semantic_hit_visible(repo, db, access, hit, verified, snapshot, *, event_id):
    if hit['binding_id'] not in verified or hit['entity_id'] not in snapshot['entities']:
        return False
    if hit['index_kind'] == 'entity_role' and hit['event_id'] != event_id:
        return False
    if not any(row['event_id'] == event_id and row['entity_id'] == hit['entity_id'] for row in snapshot['links']):
        return False
    try:
        # Permission may change after physical verification. Require the exact
        # immutable binding and its underlying name/role evidence again.
        require_binding(repo, db, access, hit['binding_id'])
    except SerenitaError:
        return False
    return True


def project_semantic_hit(hit, snapshot, event_id):
    entity, space = snapshot['entities'][hit['entity_id']], snapshot['spaces'][hit['space_id']]
    name = next((row for row in snapshot['names'] if row['entity_id'] == hit['entity_id'] and row['name_id'] == hit['name_id']), None)
    return {**hit, 'path_event_id': event_id,
        'name': name['name'] if name else entity['canonical_name'],
        **{key: entity[key] for key in ('canonical_name', 'entity_type', 'formal_resource_type', 'formal_resource_id')},
        **{key: space[key] for key in ('model_id', 'model_signature', 'dimensions')}}


def paths_from_sag(result):
    """Project only edges recorded by SAG, backed by the actual I/O hits."""
    event_hits, names, roles = {}, {}, {}
    for hit in result['vector_evidence']['vector_hits']:
        kind = hit['index_kind']
        if kind == 'event':
            event_hits.setdefault(hit['event_id'], {**{key: hit[key] for key in
                ('binding_id', 'status_id', 'vector_id', 'space_id', 'text_hash', 'vector_hash')}, 'score': hit['cosine_score']})
        elif kind == 'entity_name':
            names.setdefault(hit['entity_id'], hit)
        elif kind == 'entity_role':
            roles.setdefault((hit['event_id'], hit['entity_id']), hit)
    paths, limited = defaultdict(list), False
    def add(identity, path):
        nonlocal limited
        if path in paths[identity]:
            return
        if len(paths[identity]) >= 8:
            limited = True
        else:
            paths[identity].append(path)
    edges = [edge for incoming in result['route_index']['incoming'].values() for edge in incoming]
    for rank, identity in enumerate(result['query_event_ids'], 1):
        if identity in event_hits:
            add(identity, {'route': 'seed', 'text_rank': None, 'text_hits': [], 'vector_rank': rank,
                'vector_hits': [event_hits[identity]]})
    for edge in edges:
        if edge['method'] == 'entity_event_recall' and edge['from_type'] == 'entity' and edge['to_type'] == 'event':
            entity, identity = edge['from_id'], edge['to_id']
            if entity in names and identity in event_hits:
                add(identity, {'route': 'entity_seed', 'entity_hit': names[entity], 'text_rank': None, 'text_hits': [],
                    'vector_rank': 1, 'vector_hits': [event_hits[identity]]})
    for edge in edges:
        if edge['method'] != 'expand_key_to_event' or edge['from_type'] != 'entity' or edge['to_type'] != 'event':
            continue
        entity, identity, hop = edge['from_id'], edge['to_id'], edge['hop']
        if identity not in event_hits or hop not in (1, 2):
            continue
        for previous in edges:
            if (previous['method'] not in {'seed_event_to_key', 'expand_event_to_key'} or previous['from_type'] != 'event'
                    or previous['to_type'] != 'entity' or previous['to_id'] != entity or previous['to_hop'] != hop):
                continue
            via = previous['from_id']
            role = roles.get((via, entity))
            if role is not None:
                add(identity, {'route': 'entity_vector', 'via_event_id': via, 'hop': hop,
                    'entity_id': entity, 'entity_hit': role, 'vector_hits': [event_hits[identity]]})
    return dict(paths), event_hits, limited
