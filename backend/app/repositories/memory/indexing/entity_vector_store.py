"""Physical entity-name and event-role vectors with verified target identity."""
from backend.app.repositories.memory.indexing.vector_store import LanceVectors
from backend.app.domain.memory.vectors import fail

class LanceEntityVectors(LanceVectors):
    index_name = 'entity_vectors'
    vector_field = 'vector'
    string_fields = (LanceVectors.identity_fields
        + tuple((key, nullable) for key, nullable in LanceVectors.reference_fields if key != 'event_id')
        + (('entity_id', False), ('event_id', False), ('name_id', True))
        + LanceVectors.metadata_fields + (('name', False),))

    @staticmethod
    def expected(account_id, member_id, binding, space):
        values = LanceVectors.expected(account_id, member_id, binding, space)
        return {**values, **{key: binding[key] for key in ('entity_id', 'event_id', 'name_id')},
            'name': binding['name']}


class LanceEventEntityVectors(LanceVectors):
    index_name = 'event_entity_vectors'
    vector_field = 'vector'
    string_fields = (LanceVectors.identity_fields + LanceVectors.reference_fields
        + (('entity_id', False),)
        + LanceVectors.metadata_fields + (('description', False),))

    @staticmethod
    def expected(account_id, member_id, binding, space):
        return {**LanceVectors.expected(account_id, member_id, binding, space),
            'entity_id': binding['entity_id'],
            'description': binding['description']}


class LanceSemanticVectors:
    """Dispatch the two SAG entity indexes by their declared target kind."""
    def __init__(self, paths):
        self.indexes = {'entity_name': LanceEntityVectors(paths), 'entity_role': LanceEventEntityVectors(paths)}

    def _index(self, kind):
        if kind not in self.indexes:
            fail('MEMORY_SEMANTIC_TARGET_INVALID', '未知实体索引类型。')
        return self.indexes[kind]

    def binding_guard(self, *args, **kwargs):
        return self.indexes['entity_name'].binding_guard(*args, **kwargs)

    def rows(self, account, space, vector_id, *, index_kind):
        return self._index(index_kind).rows(account, space, vector_id)

    def confirm(self, account, member, binding, space, vector_hash):
        return self._index(binding['index_kind']).confirm(account, member, binding, space, vector_hash)

    def verify(self, account, member, binding, space, vector_hash):
        return self._index(binding['index_kind']).verify(account, member, binding, space, vector_hash)

    def verify_row(self, account, member, binding, space, vector_hash, row):
        return self._index(binding['index_kind']).verify_row(account, member, binding, space, vector_hash, row)

    def add(self, account, member, binding, space, vector):
        return self._index(binding['index_kind']).add(account, member, binding, space, vector)

    def verify_many(self, account, member, bindings, space):
        if len({row['binding_id'] for row in bindings}) != len(bindings):
            raise ValueError('Exact binding verification requires unique binding identities')
        verified, failures = {}, []
        for kind in dict.fromkeys(row['index_kind'] for row in bindings):
            rows = [row for row in bindings if row['index_kind'] == kind]
            actual, errors = self._index(kind).verify_many(account, member, rows, space)
            verified.update(actual)
            failures.extend(errors)
        return verified, failures

    def search(self, account, member, space, vector, bindings):
        hits, failures = [], []
        for kind in dict.fromkeys(row['index_kind'] for row in bindings):
            rows = [row for row in bindings if row['index_kind'] == kind]
            actual, errors = self._index(kind).search(account, member, space, vector, rows)
            hits.extend(actual)
            failures.extend(errors)
        return sorted(hits, key=lambda row: (-row['score'], row['binding_id'])), failures

