"""Signed, bounded SAG paths; cursor identity never grants source permission.

All MemoryService instances in this process share an ephemeral key. A process
restart invalidates its cursors. The caller must re-evaluate the original seed
and every edge against current permissions before continuing a two-hop search.
"""
import base64
import binascii
from collections import Counter
import hashlib
import hmac
import json
import re
import secrets

from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.relations import RELATION_TYPES
from backend.app.schemas.memory.values import canonical_uuid
from backend.app.repositories.memory.reading.search_hits import validate_seed_hits, MAX_PATH_HITS


MAX_ENCODED_CHARACTERS = 200_000
MAX_IDENTITIES = 5_000
MAX_CHAINS_PER_SEED = 8
MAX_CHAINS = 1_000
MAX_PATH_STEPS = 3_000
MAX_PATH_BYTES = 120_000
MAX_SCOPE_BYTES = 32_768
_SECRET = secrets.token_bytes(32)
_DOMAIN = b'serenita-memory-search-continuation\x00'
_BASE64 = re.compile(r'[A-Za-z0-9_-]+\Z')
_SIGNATURE = re.compile(r'[0-9a-f]{64}\Z')


def _invalid():
    raise SerenitaError('invalid_input', 'MEMORY_CONTINUATION_INVALID',
                        '继续检索位置无效、已失效或与当前范围不一致，请重新查询。')


def _budget(dimension, limit):
    raise SerenitaError('resource_limit', 'MEMORY_CONTINUATION_BUDGET',
                        '继续检索的路径或位置超出容量，请缩小查询范围后重新查询。',
                        details={'dimension': dimension, 'limit': limit})


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _invalid()


def _scope_hash(scope):
    if type(scope) is not dict or not scope:
        _invalid()
    encoded = _json(scope)
    if len(encoded) > MAX_SCOPE_BYTES:
        _budget('scope_bytes', MAX_SCOPE_BYTES)
    return hashlib.sha256(encoded).hexdigest()


def _uuid(value):
    if type(value) is not str:
        _invalid()
    try:
        return canonical_uuid(value)
    except ValueError:
        _invalid()


def _integer(value, *, maximum=2**63 - 1):
    if type(value) is not int or not 1 <= value <= maximum:
        _invalid()


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        _invalid()


def _references(actual, expected):
    if type(actual) is not list or len(actual) != len(expected):
        _invalid()
    for reference in actual:
        if type(reference) is not dict or type(reference.get('object_type')) is not str:
            _invalid()
        _keys(reference, {'object_type', 'object_id', 'version'} if reference['object_type'] == 'episode_revision'
              else {'object_type', 'object_id'})
        _uuid(reference['object_id'])
        if 'version' in reference:
            _integer(reference['version'])
    if Counter(_json(item) for item in actual) != Counter(_json(item) for item in expected):
        _invalid()


def _step(step, previous, depth):
    common = {'route', 'event_id'}
    if depth == 0:
        if type(step) is not dict:
            _invalid()
        extra = {'entity_hit'} if step.get('route') == 'entity_seed' else set()
        _keys(step, common | {'text_rank', 'vector_rank', 'text_hits', 'vector_hits'} | extra)
        if step['route'] not in {'seed', 'query_probe', 'entity_seed'} or step['text_rank'] is None and step['vector_rank'] is None:
            _invalid()
        for key in ('text_rank', 'vector_rank'):
            if step[key] is not None:
                _integer(step[key], maximum=2**31 - 1)
        try:
            validate_seed_hits(step)
            if step['route'] == 'query_probe' and (step['text_hits'] or len(step['vector_hits']) != 1):
                _invalid()
            if extra:
                from backend.app.repositories.memory.reading.sag_paths import validate_semantic_hit
                validate_semantic_hit(step['entity_hit'], 'entity_name')
                if step['text_hits'] or len(step['vector_hits']) != 1:
                    _invalid()
        except (ValueError, TypeError, KeyError):
            _invalid()
    else:
        common |= {'via_event_id', 'hop'}
        if type(step) is not dict:
            _invalid()
        route = step.get('route')
        if route == 'entity':
            _keys(step, common | {'entity_id'})
            _uuid(step['entity_id'])
        elif route == 'entity_vector':
            _keys(step, common | {'entity_id', 'entity_hit', 'vector_hits'})
            _uuid(step['entity_id'])
            try:
                from backend.app.repositories.memory.reading.sag_paths import validate_semantic_hit
                validate_semantic_hit(step['entity_hit'], 'entity_role')
                validate_seed_hits({'text_rank': None, 'text_hits': [], 'vector_rank': 1, 'vector_hits': step['vector_hits']})
            except (ValueError, TypeError, KeyError):
                _invalid()
            if step['entity_hit']['entity_id'] != step['entity_id'] or step['entity_hit']['event_id'] != previous:
                _invalid()
        elif route == 'episode':
            _keys(step, common | {'episode_id', 'from_event_id', 'to_event_id',
                                 'references'})
            for key in ('episode_id', 'from_event_id', 'to_event_id'):
                _uuid(step[key])
            if step['from_event_id'] != previous or step['to_event_id'] != step['event_id'] or previous == step['event_id']:
                _invalid()
            _references(step['references'], [
                {'object_type': 'episode_membership', 'object_id': step['from_event_id']},
                {'object_type': 'episode_membership', 'object_id': step['to_event_id']},
                {'object_type': 'episode', 'object_id': step['episode_id']},
            ])
        elif route == 'event_relation':
            _keys(step, common | {'relation_id', 'relation_type', 'from_event_id',
                                 'to_event_id', 'references'})
            for key in ('relation_id', 'from_event_id', 'to_event_id'):
                _uuid(step[key])
            if step['relation_type'] not in RELATION_TYPES or step['from_event_id'] == step['to_event_id']:
                _invalid()
            _references(step['references'], [
                {'object_type': 'event_relation', 'object_id': step['relation_id']},
            ])
        else:
            _invalid()
        _uuid(step['via_event_id'])
        if type(step['hop']) is not int or step['hop'] != depth or step['via_event_id'] != previous:
            _invalid()
    _uuid(step['event_id'])


