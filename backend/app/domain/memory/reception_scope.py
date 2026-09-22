"""Decide reception from the latest effective settings and a business change."""
from backend.app.core.time import parse_local_datetime
from backend.app.domain.memory.sources import SOURCE_REGISTRATIONS


def accepts_change(setting, change):
    registration = SOURCE_REGISTRATIONS.get(change['resource_type'])
    if setting.get('formation_state') != 'enabled' or registration is None or change.get('scope_kind', 'member') != 'member':
        return False
    if not registration.categories.intersection(setting.get('source_categories', [])):
        return False
    enabled_at = setting.get('effective_at')
    return enabled_at is None or parse_local_datetime(change['recorded_at']) >= parse_local_datetime(enabled_at)
