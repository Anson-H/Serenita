"""Second-brain Task2 entity resolution adapted to authorized append-only batches.

Source: task2_service/extraction/worker.py (_resolve_entity_id,
_find_existing_entity_id, _record_entity_aliases). Names use its exact normalizer.
The host prepares one readable catalog and appends the resulting rows together.
"""
from copy import deepcopy

from backend.app.application.memory.sag.entity_names import normalize_entity_name, normalize_entity_type
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import stable_memory_id


def fail(message):
    raise SerenitaError('conflict', 'MEMORY_ENTITY_IDENTITY_CONFLICT', message)


class EntityResolver:
    def __init__(self, catalog, member, operation):
        self.entities = {row['entity_id']: deepcopy(row) for row in catalog}
        self.original_ids = set(self.entities)
        self.member = member
        self.operation = operation

    def _resolve_entity_id(self, entity):
        if entity['entity_id'] is not None:
            row = self.entities.get(entity['entity_id'])
            if row is None or entity['entity_id'] not in self.original_ids:
                fail('模型选择了未提供的历史实体编号。')
            if normalize_entity_type(row['type']) != normalize_entity_type(entity['type']):
                fail('模型选择的历史实体类型不一致。')
            return row['entity_id']
        existing = self._find_existing_entity_id(entity)
        if existing is not None:
            return existing
        normalized_name = normalize_entity_name(entity['name'])
        normalized_type = normalize_entity_type(entity['type'])
        if not normalized_name or not normalized_type:
            fail('实体名称和类型必须有规范化后的文字。')
        identity = stable_memory_id(self.member, self.operation, 'entity',
            f'{normalized_type}:{normalized_name}')
        self.entities[identity] = {'entity_id': identity, 'name': entity['name'].strip(),
            'type': entity['type'].strip(), 'aliases': []}
        return identity

    def _find_existing_entity_id(self, entity):
        normalized_type = normalize_entity_type(entity['type'])
        canonical_key = normalize_entity_name(entity['name'])
        alias_keys = {key for alias in entity['aliases'] if (key := normalize_entity_name(alias))}
        if not normalized_type or not canonical_key:
            return None
        canonical_matches, alias_matches, incoming_alias_matches = set(), set(), set()
        for row in self.entities.values():
            if normalize_entity_type(row['type']) != normalized_type:
                continue
            existing_canonical_key = normalize_entity_name(row['name'])
            existing_alias_keys = {normalize_entity_name(alias) for alias in row['aliases']}
            if existing_canonical_key == canonical_key:
                canonical_matches.add(row['entity_id'])
            if canonical_key in existing_alias_keys:
                alias_matches.add(row['entity_id'])
            if alias_keys.intersection({existing_canonical_key, *existing_alias_keys}):
                incoming_alias_matches.add(row['entity_id'])
        for matches in (canonical_matches, alias_matches, incoming_alias_matches):
            if len(matches) == 1:
                return next(iter(matches))
            if len(matches) > 1:
                fail('规范名称或别名对应多个历史实体。')
        return None

    def _record_entity_aliases(self, identity, entity):
        row = self.entities[identity]
        existing_alias_keys = {normalize_entity_name(row['name']),
            *(normalize_entity_name(alias) for alias in row['aliases'])}
        added = []
        for alias in (entity['name'], *entity['aliases']):
            normalized_alias = normalize_entity_name(alias)
            if not normalized_alias or normalized_alias in existing_alias_keys:
                continue
            existing_alias_keys.add(normalized_alias)
            row['aliases'].append(alias)
            added.append(alias)
        return added


def resolve_entities(batch, repository, actor, member, operation, *, catalog=None):
    resolver = EntityResolver(entity_catalog(repository, actor, member) if catalog is None else catalog, member, operation)
    result = {}
    for index, event in batch:
        for number, mention in enumerate(event.get('entities', [])):
            identity = resolver._resolve_entity_id(mention)
            aliases = resolver._record_entity_aliases(identity, mention)
            entity = resolver.entities[identity]
            result[index, number] = {'entity': deepcopy(entity),
                'new': identity not in resolver.original_ids, 'aliases': aliases}
    references = []
    for identity in {row['entity']['entity_id'] for row in result.values()} & resolver.original_ids:
        references.append({'object_type': 'entity', 'object_id': identity})
        references.extend({'object_type': 'entity_name', 'object_id': identity, 'item_id': alias_id}
            for alias_id in resolver.entities[identity].get('_alias_ids', []))
    repository.check_references(actor, member, references)
    return result

from backend.app.repositories.memory.facts.entity_catalog import entity_catalog
