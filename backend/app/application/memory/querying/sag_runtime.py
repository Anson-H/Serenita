"""Request-scoped model dependencies for the pinned SAG orchestrator."""
from backend.app.domain.model_capabilities import minimum_thinking_mode
from backend.app.domain.memory.event_text import event_text
from dataclasses import dataclass
from copy import deepcopy
import json
import time
from types import SimpleNamespace

from jsonschema import Draft202012Validator, ValidationError
from pydantic import BaseModel

from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.domain.memory.model_output import parse_json
from backend.app.application.memory.sag.core import run_core
from backend.app.application.memory.querying.sag_storage import SAGStorage
from backend.app.application.memory.progress import report_model_retry
from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import run_model_request
from zleap.sag.config import SAGConfig
from zleap.sag.orchestrator import SAGSearcher


class NEROutput(BaseModel):
    named_entities: list[str]


@dataclass(frozen=True)
class SAGModelInput:
    config: MemoryPromptConfig
    data: dict


class SAGPrompts:
    def get_messages(self, name, *, query):
        if name != 'ner':
            raise ValueError('Unsupported SAG prompt')
        return SAGModelInput(MemoryPromptConfig.load('sag_ner'), {'query': query})

    def get_sag_rerank_messages(self, *, question, relations, top_k):
        return SAGModelInput(MemoryPromptConfig.load('sag_rank'),
            {'question': question, 'relations': relations, 'top_k': top_k})


class SAGModel:
    def __init__(self, runtime):
        self.runtime = runtime
        self._last_call_timing, self._last_call_usage = {}, None

    async def chat_parsed(self, messages, output_type):
        runtime, config, data = self.runtime, messages.config, messages.data
        self._last_call_timing, self._last_call_usage = {}, None
        started = time.monotonic()
        try:
            snapshot = runtime.guard()
            config.validate_input(data)
            request = ModelRequest.build(system=config.prompt(), messages=[{
                'role': 'user', 'content': json.dumps(data, ensure_ascii=False, separators=(',', ':'))}],
                tools=(), tool_choice=None)
            index = runtime.index
            complete_model = index.complete_model
            if complete_model is None:
                model = deepcopy(index.models.default_model_for_account(snapshot['account_id'], 'memory_generation'))
                if model is None:
                    raise SerenitaError('invalid_structure', 'MEMORY_QUERY_MODEL_REQUIRED', 'SAG 查询需要已配置的长期记忆生成模型。')
            def invoke():
                if complete_model is not None:
                    return complete_model(request)
                remaining = max(.001, index.deadline - time.monotonic()) if index.deadline else None
                return index.models.complete_chat_for_account(snapshot['account_id'], model, request, minimum_thinking_mode(model),
                    cancellation_token=index.cancellation_token, timeout_seconds=remaining)
            output = run_model_request(invoke, check_running=runtime.guard,
                cancellation_token=index.cancellation_token, on_retry=report_model_retry)
            runtime.guard()
            self._last_call_usage = SimpleNamespace(prompt_tokens=output.usage.get('input_tokens', 0),
                completion_tokens=output.usage.get('output_tokens', 0))
            if output.tool_calls:
                raise ValueError('SAG model cannot call tools')
            value = parse_json(output.content)
            Draft202012Validator(config.schema('output')).validate(value)
            if config.name == 'sag_rank':
                selected = value['useful_relations']
                if len(selected) > data['top_k'] or any(int(item[1:-1]) >= len(runtime.rank_ids) for item in selected):
                    raise ValueError('SAG selection exceeds its actual input')
            elif any(not name.strip() for name in value['named_entities']):
                raise ValueError('SAG entity name cannot be blank')
            parsed = output_type.model_validate(value)
            runtime.model_calls.append({'stage': config.name, 'state': 'completed', 'usage': output.usage})
            return parsed
        except Exception as exc:
            if isinstance(exc, (ValueError, ValidationError)):
                exc = SerenitaError('invalid_structure', 'MEMORY_QUERY_MODEL_INVALID', 'SAG 模型输出不符合当前阶段要求。')
            runtime.model_error = exc
            runtime.model_calls.append({'stage': config.name, 'state': 'failed',
                'error_code': getattr(exc, 'code', 'MEMORY_QUERY_MODEL_FAILED')})
            raise exc
        finally:
            elapsed = time.monotonic() - started
            self._last_call_timing = {'total_time': elapsed, 'success_time': elapsed if runtime.model_error is None else 0,
                'wasted_retry_time': 0, 'retries': 0}


