"""Translate persisted objects and declared references without leaking table metadata."""
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.values import MemoryReference
from backend.app.domain.memory.references import object_reference
from backend.app.core.values import strict_digest as digest
from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA, MEMORY_OBJECTS

def persistent_object_digest(row):
    """Only immutable table content; view-dependent projections are separate."""
    from backend.app.storage.memory.database import MEMORY_DATABASE_SCHEMA, MEMORY_OBJECTS
    table = MEMORY_DATABASE_SCHEMA.table_by_name[MEMORY_OBJECTS[row["object_type"]][0]]
    values = {"object_type": row["object_type"]}
    for column in table.columns:
        name = column.name.removesuffix("_json") if column.name.endswith("_json") else column.name
        from backend.app.domain.memory.processing_state import RUNTIME_FIELDS
        if row['object_type'] == 'processing_attempt' and name in RUNTIME_FIELDS:
            continue
        values[name] = row[name]
    return digest(values)


def reference(kind, identity, **detail):
    return MemoryReference.model_validate({'object_type': kind, 'object_id': identity, **detail}).model_dump(mode='json')


def stored_references(row):
    """Read typed dependencies for evidence traversal and graph projection."""
    values = []
    table = MEMORY_DATABASE_SCHEMA.table_by_name[MEMORY_OBJECTS[row['object_type']][0]]
    kinds = {value[0]: kind for kind, value in MEMORY_OBJECTS.items()}
    for foreign in table.foreign_keys:
        kind = kinds.get(foreign.target_table)
        fields = {target: row.get(source) for source, target in zip(foreign.columns, foreign.target_columns)}
        if kind:
            try:
                values.append((object_reference({'object_type': kind, **fields}), '/'+foreign.columns[0]))
            except (KeyError, ValueError):
                pass

    def walk(value, path):
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path+'/'+str(index))
        elif isinstance(value, dict):
            if 'object_type' in value and 'object_id' in value:
                try:
                    reference_value = MemoryReference.model_validate(value).model_dump(mode='json')
                except ValueError as exc:
                    raise SerenitaError('missing', 'MEMORY_REFERENCE_UNAVAILABLE', '记忆依据引用当前不可读取。') from exc
                values.append((reference_value, path))
            else:
                for field in ('reference', 'evidence', 'supports', 'counterevidence'):
                    if field in value:
                        walk(value[field], path+'/'+field)

    for field in ('evidence', 'counterevidence', 'supports', 'dependencies', 'target',
                  'input_references', 'result_references', 'revisions', 'entry_references'):
        if field == 'result_references' and row['object_type'] == 'processing_attempt':
            continue
        if field in row:
            walk(row[field], '/'+field)
    for field, kind in (('entity_ids', 'entity'),):
        if field == 'entity_ids' and row['object_type'] == 'event':
            continue
        values.extend((reference(kind, identity), f'/{field}/{index}') for index, identity in enumerate(row.get(field, [])))
    for field in ('items', 'names'):
        values.extend((object_reference(item), f'/{field}/{index}') for index, item in enumerate(row.get(field, []))
                      if isinstance(item, dict) and item.get('object_type') in MEMORY_OBJECTS)
    return values

