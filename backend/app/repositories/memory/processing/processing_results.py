"""Read extraction commits and their current, authorized vector confirmations."""
import json
from backend.app.domain.memory.event_text import event_text

from backend.app.repositories.memory.indexing.index_repository import MemoryIndexRepository
from backend.app.repositories.memory.indexing.semantic_index_repository import MemorySemanticIndexRepository
from backend.app.repositories.memory.indexing.chunk_index_repository import MemoryChunkIndexRepository


def stage_input(item):
    request = json.loads(item['content'])
    content = next((row['content'] for row in reversed(request.get('messages', [])) if row['role'] == 'user'), '')
    if isinstance(content, list):
        content = next((block['text'] for block in content if block.get('type') == 'text'), '')
    return json.loads(content)


class MemoryProcessingResultsRepository:
    def __init__(self, repository):
        self.repo = repository

    def read_relations(self, actor, member, inputs):
        """Locate committed relations using authorized, host-recorded requests."""
        operations = {}
        for item in inputs:
            try:
                data = stage_input(item)
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and data.get('pipeline_stage') == 'event_organization' and data.get('operation_prefix'):
                operations[data['operation_prefix'] + '-organizations-'] = item['attempt_id']
        if not operations:
            return []
        repo = self.repo
        with repo._transaction(actor, member) as (access, db):
            cutoff = repo._cutoff(db, access)
            results = {}
            seen = set()
            for prefix, attempt in operations.items():
                rows = db.execute('SELECT r.relation_id, c.operation_id FROM event_relations r JOIN commits c USING(commit_id) '
                    'WHERE r.account_id=? AND r.member_id=? AND substr(c.operation_id,1,?)=? AND c.sequence<=? ORDER BY c.sequence',
                    (access.account_id, member, len(prefix), prefix, cutoff)).fetchall()
                for raw in rows:
                    if not raw['operation_id'][len(prefix):].isdigit() or raw['relation_id'] in seen:
                        continue
                    seen.add(raw['relation_id'])
                    relation = repo._record(db, access, 'event_relation', raw['relation_id'], cutoff=cutoff)
                    if not repo._visible(db, access, relation):
                        continue
                    result = results.setdefault(attempt, {'attempt_id': attempt, 'record_cutoff': cutoff, 'relations': [], 'events': []})
                    result['relations'].append(repo._project(db, access, relation, cutoff))
                    for identity in (relation['from_event_id'], relation['to_event_id']):
                        if any(event['event_id'] == identity for event in result['events']):
                            continue
                        event = repo._record(db, access, 'event', identity, cutoff=cutoff)
                        if repo._visible(db, access, event):
                            result['events'].append(repo._project(db, access, event, cutoff))
            return list(results.values())

    def read(self, actor, member, inputs):
        operations = {}
        for item in inputs:
            try:
                data = stage_input(item)
            except (ValueError, TypeError):
                continue
            meta = data.get('data', {}).get('meta', {}) if data.get('type') == 'request' else data
            if meta.get('pipeline_stage') == 'sag_extract' and meta.get('operation_prefix'):
                # The host's recorded operation prefix identifies the one atomic
                # extraction commit, including a repaired invocation's own prefix.
                operations[meta['operation_prefix'] + '-extraction-0'] = item['attempt_id']
        if not operations:
            return []
        repo = self.repo
        with repo._transaction(actor, member) as (access, db):
            cutoff = repo._cutoff(db, access)
            commits = {}
            for operation, attempt in operations.items():
                row = db.execute('SELECT commit_id FROM commits WHERE account_id=? AND member_id=? AND operation_id=? AND sequence<=?',
                    (access.account_id, member, operation, cutoff)).fetchone()
                if row:
                    commits[row['commit_id']] = attempt
            if not commits:
                return []
            snapshot = MemoryIndexRepository(repo).snapshot(actor, member, cutoff)
            events = {identity: row for identity, row in snapshot['events'].items() if row['commit_id'] in commits}
            semantic = MemorySemanticIndexRepository(repo).snapshot(actor, member, cutoff)['bindings'] if events else []
            results = {}
            for commit_id, attempt in commits.items():
                results.setdefault(attempt, {'attempt_id': attempt, 'events': [], 'entities': [], 'vectors': []})
            for identity, event in events.items():
                result = results[commits[event['commit_id']]]
                links = [row for row in snapshot['links'] if row['event_id'] == identity]
                evidence = [dict(row) for row in db.execute('SELECT source_database,change_id,field_path FROM event_evidence WHERE event_id=? AND account_id=? AND member_id=?',
                    (identity, access.account_id, member))]
                result['events'].append({**event, 'entity_ids': [row['entity_id'] for row in links], 'evidence': evidence})
                for link in links:
                    entity = snapshot['entities'][link['entity_id']]
                    current = next((row for row in result['entities'] if row['entity_id'] == entity['entity_id']), None)
                    if current is None:
                        current = {**entity, 'save_kind': 'created' if commits.get(entity['commit_id']) == result['attempt_id'] else 'reused',
                            'aliases': [], 'event_associations': []}
                        result['entities'].append(current)
                    current['event_associations'].append({'event_id': identity, 'entity_id': entity['entity_id'], 'description': link['description']})
                    current['aliases'].extend(row['name'] for row in snapshot['names'] if row['event_id'] == identity and row['entity_id'] == entity['entity_id'])
                bindings = [{**row, 'index_kind': 'event', 'content_text': event_text(event)} for row in snapshot['bindings'] if row['event_id'] == identity]
                bindings.extend({**row, 'content_text': row['name'] if row['index_kind'] == 'entity_name' else row['description']} for row in semantic if row['event_id'] == identity or row['index_kind'] == 'entity_name' and not row['name_id'] and row['entity_id'] in event_entity_ids(links))
                bindings.extend({**row, 'index_kind': 'source_chunk', 'content_text': row['content']} for row in
                    MemoryChunkIndexRepository(repo).snapshot(actor, member, cutoff, event_id=identity)['bindings'])
                for binding in bindings:
                    space = snapshot['spaces'].get(binding['space_id'])
                    if space is None:
                        continue
                    result['vectors'].append({key: binding.get(key) for key in ('binding_id', 'vector_id', 'entity_id', 'name_id', 'index_kind', 'content_text', 'space_id', 'status')} |
                        {'event_id': identity, 'model_id': space['model_id'], 'dimensions': space['dimensions']})
            return list(results.values())


def event_entity_ids(links):
    return {row['entity_id'] for row in links}
