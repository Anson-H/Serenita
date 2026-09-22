"""Run fixed memory generation stages with durable claims and execution records."""
from contextlib import nullcontext
import time
from copy import deepcopy

from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.errors import SerenitaError
from backend.app.core import model_retry
from backend.app.core.model_retry import run_model_request, current_retry_attempt
from backend.app.application.memory.progress import model_retry_metadata, report_model_request, report_model_retry
from backend.app.schemas.memory.append import stable_memory_id


def fail(code, message, kind='conflict'):
    raise SerenitaError(kind, code, message)


from backend.app.core.time import local_now_iso
from backend.app.application.memory.progress import current_step, operation as record_operation
from backend.app.repositories.memory.processing.execution_repository import MemoryExecutionRepository


class MemoryModelRecorder:
    """Own call numbering, request receipts, response caches and the shared retry budget."""
    def __init__(self, repository, actor, member, attempt_id, *, work, token, guard, dependencies):
        self.repository, self.actor, self.member = repository, actor, member
        self.attempt_id, self.work, self.token = attempt_id, work, token
        self.guard, self.dependencies = guard, dependencies
        self.execution = MemoryExecutionRepository(repository)
        self.entry_sequence, self.calls = self.execution.positions(actor, member, attempt_id)
        self.request_occurrences = {}
        self.stage_input = None
        self.last_receipt = None

    def bind_stage_input(self, data):
        self.stage_input = deepcopy(data)

    def execution_receipt(self):
        if self.last_receipt is None:
            fail('MEMORY_REVISION_INPUT_UNAVAILABLE', '阶段缺少已完成的模型请求与结果。')
        return deepcopy(self.last_receipt)

    def entry(self, kind, payload, *, settlement=False, checked=False):
        if not settlement and not checked: self.guard()
        next_sequence = self.entry_sequence + 1
        operation = f'execution-{self.attempt_id}-{next_sequence}'
        entry_id = stable_memory_id(self.member, operation, 'execution_entry', str(next_sequence))
        from backend.app.repositories.memory.transaction import memory_operation
        with memory_operation('append_execution', attempt_id=self.attempt_id, entry_id=entry_id,
                              call_number=payload.get('call_number'), entry_kind=kind):
            self.repository.write(self.actor, self.member, operation, {'execution_entries': [{
                'attempt_id': self.attempt_id, 'entry_id': entry_id, 'entry_sequence': next_sequence, 'entry_kind': kind,
                'payload': payload,
                'dependencies': list(self.dependencies.values())}]})
        self.entry_sequence = next_sequence
        return {'object_type': 'memory_execution_entry', 'object_id': self.attempt_id, 'item_id': entry_id}

    def record_call(self, **kwargs):
        try:
            return run_model_request(lambda: self.record_call_once(**kwargs), check_running=self.guard,
                cancellation_token=self.token, on_retry=report_model_retry)
        except Exception as error:
            if self.work is not None:
                from backend.app.application.memory.processing.model_checkpoint import ModelCheckpoint
                ModelCheckpoint(self.work, current_step(), kwargs['kind'], kwargs['model'], kwargs['payload']).describe_error(error)
            raise

    def record_call_once(self, *, account_id, kind, model, payload, timeout_seconds, invoke, streaming=False):
        self.guard()
        if account_id != self.actor:
            fail('MEMORY_MODEL_ACCOUNT_SCOPE', '后台模型调用不能改变获授权的账号。', 'forbidden')
        checkpoint = None
        request_attempt = current_retry_attempt()
        if self.work is not None:
            from backend.app.application.memory.processing.model_checkpoint import ModelCheckpoint, decode_output, request_digest
            from backend.app.core.values import strict_digest as digest
            occurrence_key = digest({'step': current_step(), 'kind': kind, 'model': model['model_id'], 'payload': request_digest(payload)})
            occurrence = self.request_occurrences.get(occurrence_key, 0)
            checkpoint = ModelCheckpoint(self.work, current_step(), kind, model, payload, occurrence=occurrence)
            cached = checkpoint.cached()
            durable = self.execution.checkpoint_result(self.actor, self.member, self.attempt_id, checkpoint.key)
            if durable is not None:
                durable_payload = durable['payload']
                response = cached if cached is not None else decode_output(durable_payload['checkpoint_output'], kind)
                if kind != 'chat' or response.has_final_stop:
                    self.last_receipt = {'request': durable_payload['request_reference'], 'result': durable['reference']}
                    checkpoint.finish(response, local_now_iso())
                    self.request_occurrences[occurrence_key] = occurrence + 1
                    return response
            request_attempt = checkpoint.start(payload, local_now_iso())
        self.calls += 1
        call_number = self.calls
        retry = model_retry_metadata(request_attempt, 'running')
        started_at = local_now_iso()
        request_reference = self.entry('model_request', {'call_number': call_number, 'kind': kind, 'model_id': model['model_id'],
                                'request': payload, 'processing_step': current_step(), 'retry': retry,
                                'stage_input': deepcopy(self.stage_input),
                                'started_at': started_at}, checked=True)
        report_model_request(request_attempt, 'running')
        started = time.monotonic()
        remaining = timeout_seconds
        stream = None
        try:
            with model_retry.request_attempt_scope(request_attempt), record_operation('生成向量', {'reference': request_reference}) if kind == 'embedding' else nullcontext() as trace:
                if streaming:
                    from backend.app.application.memory.processing.model_stream import MemoryModelStream
                    stream = MemoryModelStream(self.token, remaining, started,
                        lambda fragment: self.entry('model_result', {'call_number': call_number, 'kind': kind,
                            'processing_step': current_step(), 'retry': retry, **fragment}, settlement=True))
                    output = stream.run(invoke)
                else:
                    output = invoke(remaining)
        except Exception as exc:
            exc.memory_request_attempt = request_attempt
            exc.retry_attempts = request_attempt
            exc.retry_max_attempts = model_retry.MAX_MODEL_ATTEMPTS
            self.entry('model_result', {'call_number': call_number, 'kind': kind, 'usage': None,
                **(stream.result('failed') if stream else {}),
                'started_at': started_at, 'finished_at': local_now_iso(),
                'elapsed_seconds': time.monotonic() - started, 'processing_step': current_step(),
                'retry': model_retry_metadata(request_attempt, 'cancelled' if isinstance(exc, OperationCancelledError) else 'failed'),
                'error': model_retry.error_details(exc),
                'error_type': type(exc).__name__,
                'error_cause_type': type(exc.__cause__).__name__ if exc.__cause__ else None,
                'error_code': getattr(exc, 'code', None) or type(exc).__name__}, settlement=True)
            raise
        usage = output.usage or {}
        result_payload = {'call_number': call_number, 'kind': kind, 'usage': usage,
            'request_reference': request_reference,
            'started_at': started_at, 'finished_at': local_now_iso(), 'elapsed_seconds': time.monotonic()-started,
            'processing_step': current_step(), 'retry': model_retry_metadata(request_attempt, 'completed')}
        if stream:
            result_payload.update(stream.result('completed'))
        if kind == 'chat':
            result_payload.update(stop_reason=output.stop_reason, content=output.content, reasoning=output.reasoning,
                tool_calls=[call.as_dict() for call in output.tool_calls])
        else:
            result_payload.update(dimensions=output.dimensions, vector_count=len(output.vectors), vectors=output.vectors)
        if checkpoint is not None:
            from backend.app.application.memory.processing.model_checkpoint import encode_output
            result_payload.update(checkpoint_key=checkpoint.key, checkpoint_output=encode_output(output, kind))
        result_reference = self.entry('model_result', result_payload, settlement=True)
        self.last_receipt = {'request': request_reference, 'result': result_reference}
        if checkpoint is not None:
            checkpoint.finish(output, local_now_iso())
            # Only complete responses occupy replay positions. Failed or
            # partial sends consume the durable budget, not a cache slot.
            if kind != 'chat' or output.has_final_stop:
                self.request_occurrences[occurrence_key] = occurrence + 1
        if trace is not None:
            trace['output'] = {'reference': result_reference}
        return output

    def record_stream(self, **kwargs):
        return self.record_call(**kwargs, streaming=True)

