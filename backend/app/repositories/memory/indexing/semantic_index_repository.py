"""SAG vector delivery metadata tied to actual, currently authorized evidence."""
from hashlib import sha256
from backend.app.domain.memory.vectors import fail
from backend.app.schemas.memory.append import canonical_uuid
from backend.app.repositories.memory.facts.entity_roles import entity_role_text
from backend.app.storage.memory.semantic_index_database import SEMANTIC_INDEX_TARGETS


# This is a query over the two current tables, not a persisted view.
_BINDINGS = "(" + " UNION ALL ".join(
    f"SELECT binding_id,account_id,member_id,entity_id,{event},{name},space_id,vector_id,text_hash,commit_id,'{kind}' AS index_kind FROM {tables[0]}"
    for kind, tables in SEMANTIC_INDEX_TARGETS.items()
    for event, name in (("NULL AS event_id", "name_id") if kind == "entity_name" else ("event_id", "NULL AS name_id"),)
) + ")"


def append_table(repo, db, access, collection, item):
    if collection == 'semantic_vector_bindings':
        if db.execute(f'SELECT 1 FROM {_BINDINGS} WHERE binding_id=? OR vector_id=?',
                (item.binding_id, item.vector_id)).fetchone():
            fail('MEMORY_SEMANTIC_IDENTITY_CONFLICT', '实体向量的绑定与向量标识必须唯一。')
        return SEMANTIC_INDEX_TARGETS[item.index_kind][0]
    binding = require_binding(repo, db, access, item.binding_id)
    return SEMANTIC_INDEX_TARGETS[binding['index_kind']][1]









def require_binding(repo, db, access, binding_id):
    row = db.execute(f'SELECT * FROM {_BINDINGS} WHERE binding_id=? AND account_id=? AND member_id=?',
        (binding_id, access.account_id, access.member_id)).fetchone()
    if row is None:
        fail('MEMORY_SEMANTIC_BINDING_UNAVAILABLE', '实体向量绑定不存在或当前不可访问。')
    row = dict(row)
    require_target(repo, db, access, row)
    return row


def require_target(repo, db, access, binding):
    """Resolve text from exact saved evidence; never reconstruct a role by name similarity."""
    entity = repo._require(db, access, 'entity', binding['entity_id'])
    if binding['index_kind'] == 'entity_name':
        if binding['name_id'] is None:
            text, basis = entity['canonical_name'], entity['event_id']
        else:
            name = repo._require(db, access, 'entity_name', binding['entity_id'], item_id=binding['name_id'])
            text, basis = name['name'], name['event_id']
        binding['event_id'] = basis
        binding['name'] = text
    else:
        event = repo._require(db, access, 'event', binding['event_id'])
        text = entity_role_text(repo, db, access, entity, event)
        binding['description'] = text
    if sha256(text.encode()).hexdigest() != binding['text_hash']:
        fail('MEMORY_SEMANTIC_TEXT_UNPROVEN', '实体索引校验值必须与实际名称或事件作用说明一致。')
    return text


def validate_semantic_index_append(repo, db, access, batch):
    checked = {}
    for item in batch.semantic_vector_bindings:
        binding = item.model_dump()
        require_target(repo, db, access, binding)
        checked[binding['binding_id']] = binding
        repo._require(db, access, 'vector_space', item.space_id)
        if not any(status.binding_id == item.binding_id and status.previous_status_id is None and status.state == 'pending'
                for status in batch.semantic_vector_statuses):
            fail('MEMORY_VECTOR_PENDING_REQUIRED', '新实体向量绑定必须共同保存待处理状态。')
    transitions = {'pending': {'confirmed', 'failed'}, 'failed': {'pending'}, 'confirmed': set()}
    for item in batch.semantic_vector_statuses:
        if item.binding_id not in checked:
            checked[item.binding_id] = require_binding(repo, db, access, item.binding_id)
        binding = checked[item.binding_id]
        if item.previous_status_id is None:
            if item.state != 'pending':
                fail('MEMORY_VECTOR_STATUS_TRANSITION', '向量初始状态必须为待处理。')
        else:
            status_table = SEMANTIC_INDEX_TARGETS[binding['index_kind']][1]
            previous = db.execute(f'SELECT state FROM {status_table} WHERE binding_id=? AND status_id=? AND account_id=? AND member_id=?',
                (item.binding_id, item.previous_status_id, access.account_id, access.member_id)).fetchone()
            if previous is None or item.state not in transitions[previous[0]]:
                fail('MEMORY_VECTOR_STATUS_TRANSITION', '实体向量状态必须沿当前允许的历史追加。')
        if item.state == 'confirmed':
            space = repo._require(db, access, 'vector_space', binding['space_id'])
            LanceSemanticVectors(repo.paths).confirm(access.account_id, access.member_id, binding, space, item.vector_hash)
    allowed = set(repo._settings(db, access)['source_categories'])
    for binding in checked.values():
        targets = [repo._require(db, access, 'event', binding['event_id']),
            repo._require(db, access, 'entity', binding['entity_id'])]
        if binding['name_id'] is not None:
            targets.append(repo._require(db, access, 'entity_name', binding['entity_id'], item_id=binding['name_id']))
        for target in targets:
            from backend.app.repositories.memory.sources.evidence import evidence_categories
            if not evidence_categories(repo,db,access,target)<=allowed:
                fail('MEMORY_SOURCE_SCOPE_DISABLED','实体索引依据不在获准形成记忆的范围。',kind='forbidden')


