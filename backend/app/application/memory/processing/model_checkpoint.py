"""Persist completed responses and request budgets before another substep runs."""
from dataclasses import asdict
import json

from backend.app.agent_runtime.model_types import AssistantModelOutput, ToolCall
from backend.app.core.values import strict_digest as digest
from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS
from backend.app.providers.embeddings import EmbeddingResult


def request_digest(payload):
    # SQLite JSON serialization can reorder dictionaries inside the fixed
    # stage input. JSON message key order cannot identify a new model request.
    def normalized(value):
        if isinstance(value, dict):
            return {key: normalized(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalized(item) for item in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return value
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return value
    return digest(normalized(payload))


def encode_output(output, kind):
    if kind == 'chat':
        return {'content': output.content, 'reasoning': output.reasoning,
            'stop_reason': output.stop_reason, 'usage': output.usage,
            'raw_content': output.raw_content,
            'tool_calls': [asdict(call) for call in output.tool_calls]}
    return {key: getattr(output, key) for key in ('model', 'vectors', 'dimensions', 'mode', 'usage')}


def decode_output(value, kind):
    if kind == 'chat':
        return AssistantModelOutput(**{**value,
            'tool_calls': tuple(ToolCall(**call) for call in value.get('tool_calls', []))})
    return EmbeddingResult(**value)


class ModelCheckpoint:
    def __init__(self, work, step, kind, model, payload, *, occurrence=0):
        self.work, self.kind = work, kind
        self.epoch = work.get('retry_epoch', 0)
        self.key = 'model:' + digest({'step': step, 'kind': kind, 'model_id': model['model_id'],
            'payload': request_digest(payload), 'epoch': self.epoch, 'occurrence': occurrence})
        self.budget_key = 'budget:' + digest({'step': step, 'kind': kind,
            'epoch': self.epoch, 'input': request_digest(payload) if kind == 'embedding' else None})

    def cached(self):
        value = self.work.get(self.key)
        return decode_output(value['output'], self.kind) if value and value.get('status') == 'completed' else None

    def request_count(self):
        return self.work.get(self.budget_key, 0)

    def describe_error(self, error):
        count = self.request_count()
        if count:
            error.memory_request_attempt = count
            error.retry_attempts = count
            error.retry_max_attempts = MAX_MODEL_ATTEMPTS
        return error

    def start(self, payload, at):
        with self.work.transaction():
            count = self.request_count()
            if count >= MAX_MODEL_ATTEMPTS:
                raise self.describe_error(SerenitaError('invalid_input', 'MEMORY_SUBSTEP_REQUEST_LIMIT',
                    f'当前子步骤在这次重试轮次已用尽 {MAX_MODEL_ATTEMPTS} 次模型请求额度。',
                    details={'retry_attempts': count, 'retry_max_attempts': MAX_MODEL_ATTEMPTS}))
            self.work.put(self.budget_key, count + 1)
            self.work.put(self.key, {'status': 'running', 'started_at': at, 'request': payload,
                'request_number': count + 1})
        return count + 1

    def finish(self, output, at):
        if self.kind == 'chat' and not output.has_final_stop:
            self.work.put(self.key, {**self.work.get(self.key, {}), 'status': 'partial',
                'finished_at': at, 'output': encode_output(output, self.kind)})
            return
        self.work.put(self.key, {**self.work.get(self.key, {}), 'status': 'completed',
            'finished_at': at, 'output': encode_output(output, self.kind)})
