"""Read bounded model records; decompress and assemble output outside the lock."""
import json
from contextlib import nullcontext

from backend.app.repositories.memory.reading.read_cache import access_key
from backend.app.repositories.memory.transaction import memory_operation


_KEYS = ('call_number', 'kind', 'model_id', 'processing_step', 'source_dependencies',
         'retry', 'error_code', 'stream_status', 'stream_sequence')
_METADATA = 'json_object(' + ','.join("'" + key + "',json_extract(e.payload_json,'$." + key + "')" for key in _KEYS) + ')'
_BASE = 'e.attempt_id,e.entry_id,e.entry_sequence,e.account_id,e.member_id,e.commit_id,e.dependencies_json,'


def _columns(full):
    return _BASE + ("e.payload_json," if full else '') + _METADATA + " AS metadata_json,json_extract(e.payload_json,'$.source_dependencies') AS source_dependencies_json"


def _metadata(raw):
    payload = json.loads(raw['metadata_json'])
    if payload.get('source_dependencies') is None:
        payload.pop('source_dependencies', None)
    return {'object_type': 'memory_execution_entry', **{key: raw[key] for key in
        ('attempt_id', 'entry_id', 'account_id', 'member_id', 'commit_id')},
        'dependencies': json.loads(raw['dependencies_json']), 'payload': payload}


def _status(outcome, visible):
    if not visible:
        return 'unavailable'
    if outcome and outcome.get('error_code'):
        return 'failed'
    if outcome and outcome.get('stream_status') != 'streaming':
        return 'completed'
    return 'running'


def assemble_fragments(fragments):
    """Use the same delta rules as the receiver, including tool calls and usage."""
    content, reasoning, raw_content, tools, usage = [], [], [], {}, {}
    first_chunk = first_content = stop = None
    for fragment in fragments:
        delta = fragment['delta']
        first_chunk = first_chunk or fragment['received_at']
        if delta.get('content_delta'):
            first_content = first_content or fragment['received_at']
        content.append(delta.get('content_delta', ''))
        reasoning.append(delta.get('reasoning_delta', ''))
        raw_content.append(delta.get('raw_content_delta', ''))
        usage.update(delta.get('usage', {}))
        if delta.get('stop_reason') is not None:
            stop = delta['stop_reason']
        for part in delta.get('tool_call_deltas', []):
            value = tools.setdefault(part['index'], {'index': part['index'], 'id': '', 'name_delta': '', 'arguments_delta': ''})
            for key in ('id', 'name_delta', 'arguments_delta'):
                value[key] += part.get(key, '')
    deltas = [value for _, value in sorted(tools.items())]
    return {'content': ''.join(content), 'reasoning': ''.join(reasoning), 'raw_content': ''.join(raw_content),
        'tool_call_deltas': deltas, 'tool_calls': [{'id': value['id'], 'type': 'function',
            'function': {'name': value['name_delta'], 'arguments': value['arguments_delta']}} for value in deltas],
        'usage': usage, 'stop_reason': stop, 'first_chunk_at': first_chunk, 'first_content_at': first_content}


