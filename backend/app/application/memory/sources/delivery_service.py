"""Receive business changes for the fixed background generation pipeline."""

from backend.app.application.memory.sources.business_sources import BUSINESS_SOURCE_DATABASES
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import stable_memory_id


class MemoryDeliveryService:
    def __init__(self, memory):
        self.memory = memory
        self.repository = memory.repository


    def _new_attempt(self, actor, member, source):
        predecessor = 'initial'
        key = f"{source['source_account_id']}/{source['source_database']}/{source['change_id']}/{predecessor}"
        operation = stable_memory_id(member, 'business-delivery-attempt', 'intake_review', key)
        attempt_id = stable_memory_id(member, operation, 'processing_attempt', 'attempt')
        snapshot = self.repository.snapshot(actor, member)['record_cutoff']
        attempt = {key: source[key] for key in ('source_account_id', 'source_database', 'change_id', 'change_sequence')}
        attempt.update(attempt_id=attempt_id, previous_attempt_id=None,
                       task_kind='intake_review', purpose='交付已提交且获准读取的业务变化。',
                       input_sequence=snapshot)
        saved = self.repository.write(actor, member, operation, {'attempts': [attempt],
            'attempt_updates': [{'attempt_id': attempt_id, 'processing_status': 'pending'}]}, command={'source': {key: source[key] for key in ('source_account_id', 'source_database', 'change_id', 'change_sequence')},
                     'previous_attempt_id': None}, return_attempts=True)
        return saved['attempts'][0]

    def _status(self, actor, member, attempt, state, **fields):
        previous = attempt['updated_commit_id']
        operation = stable_memory_id(member, attempt['attempt_id'], 'delivery-status', previous + '/' + state)
        command = {'attempt_id': attempt['attempt_id'], 'expected_updated_commit_id': previous, 'processing_status': state, **fields}
        saved = self.repository.write(actor, member, operation, {'attempt_updates': [{
            **command}]},
            command=command, return_attempts=True)
        return saved['attempts'][0]

    def _deliver(self, actor, member, attempt):
        from backend.app.repositories.memory.processing.formation_queue import execution_guard
        with execution_guard(self.repository, actor, member, attempt['attempt_id']) as acquired:
            if not acquired:
                return {'change_id': attempt['change_id'], 'status': 'running'}
            if attempt['processing_status'] == 'running':
                # The previous owner has exited. Read only current task state
                # to distinguish an interruption from a stale queue snapshot.
                attempt = self.repository.read_processing_attempt(actor, member, attempt['attempt_id'])
                if attempt['processing_status'] == 'running':
                    self._failed(actor, member, attempt, 'MEMORY_EXECUTION_INTERRUPTED', '前次执行已中断。')
                    return {'change_id': attempt['change_id'], 'status': 'failed', 'reason': 'MEMORY_EXECUTION_INTERRUPTED'}
            return self._deliver_owned(actor, member, attempt)

    def _deliver_owned(self, actor, member, attempt):
        if attempt['processing_status'] == 'pending':
            attempt = self._status(actor, member, attempt, 'running')
        if attempt['processing_status'] in {'completed', 'cancelled', 'failed'}:
            return {'change_id': attempt['change_id'], 'status': attempt['processing_status']}
        try:
            receipt = self.memory.business_sources.receive(actor, member, attempt['source_database'], attempt['change_id'])
        except SerenitaError as exc:
            if exc.code in {'MEMORY_FORMATION_PAUSED', 'MEMORY_FORMATION_DISABLED'}:
                raise
            if exc.kind in {'forbidden', 'missing'}:
                self._status(actor, member, attempt, 'cancelled', gaps=[exc.message])
                return {'change_id': attempt['change_id'], 'status': 'cancelled', 'reason': exc.code}
            self._failed(actor, member, attempt, exc.code, exc.message)
            return {'change_id': attempt['change_id'], 'status': 'failed', 'reason': exc.code}
        except Exception as exc:
            # Transport failures may contain provider secrets or SQL values.
            # Their actual exception class is retained, without copying raw text.
            self._failed(actor, member, attempt, type(exc).__name__, f'业务资料交付发生 {type(exc).__name__}。')
            return {'change_id': attempt['change_id'], 'status': 'failed', 'reason': type(exc).__name__}
        self._status(actor, member, attempt, 'completed', result_references=[
            {'object_type': 'processing_attempt', 'object_id': receipt['processing_attempt']['attempt_id']}])
        return {'change_id': attempt['change_id'], 'status': 'received', 'receipt': receipt}

    def _failed(self, actor, member, attempt, code, message):
        self._status(actor, member, attempt, 'failed', error_code=code, error_message=message)

    def process_member(self, actor, member, *, limit=50):
        """Start queued deliveries and terminate interrupted work without retry."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SerenitaError('invalid_input', 'MEMORY_DELIVERY_LIMIT', '交付数量必须为 1 至 100。')
        with self.memory.members.access_guard(actor, member, write=True) as access:
            if access.permission != 'owner':
                raise SerenitaError('forbidden', 'MEMORY_DELIVERY_OWNER', '自动业务交付由档案所有者范围执行。')
            if self.memory.settings(actor, member)['formation_state'] != 'enabled':
                return {'status': 'paused', 'deliveries': []}
        latest, maxima = self.repository.processing.delivery_snapshot(actor, member)
        outcomes = []
        for attempt in latest:
            state = attempt
            if state['processing_status'] in {'completed', 'cancelled', 'failed'}:
                continue
            outcomes.append(self._deliver(actor, member, attempt))
            if len(outcomes) >= limit:
                return {'status': 'active', 'deliveries': outcomes}
        for database in BUSINESS_SOURCE_DATABASES:
            cursor = maxima.get(database, 0)
            while len(outcomes) < limit:
                page = self.memory.business_sources.catalog(actor, member, database, after_sequence=cursor, limit=min(100, limit-len(outcomes)))
                for change in page['changes']:
                    source = {**change, 'source_account_id': actor, 'source_database': database}
                    attempt = self._new_attempt(actor, member, source)
                    if attempt['processing_status'] in {'completed', 'cancelled', 'failed'}:
                        continue
                    outcomes.append(self._deliver(actor, member, attempt))
                if page['next_sequence'] is None:
                    break
                cursor = page['next_sequence']
        return {'status': 'active', 'deliveries': outcomes}
