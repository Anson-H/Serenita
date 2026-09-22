"""Member-authorized browsing of persisted business changes."""
from backend.app.core.errors import SerenitaError
from backend.app.repositories.memory.sources.change_repository import MemoryChangeRepository
from backend.app.repositories.memory.transaction import memory_operation
from backend.app.repositories.memory.processing.model_reader import MemoryModelReader


class MemoryChangesService:
    def __init__(self, memory):
        self.memory = memory
        self.sources = memory.business_sources.sources
        self.repository = MemoryChangeRepository.for_memory(memory.repository)

    @memory_operation('change_catalog')
    def catalog(self, actor, member, cursor=None, limit=30):
        with self.memory.members.access_guard(actor, member) as access:
            try:
                page = self.repository.catalog(access, cursor, limit)
                progress = self.processing(actor, member, page['changes'], summary=True)
                return {**page, 'changes': [{**change, 'processing': progress.get((change['source_database'], change['change_id']))}
                    for change in page['changes']]}
            except ValueError as exc:
                raise SerenitaError('invalid_input', 'MEMORY_CHANGE_CURSOR_INVALID', '分页范围已改变，请刷新变更记录。') from exc

    @memory_operation('change_summaries')
    def summaries(self, actor, member, references):
        with self.memory.members.access_guard(actor, member) as access:
            rows = self.repository.summaries(access, references)
            progress = self.processing(actor, member, rows, summary=True)
            return {'changes': [{key: row[key] for key in ('source_database', 'change_id', 'memory_status')} |
                    {'processing': progress.get((row['source_database'], row['change_id']))} for row in rows]}

    @memory_operation('change_detail')
    def detail(self, actor, member, database, change_id, *, step=None, model_entry=None, results=False, status_only=False):
        with self.memory.members.access_guard(actor, member) as access:
            try:
                change = self.repository.detail(access, database, change_id, content=not status_only)
                source = self.memory.business_sources.repository.identity(access, database, change)
                allowed = self.sources.check(access, {**source, 'account_id': access.account_id, 'member_id': member})
                restricted, access_revision = self.memory.repository.evidence.source_access(actor, member, source)
                allowed = allowed and restricted
            except (LookupError, FileNotFoundError) as exc:
                raise SerenitaError('missing', 'MEMORY_CHANGE_UNAVAILABLE', '变更记录不存在或当前不可访问。') from exc
            result = {key: change[key] for key in ('change_id', 'source_database', 'resource_type', 'resource_id', 'operation_kind', 'recorded_at', 'memory_status')}
            result['content_available'] = allowed
            result['access_revision'] = access_revision
            result['targets'] = change['targets'] if allowed else []
            result['fields'] = []
            result['content_text'] = None
            if allowed and not status_only:
                result['fields'] = change['fields']
                from backend.app.domain.memory.source_markdown import source_markdown
                result['content_text'] = source_markdown(change)
            result['processing'] = self.processing(actor, member, [result]).get((database, change_id))
            result['model_inputs'] = self.model_inputs(actor, member, result['processing'], entry_id=model_entry, step=step, full=results) if allowed else []
            result['processing_steps'] = self.memory.repository.processing.read_steps(actor, member, result['processing'], step=step) if allowed else []
            if allowed:
                from backend.app.repositories.memory.sources.reception_journal import MemoryReceptionJournal
                receipts = MemoryReceptionJournal(self.memory.paths, access, database, change_id).read()
                attempts = {row['receipt_id']: row['details']['output']['processing_attempt']['attempt_id'] for row in receipts
                    if isinstance(row['details'].get('output'), dict) and row['details']['output'].get('processing_attempt')}
                if step is None:
                    receipts = [{**row, 'details': {key: value for key, value in row['details'].items() if key in {'resumed', 'timing'}}} for row in receipts]
                else:
                    receipts = [row for row in receipts if (row['step_id'], row['parent_step_id']) == step]
                result['processing_steps'] = [{
                    'attempt_id': attempts.get(row['receipt_id']), 'receipt_id': row['receipt_id'],
                    **{key:row[key] for key in ('progress_id','step_id','parent_step_id','status','details','submitted_at')},
                    'error_code':row.get('error_code'), 'error_message':row.get('error_message'), 'record_sequence':index+1,
                } for index,row in enumerate(receipts)] + result['processing_steps']
                if receipts and result['processing'] is None:
                    latest = receipts[-1]
                    result['processing'] = {'object_type':'processing_group','group_id':latest['receipt_id'],
                        'change':{**{key:result[key] for key in ('source_database','change_id','resource_type','resource_id','operation_kind','recorded_at','fields')},'title':None},'events':[],'records':[],
                        'event_count':0,'completed_tasks':0,'total_tasks':0,
                        'processing_status':latest['status'],'submitted_at':latest['submitted_at']}

            from backend.app.repositories.memory.processing.processing_results import MemoryProcessingResultsRepository
            result['extraction_results'] = MemoryProcessingResultsRepository(self.memory.repository).read(
                actor, member, result['model_inputs']) if allowed and results else []
            result['relation_results'] = MemoryProcessingResultsRepository(self.memory.repository).read_relations(
                actor, member, result['model_inputs']) if allowed and results else []
            available, revision = self._access_state(actor, member, database, change_id)
            if not available or revision != access_revision:
                result.update(content_available=False, access_revision=revision, fields=[], targets=[],
                    content_text=None, processing=None, model_inputs=[], processing_steps=[], extraction_results=[], relation_results=[])
            return result

    def _access_state(self, actor, member, database, change_id):
        with memory_operation('change_access', change_id=change_id), self.memory.members.access_guard(actor, member) as access:
            try:
                change = self.repository.detail(access, database, change_id, content=False)
                source = self.memory.business_sources.repository.identity(access, database, change)
                allowed = self.sources.check(access, {**source, 'account_id': access.account_id, 'member_id': member})
            except (LookupError, FileNotFoundError) as exc:
                raise SerenitaError('missing', 'MEMORY_CHANGE_UNAVAILABLE', '变更记录不存在或当前不可访问。') from exc
            restricted, revision = self.memory.repository.evidence.source_access(actor, member, source)
            return allowed and restricted, revision

    @memory_operation('change_status')
    def status(self, actor, member, database, change_id):
        """One metadata snapshot for polling, without detail content projections."""
        from backend.app.repositories.memory.sources.reception_journal import MemoryReceptionJournal
        repo = self.memory.repository
        allowed, revision = self._access_state(actor, member, database, change_id)
        group, inputs, steps = None, [], []
        with self.memory.members.access_guard(actor, member) as access:
            change = self.repository.detail(access, database, change_id, content=False)
            if allowed:
                group, jobs, inputs, steps, eligible, states = repo.processing.change_snapshot(
                    actor, member, database, change_id)
                successors = {row['previous_attempt_id'] for row in states}
                complete = any(row['task_kind'] == 'event_formation' and row['processing_status'] == 'completed'
                    and (row['source_database'], row['change_id']) == (database, change_id) for row in states)
                from backend.app.application.memory.processing.processing_actions import project_processing_actions
                for job in jobs:
                    project_processing_actions(repo, actor, member, job, live=eligible,
                        successor=job['attempt_id'] in successors, completed_change=complete and job['task_kind'] == 'event_formation')
                if group:
                    fields = {'object_type', 'attempt_id', 'previous_attempt_id', 'task_kind', 'processing_status',
                        'error_code', 'error_message', 'gaps', 'outcome_reason', 'result_references', 'updated_at',
                        'available_actions', 'checkpoint', 'recovery_status', 'recovery_reason', 'recovery_records', 'submitted_at', 'record_sequence'}
                    group['records'] = [{key: value for key, value in row.items() if key in fields}
                        for row in group['records'] if row['object_type'] == 'processing_attempt']
                    group['events'] = [{key: row[key] for key in ('object_type', 'event_id', 'title')} for row in group['events']]
                    group['change'].pop('fields', None)
                receipts = MemoryReceptionJournal(self.memory.paths, access, database, change_id).read()
                attempts = {row['receipt_id']: row['details']['output']['processing_attempt']['attempt_id'] for row in receipts
                    if isinstance(row['details'].get('output'), dict) and row['details']['output'].get('processing_attempt')}
                steps = [{'attempt_id': attempts.get(row['receipt_id']), 'receipt_id': row['receipt_id'],
                    **{key: row[key] for key in ('progress_id', 'step_id', 'parent_step_id', 'status', 'submitted_at')},
                    'details': {key: value for key, value in row['details'].items() if key in {'resumed', 'timing'}},
                    'error_code': row.get('error_code'), 'error_message': row.get('error_message'), 'record_sequence': index+1}
                    for index, row in enumerate(receipts)] + steps
                if receipts and group is None:
                    latest = receipts[-1]
                    group = {'object_type': 'processing_group', 'group_id': latest['receipt_id'],
                        'change': {**{key: change[key] for key in ('source_database', 'change_id', 'resource_type', 'resource_id', 'operation_kind', 'recorded_at')}, 'title': None},
                        'events': [], 'records': [], 'event_count': 0, 'completed_tasks': 0, 'total_tasks': 0,
                        'processing_status': latest['status'], 'submitted_at': latest['submitted_at']}
        current, latest_revision = self._access_state(actor, member, database, change_id)
        available = allowed and current and revision == latest_revision
        return {'memory_status': change['memory_status'], 'content_available': available, 'access_revision': latest_revision,
            'processing': group if available else None, 'model_inputs': inputs if available else [], 'processing_steps': steps if available else []}

    def _model_context(self, actor, member, database, change_id):
        """Scope selection and return authorization share the model snapshots."""
        repo = self.memory.repository
        with self.memory.members.access_guard(actor, member) as access:
            try:
                change = self.repository.detail(access, database, change_id, content=False)
                source = self.memory.business_sources.repository.identity(access, database, change)
                source = {**source, 'account_id': access.account_id, 'member_id': member}
            except (LookupError, FileNotFoundError) as exc:
                raise SerenitaError('missing', 'MEMORY_CHANGE_UNAVAILABLE', '变更记录不存在或当前不可访问。') from exc
        return repo.processing.model_context(actor, member, database, change_id, source)

    def model(self, actor, member, database, change_id, entry_id):
        attempts, check, state = self._model_context(actor, member, database, change_id)
        inputs = MemoryModelReader(self.memory.repository).read(actor, member,
            attempts, entry_id=entry_id, change_check=check)
        return {**state, 'model_inputs': inputs if state['content_available'] else []}

    def fragments(self, actor, member, database, change_id, entry_id, *, after_entry_sequence=0, limit=200):
        if type(after_entry_sequence) is not int or not 0 <= after_entry_sequence < 2**63 or type(limit) is not int or not 1 <= limit <= 1000:
            raise SerenitaError('invalid_input', 'MEMORY_FRAGMENT_RANGE_INVALID', '片段序号或每页数量无效。')
        empty = {'fragments': [], 'next_entry_sequence': after_entry_sequence, 'has_more': False,
            'status': 'unavailable', 'output_revision': None}
        attempts, check, state = self._model_context(actor, member, database, change_id)
        result = MemoryModelReader(self.memory.repository).fragments(actor, member,
            attempts, entry_id, after_entry_sequence, limit, change_check=check)
        available = state['content_available'] and result['status'] != 'unavailable'
        return {**(result if available else empty), 'content_available': available, 'access_revision': state['access_revision']}


    def model_inputs(self, actor, member, processing, *, entry_id=None, step=None, full=False):
        """Read the complete recorded model request, never reconstruct it from business data."""
        if not processing:
            return []
        attempts = {row['attempt_id'] for row in processing['records'] if row['object_type'] == 'processing_attempt'}
        return MemoryModelReader(self.memory.repository).read(actor, member, attempts, entry_id=entry_id, step=step, full=full)

    def processing(self, actor, member, changes, *, summary=False):
        if not changes:
            return {}
        from backend.app.application.memory.processing.processing_catalog import MemoryProcessingCatalog
        keys = {(change['source_database'], change['change_id']) for change in changes}
        result = MemoryProcessingCatalog(self.memory).read(actor, member, {'limit': 100}, change_keys=keys, summary=summary, compact=not summary)
        return {(row['change']['source_database'], row['change']['change_id']): row
            for row in result['objects'] if row['change'] is not None}
