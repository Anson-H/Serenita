"""Program-owned creation, claims and completion of processing attempts."""
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import stable_memory_id


class MemoryProcessingService:
    def __init__(self, memory):
        self.memory, self.repository = memory, memory.repository

    def read(self, actor, member, attempt_id):
        return self.repository.read_processing_attempt(actor, member, attempt_id)

    def create(self, actor, member, operation_id, task):
        return self.repository.write(actor, member, operation_id, {'attempts':[task]}, return_attempts=True)['attempts'][0]

    def claim(self, actor, member, task, *, model_id):
        return self.repository.write(actor, member, 'claim-'+task['attempt_id'], {'attempt_updates':[{
            'attempt_id':task['attempt_id'], 'expected_updated_commit_id':task['updated_commit_id'],
            'processing_status':'running', 'model_id':model_id}]})

    def update(self, actor, member, task, state, *, return_attempts=False, **fields):
        operation = stable_memory_id(member, task['attempt_id'], 'task-update', task['updated_commit_id']+'/'+state)
        return self.repository.write(actor, member, operation, {'attempt_updates':[{
            'attempt_id':task['attempt_id'], 'expected_updated_commit_id':task['updated_commit_id'],
            'processing_status':state, **fields}]}, return_attempts=return_attempts)

    def finish(self, actor, member, task, state, **fields):
        if state not in {'completed','failed','cancelled'}:
            raise SerenitaError('invalid_input', 'MEMORY_TASK_FINISH_STATE', '结束任务必须提供完成、失败或取消状态。')
        return self.update(actor, member, task, state, **fields)
