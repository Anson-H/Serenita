"""Program-owned retrieval, model selection and evidence reading without Harness."""
from backend.app.domain.model_capabilities import minimum_thinking_mode
from collections import defaultdict
from copy import deepcopy
import json
import time

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from backend.app.application.memory.progress import track_step, report_model_retry
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.errors import SerenitaError
from backend.app.core.model_retry import run_model_request
from backend.app.providers.errors import ProviderChatCompletionError


def _selection_changed():
    raise SerenitaError('forbidden', 'MEMORY_SEARCH_SCOPE_CHANGED',
                        '检索采用的来源或连接已不可用，请重新查询。')


def _current_search_chains(index, actor, member, result):
    """Recheck the original search's bounded evidence, without a model call."""
    from backend.app.repositories.memory.reading.search_paths import authorized_chains
    repo = index.repository
    snapshot = repo.snapshot(actor, member, result['record_cutoff'])
    paths = defaultdict(list)
    candidates = {row['event_id'] for row in result['candidates']}
    for row in result['candidates']:
        chains = row.get('source_chains')
        if not chains:
            _selection_changed()
        for chain in chains:
            if not chain or chain[-1]['event_id'] != row['event_id']:
                _selection_changed()
            for step in chain:
                identity = step['event_id']
                value = {key: field for key, field in step.items() if key != 'event_id'}
                if value not in paths[identity]:
                    paths[identity].append(value)
    verification = {}
    chains, _, changed = authorized_chains(index.memory.repository, actor, member,
        result['record_cutoff'], paths, snapshot, result['query'], verification=verification)
    if candidates.difference(chains):
        # The model selected from the whole returned evidence set. A missing
        # side may have supplied a conflict or the original connecting basis.
        _selection_changed()
    from backend.app.repositories.memory.reading.search_hits import ranking_evidence
    ranking, ranking_changed = ranking_evidence(index.memory.repository, actor, member, result['record_cutoff'],
        {row['event_id']: row['ranking_vector_hits'] for row in result['candidates']}, snapshot, result['query'], verification=verification)
    return chains, changed or ranking_changed, ranking


