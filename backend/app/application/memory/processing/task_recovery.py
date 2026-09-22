"""Prepare fixed work snapshots and verify recovery eligibility before execution."""
from uuid import uuid4
from backend.app.core.errors import SerenitaError
from backend.app.core.values import strict_digest as digest

def fail(code,message):
    raise SerenitaError('conflict',code,message)

class MemoryTaskRecovery:
    def __init__(self,memory):
        self.memory,self.repository=memory,memory.repository

    def check_context(self, actor, member, task, work):
        snapshot = work.get('model_snapshot')
        lookup = getattr(self.memory.models, 'model_for_account', None)
        if snapshot is not None and lookup is not None and not lookup(actor, snapshot['model_id']):
            fail('MEMORY_MODEL_UNAVAILABLE', '检查点使用的模型当前不可用。')
        change = self.repository.evidence.read_changes(actor, member,
            [{key: task[key] for key in ('source_database', 'change_id')}])[0]
        source_hash = digest({key: value for key, value in change.items() if key != 'memory_status'})
        if work.get('source_hash', source_hash) != source_hash:
            fail('MEMORY_CHECKPOINT_SOURCE_CHANGED', '来源内容已变化，保留检查点，请从头重新处理。')
        work.put('source_hash', source_hash)


    def prepare(self,actor,member,task,model,*,recovering):
        from backend.app.repositories.memory.processing.checkpoints import WorkStore, inspect_work
        from backend.app.application.memory.processing.checkpoint_runtime import require_contract
        attempt_id=task['attempt_id']
        work=None
        try:
            if recovering:
                inspection = inspect_work(self.repository, actor, member, attempt_id)
                if not inspection['available']:
                    fail('MEMORY_CHECKPOINT_UNAVAILABLE', inspection['recovery_reason'])
            work = WorkStore(self.repository, actor, member, attempt_id)
            require_contract(work)
            snapshot = work.get('model_snapshot')
            if snapshot is not None:
                model = snapshot
            elif model:
                work.put('model_snapshot', model)
            self.check_context(actor, member, task, work)
            if recovering:
                from backend.app.repositories.memory.processing.checkpoints import append_recovery
                recovery_id = str(uuid4())
                append_recovery(self.repository, actor, member, attempt_id, recovery_id,
                    'auto', work.get('current_checkpoint'), work.get('retry_epoch', 0))
                work.put('active_recovery_id', recovery_id)
                work.put('recovery_reason', None)
            return work,model
        except Exception as error:
            if work is not None:
                work.put('recovery_reason',str(error))
                work.put('recovery_code',getattr(error,'code',None) or type(error).__name__)
                work.close()
            raise
