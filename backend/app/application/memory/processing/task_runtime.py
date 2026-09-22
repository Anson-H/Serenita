"""Run fixed memory generation stages with durable claims and execution records."""
from backend.app.domain.model_capabilities import minimum_thinking_mode
from dataclasses import replace
import json
from threading import Lock

from backend.app.core.cancellation import CancellationToken
from backend.app.core.errors import SerenitaError
from backend.app.core.runtime.model_call_scope import model_call_scope, observe_model_call
from backend.app.domain.memory.execution_references import retain_memory_references
from backend.app.application.memory.formation.pipeline import MemoryPipeline
from backend.app.application.memory.evidence_scope import MemoryEvidenceScope
from backend.app.repositories.memory.processing.execution import execution_scope
from backend.app.schemas.memory.append import stable_memory_id


def fail(code, message, kind='conflict'):
    raise SerenitaError(kind, code, message)


class MemoryTaskRuntime:
    def __init__(self, memory, *, complete_model=None):
        self.memory, self.repository = memory, memory.repository
        from backend.app.application.memory.processing.tasks import MemoryProcessingService
        self.processing = MemoryProcessingService(memory)
        self.complete_model = complete_model
        self._tokens, self._tokens_lock = {}, Lock()

    def cancel_active(self):
        with self._tokens_lock:
            tokens = list(self._tokens.values())
        for token in tokens:
            token.cancel()

    def pending(self, actor, member, *, limit=20):
        """Only the earliest unfinished registration may start or recover."""
        from backend.app.repositories.memory.processing.formation_queue import formation_head, formation_guard
        from backend.app.repositories.memory.processing.checkpoints import cleanup_published_work
        with formation_guard(self.repository, actor, member) as acquired:
            if acquired:
                cleanup_published_work(self.repository, actor, member)
        task = formation_head(self.repository, actor, member) if limit > 0 else None
        if task is None:
            return []
        if task['processing_status'] in {'failed', 'cancelled'}:
            return []
        from backend.app.repositories.memory.processing.formation_queue import execution_active
        if task['processing_status'] == 'running' and execution_active(self.repository, actor, member, task['attempt_id']):
            return []
        return [task]

    def attempt(self, actor, member, attempt_id):
        return self.processing.read(actor, member, attempt_id)

    def status(self, actor, member, attempt_id, state, **values):
        attempt = self.attempt(actor, member, attempt_id)
        if attempt['processing_status'] in {'completed', 'failed', 'cancelled'}:
            return attempt
        action = self.processing.finish if state in {'completed','failed','cancelled'} else self.processing.update
        return action(actor, member, attempt, state, return_attempts=True, **values)['attempts'][0]

    def retry(self, actor, member, attempt_id, *, operation_id):
        previous = self.attempt(actor, member, attempt_id)
        if previous['task_kind'] != 'event_formation':
            fail('MEMORY_RETRY_KIND', '此入口只支持已登记的事件形成任务。')
        if previous['processing_status'] not in {'failed', 'cancelled'}:
            fail('MEMORY_RETRY_STATE', '只有失败或已取消的计算尝试可以重试。')
        eligibility = self.repository.processing.eligibility(actor, member, previous)
        if eligibility['completed_change']:
            fail('MEMORY_RETRY_STATE', '这条变更记录已经全部处理完成，不能重试。')
        if eligibility['successor']:
            fail('MEMORY_RETRY_STATE', '此处理已有后续尝试，请查看最新处理结果。')
        from backend.app.repositories.memory.processing.formation_queue import execution_guard
        with execution_guard(self.repository, actor, member, attempt_id) as acquired:
            if not acquired:
                fail('MEMORY_RETRY_ACTIVE', '前次处理仍在退出，请在其结束后重试。')
            from backend.app.repositories.memory.processing.checkpoints import discard_work
            discard_work(self.repository, actor, member, attempt_id)
            return self._followup(actor, member, previous, operation_id)

    def resume(self, actor, member, attempt_id, *, operation_id):
        from backend.app.repositories.memory.processing.checkpoints import WorkStore, inspect_work, append_recovery, read_recoveries
        from backend.app.repositories.memory.processing.formation_queue import execution_guard, formation_guard
        from backend.app.application.memory.processing.checkpoint_runtime import require_contract
        with formation_guard(self.repository, actor, member) as owned:
            if not owned:
                fail('MEMORY_RETRY_ACTIVE', '成员正在处理，请等待当前执行退出。')
            with execution_guard(self.repository, actor, member, attempt_id) as acquired:
                if not acquired:
                    fail('MEMORY_RETRY_ACTIVE', '前次处理仍在退出。')
                task = self.attempt(actor, member, attempt_id)
                done = self.repository.processing.operation_applied(actor, member, 'resume-' + operation_id)
                if done:
                    if not any(row['operation_id'] == operation_id for row in
                            read_recoveries(self.repository, actor, member, attempt_id)):
                        fail('MEMORY_RECOVERY_OPERATION_CONFLICT', '此操作标识已用于另一项继续处理操作。')
                    return task
                inspection = inspect_work(self.repository, actor, member, attempt_id)
                if not inspection['available']:
                    fail('MEMORY_CHECKPOINT_UNAVAILABLE', inspection['recovery_reason'])
                work = WorkStore(self.repository, actor, member, attempt_id)
                try:
                    command_key = 'resume:' + operation_id
                    if work.get(command_key) is not None:
                        return task
                    if task['task_kind'] != 'event_formation' or task['processing_status'] != 'failed':
                        fail('MEMORY_RESUME_STATE', '只有失败的事件形成任务可以继续处理。')
                    require_contract(work)
                    MemoryTaskRecovery(self.memory).check_context(actor, member, task, work)
                    # Prepare the new request allowance before the authoritative CAS.
                    # Repeating the same command after a crash never adds another epoch.
                    with work.transaction():
                        prepared = work.get('resume_prepared')
                        if prepared != operation_id:
                            work.put('retry_epoch', work.get('retry_epoch', 0) + 1)
                            work.put('resume_prepared', operation_id)
                            work.put('resume_checkpoint', work.get('current_checkpoint'))
                    append_recovery(self.repository, actor, member, attempt_id, operation_id,
                        'explicit', work.get('resume_checkpoint'), work.get('retry_epoch'))
                    result = self.repository.write(actor, member, 'resume-' + operation_id,
                        {'attempt_updates': [{'attempt_id': attempt_id,
                            'expected_updated_commit_id': task['updated_commit_id'],
                            'processing_status': 'running', 'resume': True}]},
                        command={'resume_attempt_id': attempt_id}, return_attempts=True)
                    work.put(command_key, {'at': self._local_time(), 'retry_epoch': work.get('retry_epoch')})
                    return result['attempts'][0]
                except SerenitaError as error:
                    work.put('recovery_code', error.code)
                    work.put('recovery_reason', error.message)
                    raise
                finally:
                    work.close()

    @staticmethod
    def _local_time():
        from backend.app.core.time import local_now
        return local_now().isoformat()


    def _followup(self, actor, member, previous, operation_id):
        attempt_id = previous['attempt_id']
        identity = stable_memory_id(member, operation_id, 'processing_attempt', attempt_id)
        data = {key: previous[key] for key in ('source_account_id', 'source_database', 'change_id', 'change_sequence', 'task_kind', 'purpose', 'target_time', 'coverage', 'input_references')}
        data.update(attempt_id=identity, previous_attempt_id=attempt_id, input_sequence=self.repository.snapshot(actor, member)['record_cutoff'])
        saved = self.repository.write(actor, member, operation_id, {'attempts': [data],
            'attempt_updates': [{'attempt_id': identity, 'processing_status': 'pending'}]},
            command={'previous_attempt_id': attempt_id}, return_attempts=True)
        return saved['attempts'][0]

    def cancel(self, actor, member, attempt_id):
        with self._tokens_lock:
            token = self._tokens.get(attempt_id)
        result = self.status(actor, member, attempt_id, 'cancelled', gaps=['用户取消了这次计算。'])
        if token:
            token.cancel()
        return result

    def run(self, actor, member, attempt_id):
        from backend.app.repositories.memory.processing.formation_queue import formation_guard, formation_head
        with formation_guard(self.repository, actor, member) as acquired:
            if not acquired:
                return {'attempt_id': attempt_id, 'status': 'queued'}
            task = self.attempt(actor, member, attempt_id)
            if task['processing_status'] in {'completed', 'failed', 'cancelled'}:
                if task['processing_status'] == 'completed':
                    from backend.app.repositories.memory.processing.checkpoints import cleanup_published_work
                    cleanup_published_work(self.repository, actor, member)
                return {'attempt_id': attempt_id, 'status': task['processing_status']}
            head = formation_head(self.repository, actor, member)
            if head is None or head['attempt_id'] != attempt_id:
                return {'attempt_id': attempt_id, 'status': 'queued'}
            return self._run(actor, member, attempt_id, task=task)

    def run_index_recovery(self, actor, member, job):
        """Resume a registered storage delivery with the execution recording."""
        from backend.app.application.memory.indexing.index_service import MemoryIndexService
        index = MemoryIndexService(self.memory)
        if job['model_account_id'] != actor:
            fail('MEMORY_MODEL_ACCOUNT_SCOPE', '索引恢复只能使用实际执行账号的模型配置。', 'forbidden')
        job = index.prepare_recovery(actor, member, job)
        if job is None:
            return {'status': 'already_claimed_or_changed'}
        model = self.memory.models.model_for_account(actor, job['model_id']) if job['model_id'] else None
        if model is None:
            # Configuration validation can close a failed attempt without a
            # model request. A concurrent configuration change must not turn
            # this path into an unrecorded provider call.
            def unavailable(**kwargs):
                fail('MEMORY_EMBEDDING_MODEL_UNAVAILABLE', '索引恢复尚未取得可用模型及执行记录。')
            with model_call_scope(unavailable):
                return index.resume_pending(actor, member, job)

        def resume(token, deadline):
            index.vector_models.cancellation_token, index.vector_models.deadline = token, deadline
            return index.resume_pending(actor, member, job)

        return self._run(actor, member, job['attempt_id'], registered_work=(job, model, resume))

    def _run(self, actor, member, attempt_id, *, registered_work=None, task=None):
        from backend.app.repositories.memory.reading.prepared_reads import prepared_read_scope
        from backend.app.repositories.memory.processing.formation_queue import execution_guard
        with execution_guard(self.repository, actor, member, attempt_id) as acquired:
            if not acquired:
                return {'attempt_id': attempt_id, 'status': 'already_running'}
            with prepared_read_scope(self.repository, actor, member):
                return self._run_prepared(actor, member, attempt_id, registered_work=registered_work, task=task)

    def _run_prepared(self, actor, member, attempt_id, *, registered_work=None, task=None):
        task = task if task is not None else self.attempt(actor, member, attempt_id)
        if task['processing_status'] == 'running' and registered_work:
            self.status(actor, member, attempt_id, 'failed', error_code='MEMORY_EXECUTION_INTERRUPTED', error_message='前次执行已中断。')
            return {'attempt_id': attempt_id, 'status': 'failed', 'error_code': 'MEMORY_EXECUTION_INTERRUPTED'}
        if task['processing_status'] not in {'pending', 'running'}:
            return {'attempt_id': attempt_id, 'status': task['processing_status']}
        work = None
        recovering = task['processing_status'] == 'running'
        model = registered_work[1] if registered_work else self.memory.models.default_model_for_account(actor, 'memory_generation')
        if not registered_work:
            try:
                work,model=MemoryTaskRecovery(self.memory).prepare(actor,member,{**task,'attempt_id':attempt_id},model,recovering=recovering)
            except Exception as error:
                code=getattr(error,'code',None) or type(error).__name__
                self.status(actor,member,attempt_id,'failed',error_code=code,
                    error_message=getattr(error,'message','检查点恢复检查失败。'))
                return {'attempt_id':attempt_id,'status':'failed','error_code':code}
        if not model:
            if work is not None:
                work.close()
            self.status(actor, member, attempt_id, 'failed', error_code='MEMORY_MODEL_UNAVAILABLE', error_message='请在默认模型中设置长期记忆生成模型。')
            return {'attempt_id': attempt_id, 'status': 'failed', 'error_code': 'MEMORY_MODEL_UNAVAILABLE'}
        try:
            claim = {'replayed': False} if recovering else self.processing.claim(actor, member, task, model_id=model['model_id'])
            if claim['replayed']:
                if work is not None:
                    work.close()
                return {'attempt_id': attempt_id, 'status': 'already_running'}
        except SerenitaError as error:
            if work is not None:
                work.close()
            if error.code in {'MEMORY_ATTEMPT_CONFLICT', 'MEMORY_OPERATION_CONFLICT'}:
                return {'attempt_id': attempt_id, 'status': 'already_running'}
            raise
        token = CancellationToken()
        with self._tokens_lock:
            self._tokens[attempt_id] = token
        scope = MemoryEvidenceScope(actor, member, attempt_id, cancellation_token=token)
        dependencies = {json.dumps({'object_type': 'processing_attempt', 'object_id': attempt_id}, sort_keys=True):
                        {'object_type': 'processing_attempt', 'object_id': attempt_id}}
        if registered_work:
            job = registered_work[0]
            dependencies['description'] = {'object_type': 'event', 'object_id': job['event_id']}
            if job['binding_id']:
                dependencies['binding'] = {'object_type': 'vector_binding', 'object_id': job['binding_id']}
        execution_model_id = model['model_id']
        source_reference = {key: task[key] for key in ('source_database', 'change_id')} if task.get('change_id') else None

        def guard():
            from backend.app.repositories.memory.processing.staging_scope import staging, published_memory
            draft = staging(self.repository)
            token.raise_if_cancelled()
            with published_memory(), self.memory.members.access_guard(actor, member, write=True):
                if self.memory.settings(actor, member)['formation_state'] != 'enabled':
                    token.cancel()
                    fail('MEMORY_FORMATION_PAUSED', '自动记忆形成已经暂停。', 'forbidden')
                current = self.repository.execution_status(actor, member, attempt_id, source_reference=source_reference)
                if current['model_id'] != execution_model_id:
                    fail('MEMORY_EXECUTION_CANCELLED', '这次后台任务的执行归属已经变化。', 'forbidden')
                if current['processing_status'] in {'cancelled', 'failed'}:
                    token.cancel()
                    fail('MEMORY_EXECUTION_CANCELLED', '这次后台任务已停止。', 'forbidden')
                references = [ref for ref in dependencies.values()
                    if not (ref['object_type'] == 'processing_attempt' and ref['object_id'] == attempt_id)
                    and (draft is None or draft.existing_reference(ref))]
                self.repository.check_references(actor, member, references)
            if draft is not None:
                self.repository.check_references(actor, member,
                    [ref for ref in dependencies.values() if not draft.existing_reference(ref)])

        def retain_references(value):
            retain_memory_references(value, dependencies)


        recorder = MemoryModelRecorder(self.repository, actor, member, attempt_id,
            work=work, token=token, guard=guard, dependencies=dependencies)

        def complete(request):
            if work is not None:
                # Rendered local clock context belongs to this fixed input.
                # Contract fingerprints separately detect prompt changes.
                key = 'system:' + str(current_step())
                system = work.get(key)
                if system is None:
                    work.put(key, request.system)
                else:
                    request = replace(request, system=system, context_sections=())
            if self.complete_model is not None:
                return observe_model_call(account_id=actor, kind='chat', model=model,
                    payload={'system': request.system, 'messages': list(request.messages)},
                    timeout_seconds=0, invoke=lambda _: self.complete_model(request))
            return self.memory.models.complete_chat_for_account(actor, model, request, minimum_thinking_mode(model), cancellation_token=token,
                timeout_seconds=0)

        complete.bind_stage_input = recorder.bind_stage_input
        complete.execution_receipt = recorder.execution_receipt
        complete.check_running = guard
        complete.extraction_model = lambda: dict(model)

        from backend.app.application.memory.progress import MemoryProgressService, observe_progress, current_step
        pipeline = None
        progress = None
        try:
            progress = MemoryProgressService(self.memory, actor, member, task)
            with execution_scope(actor, member, attempt_id), model_call_scope(recorder.record_call, stream_observer=recorder.record_stream), observe_progress(progress.record):
                if registered_work:
                    guard()
                    final_output = registered_work[2](token, scope.deadline)
                    retain_references(final_output)
                    outcome = final_output.get('status', {})
                    if isinstance(outcome, dict) and outcome.get('state') in {'confirmed', 'failed'}:
                        return {'attempt_id': attempt_id,
                            'status': 'completed' if outcome['state'] == 'confirmed' else 'failed',
                            **({'error_code': outcome['error_code']} if outcome.get('error_code') else {})}
                    fail('MEMORY_INDEX_UNCONFIRMED', '向量处理未返回成功或失败状态。')
                else:
                    from backend.app.repositories.memory.processing.staging import MemoryStaging
                    with MemoryStaging(self.repository, actor, member, attempt_id, work_store=work) as draft:
                        pipeline = MemoryPipeline(self.memory, actor, member, task, scope,
                            complete=complete, guard=guard, retain=retain_references)
                        final_output = pipeline.run()
                        guard()
                        from backend.app.application.memory.progress import report_progress
                        report_progress('commit_memory', 'running', parent_step_id='')
                        draft.defer_traces = True
                        report_progress('commit_memory', 'completed', parent_step_id='')
                        completed = self.status(actor, member, attempt_id, 'completed',
                            outcome_reason='全部阶段已成功，记忆与索引统一提交。',
                            result_references=list(pipeline.state.references.values())[:100])
                        draft.publish(check_running=guard, references=list(dependencies.values()), token=token)
                        return {'attempt_id': attempt_id, 'status': completed['processing_status']}
        except Exception as exc:
            return MemoryTaskCompletion(read_attempt=self.attempt,set_status=self.status).failed(
                actor,member,attempt_id,exc,work=work,draft=locals().get('draft'),progress=progress)
        finally:
            if work is not None:
                work.close()
            with self._tokens_lock:
                self._tokens.pop(attempt_id, None)

from backend.app.application.memory.processing.model_recorder import MemoryModelRecorder

from backend.app.application.memory.processing.task_recovery import MemoryTaskRecovery
from backend.app.application.memory.processing.task_completion import MemoryTaskCompletion
