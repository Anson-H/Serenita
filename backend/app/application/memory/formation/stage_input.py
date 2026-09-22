"""Prepare the exact model-visible input from authorized memory facts."""
from copy import deepcopy
from backend.app.domain.memory.stage_facts import FIELDS, project_object

def stage_input(data):
    """Keep source texts, factual limits and exact evidence IDs; omit host bookkeeping."""
    objects = [project_object(row) for row in data['objects'] if row.get('object_type') in FIELDS]
    sources = {}
    for row in data['change_sources']:
        sources[row['source_key']] = {key: deepcopy(row[key]) for key in
            ('source_key', 'source_database', 'change_id', 'resource_type', 'operation_kind',
             'recorded_at', 'content_text') if key in row}
    from backend.app.application.memory.sag.adapter import extraction_coverage
    return {
        **{key: deepcopy(data[key]) for key in ('pipeline_stage', 'new_event_ids', 'record_cutoff',
            'operation_prefix', 'revision_event_id', 'organization_event_id', 'selected_episode_id', 'validation_errors', 'previous_output') if key in data},
        'objects': objects, 'change_sources': list(sources.values()),
        'coverage': extraction_coverage(data.get('coverage', [])),
        'retrieval': {'episode_event_ids': deepcopy(data['retrieval'].get('episode_event_ids', {}))},
    }
