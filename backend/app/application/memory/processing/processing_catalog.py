"""Business-change pagination for the ordinary processing progress page."""
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import MemoryQuery


class MemoryProcessingCatalog:
    def __init__(self, memory):
        self.memory = memory

    def read(self, actor, member, values, *, change_keys=None, summary=False, compact=False):
        query = MemoryQuery.model_validate(values)
        if query.view != 'current':
            raise SerenitaError('invalid_input','MEMORY_PROCESSING_HISTORY_UNSUPPORTED','处理记录只保存最新情况，不能读取历史运行状态。')
        repo = self.memory.repository
        settings = self.memory.settings(actor, member)
        from backend.app.repositories.memory.processing.processing_catalog import MemoryProcessingCatalogRepository
        snapshot = MemoryProcessingCatalogRepository(repo).read_snapshot(actor, member, query,
            can_append=settings['can_append'], change_keys=change_keys, summary=summary, compact=compact)
        result, rows, selected = snapshot['result'], snapshot['rows'], snapshot['selected']
        live, successors, completed_changes = snapshot['live'], snapshot['successors'], snapshot['completed_changes']
        for row in ([] if summary else [record for group in selected for record in group['records']
                                        if record['object_type'] == 'processing_attempt']):
            from backend.app.application.memory.processing.processing_actions import project_processing_actions
            project_processing_actions(repo, actor, member, row, live=live,
                successor=row['attempt_id'] in successors,
                completed_change=row['task_kind'] == 'event_formation' and
                    (row.get('source_database'), row.get('change_id')) in completed_changes)
        if compact:
            record_fields = {'object_type', 'attempt_id', 'previous_attempt_id', 'task_kind',
                'processing_status', 'error_code', 'error_message', 'gaps', 'outcome_reason', 'result_references', 'updated_at', 'available_actions', 'checkpoint', 'recovery_status', 'recovery_reason', 'recovery_records', 'submitted_at', 'record_sequence'}
            for row in selected:
                row['records'] = [{key: value for key, value in record.items() if key in record_fields}
                    for record in row['records'] if record['object_type'] in {'processing_attempt'}]
                row['events'] = [{key: event[key] for key in ('object_type', 'event_id', 'title')} for event in row['events']]
                if row['change']:
                    row['change'].pop('fields', None)
        if summary:
            selected = [{**{key: row[key] for key in ('object_type', 'group_id', 'title', 'processing_status',
                'completed_tasks', 'total_tasks', 'event_count', 'submitted_at')},
                'change': {key: value for key, value in row['change'].items() if key != 'fields'} if row['change'] else None}
                for row in selected]
        else:
            # The fixed content was assembled outside the lock. Recheck its
            # references with current permissions before handing it to the caller.
            repo.evidence.check_visible_objects(actor, member, rows, code='MEMORY_PROCESSING_UNAVAILABLE')
        result['objects'] = selected
        return {**result, 'settings': settings, 'read_only': True}
