"""Persist received model fragments before consuming the next fragment."""
from dataclasses import asdict
from threading import Event, Timer
import time
import logging

from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.core.cancellation import CancellationToken
from backend.app.core.errors import SerenitaError
from backend.app.core.time import local_now
from backend.app.providers.responses import parse_tool_calls

_logger = logging.getLogger(__name__)


class MemoryModelStream:
    def __init__(self, parent_token, timeout, started, save):
        self.parent_token, self.timeout, self.started, self.save = parent_token, timeout, started, save
        self.content, self.reasoning, self.raw_content = [], [], []
        self.tools, self.usage = {}, {}
        self.stop_reason = None
        self.sequence = 0
        self.first_chunk_at = self.first_content_at = None

    def result(self, state):
        return {'stream_status': state, 'stream_sequence': self.sequence,
            'content': ''.join(self.content), 'reasoning': ''.join(self.reasoning),
            'raw_content': ''.join(self.raw_content), 'tool_calls': self.tool_calls(),
            'usage': self.usage, 'stop_reason': self.stop_reason,
            'first_chunk_at': self.first_chunk_at, 'first_content_at': self.first_content_at,
            'finished_at': local_now().isoformat(), 'timeout_seconds': self.timeout}

    def tool_calls(self):
        return [{'id': value['id'], 'type': 'function',
            'function': {'name': value['name'], 'arguments': value['arguments']}}
            for _, value in sorted(self.tools.items())]

    def run(self, invoke):
        token, expired = CancellationToken(), Event()
        unregister = self.parent_token.register(token.cancel)
        def expire():
            expired.set()
            token.cancel()
        timer = Timer(self.timeout, expire) if self.timeout is not None and self.timeout > 0 else None
        if timer is not None:
            timer.daemon = True
        chunks = None
        if timer is not None:
            timer.start()
        try:
            token.raise_if_cancelled()
            chunks = invoke(self.timeout, token)
            for chunk in chunks:
                received_at = local_now().isoformat()
                self.first_chunk_at = self.first_chunk_at or received_at
                if chunk.content_delta:
                    self.first_content_at = self.first_content_at or received_at
                self.content.append(chunk.content_delta)
                self.reasoning.append(chunk.reasoning_delta)
                self.raw_content.append(chunk.raw_content_delta)
                self.usage.update(chunk.usage)
                if chunk.stop_reason is not None:
                    self.stop_reason = chunk.stop_reason
                for delta in chunk.tool_call_deltas:
                    value = self.tools.setdefault(delta.index, {'id': '', 'name': '', 'arguments': ''})
                    value['id'] += delta.id
                    value['name'] += delta.name_delta
                    value['arguments'] += delta.arguments_delta
                save_started = time.monotonic()
                self.save({'stream_status': 'streaming', 'stream_sequence': self.sequence + 1,
                    'received_at': received_at, 'elapsed_seconds': time.monotonic() - self.started,
                    'delta': {**asdict(chunk), 'tool_call_deltas': [asdict(delta) for delta in chunk.tool_call_deltas]}})
                from backend.app.repositories.memory.processing.execution import current_execution_identity
                identity = current_execution_identity()
                elapsed = time.monotonic() - save_started
                _logger.log(logging.WARNING if elapsed >= 1 else logging.DEBUG, 'memory_fragment_saved %s', {
                    'attempt_id': identity[2] if identity else None, 'stream_sequence': self.sequence + 1,
                    'received_at': received_at, 'saved_at': local_now().isoformat(), 'save_seconds': elapsed})
                self.sequence += 1
                token.raise_if_cancelled()
            token.raise_if_cancelled()
            output = AssistantModelOutput(content=''.join(self.content), reasoning=''.join(self.reasoning),
                raw_content=''.join(self.raw_content), usage=self.usage,
                tool_calls=parse_tool_calls(self.tool_calls()), stop_reason=self.stop_reason or 'interrupted')
            if not output.has_final_stop:
                raise SerenitaError('invalid_structure', 'MEMORY_MODEL_STREAM_INCOMPLETE',
                    '模型输出未完整结束，已保存收到的内容。')
            return output
        except Exception as exc:
            if expired.is_set() and not self.parent_token.is_cancelled:
                raise SerenitaError('invalid_structure', 'MODEL_TIMEOUT',
                    '模型流式请求超过时限，已保存收到的内容。') from exc
            raise
        finally:
            if timer is not None:
                timer.cancel()
            unregister()
            close = getattr(chunks, 'close', None)
            if callable(close):
                close()
