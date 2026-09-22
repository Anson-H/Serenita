"""Ephemeral, evidence-checked eligibility for complete-population statistics."""
from backend.app.domain.model_capabilities import minimum_thinking_mode
import json
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.core.errors import SerenitaError
from backend.app.providers.errors import ProviderChatCompletionError

MAX_JUDGED_EVENTS = 256
BATCH_SIZE = 16
MAX_SOURCE_CHARACTERS = 32000


class MemoryExperienceService:
    def __init__(self, memory, *, complete_model=None):
        self.memory, self.complete_model = memory, complete_model

    def _inputs(self, actor, member, events, cutoff):
        inputs = self.memory.repository.evidence.event_sources(actor, member, events, cutoff)
        return [row for row in inputs if sum(len(source['text']) for source in row['sources']) <= MAX_SOURCE_CHARACTERS]

    def judge(self, actor, member, events, cutoff):
        result = {}
        config = MemoryPromptConfig.load('experience_eligibility')
        for offset in range(0, min(len(events), MAX_JUDGED_EVENTS), BATCH_SIZE):
            population = events[offset:offset + BATCH_SIZE]
            inputs = self._inputs(actor, member, population, cutoff)
            inputs = [row for row in inputs if row['sources']]
            if not inputs:
                continue
            data = {'events': inputs}
            config.validate_input(data)
            request = ModelRequest.build(system=config.prompt(), messages=[{'role': 'user',
                'content': json.dumps(data, ensure_ascii=False)}], tools=(), tool_choice=None)
            try:
                if self.complete_model:
                    output = self.complete_model(request)
                else:
                    model = self.memory.models.default_model_for_account(actor, 'memory_generation')
                    if model is None:
                        raise ValueError('请在默认模型中设置长期记忆生成模型。')
                    output = self.memory.models.complete_chat_for_account(actor, model, request, minimum_thinking_mode(model), timeout_seconds=0)
                if output.tool_calls:
                    raise ValueError('Statistics stage cannot call tools')
                value = json.loads(output.content)
                Draft202012Validator(config.schema('output')).validate(value)
                judgments = value['judgments']
                ids = [row['event_id'] for row in judgments]
                by_id = {row['event_id']: row for row in inputs}
                if len(set(ids)) != len(ids) or set(ids) != set(by_id):
                    raise ValueError('Statistics judgments must cover exactly the input events')
                for row in judgments:
                    sources = by_id[row['event_id']]['sources']
                    if row['decision'] != 'unknown' and not row['evidence']:
                        raise ValueError('A decided eligibility requires actual evidence')
                    for evidence in row['evidence']:
                        if evidence['source_index'] >= len(sources) or evidence['quote'] not in sources[evidence['source_index']]['text']:
                            raise ValueError('Statistics evidence does not match the actual source')
                # Permissions are live even though the memory record cutoff is fixed.
                self.memory.repository.check_references(actor, member,
                    [{'object_type': 'event', 'object_id': row['event_id']} for row in inputs])
                result.update({row['event_id']: row for row in judgments})
            except (ValueError, ValidationError, ProviderChatCompletionError, SerenitaError) as exc:
                for row in inputs:
                    result[row['event_id']] = {'decision': 'unknown', 'reason': 'experience_judgment_failed',
                        'failure_code': getattr(exc, 'code', type(exc).__name__), 'failure_detail': str(exc)[:2000]}
                break
        return result
