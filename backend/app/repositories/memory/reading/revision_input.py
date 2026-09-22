"""Read exact request/result and fixed-input provenance attached to each revision."""
import json
from copy import deepcopy
from backend.app.core.errors import SerenitaError
from backend.app.core.values import strict_digest as digest


def resolve_input_cutoff(repo, db, access, data, revision_sequence):
    """Map fixed input objects to this view after draft commit renumbering.

    Original model request content remains untouched. Only the host's read
    cutoff is derived from the exact, content-checked input references.
    """
    from backend.app.domain.memory.references import object_reference
    from backend.app.domain.memory.stage_facts import project_object
    from backend.app.repositories.memory.facts.event_evidence import event_references
    from backend.app.repositories.memory.processing.staging_scope import staging
    if staging(repo) is None and not data.get('draft_scope'):
        return deepcopy(data)
    cutoff = data['record_cutoff']
    for supplied in data.get('objects', []):
        reference = object_reference(supplied)
        actual = repo._require(db, access, reference['object_type'], reference['object_id'],
            cutoff=revision_sequence - 1, version=reference.get('version'), item_id=reference.get('item_id'))
        if actual['object_type'] == 'event':
            actual['evidence'] = event_references(db, access, actual['event_id'])
        if project_object(actual) != project_object(supplied):
            raise SerenitaError('conflict', 'MEMORY_REVISION_INPUT_INVALID', '事项版本的固定输入对象与当前获授权内容不同。')
        sequence = db.execute('SELECT sequence FROM commits WHERE commit_id=?', (actual['commit_id'],)).fetchone()[0]
        cutoff = max(cutoff, sequence)
    return {**deepcopy(data), 'record_cutoff': cutoff}



def revision_input(repo, db, access, row):
    from backend.app.repositories.memory.reading.read_cache import current_read_cache, MAX_ROWS
    cache = current_read_cache(db, access)
    key = ('revision_input', row['episode_id'], row['version'])
    if cache is not None and key in cache.rows:
        return deepcopy(cache.rows[key])
    origin = db.execute('SELECT i.*, c.sequence FROM episode_revision_inputs i JOIN commits c USING(commit_id) '
        'WHERE i.account_id=? AND i.member_id=? AND i.episode_id=? AND i.version=?',
        (access.account_id, access.member_id, row['episode_id'], row['version'])).fetchone()
    if origin is None:
        raise SerenitaError('missing', 'MEMORY_REVISION_INPUT_UNAVAILABLE', '事项版本缺少明确的模型输入关联。')
    if origin['commit_id'] != row['commit_id']:
        raise SerenitaError('conflict', 'MEMORY_REVISION_INPUT_INVALID', '事项版本与输入依据必须共同追加。')
    entries = []
    for identity, kind in ((origin['request_entry_id'], 'model_request'), (origin['result_entry_id'], 'model_result')):
        entry = repo._record(db, access, 'memory_execution_entry', origin['attempt_id'], item_id=identity)
        if entry is None or entry['entry_kind'] != kind or entry['payload'].get('kind') != 'chat':
            raise SerenitaError('missing', 'MEMORY_REVISION_INPUT_UNAVAILABLE', '事项版本的模型请求或结果当前不可读取。')
        entries.append(entry)
    request, result = entries
    # Existence is not an authorization grant: the normal evidence traversal
    # rechecks each fixed input object's source permissions in this transaction.
    data = json.loads(origin['fixed_input_json'])
    output = result['payload']
    expected_step = 'revisions:' + row['trigger_event_id']
    expected_request = {'object_type':'memory_execution_entry','object_id':origin['attempt_id'],
        'item_id':origin['request_entry_id']}
    if (data.get('pipeline_stage') != 'revisions'
            or data.get('revision_event_id') != row['trigger_event_id']
            or request['payload'].get('processing_step') != expected_step
            or output.get('processing_step') != expected_step
            or output.get('request_reference') != expected_request
            or output.get('error_code') or output.get('stream_status') == 'streaming'
            or output.get('call_number') != request['payload'].get('call_number')
            or digest(data) != digest(request['payload'].get('stage_input'))
            or type(data.get('record_cutoff')) is not int
            or not 0 <= data['record_cutoff'] < request['payload'].get('draft_sequence', request['record_sequence'])
            or request['entry_sequence'] >= result['entry_sequence']
            or not request['record_sequence'] < result['record_sequence'] < origin['sequence']
            or (origin['draft_scope'] is not None and origin['draft_scope'] != origin['attempt_id'])):
        raise SerenitaError('conflict', 'MEMORY_REVISION_INPUT_INVALID', '事项版本与实际保存的阶段输入或模型结果不同。')
    # The output is read by its exact entry identity, using the common JSON parser.
    from backend.app.domain.memory.model_output import parse_json
    try:
        drafts = parse_json(output.get('content', ''))['revisions']
        fields = ('episode_id', 'trigger_event_id', 'summary', 'state', 'reason')
        valid = len(drafts) == 1 and all(drafts[0].get(field) == row[field] for field in fields)
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise SerenitaError('conflict', 'MEMORY_REVISION_INPUT_INVALID', '事项版本内容与明确关联的成功模型结果不同。')
    if origin['draft_scope'] is not None:
        data['draft_scope'] = origin['draft_scope']
    data = resolve_input_cutoff(repo, db, access, data, origin['sequence'])
    if cache is not None:
        cache.save(cache.rows, key, deepcopy(data), MAX_ROWS)
    return data


def revision_sources(data):
    from backend.app.schemas.memory.evidence import ChangeReference
    for source in data.get('change_sources', []):
        try:
            database, change, path = json.loads(source['source_key'])
            yield ChangeReference(source_database=database, change_id=change, field_path=path).model_dump()
        except (KeyError, TypeError, ValueError) as exc:
            raise SerenitaError('missing', 'MEMORY_REVISION_INPUT_UNAVAILABLE', '事项版本实际输入的来源引用无效。') from exc

