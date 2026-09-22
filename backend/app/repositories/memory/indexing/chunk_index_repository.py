"""SAG source_chunks with exact business-field provenance and live permissions."""
from hashlib import sha256
import json

from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.vectors import fail
from backend.app.repositories.memory.sources.evidence import read_change, change_source
from backend.app.repositories.memory.facts.event_evidence import event_references
from backend.app.schemas.memory.append import stable_memory_id
from backend.app.schemas.memory.evidence import source_key




def event_chunks(repo, db, access, event_id, *, source_parts=None):
    """Embed each complete evidenced text, preserving its actual source range."""
    from backend.app.domain.memory.source_chunks import index_fragments as fragments
    repo._require(db, access, 'event', event_id)
    result = []
    for reference in event_references(db, access, event_id):
        change = read_change(repo, access, reference, db, include_subject_names=True)
        key = (access.account_id, access.member_id, source_key(reference))
        parts = source_parts.get(key) if source_parts is not None else None
        if parts is None:
            source = change_source(change)
            parts = []
            for rank, fragment in enumerate(fragments({source['source_key']: source}), 1):
                digest = sha256(fragment['content'].encode()).hexdigest()
                identity = json.dumps([source_key(reference), fragment['character_start'], fragment['character_end'], digest], separators=(',', ':'))
                parts.append({**reference,
                    'chunk_id': stable_memory_id(access.member_id, 'sag-source-chunk', 'chunk', identity),
                    'character_start': fragment['character_start'], 'character_end': fragment['character_end'],
                    'rank': rank, 'content': fragment['content'], 'text_hash': digest})
            if source_parts is not None:
                source_parts[key] = parts
        result.extend({**part, 'event_id': event_id} for part in parts)
    if len(result) > 50:
        fail('MEMORY_CHUNK_INDEX_LIMIT', '当前事件的原文片段超过单次索引预算。')
    return result


def require_chunk(repo, db, access, binding):
    reference = {key: binding[key] for key in ('source_database', 'change_id', 'field_path')}
    repo._require(db, access, 'event', binding['event_id'])
    if reference not in event_references(db, access, binding['event_id']):
        fail('MEMORY_CHUNK_SOURCE_UNPROVEN', '原文片段必须引用该事件的实际业务变更字段。')
    change = read_change(repo, access, reference, db, include_subject_names=True)
    # A persisted vector's signed text is immutable derived content. Read that
    # exact text rather than regenerating it with today's prose formatter.
    space = repo._require(db, access, 'vector_space', binding['space_id'])
    vectors = LanceSourceChunks(repo.paths)
    content = None
    for row in vectors.rows(access.account_id, space, binding['vector_id']):
        text = row.get('content')
        if (isinstance(text, str) and sha256(text.encode()).hexdigest() == binding['text_hash']
                and len(text) == binding['character_end'] - binding['character_start']
                and all(row.get(key) == value for key, value in
                    vectors.expected(access.account_id, access.member_id, {**binding, 'content': text}, space).items())):
            content = text
            break
    if content is None:
        source = change_source(change)
        content = source['content_text'][binding['character_start']:binding['character_end']]
        if binding['character_end'] > len(source['content_text']):
            fail('MEMORY_CHUNK_TEXT_MISMATCH', '原文片段范围超出实际文本。')
    if not content.strip() or sha256(content.encode()).hexdigest() != binding['text_hash']:
        fail('MEMORY_CHUNK_TEXT_MISMATCH', '原文片段范围或文字校验值与实际字段不符。')
    identity = json.dumps([source_key(reference), binding['character_start'], binding['character_end'], binding['text_hash']], separators=(',', ':'))
    if stable_memory_id(access.member_id, 'sag-source-chunk', 'chunk', identity) != binding['chunk_id']:
        fail('MEMORY_CHUNK_IDENTITY_MISMATCH', '原文片段标识与实际来源及范围不一致。')
    return {**binding, 'content': content}


def require_binding(repo, db, access, binding_id):
    row = db.execute('SELECT * FROM source_chunks WHERE binding_id=? AND account_id=? AND member_id=?',
        (binding_id, access.account_id, access.member_id)).fetchone()
    if row is None:
        fail('MEMORY_CHUNK_BINDING_UNAVAILABLE', '原文片段向量绑定不存在或当前不可访问。')
    return require_chunk(repo, db, access, dict(row))