class MemoryQueryService:
    def __init__(self, memory, *, recall=None, complete_model=None, cancellation_token=None, deadline=None):
        from backend.app.application.memory.querying.recall import MemoryRecallService
        self.memory = memory
        self.recall = recall or MemoryRecallService(memory, complete_model=complete_model,
            cancellation_token=cancellation_token, deadline=deadline)


    def _guard(self, actor, member, result):
        self.recall.check_running()
        _, changed, _ = _current_search_chains(self.recall, actor, member, result)
        if changed:
            _selection_changed()

    @track_step('joint_selection')
    def _select(self, actor, member, result):
        self._guard(actor, member, result)
        ids = [row['event_id'] for row in result['candidates']]
        relations = self.recall.relation_provider(actor, member, result['record_cutoff'], ids)
        groups = [list(group) for group in relations['groups']]
        config = MemoryPromptConfig.load('search_selection')
        data = {'query': result['query'], 'candidates': result['candidates'], 'groups': groups, 'maximum': 12}
        config.validate_input(data)
        request = ModelRequest.build(system=config.prompt(),
            messages=[{'role': 'user', 'content': json.dumps(data, ensure_ascii=False, separators=(',', ':'))}],
            tools=(), tool_choice=None)
        started = time.monotonic()
        account = result['account_id']
        complete_model = self.recall.complete_model
        if complete_model is None:
            model = deepcopy(self.recall.models.default_model_for_account(account, 'memory_generation'))
            if model is None:
                raise SerenitaError('invalid_structure', 'MEMORY_QUERY_MODEL_REQUIRED', '记忆查询需要已配置的长期记忆生成模型。')
        def invoke():
            if complete_model is not None:
                return complete_model(request)
            remaining = max(.001, self.recall.deadline - time.monotonic()) if self.recall.deadline else None
            return self.recall.models.complete_chat_for_account(account, model, request, minimum_thinking_mode(model),
                cancellation_token=self.recall.cancellation_token, timeout_seconds=remaining)
        output = run_model_request(invoke, check_running=lambda: self._guard(actor, member, result),
            cancellation_token=self.recall.cancellation_token, on_retry=report_model_retry)
        self._guard(actor, member, result)
        if output.tool_calls:
            raise SerenitaError('invalid_structure', 'MEMORY_QUERY_MODEL_INVALID', '记忆查询阶段只能返回选择结果。')
        value = json.loads(output.content)
        Draft202012Validator(config.schema('output')).validate(value)
        self.recall.validate_selection(result, value['event_ids'])
        selected = set(value['event_ids'])
        if any(selected.intersection(group) and not set(group) <= selected for group in groups):
            raise SerenitaError('invalid_structure', 'MEMORY_QUERY_GROUP_INCOMPLETE', '模型选择未包含完整证据组。')
        result['stages'].append({'stage': 'joint_selection', 'state': 'completed', 'inputs': len(ids),
            'outputs': len(selected), 'elapsed_ms': round((time.monotonic() - started) * 1000, 3), 'usage': output.usage})
        return value

    @track_step('source_read')
    def _evidence(self, actor, member, result, selected):
        from backend.app.domain.memory.references import object_reference, reference_key
        wanted = {reference_key(row['reference']): row['reference'] for row in selected}
        objects, gaps, unread = {}, [], []
        while wanted:
            self.recall.check_running()
            pending = [ref for key, ref in wanted.items() if key not in objects]
            if not pending:
                break
            if len(objects) + len(pending) > 1000:
                raise SerenitaError('invalid_structure', 'MEMORY_QUERY_EVIDENCE_LIMIT', '查询所需原始证据超过读取预算。')
            for offset in range(0, len(pending), 100):
                read = self.memory.query(actor, member, {'references': pending[offset:offset+100],
                    'record_cutoff': result['record_cutoff']})
                gaps.extend(read.get('gaps', [])); unread.extend(read.get('unread', []))
                received = {reference_key(object_reference(row)): row for row in read['objects']}
                if any(reference_key(ref) not in received for ref in pending[offset:offset+100]):
                    raise SerenitaError('forbidden', 'MEMORY_QUERY_EVIDENCE_UNAVAILABLE', '所选事件的原始证据未能完整读取。')
                objects.update(received)
            wanted = {}
        # Keep fixed content; the return boundary checks exact live access.
        refs = [object_reference(row) for row in objects.values()]
        self.memory.repository.check_references(actor, member, refs)
        fresh = objects
        self._guard(actor, member, result)
        refs = self.memory.repository.evidence.source_references(actor, member, fresh.values())
        changes = self.memory.repository.evidence.read_changes(actor, member, refs)
        return {'member_id': member, 'record_cutoff': result['record_cutoff'], 'objects': list(fresh.values()), 'business_changes':changes,
            'gaps': gaps, 'unread': unread, 'coverage': {'complete': not gaps and not unread}, 'next_cursor': None}

    def search(self, actor, member, values):
        from backend.app.repositories.memory.reading.prepared_reads import prepared_read_scope
        with prepared_read_scope(self.memory.repository, actor, member):
            return self._search(actor, member, values)

    def _search(self, actor, member, values):
        result = self.recall.recall(actor, member, values)
        result['evidence'] = {'objects': [], 'gaps': [], 'unread': [], 'coverage': {'complete': False}}
        result['joint_selection'] = {'state': 'empty', 'selected_event_ids': [], 'maximum': 12}
        if not result['candidates']:
            result['joint_selection']['state'] = 'failed' if result['failures'] else 'empty'
            result['evidence']['coverage']['complete'] = not result['failures']
            return result
        phase = 'joint_selection'
        started = time.monotonic()
        try:
            value = self._select(actor, member, result)
            by_id = {row['event_id']: row for row in result['candidates']}
            selected = [by_id[key] for key in value['event_ids']]
            phase = 'source_read'
            started = time.monotonic()
            if selected:
                result['evidence'] = self._evidence(actor, member, result, selected)
            else:
                result['evidence']['coverage']['complete'] = True
            complete = result['evidence']['coverage']['complete']
            result['candidates'] = [{**row, 'evidence_read': complete} for row in selected]
            result['joint_selection'] = {'state': 'completed' if selected else 'empty',
                'selected_event_ids': value['event_ids'], 'maximum': 12, 'reason': value['reason']}
            result['stages'].append({'stage': 'source_read', 'state': 'completed' if complete else 'partial',
                'outputs': len(result['evidence']['objects']), 'elapsed_ms': round((time.monotonic()-started)*1000, 3)})
            result['coverage']['returned'] = len(selected)
            result['coverage']['complete'] &= complete
            result['gaps'].extend(result['evidence']['gaps'])
            return result
        except OperationCancelledError:
            raise
        except Exception as exc:
            # Never return model text or recalled identifiers after an access
            # change; a failed query has no substituted ranking or evidence.
            if isinstance(exc, SerenitaError):
                code = exc.code
            elif isinstance(exc, ProviderChatCompletionError):
                code = exc.code or 'MEMORY_QUERY_MODEL_FAILED'
            elif phase == 'joint_selection' and isinstance(exc, (json.JSONDecodeError, ValidationError)):
                code = 'MEMORY_QUERY_MODEL_INVALID'
            else:
                code = 'MEMORY_QUERY_MODEL_FAILED' if phase == 'joint_selection' else 'MEMORY_QUERY_EVIDENCE_FAILED'
            result['stages'].append({'stage': phase, 'state': 'failed', 'error_code': code,
                'elapsed_ms': round((time.monotonic() - started) * 1000, 3)})
            result.update(candidates=[], evidence={'objects': [], 'gaps': [], 'unread': [], 'coverage': {'complete': False}},
                continuation=None, joint_selection={'state': 'failed', 'selected_event_ids': [], 'maximum': 12})
            result['failures'] = [{'code': code, 'message': '记忆查询未完成选择或证据读取，请根据失败原因重新查询。'}]
            result['gaps'] = [{'code': code, 'detail': '本次查询未返回完整证据。'}]
            result['coverage'] = {'returned': 0, 'unread': 0, 'complete': False}
            return result
