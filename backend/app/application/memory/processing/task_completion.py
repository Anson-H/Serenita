"""Settle generation failures against publication and current cancellation state."""
from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.errors import SerenitaError
from backend.app.repositories.memory.processing.execution import execution_scope

class MemoryTaskCompletion:
    def __init__(self,*,read_attempt,set_status):
        self.read_attempt,self.set_status=read_attempt,set_status

    def failed(self,actor,member,attempt_id,error,*,work,draft,progress):
        exc=error
        if draft is not None and draft.published:
            # The authoritative commit succeeded. A later derived-status
            # refresh cannot turn it into a failed, retryable generation.
            import logging
            logging.getLogger(__name__).exception('Post-publication memory status refresh failed')
            return {'attempt_id': attempt_id, 'status': 'completed'}
        code = getattr(exc, 'code', None) or type(exc).__name__
        if work is not None and code.startswith('MEMORY_CHECKPOINT_'):
            work.put('recovery_code', code)
            work.put('recovery_reason', getattr(exc, 'message', '检查点恢复失败。'))
        if work is not None and (isinstance(exc, OperationCancelledError) or code == 'MEMORY_FORMATION_PAUSED'):
            from backend.app.repositories.memory.processing.staging_scope import published_memory
            with published_memory():
                current = self.read_attempt(actor, member, attempt_id)
            if current['processing_status'] == 'running':
                work.put('recovery_reason', '执行已暂停，等待服务和成员设置允许后继续。')
                return {'attempt_id': attempt_id, 'status': 'running', 'recovery_status': 'interrupted'}
        # Error messages from providers may contain credentials. Retain the
        # actual class/code, with a controlled explanation only.
        if draft is not None and draft.defer_traces and not draft.published:
            try:
                from backend.app.application.memory.progress import error_details
                with execution_scope(actor, member, attempt_id):
                    progress.record({'step_id': 'commit_memory', 'parent_step_id': None,
                        'status': 'failed', **error_details(exc)})
            except SerenitaError:
                pass
        try:
            self.set_status(actor, member, attempt_id, 'failed', error_code=code,
                error_message=getattr(exc, 'message', f'后台执行因 {code} 停止。'))
        except SerenitaError:
            pass
        return {'attempt_id': attempt_id, 'status': 'failed', 'error_code': code}