class MemoryModelReader:
    def __init__(self, repository):
        self.repo = repository
        self._payloads = {}

    def _requests(self, db, access, attempts, detailed, entry_id=None, step=None):
        # Terminal calls before the next request can use that short range.
        # _latest also checks beyond it when requests overlap.
        from backend.app.repositories.memory.processing.request_positions import request_positions
        rows = []
        for attempt in sorted(attempts):
            positions = request_positions(self.repo, db, access, attempt)
            bounds = {identity: positions[index+1][1] if index+1 < len(positions) else 2**63-1
                      for index, (identity, _) in enumerate(positions)}
            identities = [identity for identity, _ in positions if entry_id is None or identity == entry_id]
            for start in range(0, len(identities), 500):
                batch = identities[start:start+500]
                where = " AND json_extract(e.payload_json,'$.processing_step')=?" if step else ''
                selected = db.execute('SELECT ' + _columns(detailed) + ',c.submitted_at,c.sequence AS record_sequence '
                    'FROM execution_entries e JOIN commits c USING(commit_id) WHERE e.attempt_id=? AND e.account_id=? '
                    "AND e.member_id=? AND e.entry_kind='model_request' AND e.entry_id IN (" + ','.join('?' for _ in batch) + ')' + where,
                    (attempt, access.account_id, access.member_id, *batch, *((step[0],) if step else ())))
                rows.extend({**dict(row), 'next_entry_sequence': bounds[row['entry_id']]} for row in selected)
        return sorted(rows, key=lambda row: row['record_sequence'])

    def _visible(self, db, access, raw, checked):
        # Identical dependencies in this one snapshot need one authorization
        # walk. No permission result survives this transaction.
        key = (raw['attempt_id'], raw['dependencies_json'], raw['source_dependencies_json'])
        if key not in checked:
            checked[key] = self.repo._visible(db, access, _metadata(raw))
        return checked[key]

    def _latest(self, db, request, number, detailed):
        sql = ('SELECT ' + _columns(detailed) + ' FROM execution_entries e '
            "WHERE e.attempt_id=? AND e.entry_sequence>? AND e.entry_sequence<? AND e.entry_kind='model_result' "
            "AND json_extract(e.payload_json,'$.call_number')=? ORDER BY e.entry_sequence DESC LIMIT 1")
        row = db.execute(sql, (request['attempt_id'], request['entry_sequence'], request['next_entry_sequence'], number)).fetchone()
        # A terminal result cannot be appended to. An overlapping request may
        # still have later fragments, so only a terminal record proves this bound.
        if request['next_entry_sequence'] < 2**63 - 1 and (row is None or json.loads(row['metadata_json']).get('stream_status') == 'streaming'):
            later = db.execute(sql, (request['attempt_id'], request['next_entry_sequence'], 2**63 - 1, number)).fetchone()
            row = later or row
        return dict(row) if row is not None else None

    def _decode(self, raw):
        from backend.app.storage.memory.payloads import payload_has_references
        payload = json.loads(raw['payload_json'])
        if not payload_has_references(payload, request=True):
            return payload
        scope = (raw['account_id'], raw['member_id'])
        if scope not in self._payloads:
            self._payloads[scope] = self.repo.payload_store(*scope)
        return self._payloads[scope].decode(payload, request=True)

    def _recheck(self, actor, member, scope, records, change_check=None):
        checked = {}
        with memory_operation('model_access_recheck'), self.repo._transaction(actor, member) as (access, db):
            return db is not None and (change_check is None or change_check(access, db)) and access_key(access) == scope and all(
                self._visible(db, access, row, checked) for row in records)

    def read(self, actor, member, attempts, *, entry_id=None, step=None, full=False, snapshot=None, change_check=None):
        if not attempts:
            return []
        detailed = bool(entry_id or full)
        snapshots, authorized = [], []
        if snapshot is not None and detailed:
            raise ValueError('Complete model content must be assembled outside the transaction.')
        with memory_operation('model_snapshot' if detailed else 'model_status', entry_id=entry_id), (nullcontext(snapshot) if snapshot is not None else self.repo._transaction(actor, member)) as (access, db):
            if db is None:
                return []
            if change_check is not None and not change_check(access, db):
                return []
            attempts = attempts(access, db) if callable(attempts) else attempts
            scope, checked = access_key(access), {}
            requests = self._requests(db, access, attempts, detailed, entry_id, step)
            for request in requests:
                request = dict(request)
                if not self._visible(db, access, request, checked):
                    continue
                metadata = json.loads(request['metadata_json'])
                response = self._latest(db, request, metadata['call_number'], detailed)
                visible = response is None or self._visible(db, access, response, checked)
                outcome = json.loads(response['metadata_json']) if response and visible else None
                fragments = []
                if detailed and outcome and outcome.get('stream_status') == 'streaming':
                    fragments = [dict(row) for row in db.execute('SELECT ' + _columns(True) + ' FROM execution_entries e '
                        'WHERE e.attempt_id=? AND e.entry_sequence>? AND e.entry_sequence<=? '
                        "AND e.entry_kind='model_result' AND json_extract(e.payload_json,'$.call_number')=? "
                        "AND json_extract(e.payload_json,'$.stream_status')='streaming' ORDER BY e.entry_sequence",
                        (request['attempt_id'], request['entry_sequence'], response['entry_sequence'], metadata['call_number']))]
                    visible = all(self._visible(db, access, row, checked) for row in fragments)
                records = [request, *([response] if response and visible else []), *(fragments if visible else [])]
                authorized.extend(records)
                snapshots.append((request, response, fragments, visible))
        inputs = []
        for request, response, fragments, visible in snapshots:
            payload = self._decode(request) if detailed else json.loads(request['metadata_json'])
            outcome = (self._decode(response) if detailed else json.loads(response['metadata_json'])) if response and visible else None
            if fragments and visible:
                outcome = {**outcome, **assemble_fragments([self._decode(row) for row in fragments])}
            inputs.append({'attempt_id': request['attempt_id'], 'entry_id': request['entry_id'],
                'model_id': payload['model_id'], 'kind': payload['kind'], 'call_number': payload['call_number'],
                'processing_step': payload.get('processing_step'),
                'retry': (outcome or {}).get('retry') or payload.get('retry'),
                'status': _status(outcome, visible),
                'output_revision': response['entry_id'] if response and visible else None,
                'output_entry_sequence': response['entry_sequence'] if response and visible else None,
                'error_code': (outcome or {}).get('error_code'), 'submitted_at': request['submitted_at'],
                'content': json.dumps(payload['request'], ensure_ascii=False, indent=2) if detailed else None,
                'output': outcome if detailed else None})
        if detailed and not self._recheck(actor, member, scope, authorized, change_check):
            return []
        return inputs

    def fragments(self, actor, member, attempts, entry_id, after, limit, *, change_check=None):
        empty = {'fragments': [], 'next_entry_sequence': after, 'has_more': False,
                 'status': 'unavailable', 'output_revision': None}
        if not attempts:
            return empty
        with memory_operation('model_fragments', entry_id=entry_id), self.repo._transaction(actor, member) as (access, db):
            if db is None:
                return empty
            if change_check is not None and not change_check(access, db):
                return empty
            attempts = attempts(access, db) if callable(attempts) else attempts
            scope, checked = access_key(access), {}
            requests = self._requests(db, access, attempts, False, entry_id)
            request = requests[0] if requests else None
            if request is None or not self._visible(db, access, request, checked):
                return empty
            request = dict(request)
            number = json.loads(request['metadata_json'])['call_number']
            latest = self._latest(db, request, number, False)
            if latest is not None and not self._visible(db, access, latest, checked):
                return empty
            rows = [dict(row) for row in db.execute('SELECT ' + _columns(True) + ' FROM execution_entries e WHERE e.attempt_id=? '
                "AND e.entry_sequence>? AND e.entry_sequence<=? AND e.entry_kind='model_result' "
                "AND json_extract(e.payload_json,'$.call_number')=? AND json_extract(e.payload_json,'$.stream_status')='streaming' "
                'ORDER BY e.entry_sequence LIMIT ?', (request['attempt_id'], max(after, request['entry_sequence']),
                latest['entry_sequence'] if latest else request['entry_sequence'], number, limit + 1))]
            if not all(self._visible(db, access, row, checked) for row in rows):
                return empty
        fragments = []
        for row in rows[:limit]:
            payload = self._decode(row)
            fragments.append({key: row[key] for key in ('entry_id', 'entry_sequence')} |
                {key: payload[key] for key in ('stream_sequence', 'received_at', 'delta')})
        if not self._recheck(actor, member, scope, [request, *([dict(latest)] if latest else []), *rows], change_check):
            return empty
        return {'fragments': fragments, 'next_entry_sequence': fragments[-1]['entry_sequence'] if fragments else after,
            'has_more': len(rows) > limit, 'status': _status(json.loads(latest['metadata_json']) if latest else None, True),
            'output_revision': latest['entry_id'] if latest else None}
