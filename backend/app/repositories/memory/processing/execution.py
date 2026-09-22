"""Host-bound model requests and results, owned by one processing attempt."""
from contextlib import contextmanager
from contextvars import ContextVar
import json

from backend.app.core.errors import SerenitaError

_execution = ContextVar('memory_processing_attempt', default=None)
_validation = ContextVar('memory_execution_validation', default=None)


@contextmanager
def execution_validation_scope(connection):
    """Reuse immutable input reads only within this one append transaction."""
    token = _validation.set((connection, {}))
    try:
        yield
    finally:
        _validation.reset(token)


def _call_state(repo, db, access, attempt, number, cutoff):
    current = _validation.get()
    cache = current[1] if current is not None and current[0] is db else {}
    key = (access.account_id, access.member_id, attempt, number, cutoff)
    if key in cache:
        return cache[key]
    from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
    from backend.app.repositories.memory.reading.read_cache import MAX_ROWS
    from backend.app.repositories.memory.reading.read_cache import access_key
    from backend.app.repositories.memory.processing.staging_scope import staging
    prepared = prepared_reads(repo, access)
    draft = staging(repo)
    view = draft.db if draft is not None else str(repo.path_for_account(access.account_id))
    request_key = (view, *access_key(access), attempt, number)
    saved = prepared.execution_requests.get(request_key) if prepared is not None else None
    if saved is not None and saved['record_sequence'] <= cutoff:
        request = saved
    else:
        requests = db.execute('SELECT e.entry_sequence,e.payload_json,e.dependencies_json,c.sequence AS record_sequence '
            'FROM execution_entries e JOIN commits c USING(commit_id) WHERE e.attempt_id=? '
            "AND e.entry_kind='model_request' AND json_extract(e.payload_json,'$.call_number')=? "
            'AND c.sequence<=? ORDER BY e.entry_sequence LIMIT 2', (attempt, number, cutoff)).fetchall()
        if len(requests) > 1:
            fail('同一次模型调用只能登记一个请求。')
        request = ({'entry_kind': 'model_request', 'payload': json.loads(requests[0]['payload_json']),
            'dependencies': json.loads(requests[0]['dependencies_json']),
            'entry_sequence': requests[0]['entry_sequence'], 'record_sequence': requests[0]['record_sequence']}
            if requests else None)
        if request is not None and prepared is not None:
            # These rows precede the transaction cutoff and are already committed.
            prepared.save(prepared.execution_requests, request_key, request, MAX_ROWS)
    latest = db.execute('SELECT e.entry_kind,e.payload_json FROM execution_entries e JOIN commits c USING(commit_id) '
        'WHERE e.attempt_id=? AND e.entry_sequence>=? AND c.sequence<=? '
        "AND json_extract(e.payload_json,'$.call_number')=? ORDER BY e.entry_sequence DESC LIMIT 1",
        (attempt, request['entry_sequence'] if request else 0, cutoff, number)).fetchone()
    latest = {'entry_kind': latest['entry_kind'], 'payload': json.loads(latest['payload_json'])} if latest else None
    cache[key] = (request, latest)
    return request, latest


@contextmanager
def execution_scope(actor, member, attempt):
    token = _execution.set((actor, member, attempt))
    try:
        yield
    finally:
        _execution.reset(token)


def current_execution_identity():
    return _execution.get()


def fail(message, code='MEMORY_EXECUTION_SETTLEMENT_INVALID'):
    raise SerenitaError('forbidden', code, message)


def _reference_key(value):
    return tuple(value.get(key) for key in ('object_type', 'object_id', 'version', 'item_id'))


def validate_result(repo, db, access, entry, before_cutoff, earlier=()):
    number = entry.payload.get('call_number')
    if type(number) is not int or number < 1 or entry.payload.get('kind') not in {'chat','embedding'}:
        fail('模型记录必须包含实际调用标识及类型。')
    request, latest = _call_state(repo, db, access, entry.attempt_id, number, before_cutoff)
    for item in earlier:
        if item.attempt_id == entry.attempt_id and item.payload.get('call_number') == number:
            latest = item.model_dump(mode='json')
            if item.entry_kind == 'model_request':
                request = latest
    if entry.entry_kind == 'model_request':
        if request is not None or latest is not None:
            fail('同一次模型调用只能登记一个请求。')
        return
    result = latest if latest and latest['entry_kind'] == 'model_result' else None
    if request is None or (result and result['payload'].get('stream_status') != 'streaming') or request['payload'].get('kind') != entry.payload['kind']:
        fail('模型结果必须对应尚未保存结果的原模型请求。')
    state = entry.payload.get('stream_status')
    if state is not None:
        if (entry.payload['kind'] != 'chat' or request['payload'].get('request', {}).get('stream') is not True
                or state not in {'streaming', 'completed', 'failed'}):
            fail('流式结果必须来自已登记的流式生成请求。')
        expected = (result['payload']['stream_sequence'] if result else 0) + (1 if state == 'streaming' else 0)
        if type(entry.payload.get('stream_sequence')) is not int or entry.payload['stream_sequence'] != expected:
            fail('流式片段必须按实际接收顺序追加。')
        if state == 'streaming' and (not isinstance(entry.payload.get('delta'), dict) or entry.payload.get('error_code')):
            fail('流式片段必须保存实际收到的增量内容。')
    elif result:
        fail('流式调用必须保存明确的结束状态。')
    required = request['dependencies']
    supplied = {_reference_key(value.model_dump(mode='json')) for value in entry.dependencies}
    if not {_reference_key(value) for value in required} <= supplied:
        fail('模型结果不能丢弃原请求的来源依赖。')
    for reference in required:
        repo._require(db, access, reference['object_type'], reference['object_id'],
            item_id=reference.get('item_id'), version=reference.get('version'), cutoff=before_cutoff)


