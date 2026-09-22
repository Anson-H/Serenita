"""The mutable memory processing status of one business change."""
from backend.app.domain.memory.change_scope import memory_change_fields
from backend.app.domain.memory.reception_scope import accepts_change
from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS


MEMORY_STATUSES = ('not_included', 'skipped', 'pending', 'processing', 'failed', 'completed_empty', 'generated')
FINAL_MEMORY_STATUSES = frozenset({'not_included', 'skipped', 'completed_empty', 'generated'})


def initial_memory_status(change, fields, setting):
    if (change['scope_kind'] != 'member' or change['resource_type'] not in SOURCE_REGISTRATIONS
            or not memory_change_fields(change['resource_type'], fields)):
        return 'not_included'
    return 'pending' if accepts_change(setting, change) else 'skipped'