def validate_chunk_index_append(repo, db, access, batch):
    checked, event_parts, source_parts = {}, {}, {}
    for item in batch.chunk_vector_bindings:
        actual = require_chunk(repo, db, access, item.model_dump())
        checked[item.binding_id] = actual
        if item.event_id not in event_parts:
            event_parts[item.event_id] = event_chunks(repo, db, access, item.event_id, source_parts=source_parts)
        # A new binding must select a complete input text and its actual rank.
        if not any(all(actual[key] == part[key] for key in part) for part in event_parts[item.event_id]):
            fail('MEMORY_CHUNK_RANGE_INVALID', '原文片段必须采用完整输入文本的实际范围和顺序。')
        repo._require(db, access, 'vector_space', item.space_id)
        if not any(row.binding_id == item.binding_id and row.previous_status_id is None and row.state == 'pending'
                for row in batch.chunk_vector_statuses):
            fail('MEMORY_VECTOR_PENDING_REQUIRED', '新原文片段绑定必须同时追加待处理状态。')
    transitions = {'pending': {'confirmed', 'failed'}, 'failed': {'pending'}, 'confirmed': set()}
    for item in batch.chunk_vector_statuses:
        if item.binding_id not in checked:
            checked[item.binding_id] = require_binding(repo, db, access, item.binding_id)
        binding = checked[item.binding_id]
        if item.previous_status_id is None:
            if item.state != 'pending':
                fail('MEMORY_VECTOR_STATUS_TRANSITION', '原文片段向量初始状态必须为待处理。')
        else:
            previous = db.execute('SELECT state FROM source_chunk_statuses WHERE binding_id=? AND status_id=?',
                (item.binding_id, item.previous_status_id)).fetchone()
            if previous is None or item.state not in transitions[previous[0]]:
                fail('MEMORY_VECTOR_STATUS_TRANSITION', '原文片段向量状态必须沿允许的历史追加。')
        if item.state == 'confirmed':
            space = repo._require(db, access, 'vector_space', binding['space_id'])
            LanceSourceChunks(repo.paths).confirm(access.account_id, access.member_id, binding, space, item.vector_hash)
    allowed = repo._settings(db, access)['source_categories']
    for binding in checked.values():
        reference = {key: binding[key] for key in ('source_database', 'change_id', 'field_path')}
        if read_change(repo, access, reference, db)['source_category'] not in allowed:
            fail('MEMORY_SOURCE_SCOPE_DISABLED', '原文片段来源不在获准形成记忆的范围。', kind='forbidden')


class MemoryChunkIndexRepository:
    def event_chunks(self, actor, member, event_id, *, source_parts=None):
        with self.memory._transaction(actor, member) as (access, db):
            return event_chunks(self.memory, db, access, event_id, source_parts=source_parts)

    def __init__(self, memory):
        self.memory, self.vectors = memory, LanceSourceChunks(memory.paths)

    def snapshot(self, actor, member, record_cutoff=None, *, event_id=None, binding_ids=None):
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            cutoff = repo._cutoff(db, access, record_cutoff)
            result = {'account_id': access.account_id, 'member_id': member, 'record_cutoff': cutoff, 'bindings': []}
            if db is None:
                return result
            query = 'SELECT b.* FROM source_chunks b JOIN commits c USING(commit_id) WHERE b.account_id=? AND b.member_id=? AND c.sequence<=?'
            args = [access.account_id, member, cutoff]
            if binding_ids is not None:
                if not binding_ids:
                    return result
                query += ' AND b.binding_id IN (' + ','.join('?' for _ in binding_ids) + ')'
                args.extend(binding_ids)
            if event_id is not None:
                event = repo._record(db, access, 'event', event_id, cutoff=cutoff)
                if not repo._visible(db, access, event):
                    fail('MEMORY_CHUNK_SOURCE_UNPROVEN', '事件在指定记录截点不可读取。', kind='missing')
                query += (' AND EXISTS (SELECT 1 FROM event_evidence e JOIN commits ec ON ec.commit_id=e.commit_id WHERE e.event_id=? '
                    'AND e.account_id=b.account_id AND e.member_id=b.member_id AND e.source_database=b.source_database '
                    'AND e.change_id=b.change_id AND e.field_path=b.field_path AND ec.sequence<=?)')
                args.extend((event_id, cutoff))
            for raw in db.execute(query, args):
                try:
                    row = require_chunk(repo, db, access, dict(raw))
                except SerenitaError:
                    continue
                status = db.execute('SELECT s.*, c.submitted_at FROM source_chunk_statuses s JOIN commits c USING(commit_id) '
                    'WHERE s.binding_id=? AND c.sequence<=? AND NOT EXISTS (SELECT 1 FROM source_chunk_statuses n '
                    'JOIN commits nc ON nc.commit_id=n.commit_id WHERE n.binding_id=s.binding_id '
                    'AND n.previous_status_id=s.status_id AND nc.sequence<=?)', (row['binding_id'], cutoff, cutoff)).fetchone()
                row.update(status=dict(status) if status else None, vector_hash=status['vector_hash'] if status else None)
                result['bindings'].append(row)
            return result

    def search(self, actor, member, space, vector, *, record_cutoff=None, event_id=None):
        snapshot = self.snapshot(actor, member, record_cutoff, event_id=event_id)
        bindings = [row for row in snapshot['bindings'] if row['space_id'] == space['space_id'] and row['status'] and row['status']['state'] == 'confirmed']
        hits, failures = self.vectors.search(snapshot['account_id'], member, space, vector, bindings)
        from backend.app.repositories.memory.sources.evidence import check_change
        needed = {row['binding_id'] for row in [*hits, *failures]}
        visible = set()
        with self.memory._transaction(actor, member) as (access, db):
            for row in bindings:
                if row['binding_id'] not in needed:
                    continue
                try:
                    self.memory._require(db, access, 'event', row['event_id'], cutoff=snapshot['record_cutoff'])
                    check_change(self.memory, access, {key: row[key] for key in ('source_database', 'change_id', 'field_path')}, db)
                    visible.add(row['binding_id'])
                except SerenitaError as error:
                    if error.kind not in {'forbidden', 'missing'}:
                        raise
        return [row for row in hits if row['binding_id'] in visible], [row for row in failures if row['binding_id'] in visible]

from backend.app.repositories.memory.indexing.source_vector_store import LanceSourceChunks