def _payload(seen, seeds, seed_paths):
    for name, values in (('seen', seen), ('seeds', seeds)):
        if type(values) is not list:
            _invalid()
        if len(values) > MAX_IDENTITIES:
            _budget(name, MAX_IDENTITIES)
        for value in values:
            _uuid(value)
        if len(set(values)) != len(values):
            _invalid()
    if set(seen).intersection(seeds) or type(seed_paths) is not dict or set(seed_paths) != set(seeds):
        _invalid()
    chain_count = step_count = hit_count = 0
    for target, chains in seed_paths.items():
        if type(chains) is not list or not chains:
            _invalid()
        if len(chains) > MAX_CHAINS_PER_SEED:
            _budget('chains_per_seed', MAX_CHAINS_PER_SEED)
        chain_count += len(chains)
        if chain_count > MAX_CHAINS:
            _budget('path_chains', MAX_CHAINS)
        distinct = set()
        for chain in chains:
            if type(chain) is not list or not 1 <= len(chain) <= 3:
                _invalid()
            step_count += len(chain)
            if step_count > MAX_PATH_STEPS:
                _budget('path_steps', MAX_PATH_STEPS)
            previous, visited = None, set()
            for depth, step in enumerate(chain):
                _step(step, previous, depth)
                hit_count += len(step.get('text_hits', [])) + len(step.get('vector_hits', [])) + int('entity_hit' in step)
                if hit_count > MAX_PATH_HITS:
                    _budget('path_hits', MAX_PATH_HITS)
                previous = step['event_id']
                if previous in visited:
                    _invalid()
                visited.add(previous)
            if previous != target:
                _invalid()
            encoded = _json(chain)
            if encoded in distinct:
                _invalid()
            distinct.add(encoded)
    if len(_json(seed_paths)) > MAX_PATH_BYTES:
        _budget('path_bytes', MAX_PATH_BYTES)
    return {'seen': seen, 'seeds': seeds, 'seed_paths': seed_paths}


def encode(scope, seen, seeds, seed_paths):
    """Return an authenticated cursor without changing inputs, services or files.

    `seed_paths[target]` contains complete seed→target chains, never a new seed
    invented from a deferred edge. The signing key is scoped to this process.
    """
    payload = {'scope': _scope_hash(scope), **_payload(seen, seeds, seed_paths)}
    body = base64.urlsafe_b64encode(_json(payload)).rstrip(b'=').decode('ascii')
    token = body + '.' + hmac.new(_SECRET, _DOMAIN + body.encode('ascii'), hashlib.sha256).hexdigest()
    if len(token) > MAX_ENCODED_CHARACTERS:
        _budget('encoded_characters', MAX_ENCODED_CHARACTERS)
    return token


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def decode(scope, token):
    """Verify identity and structure only; the caller rechecks all live edges."""
    if type(token) is not str:
        _invalid()
    if len(token) > MAX_ENCODED_CHARACTERS:
        _budget('encoded_characters', MAX_ENCODED_CHARACTERS)
    parts = token.split('.')
    if len(parts) != 2 or not _BASE64.fullmatch(parts[0]) or not _SIGNATURE.fullmatch(parts[1]):
        _invalid()
    body, signature = parts
    expected = hmac.new(_SECRET, _DOMAIN + body.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        _invalid()
    try:
        raw = base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_', validate=True)
        if base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii') != body:
            _invalid()
        payload = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                             parse_constant=lambda value: _invalid())
    except (ValueError, TypeError, binascii.Error, UnicodeError, RecursionError):
        _invalid()
    _keys(payload, {'scope', 'seen', 'seeds', 'seed_paths'})
    if (type(payload['scope']) is not str or not _SIGNATURE.fullmatch(payload['scope'])
            or not hmac.compare_digest(payload['scope'], _scope_hash(scope))):
        _invalid()
    return _payload(payload['seen'], payload['seeds'], payload['seed_paths'])