class HostSAGRuntime(SAGStorage):
    def __init__(self, *args, **kwargs):
        self.model_error, self.model_calls, self.rank_ids = None, [], []
        super().__init__(*args, **kwargs)
        self.llm_client, self.prompts = SAGModel(self), SAGPrompts()

    def fresh(self, scope=None, **selection):
        # Upstream rank catches model exceptions and constructs fallback rows.
        # Stop subsequent I/O and propagate the original failure to the caller.
        if self.model_error is not None:
            raise self.model_error
        return super().fresh(scope, **selection)

    def guard(self):
        snapshot = self.fresh()
        if self.seen_events.difference(snapshot['events']) or self.seen_entities.difference(snapshot['entities']):
            raise SerenitaError('forbidden', 'MEMORY_SEARCH_SCOPE_CHANGED', 'SAG 查询采用的事件或实体依据已不可读取。')
        if len(self.evidence(snapshot=snapshot)['vector_hits']) != len(self._evidence):
            raise SerenitaError('forbidden', 'MEMORY_SEARCH_SCOPE_CHANGED', 'SAG 查询采用的向量依据已不可读取。')
        return snapshot

    def get_prompts(self, config=None):
        self.guard()
        if config is not None and (config.use_mlflow_prompts or config.sag_rewrite_query_enabled
                or config.sag_scope.enabled or config.sag_rerank.strategy != 'llm_rank'):
            raise ValueError('SAG host requires the configured local NER and LLM rank stages')
        return self.prompts

    async def get_llm_client(self):
        self.guard()
        return self.llm_client

    async def extract_entities(self, query, config=None):
        value = await self.llm_client.chat_parsed(self.get_prompts(config).get_messages('ner', query=query), NEROutput)
        return list(dict.fromkeys(name.strip() for name in value.named_entities))

    async def get_events_by_ids(self, event_ids, source_includes):
        rows = await super().get_events_by_ids(event_ids, source_includes)
        # The native rank stage keeps this input order when assigning indices.
        if 'category' in source_includes:
            visible = {row['event_id'] for row in rows}
            self.rank_ids = [key for key in dict.fromkeys(event_ids) if key in visible]
        return rows

    async def fetch_event_chunks(self, event_ids):
        self.guard()
        rows = await super().get_events_by_ids(event_ids, [])
        # Source reading belongs to the independent query service after its
        # complete relation groups have been selected. These are locators only.
        return {row['event_id']: {'event_reference': {'object_type': 'event', 'object_id': row['source_event_id']},
            'evidence_read': False} for row in rows}

    async def aclose(self):
        # Models belong to the application's account service, not this request.
        return None


def search_sag(runtime, query, *, expansion_enabled=True):
    """Execute the full pinned pipeline; keep actual model selections explicit."""
    snapshot = runtime.guard()
    # Keep qualifying/negative statements at the end of long descriptions.
    # Model request limits may reject the request; silent truncation is unsafe.
    content_limit = max([2000, *(len(event_text(row)) for row in snapshot['events'].values())])
    config = SAGConfig(sag_recall={'max_entities': 32, 'max_events_per_key': 64},
        sag_expand={'enabled': expansion_enabled, 'max_hops': 2 if expansion_enabled else 0,
            'entities_per_hop': 32, 'max_events_per_hop': 64},
        sag_rerank={'max_results': 32, 'llm_rank_top_n': 32, 'llm_rank_max_results': 12,
            'llm_rank_max_content_len': content_limit})
    result = run_core(SAGSearcher(runtime).search(query, [runtime.member], config))
    runtime.guard()
    if result['rank_failed']:
        raise SerenitaError('invalid_structure', 'MEMORY_QUERY_MODEL_INVALID', 'SAG 模型排序未完成。')
    selected = set(result['display_event_ids'])
    result['items'] = [{**row, 'model_selected': row['event_id'] in selected, 'evidence_read': False}
        for row in result['items']]
    result['vector_evidence'] = runtime.evidence()
    result['model_calls'] = list(runtime.model_calls)
    result['config'] = config.model_dump(mode='json')
    from backend.app.repositories.memory.reading.sag_paths import paths_from_sag
    from backend.app.repositories.memory.reading.search_paths import authorized_chains
    paths, _, limited = paths_from_sag(result)
    snapshot = runtime.guard()
    chains, truncated, changed = authorized_chains(runtime.repo.memory, runtime.actor, runtime.member,
        runtime.cutoff, paths, snapshot, query)
    runtime.guard()
    if changed or {row['event_id'] for row in result['items']}.difference(chains):
        raise SerenitaError('forbidden', 'MEMORY_SEARCH_SCOPE_CHANGED', 'SAG 查询的完整来源路径已不可验证。')
    result['source_paths'], result['source_chains'] = paths, chains
    result['path_budget_limited'] = limited or truncated
    return result