class MemorySemanticIndexRepository:
    def delivery_target(self, actor, member, entity_id, *, event_id=None, name_id=None):
        from backend.app.repositories.memory.facts.entity_roles import entity_role_text
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            entity = repo._require(db, access, 'entity', entity_id)
            if event_id is not None:
                if name_id is not None:
                    fail('MEMORY_SEMANTIC_TARGET_INVALID', '实体作用索引不能同时指定名称明细。')
                event = repo._require(db, access, 'event', event_id)
                text, basis, kind = entity_role_text(repo, db, access, entity, event), event['event_id'], 'entity_role'
            else:
                name = repo._require(db, access, 'entity_name', entity_id, item_id=name_id) if name_id else entity
                text, basis, kind = name.get('name', name.get('canonical_name')), name['event_id'], 'entity_name'
            return {'account_id': access.account_id, 'text': text, 'basis': basis, 'kind': kind}

    def require_targets(self, actor, member, bindings, *, formation=False):
        from backend.app.repositories.memory.sources.evidence import evidence_categories
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            setting = repo._settings(db, access)
            if formation and setting['formation_state'] != 'enabled':
                fail('MEMORY_FORMATION_NOT_ENABLED', '当前设置不允许此次向量形成。', kind='forbidden')
            for binding in bindings:
                require_target(repo, db, access, binding)
                if formation:
                    event = repo._require(db, access, 'event', binding['event_id'])
                    if not evidence_categories(repo, db, access, event) <= set(setting['source_categories']):
                        fail('MEMORY_SOURCE_SCOPE_DISABLED', '当前来源类别未获准形成记忆索引。', kind='forbidden')

    def space_exists(self, actor, member, space_id):
        with self.memory._transaction(actor, member) as (access, db):
            return db is not None and db.execute('SELECT 1 FROM vector_spaces WHERE space_id=? AND account_id=? AND member_id=?',
                (space_id, access.account_id, member)).fetchone() is not None

    def __init__(self, memory):
        self.memory = memory
        self.vectors = LanceSemanticVectors(memory.paths)

    def binding(self, actor, member, binding_id):
        """Read one binding and its current status with current source access."""
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            if db is None:
                return None
            raw = db.execute(f'SELECT b.*,c.sequence AS record_sequence,c.submitted_at FROM {_BINDINGS} b '
                'JOIN commits c USING(commit_id) WHERE b.account_id=? AND b.member_id=? AND b.binding_id=?',
                (access.account_id, member, binding_id)).fetchone()
            if raw is None:
                return None
            row = dict(raw)
            require_target(repo, db, access, row)
            table = SEMANTIC_INDEX_TARGETS[row['index_kind']][1]
            status = db.execute(f'SELECT s.*,c.submitted_at FROM {table} s JOIN commits c USING(commit_id) '
                f'WHERE s.binding_id=? AND NOT EXISTS(SELECT 1 FROM {table} n '
                'WHERE n.binding_id=s.binding_id AND n.previous_status_id=s.status_id)', (binding_id,)).fetchone()
            row['status'] = dict(status) if status else None
            row['vector_hash'] = status['vector_hash'] if status else None
            return row

    def snapshot(self, actor, member, record_cutoff=None, *, binding_ids=None, entity_ids=None, event_ids=None, index_kind=None, space_id=None):
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            cutoff = repo._cutoff(db, access, record_cutoff)
            result = {'account_id': access.account_id, 'member_id': member, 'record_cutoff': cutoff, 'bindings': [], 'excluded': 0}
            if db is None:
                return result
            from backend.app.core.errors import SerenitaError
            filters, args = [], [access.account_id, member, cutoff]
            for column, values in (('binding_id', binding_ids), ('entity_id', entity_ids)):
                if values is not None:
                    if not values:
                        return result
                    filters.append('b.' + column + ' IN (' + ','.join('?' for _ in values) + ')')
                    args.extend(values)
            for column, value in (('index_kind', index_kind), ('space_id', space_id)):
                if value is not None:
                    filters.append('b.' + column + '=?')
                    args.append(value)
            if event_ids is not None:
                if not event_ids:
                    return result
                basis = "COALESCE(b.event_id,(SELECT n.event_id FROM entity_names n WHERE n.name_id=b.name_id AND n.entity_id=b.entity_id),(SELECT e.event_id FROM entities e WHERE e.entity_id=b.entity_id))"
                filters.append(basis + ' IN (' + ','.join('?' for _ in event_ids) + ')')
                args.extend(event_ids)
            where = ''.join(' AND ' + clause for clause in filters)
            for raw in db.execute(f'SELECT b.*,c.sequence AS record_sequence, c.submitted_at FROM {_BINDINGS} b JOIN commits c USING(commit_id) WHERE b.account_id=? AND b.member_id=? AND c.sequence<=?' + where, args):
                row = dict(raw)
                try:
                    require_target(repo, db, access, row)
                except SerenitaError:
                    result['excluded'] += 1
                    continue
                status_table = SEMANTIC_INDEX_TARGETS[row['index_kind']][1]
                status = db.execute(f'SELECT s.*, c.submitted_at FROM {status_table} s JOIN commits c USING(commit_id) '
                    'WHERE s.binding_id=? AND c.sequence<=? AND NOT EXISTS '
                    f'(SELECT 1 FROM {status_table} n JOIN commits nc ON nc.commit_id=n.commit_id '
                    'WHERE n.binding_id=s.binding_id AND n.previous_status_id=s.status_id AND nc.sequence<=?)',
                    (row['binding_id'], cutoff, cutoff)).fetchone()
                row['status'] = dict(status) if status else None
                row['vector_hash'] = status['vector_hash'] if status else None
                result['bindings'].append(row)
            return result

    def search(self, actor, member, space, vector, *, index_kind, record_cutoff=None, entity_ids=None, event_ids=None):
        if index_kind not in {'entity_name', 'entity_role'}:
            fail('MEMORY_SEMANTIC_TARGET_INVALID', '未知实体索引类型。')
        entities = {canonical_uuid(value) for value in entity_ids} if entity_ids is not None else None
        descriptions = {canonical_uuid(value) for value in event_ids} if event_ids is not None else None
        snapshot = self.snapshot(actor, member, record_cutoff, entity_ids=entities, event_ids=descriptions, index_kind=index_kind, space_id=space['space_id'])
        bindings = [row for row in snapshot['bindings'] if row['index_kind'] == index_kind
            and row['space_id'] == space['space_id'] and row['status'] and row['status']['state'] == 'confirmed'
            and (entities is None or row['entity_id'] in entities)
            and (descriptions is None or row['event_id'] in descriptions)]
        hits, failures = self.vectors.search(snapshot['account_id'], member, space, vector, bindings)
        # Physical I/O is outside the authorized SQLite snapshot. Recheck the
        # exact bindings before returning names or role evidence.
        from backend.app.core.errors import SerenitaError
        needed = {row['binding_id'] for row in [*hits, *failures]}
        live = set()
        with self.memory._transaction(actor, member) as (access, db):
            for row in bindings:
                if row['binding_id'] not in needed:
                    continue
                try:
                    require_target(self.memory, db, access, row)
                    live.add(row['binding_id'])
                except SerenitaError as error:
                    if error.kind not in {'forbidden', 'missing'}:
                        raise
        return [row for row in hits if row['binding_id'] in live], [row for row in failures if row['binding_id'] in live]

from backend.app.repositories.memory.indexing.entity_vector_store import LanceSemanticVectors