def execution_settlement_only(repo, db, access, batch):
    current = _execution.get()
    if current is None or not batch.execution_entries or any(getattr(batch, name) for name in type(batch).model_fields if name != 'execution_entries'):
        return False
    if current[:2] != (access.actor_account_id, access.member_id) or any(entry.attempt_id != current[2] or entry.entry_kind != 'model_result' for entry in batch.execution_entries):
        return False
    earlier = []
    try:
        for entry in sorted(batch.execution_entries, key=lambda item: item.entry_sequence):
            validate_result(repo, db, access, entry, repo._cutoff(db, access), earlier)
            earlier.append(entry)
    except SerenitaError:
        return False
    return True


def check_execution_write(repo, db, access, batch, *, settlement_only=False):
    current = _execution.get()
    if current is None:
        if batch.execution_entries or batch.processing_steps:
            fail('模型记录和步骤必须来自当前后台处理。', 'MEMORY_EXECUTION_SCOPE')
        return
    actor, member, attempt = current
    if (actor, member) != (access.actor_account_id, access.member_id):
        fail('后台处理不能改变授权范围。', 'MEMORY_EXECUTION_SCOPE')
    if any(item.attempt_id != attempt for item in [*batch.execution_entries, *batch.processing_steps]):
        fail('模型记录与步骤必须属于当前处理任务。', 'MEMORY_EXECUTION_SCOPE')
    row = db.execute('SELECT p.*, c.actor_account_id FROM processing_attempts p LEFT JOIN commits c ON c.commit_id=p.started_commit_id WHERE attempt_id=? AND p.account_id=? AND p.member_id=?',
                     (attempt, access.account_id, member)).fetchone()
    if row is None or row['actor_account_id'] != actor or row['started_commit_id'] is None:
        fail('后台处理缺少有效的执行登记。', 'MEMORY_EXECUTION_SCOPE')
    if not settlement_only and row['processing_status'] != 'running':
        fail('后台处理已结束。', 'MEMORY_EXECUTION_FINISHED')




def execution_visible(repo, db, access, row):
    claim = db.execute('SELECT c.actor_account_id FROM processing_attempts p JOIN commits c ON c.commit_id=p.started_commit_id WHERE p.attempt_id=?', (row['attempt_id'],)).fetchone()
    if claim is None or claim['actor_account_id'] != access.actor_account_id:
        return False
    from backend.app.repositories.memory.sources.source_dependencies import source_dependencies_visible
    return source_dependencies_visible(repo, access, row.get('payload', {}).get('source_dependencies', []))


def validate_execution_append(repo, db, access, batch, before_cutoff):
    from backend.app.repositories.memory.sources.source_dependencies import source_dependencies_visible
    groups = {}
    for entry in batch.execution_entries:
        if not source_dependencies_visible(repo, access, entry.payload.get('source_dependencies', [])):
            fail('模型记录所用来源当前不可访问。', 'MEMORY_EXECUTION_SOURCE_UNAVAILABLE')
        for reference in entry.dependencies:
            repo._require(db, access, reference.object_type, reference.object_id,
                item_id=reference.item_id, version=reference.version, cutoff=before_cutoff)
        groups.setdefault(entry.attempt_id, []).append(entry)
    for attempt, entries in groups.items():
        entries.sort(key=lambda entry: entry.entry_sequence)
        previous = db.execute('SELECT max(e.entry_sequence) FROM execution_entries e JOIN commits c USING(commit_id) WHERE e.attempt_id=? AND c.sequence<=?', (attempt,before_cutoff)).fetchone()[0] or 0
        if [entry.entry_sequence for entry in entries] != list(range(previous+1,previous+1+len(entries))):
            fail('模型记录必须紧接已保存序号。', 'MEMORY_EXECUTION_SEQUENCE')
        earlier = []
        for entry in entries:
            validate_result(repo, db, access, entry, before_cutoff, earlier)
            earlier.append(entry)
