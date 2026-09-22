"""Canonical memory object identities, independent of persistence or callers."""
from backend.app.schemas.memory.values import MemoryReference

PRIMARY_REFERENCES = {
    'event': 'event_id', 'processing_attempt': 'attempt_id', 'access_restriction': 'restriction_id',
    'memory_setting': 'setting_id', 'entity': 'entity_id', 'entity_name': 'name_id',
    'vector_space': 'space_id', 'vector_binding': 'binding_id', 'vector_status': 'status_id',
    'event_relation': 'relation_id', 'episode': 'episode_id', 'episode_revision': 'version',
    'episode_membership': 'event_id', 'memory_execution_entry': 'entry_id',
}
DETAIL_REFERENCES = {'memory_execution_entry': ('attempt_id', 'entry_id'),
    'memory_setting': ('member_id', 'setting_id'), 'entity_name': ('entity_id', 'name_id'),
    'vector_status': ('binding_id', 'status_id')}
VERSION_REFERENCES = {'episode_revision': ('episode_id', 'version')}




def reference_key(reference):
    value = reference.model_dump(mode='json') if hasattr(reference, 'model_dump') else reference
    return value['object_type'], value['object_id'], value.get('version'), value.get('item_id')


def object_reference(row):
    kind = row['object_type']
    reference = {'object_type': kind, 'object_id': row[PRIMARY_REFERENCES[kind]]}
    if kind in VERSION_REFERENCES:
        parent, field = VERSION_REFERENCES[kind]
        reference.update(object_id=row[parent], version=row[field])
    elif kind in DETAIL_REFERENCES:
        parent, detail = DETAIL_REFERENCES[kind]
        reference.update(object_id=row[parent], item_id=row[detail])
    return MemoryReference.model_validate(reference).model_dump(mode='json')
