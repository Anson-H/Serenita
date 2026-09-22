"""Fixed background memory generation; models return data and never call tools."""
from backend.app.application.memory.progress import processing_step, report_progress, call_operation, current_step
from copy import deepcopy
import json
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.application.memory.evidence_service import MemoryEvidenceService
from backend.app.domain.memory.references import object_reference, reference_key
from backend.app.application.memory.indexing.index_service import MemoryIndexService
from backend.app.repositories.memory.reading.object_projection import stored_references
from backend.app.domain.memory.execution_references import retain_memory_references
from backend.app.application.memory.formation.pipeline_stages import formation_stages, HOST_FIELDS
from backend.app.application.memory.processing.checkpoint_runtime import run_checkpoint, freeze_input
from backend.app.application.memory.formation.stage_validation import (
    model_errors, parse_stage_output,
    require_valid, retry_errors, schema_errors, wait_for_stage_retry,
)
from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS
from backend.app.core.errors import SerenitaError

EXCLUDED_INPUT_TYPES = frozenset({'memory_execution_entry', 'vector_binding', 'vector_space'})


def fail(code, message):
    raise SerenitaError('invalid_input', code, message)


class MemoryPipeline:
    def __init__(self, memory, actor, member, task, scope, *, complete, guard, retain):
        self.memory, self.actor, self.member, self.task = memory, actor, member, task
        self.scope, self.complete, self.guard, self.retain = scope, complete, guard, retain
        self.formation = MemoryEvidenceService(memory)
        self.index = MemoryIndexService(memory, cancellation_token=scope.cancellation_token, deadline=scope.deadline, retry_failed=False)
        self.state = MemoryPipelineState()

    def export_state(self):
        return self.state.export()

    def restore_state(self, value):
        self.state = MemoryPipelineState.restore(value)

    def _read(self, values, results, binding):
        self.guard()
        output = call_operation('准备阶段对象与读取凭据', values, lambda: self.formation.read_prepared(self.actor, self.member, values, binding=binding))
        results.append(output)
        self.retain(output)
        return output

    def prepare_sources(self, cutoff, binding):
        if self.state.source_input is not None:
            return deepcopy(self.state.source_input)
        results = []
        initial = [{'object_type': 'processing_attempt', 'object_id': self.task['attempt_id']}]
        with processing_step('read_registered_task', input={'references': initial, 'record_cutoff': cutoff}) as details:
            self._read({'references': initial, 'record_cutoff': cutoff}, results, binding)
            attempt = next(row for row in results[0]['objects'] if row['object_type'] == 'processing_attempt' and row['attempt_id'] == self.task['attempt_id'])
            from backend.app.domain.memory.processing_state import RUNTIME_FIELDS
            attempt = {key: value for key, value in attempt.items() if key not in RUNTIME_FIELDS and key not in {'entry_references','restricted_entries','updated_at','started_at'}}
            results[0]['objects'] = [attempt]
            self.formation.receipts(results[0], binding)
            details['output'] = deepcopy({'attempt': attempt, 'reads': results})
        from backend.app.schemas.memory.evidence import source_key
        initial_changes=[]
        if attempt.get('change_id'):
            initial_changes.append({key:attempt[key] for key in ('source_database','change_id')})
        # One business change is one text input, retaining its field labels.
        from backend.app.domain.memory.change_scope import memory_change_fields
        refs=[]
        for ref in initial_changes:
            with processing_step('read_change_record', input=ref) as details:
                change = self.memory.repository.evidence.read_changes(self.actor, self.member, [ref])[0]
                details['output'] = deepcopy(change)
                if memory_change_fields(change['resource_type'], change['fields']):
                    refs.append({**ref, 'field_path': ''})
        if refs:
            with processing_step('read_content', input={'references': refs}) as details:
                result=self.formation.read_changes(self.actor,self.member,refs,binding=binding)
                details['output']=deepcopy(result)
            result['formation_input']=True
            results.append(result)
        initial_keys=[source_key(ref) for ref in refs]
        self.state.source_input = deepcopy((results, initial_keys))
        self.state.source_input_step = {'attempt_id': self.task['attempt_id'], 'step_id': 'read_content', 'parent_step_id': current_step()} if refs else None
        return deepcopy(self.state.source_input)

    def prepare(self, stage_name, event_id=None):
        """Prepare only the facts and changing scope required by this stage."""
        self.guard()
        if stage_name == 'sag_extract' and self.state.extraction_input is not None:
            return deepcopy(self.state.extraction_input)
        cutoff = self.memory.repository.snapshot(self.actor, self.member)['record_cutoff']
        binding = self.formation.bind_prepared_input(self.scope, ())
        source_reads, initial_keys = self.prepare_sources(cutoff, binding)
        # Task metadata belongs to extraction preparation only. Later stages
        # retain signed source reads and obtain their own exact object scope.
        results = source_reads if stage_name == 'sag_extract' else [row for row in source_reads if row.get('formation_input')]
        if stage_name == 'sag_extract':
            present = {reference_key(object_reference(row)): row for result in results for row in result['objects']}
        else:
            with processing_step('expand_evidence', input={'retrieval': self.state.retrieval, 'created_episode_ids': sorted(self.state.created_episodes), 'references': list(self.state.references.values()), 'record_cutoff': cutoff}) as details:
                refs = self.prepare_episode_scope(stage_name, event_id, cutoff)
                present = self.prepare_event_evidence(refs, cutoff, results, binding)
                details['output'] = deepcopy({'objects': list(present.values()), 'change_sources': [source for result in results for source in result.get('change_sources', [])], 'coverage': [result.get('read_coverage', {}) for result in results], 'episode_event_ids': self.state.episode_groups})
        if stage_name in {'routing', 'event_organization'} and any(
                row.get('object_type') == 'episode_revision' for row in present.values()):
            fail('MEMORY_ORGANIZATION_REVISION_INPUT', '归属与关系判断不能读取事项摘要或状态。')
        # Proof metadata remains server-owned. Exactly these object contents
        # and coverage descriptions enter the stage model request.
        data = {'task': self.task['purpose'], 'attempt_id': self.task['attempt_id'],
            'objects': list(present.values()), 'source_keys': initial_keys,
            'change_sources': [row for result in results for row in result.get('change_sources', [])],
            'new_event_ids': [event_id] if event_id else list(self.state.new_events), 'record_cutoff': cutoff,
            'prepared_input_reuse': {'source_step': deepcopy(self.state.source_input_step),
                'object_references': [ref for result in results for ref in result.get('reused_references', [])]},
            'coverage': [result.get('read_coverage', {}) for result in results],
            'retrieval': {**(self.state.retrieval or {'entry': 'scope', 'coverage': {'complete': True}}),
                'episode_event_ids': self.state.episode_groups}}
        if stage_name == 'sag_extract':
            from backend.app.repositories.memory.facts.entity_catalog import entity_catalog
            data['entity_catalog'] = entity_catalog(self.memory.repository, self.actor, self.member)
            self.state.extraction_input = deepcopy((data, results))
        if stage_name == 'event_organization':
            data['organization_event_id'] = event_id
            data['selected_episode_id'] = self.state.selected_episode_id
        return data, results

    def prepare_episode_scope(self, stage_name, event_id, cutoff):
        from backend.app.repositories.memory.reading.episode_context import MemoryEpisodeContextRepository
        selected = set()
        if stage_name == 'revisions':
            membership = self.memory.repository.read_facts(self.actor, self.member,
                [{'object_type': 'episode_membership', 'object_id': event_id}], record_cutoff=cutoff)['objects'][0]
            selected = {membership['episode_id']}
        elif stage_name == 'event_organization' and self.state.selected_episode_id:
            selected = {self.state.selected_episode_id}
        refs, groups = (call_operation('读取所选事项的全部事件与关系', {'episode_ids': sorted(selected), 'record_cutoff': cutoff},
            lambda: MemoryEpisodeContextRepository(self.memory.repository).contents(self.actor, self.member, selected, cutoff, require_complete=True, include_revision=stage_name == 'revisions'))
            if selected else ([], {}))
        self.state.episode_groups = groups
        refs.append({'object_type': 'event', 'object_id': event_id})
        return refs

    def prepare_event_evidence(self, refs, cutoff, results, binding):
        """Resolve required facts from prepared content and read missing sources."""
        wanted = {reference_key(ref): ref for ref in refs}
        while True:
            present = {reference_key(object_reference(row)): row for result in results for row in result['objects']}
            if len(present) > 1000:
                fail('MEMORY_STAGE_INPUT_LIMIT', '阶段所需证据超过输入对象预算，尚未处理完成。')
            for row in present.values():
                for ref, path in stored_references(row):
                    if row['object_type'] == 'episode' and path.startswith('/revisions/'):
                        continue
                    if ref['object_type'] not in EXCLUDED_INPUT_TYPES:
                        wanted[reference_key(ref)] = ref
            missing = [ref for key, ref in wanted.items() if key not in present]
            if not missing:
                break
            if len(present) + len(missing) > 1000:
                fail('MEMORY_STAGE_INPUT_LIMIT', '阶段所需证据超过输入对象预算，尚未处理完成。')
            self._read({'references': missing[:100], 'record_cutoff': cutoff}, results, binding)
        from backend.app.schemas.memory.evidence import source_key
        refs = {source_key(ref): ref for ref in self.memory.repository.evidence.source_references(
            self.actor, self.member, present.values())}
        already={row['source_key'] for result in results for row in result.get('change_sources', [])}
        if refs.keys()-already:
            requested = [refs[key] for key in sorted(refs.keys()-already)]
            results.append(call_operation('读取依据原文', {'references': requested}, lambda: self.formation.read_changes(self.actor,self.member,requested,binding=binding)))
        return present

    def stage_errors(self, name, value, data):
        errors = []
        def reject(message, path):
            errors.append({'code': 'MEMORY_EPISODE_SCOPE', 'path': path, 'message': message})
        if name == 'revisions':
            revisions = value.get('revisions', [])
            event_id = data['revision_event_id']
            if len(revisions) != 1 or revisions[0]['trigger_event_id'] != event_id:
                reject('每个新加入的事件必须生成一份完整摘要和状态，即使内容未发生变化。', ['revisions'])
            for number, item in enumerate(revisions):
                if event_id not in self.state.episode_groups.get(item['episode_id'], []):
                    reject('新版本必须属于触发事件所在的事项。', ['revisions', number, 'episode_id'])
        if name == 'event_organization':
            draft = value
            event_id = data['organization_event_id']
            if draft.get('event_id') != event_id:
                reject('每次必须且只能判断当前一个新事件。', ['event_id'])
            elif draft.get('episode_id') is not None:
                if draft['episode_id'] != data['selected_episode_id']:
                    reject('只能加入本次已读取全部事件的事项；不合适时直接建立独立事项。', ['episode_id'])
                relation = draft.get('relation') or {}
                if relation.get('relation_type') == 'Unrelated':
                    return errors
                endpoints = {relation.get('from_event_id'), relation.get('to_event_id')}
                if event_id not in endpoints or len(endpoints) != 2:
                    reject('关系必须连接当前事件和一个所选事项内的事件。', ['relation'])
                elif not endpoints - {event_id} <= set(self.state.episode_groups.get(draft['episode_id'], [])):
                    reject('连接对象必须是所选事项中已归属并实际读取的事件。', ['relation'])
        return errors

    def _host_values(self, schema, values, results, stage_name, group, index):
        command = deepcopy(values)
        properties = schema.model_fields
        cutoff = next(result['record_cutoff'] for result in results if 'record_cutoff' in result)
        coverage = [result['coverage_read_receipt'] for result in results if result.get('coverage_read_receipt')]
        if len(coverage) > 20:
            fail('MEMORY_STAGE_INPUT_LIMIT', '阶段证据范围超过服务预算。')
        host = {'operation_id': f"pipeline-{self.scope.task_id}-{stage_name}-{group}-{index}",
            'input_sequence': cutoff, 'record_cutoff': cutoff, 'coverage_receipts': coverage,
            'counterevidence_receipts': [result['coverage_read_receipt'] for result in results
                if result.get('read_query', {}).get('object_types') and not result.get('read_query', {}).get('references')]}
        for key in HOST_FIELDS & properties.keys():
            if key in host:
                command[key] = host[key]
        if stage_name == 'revisions':
            versions = [row['version'] for result in results for row in result.get('objects', [])
                if row.get('object_type') == 'episode_revision' and row['episode_id'] == command['episode_id']]
            command['version'] = max(versions, default=0) + 1
        if stage_name == 'sag_extract':
            command['source_keys']=[row['source_key'] for result in results if result.get('formation_input')
                for row in result['change_sources']]
        return command

    def output_errors(self, stage, value, data, reads):
        errors = schema_errors(stage.output_schema(), value)
        if errors:
            return errors
        for group in stage.outputs:
            for number, draft in enumerate(stage.drafts(value, group)):
                command = self._host_values(group.schema, draft, reads, stage.name, group.name, number)
                command['operation_id'] = f"{data['operation_prefix']}-{group.name}-{number}"
                path = (['data'] if stage.name == 'sag_extract' else
                    [] if stage.name == 'event_organization' else [group.name, number])
                errors.extend(model_errors(group.schema, command, path))
        if not errors:
            errors.extend(self.stage_errors(stage.name, value, data))
        return errors

    def prepare_frozen(self, key, stage_name, event_id=None):
        def prepare():
            data, reads = self.prepare(stage_name, event_id)
            return {'data': data, 'reads': reads, 'state': self.state.export_preparation()}
        saved = freeze_input(key, prepare)
        self.guard()
        self.state.restore_preparation(saved['state'])
        reads = self.formation.revalidate_frozen_reads(self.scope, saved['reads'])
        for result in reads:
            self.retain(result)
        return saved['data'], reads

    def run_stage(self, stage, *, revision_event_id=None, organization_event_id=None):
        event_id = revision_event_id or organization_event_id
        key = stage.name + (':' + event_id if event_id else '')
        self.guard()
        return run_checkpoint(key, lambda: self._run_stage(stage,
            revision_event_id=revision_event_id, organization_event_id=organization_event_id), pipeline=self)

    def _run_stage(self, stage, *, revision_event_id=None, organization_event_id=None):
        event_id = revision_event_id or organization_event_id
        stage_key = stage.name + (':' + event_id if event_id else '')
        context_id = 'prepare' if stage.name == 'sag_extract' else stage.name + '_context'
        parent_id = '' if stage.name == 'sag_extract' else current_step()
        with processing_step(context_id, parent_step_id=parent_id, input={'attempt_id': self.task['attempt_id'], 'stage': stage.name}) as details:
            data, reads = self.prepare_frozen(stage_key, stage.name, event_id)
            self.guard()
            if revision_event_id:
                data['revision_event_id'] = revision_event_id
                data['new_event_ids'] = [revision_event_id]
            details['output'] = deepcopy(data)
        if stage.requires and not all(any(row['object_type'] == kind for row in data['objects']) for kind in stage.requires):
            self.state.results.append({'layer': stage.layer.value, 'stage': stage.name, 'status': 'not_applicable', 'reason': '当前输入没有此阶段所需的已保存对象。'})
            report_progress(stage.name, 'skipped', parent_step_id=None, details={'reason': '当前输入没有此阶段所需的已保存对象。'})
            return
        with processing_step(stage.name, parent_step_id='' if stage.name == 'sag_extract' else None):
            data.update(pipeline_stage=stage.name,
                operation_prefix=f'pipeline-{self.scope.task_id}-{stage_key}')
            def generator():
                request_data = stage.request_data(data)
                stage.config.validate_input(request_data)
                request = ModelRequest.build(system=stage.prompt(),
                    messages=[{'role': 'user', 'content': json.dumps(request_data, ensure_ascii=False, separators=(',', ':'))}],
                    tools=(), tool_choice=None, output_schema=stage.output_schema())
                # Extraction repairs its direct/synthesis substep internally; host
                # command validation runs there too, without another outer budget.
                attempts = 1 if stage.name == 'sag_extract' else MAX_MODEL_ATTEMPTS
                for repair in range(attempts):
                    try:
                        self.guard()
                        self.complete.bind_stage_input(stage.request_data(data))
                        output = stage.generate(request, self.complete,
                            validate=lambda value: self.output_errors(stage, value, data, reads))
                        self.guard()
                        value = parse_stage_output(output)
                        require_valid(self.output_errors(stage, value, data, reads))
                        break
                    except Exception as error:
                        errors = retry_errors(error)
                        if errors is None:
                            if repair == attempts - 1:
                                raise
                            wait_for_stage_retry(error, repair + 1, self.complete, check_running=self.guard)
                            continue
                    if repair == attempts - 1:
                        first = errors[0]
                        location = '.'.join(str(part) for part in first.get('path', []))
                        explanation = (location + '：' if location else '') + first.get('message', '输出结构不正确。')
                        raise SerenitaError('invalid_input', 'MEMORY_STAGE_OUTPUT_INVALID',
                            '阶段输出无法保存：' + explanation,
                            details={'validation_errors': errors[:20]})
                    if errors:
                        report_progress(stage.name, 'retrying', parent_step_id=None, error_code='MEMORY_STAGE_OUTPUT_INVALID', error_message='模型输出未通过校验，正在修正。', details={'validation_errors': errors[:20]})
                        # Corrections share the same request budget as network failures.
                        from dataclasses import replace
                        data['validation_errors'] = errors[:20]
                        data['previous_output'] = output.content
                        content = request.messages[0]['content']
                        text = json.dumps(stage.request_data(data), ensure_ascii=False, separators=(',', ':'))
                        content = [{'type': 'text', 'text': text}, *content[1:]] if isinstance(content, list) else text
                        request = replace(request, messages=({'role': 'user', 'content': content},))
                return {'output': value, 'execution_receipt': self.complete.execution_receipt() if stage.name == 'revisions' else None,
                    'fixed_input': stage.request_data(data)}
            validated = run_checkpoint('validated:' + stage_key, generator)
            value = validated['output']
            self.guard()
            require_valid(self.output_errors(stage, value, data, reads))
        save_step = stage.name + '_save'
        with processing_step(save_step, parent_step_id=stage.name, input=value) as details:
            binding = self.formation.bind_prepared_input(self.scope, reads)
            result = {'layer': stage.layer.value, 'stage': stage.name, 'status': 'saving', 'reason': stage.reason(value), 'saved': []}
            self.state.results.append(result)
            for group in stage.outputs:
                for number, draft in enumerate(stage.drafts(value, group)):
                    self.guard()
                    command = self._host_values(group.schema, draft, reads, stage.name, group.name, number)
                    command['operation_id'] = f"{data['operation_prefix']}-{group.name}-{number}"
                    kwargs = {}
                    if stage.name == 'sag_extract':
                        kwargs['entity_catalog'] = data['entity_catalog']
                    elif stage.name == 'revisions':
                        kwargs['generation_input'] = {'fixed_input': validated['fixed_input'],
                            'execution_receipt': validated['execution_receipt'], 'draft_scope': self.scope.task_id}
                    saved = call_operation({'extraction': '保存事件、实体及依据', 'revisions': '保存事项摘要与状态版本', 'organizations': '保存事项归属与事件关系'}[group.name], {**command, **kwargs}, lambda: group.save(self.actor, self.member, command, binding=binding, **kwargs))
                    result['saved'].append(saved)
                    self.adopt_saved(stage.name, saved)
            result['status'] = 'completed'
            details['output'] = deepcopy(result)
            if not result['saved']:
                report_progress(save_step, 'skipped', details={'reason': '此阶段没有需要追加的内容。'})
            return result

    def adopt_saved(self, stage, saved):
        self.retain(saved)
        refs = {}
        retain_memory_references(saved, refs)
        self.state.references.update({reference_key(ref): ref for ref in refs.values()})
        self.state.created_episodes.update(ref['object_id'] for ref in refs.values() if ref['object_type'] == 'episode')
        if stage == 'sag_extract':
            self.state.sag_index_context.update(saved.get('index_context', {}))
            self.state.new_events.extend(identity for _, identity in sorted(saved['event_ids'].items(), key=lambda item: int(item[0]))
                if identity not in self.state.new_events)

    def deliver_sag_vectors(self):
        return run_checkpoint('index', self._deliver_sag_vectors, pipeline=self)

    def _deliver_sag_vectors(self):
        # Extraction already committed events, evidence, entities and descriptions
        # together. Vector delivery is deterministic and never extracts again.
        self.state.results[-1].update(vector_deliveries=[], semantic_vector_deliveries=[], chunk_vector_deliveries=[])
        from backend.app.application.memory.indexing.semantic_index import MemorySemanticIndexService
        from backend.app.application.memory.indexing.chunk_index import MemoryChunkIndexService
        semantic = MemorySemanticIndexService(self.index)
        chunks = MemoryChunkIndexService(self.index)
        delivered_chunks, source_parts = {}, {}
        targets, target_contexts = [], []
        for number, identity in enumerate(self.state.new_events, 1):
            self.guard()
            event_step = f'index_events:{number}'
            source_step = f'index_sources:{number}'
            def index_event():
                with processing_step(event_step, input={'event_id': identity, 'operation_id': 'sag-vector-' + identity}) as details:
                    output = self.index.index_event(self.actor, self.member, 'sag-vector-' + identity, identity)
                    details['output'] = deepcopy(output)
                    if output.get('status', {}).get('state') != 'confirmed':
                        report_progress(event_step, 'failed', error_code=output.get('status', {}).get('error_code') or 'MEMORY_INDEX_UNCONFIRMED', error_message='事件向量尚未成功建立，检索索引未完成。')
                        fail(output.get('status', {}).get('error_code') or 'MEMORY_INDEX_UNCONFIRMED', '事件向量保存失败。')
                self.retain(output)
                self.state.results[-1]['vector_deliveries'].append({'event_id': identity, **output})
                return output
            output = run_checkpoint('index_event:' + identity, index_event, pipeline=self)
            context = self.state.sag_index_context.get(identity)
            if context is None:
                context = self.index.repository.delivery_context(self.actor, self.member, identity)
            def index_sources():
                with processing_step(source_step, input={'event_id': identity, 'space': output['space']}) as details:
                    details['output'] = []
                    for result in chunks.index_event(self.actor, self.member, identity,
                            space=output['space'], delivery_results=delivered_chunks, source_parts=source_parts):
                        if result.get('status', {}).get('state') not in {None, 'confirmed'}:
                            fail('MEMORY_INDEX_UNCONFIRMED', '来源检索索引未完成。')
                        self.state.results[-1]['chunk_vector_deliveries'].append({'event_id': identity, **result})
                        details['output'].append(deepcopy(result))
                # These in-memory maps use tuple keys. Rebuild them from pairs
                # when replaying a source-index substep after process restart.
                return {'delivered_chunks': list(delivered_chunks.items()), 'source_parts': list(source_parts.items())}
            cached = run_checkpoint('index_sources:' + identity, index_sources, pipeline=self)
            delivered_chunks = {tuple(key) if isinstance(key, list) else key: value for key, value in cached['delivered_chunks']}
            source_parts = {tuple(key) if isinstance(key, list) else key: value for key, value in cached['source_parts']}
            for link in context['links']:
                if link['event_id'] != identity:
                    continue
                entity_id = link['entity_id']
                for role in (False, True):
                    operation = ('sag-entity-role-' + identity + '-' + entity_id) if role else ('sag-entity-name-' + entity_id)
                    targets.append({'operation_id': operation, 'entity_id': entity_id,
                                    'event_id': identity if role else None})
                    target_contexts.append({'event_id': identity, 'entity_id': entity_id,
                        'index_kind': 'entity_role' if role else 'entity_name'})
                for name in context['names']:
                    if name['entity_id'] != entity_id or name['event_id'] != link['event_id']:
                        continue
                    targets.append({'operation_id': 'sag-entity-alias-' + name['name_id'],
                                    'entity_id': entity_id, 'name_id': name['name_id']})
                    target_contexts.append({'event_id': identity, 'entity_id': entity_id,
                        'name_id': name['name_id'], 'index_kind': 'entity_name'})
        # Building target dictionaries performs no external work. Recheck once
        # at the delivery boundary; the index service checks each actual read,
        # model request and write under its current permissions.
        self.guard()
        def index_entities():
            with processing_step('index_entities', input={'targets': targets}) as details:
                details['output'] = []
                for context, result in zip(target_contexts, semantic.index_targets(self.actor, self.member, targets)):
                    if result.get('status', {}).get('state') not in {None, 'confirmed'}:
                        fail('MEMORY_INDEX_UNCONFIRMED', '部分实体名称或作用说明的检索索引未完成。')
                    self.state.results[-1]['semantic_vector_deliveries'].append({**context, **result})
                    details['output'].append(deepcopy({**context, **result}))
                return details['output']
        run_checkpoint('index_entities', index_entities, pipeline=self)
        return {key: deepcopy(self.state.results[-1][key]) for key in
            ('vector_deliveries', 'semantic_vector_deliveries', 'chunk_vector_deliveries')}

    def organize_events(self, organization, revisions):
        from backend.app.application.memory.formation.episode_routing import MemoryEpisodeRouting
        from backend.app.application.memory.progress import event_progress
        routing = MemoryEpisodeRouting(self.memory, self.complete, self.guard, self.retain)
        self.state.retrieval = {'coverage': {'complete': True}}
        for event_id in self.state.new_events:
            self.guard()
            # One parent per Event keeps every event's latest stage records independently readable.
            with event_progress(event_id), processing_step('organize_event:' + event_id, parent_step_id='', input={'event_id': event_id}):
                def select():
                    with processing_step('episode_search_context', input={'event_id': event_id}) as details:
                        data, _ = self.prepare_frozen('routing:' + event_id, 'routing', event_id)
                        event = next(row for row in data['objects'] if row.get('object_type') == 'event' and row['event_id'] == event_id)
                        details['output'] = {'event_id': event_id, 'record_cutoff': data['record_cutoff']}
                    selected = routing.select(self.actor, self.member, event,
                        self.memory.repository.snapshot(self.actor, self.member)['record_cutoff'])
                    self.state.selected_episode_id = selected['episode_id']
                    return selected
                run_checkpoint('episode_search:' + event_id, select, pipeline=self)
                for stage, argument in ((organization, 'organization_event_id'), (revisions, 'revision_event_id')):
                    result = self.run_stage(stage, **{argument: event_id})
                    if not result or result['status'] != 'completed' or not result['saved']:
                        fail('MEMORY_STAGE_INCOMPLETE', '当前事件的处理步骤尚未成功完成。')

    def run(self):
        stages = formation_stages(self.memory, self.formation)
        extraction, organization, revisions = stages
        self.run_stage(extraction)
        with processing_step('index', parent_step_id='', input={'event_ids': self.state.new_events}) as details:
            self.deliver_sag_vectors()
            if not self.state.new_events:
                report_progress('index', 'skipped', details={'reason': '没有新事件需要建立检索索引。'})
            deliveries = [item for key in ('vector_deliveries', 'semantic_vector_deliveries', 'chunk_vector_deliveries')
                for item in self.state.results[-1].get(key, [])]
            details['output'] = deepcopy(deliveries)
            if any(item.get('status', {}).get('state') not in {None, 'confirmed'} for item in deliveries):
                fail('MEMORY_INDEX_UNCONFIRMED', '部分检索索引尚未成功建立。')
        if self.state.new_events:
            self.organize_events(organization, revisions)
        return {'stages': self.state.results, 'new_event_ids': self.state.new_events}

from backend.app.application.memory.formation.pipeline_state import MemoryPipelineState
