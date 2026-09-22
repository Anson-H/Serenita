"""Retain exact references actually returned to a running memory task."""
import json

from backend.app.core.tabular_json import decode_tabular_json
from backend.app.schemas.memory.values import MemoryReference
from backend.app.schemas.memory.values import OBJECT_TYPES


def retain_memory_references(value, dependencies):
    value = decode_tabular_json(value)
    if isinstance(value, list):
        for child in value:
            retain_memory_references(child, dependencies)
    elif isinstance(value, dict):
        if value.get('object_type') in OBJECT_TYPES:
            from backend.app.domain.memory.references import object_reference
            try:
                ref = value if 'object_id' in value else object_reference(value)
                ref = MemoryReference.model_validate({key: ref[key] for key in
                    ('object_type', 'object_id', 'version', 'item_id') if key in ref}).model_dump(mode='json', exclude_none=True)
                dependencies[json.dumps(ref, sort_keys=True)] = ref
            except (ValueError, KeyError):
                pass
        for child in value.values():
            if isinstance(child, (dict, list)):
                retain_memory_references(child, dependencies)


