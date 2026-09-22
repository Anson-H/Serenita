"""Project authorized records into the facts required by each generation stage."""
from copy import deepcopy


FIELDS = {
    'event': ('event_id', 'title', 'summary', 'content', 'category', 'priority',
              'occurrence_time', 'evidence'),
    'episode': ('episode_id', 'scope'),
    'episode_membership': ('event_id', 'episode_id', 'reason'),
    'episode_revision': ('episode_id', 'version', 'trigger_event_id', 'summary', 'state', 'reason'),
    'event_relation': ('relation_id', 'from_event_id', 'to_event_id', 'relation_type', 'reason'),
}


def project_object(row):
    kind = row.get('object_type')
    return {'object_type': kind, **{key: deepcopy(row[key]) for key in FIELDS[kind] if key in row}}


