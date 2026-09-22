"""User task commands, sharing the scheduler's cancellation and execution ownership."""
from backend.app.application.memory.indexing.index_service import MemoryIndexService


class MemoryProcessingCommands:
    def __init__(self, memory, runtime):
        self.runtime = runtime
        self.index = MemoryIndexService(memory)

    def retry(self, actor, member, attempt_id, operation_id):
        attempt = self.runtime.attempt(actor, member, attempt_id)
        if attempt['task_kind'] == 'vector_index':
            return self.index.request_retry(actor, member, attempt_id, operation_id)
        return self.runtime.retry(actor, member, attempt_id, operation_id=operation_id)

    def resume(self, actor, member, attempt_id, operation_id):
        return self.runtime.resume(actor, member, attempt_id, operation_id=operation_id)

    def cancel(self, actor, member, attempt_id):
        return self.runtime.cancel(actor, member, attempt_id)
