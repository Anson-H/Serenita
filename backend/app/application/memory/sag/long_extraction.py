"""Select important facts from budgeted structural inputs, then organize events."""
from copy import deepcopy
from dataclasses import replace
import json
import re

from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.agent_runtime.context_tokens import estimate_input_tokens
from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.application.memory.progress import processing_step
from backend.app.domain.memory.model_output import parse_json
from backend.app.application.memory.formation.stage_validation import (
    complete_once, extraction_errors,
    facts_errors, parse_stage_output, require_valid, retry_errors, schema_errors, wait_for_stage_retry,
)
from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS
from backend.app.application.memory.processing.checkpoint_runtime import run_checkpoint, freeze_input
from backend.app.core.errors import SerenitaError


def fail(message, errors=None, *, code='MEMORY_CHUNK_OUTPUT_INVALID'):
    raise SerenitaError('invalid_input', code, message,
                       details={'validation_errors': errors or []})


class Extraction:
    def __init__(self, request, complete, validate=None):
        self.request, self.complete = request, complete
        self.validate = validate
        content = request.messages[-1]['content']
        self.payload = parse_json(content[0]['text'] if isinstance(content, list) else content)
        self.attachments = content[1:] if isinstance(content, list) else []
        self.meta = deepcopy(self.payload['data']['meta'])
        positions = self.meta.pop('source_fragments', [])
        self.items = self.payload['data']['items']
        self.positions = {row['id']: row for row in positions}
        self.originals = {row['id']: row['content'] for row in self.items}
        if len(self.positions) != len(positions) or set(self.positions) != set(self.originals):
            fail('来源结构单元位置不完整。')
        # Administrative record states stay in the source/audit document.
        self.items = [row for row in self.items if self.positions[row['id']].get('kind') != 'record_context']
        model_reader = getattr(complete, 'extraction_model', None)
        self.model = model_reader() if model_reader else {}
        self.context = self.model.get('context_window_tokens') or 131072
        self.output = next((request.model_config[key] for key in
            ('max_output_tokens', 'max_tokens', 'max_completion_tokens') if request.model_config.get(key)),
            self.model.get('max_output_tokens') or 8192)
        self.limit = self.context - self.output
        self.events_prompt = MemoryPromptConfig.load('sag_extract')
        self.facts_prompt = MemoryPromptConfig.load('sag_facts')

    def contexts(self, items):
        sources = {}
        for row in items:
            position = self.positions[row['id']]
            context = sources.setdefault(position['source_key'], {
                'document_context': position.get('document_context', {}), 'unit_ids': [], 'unit_contexts': []})
            context['unit_ids'].append(row['id'])
            if row.get('continuation'):
                context['unit_contexts'].append({'id': row['id'], **row['continuation']})
            elif position.get('kind') != 'field_group' and position.get('section_heading'):
                context['unit_contexts'].append({'id': row['id'], 'heading': position['section_heading']})
        return list(sources.values())

    def data(self, items, phase, *, facts=None):
        meta = {key: deepcopy(value) for key, value in self.meta.items()
                if key not in {'previous_context', 'retrieval', 'record_cutoff', 'validation_errors', 'previous_output'}}
        meta.update(pipeline_stage='sag_facts' if phase == 'facts' else 'sag_extract', extraction_phase=phase,
            source_contexts=self.contexts(items))
        if phase == 'facts':
            meta.pop('entity_catalog', None)
        if facts is not None:
            meta['important_facts'] = [{'content': fact['content'],
                'references': list(dict.fromkeys(e['reference'] for e in fact['evidence']))} for fact in facts]
        if phase != 'facts' and self.meta.get('validation_errors'):
            meta.update({key: self.meta[key] for key in ('validation_errors', 'previous_output') if key in self.meta})
        return {'type': 'request', 'data': {'items': [{key: row[key] for key in ('id', 'content')} for row in items], 'meta': meta}}

    def build(self, config, data):
        text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        content = [{'type': 'text', 'text': text}, *self.attachments] if self.attachments else text
        return replace(self.request, system=config.prompt(), context_sections=(), tools=(), tool_choice=None,
            output_schema=config.schema('output'),
            model_config={**{key: value for key, value in self.request.model_config.items()
                            if key not in {'max_tokens', 'max_completion_tokens'}}, 'max_output_tokens': self.output},
            messages=({'role': 'user', 'content': content},))

    def fits(self, config, data):
        return estimate_input_tokens(self.build(config, data).canonical_dict(), model=self.model) <= self.limit

    def require_budget(self, config, data):
        actual = self.build(config, data)
        estimated = estimate_input_tokens(actual.canonical_dict(), model=self.model)
        if estimated > self.limit:
            fail(f'阶段输入估算 {estimated}，可用输入预算 {self.limit}，上下文 {self.context}，预留输出 {self.output}；已完成结果保留。',
                 code='MEMORY_EXTRACTION_CONTEXT_LIMIT')
        return actual

    def check(self, value, config, data):
        require_valid(schema_errors(config.schema('output'), value))
        source = {row['id']: row['content'] for row in data['data']['items']}
        if config.name == 'sag_facts':
            require_valid(facts_errors(value, source, self.originals))
        else:
            require_valid(extraction_errors(value['data']['items'], source, self.meta.get('entity_catalog', [])))
            if self.validate is not None:
                require_valid(self.validate(value))

    def call(self, config, data, step):
        return run_checkpoint('extraction:' + step, lambda:
            self._call(config, freeze_input('extraction:' + step, lambda: data), step))

    def _call(self, config, data, step):
        config.validate_input(data)
        data = deepcopy(data)
        for repair in range(MAX_MODEL_ATTEMPTS):
            with processing_step(step, parent_step_id='sag_extract', retry=bool(repair), input=data) as details:
                actual = self.require_budget(config, data)
                try:
                    output = complete_once(self.complete, actual)
                    value = parse_stage_output(output)
                    self.check(value, config, data)
                except Exception as error:
                    errors = retry_errors(error)
                    if errors is None:
                        if repair == MAX_MODEL_ATTEMPTS - 1:
                            raise
                        details['retry_requested'] = True
                        details['error_code'] = getattr(error, 'code', type(error).__name__)
                        wait_for_stage_retry(error, repair + 1, self.complete)
                        continue
                    details['validation_errors'] = errors
                    if repair == MAX_MODEL_ATTEMPTS - 1:
                        fail(errors[0]['message'], errors)
                    data['data']['meta'].update(validation_errors=errors, previous_output=output.content)
                    if not self.fits(config, data):
                        # Regenerate from complete evidence and precise diagnostics.
                        # The full invalid answer remains in the model result record.
                        data['data']['meta'].pop('previous_output')
                        details['repair_context'] = '保留完整来源与校验错误；前次输出沿模型结果记录读取。'
                    details['retry_requested'] = True
                    continue
                details.update(value=deepcopy(value), prepared_messages=list(actual.messages), output=deepcopy(value))
                return value

    def divide(self, item):
        """Subdivide an oversized prose unit at paragraph/sentence boundaries only."""
        if self.positions[item['id']].get('kind') == 'field_group':
            fail('单个完整字段组超过模型输入预算，需要更大的可用上下文。', code='MEMORY_EXTRACTION_UNIT_LIMIT')
        text = item['content']
        # Keep a full table row, a sentence, or a paragraph as the minimum unit.
        table_match = re.search(r'^[ \t]*\|?.+\|.+\n[ \t]*\|?[ :|-]+\|[^\n]*', text, re.MULTILINE)
        table = table_match is not None
        boundaries = [match.end() for match in re.finditer(r'\n' if table else r'\n\s*\n|(?<=[。！？.!?])(?=\s|[\u4e00-\u9fff])', text)]
        boundaries = sorted({0, *boundaries, len(text)})
        pieces, start = [], 0
        heading = '\n'.join(re.findall(r'^#{1,6} .+$', text, re.MULTILINE))
        table_header = table_match.group() if table_match else ''
        for left, right in zip(boundaries, boundaries[1:]):
            part = {**item, 'content': text[start:right], 'continuation': {'unit_id': item['id'],
                'character_start': start, 'character_end': right, 'heading': heading, 'table_header': table_header}}
            if not self.fits(self.facts_prompt, self.data([part], 'facts')):
                if left == start:
                    fail('单个完整句子或表格行超过模型输入预算，需要更大的可用上下文。', code='MEMORY_EXTRACTION_UNIT_LIMIT')
                pieces.append({**part, 'content': text[start:left], 'continuation': {**part['continuation'], 'character_end': left}})
                start = left
                part = {**part, 'content': text[start:right], 'continuation': {**part['continuation'], 'character_start': start}}
                if not self.fits(self.facts_prompt, self.data([part], 'facts')):
                    fail('单个完整句子或表格行超过模型输入预算。', code='MEMORY_EXTRACTION_UNIT_LIMIT')
        if start < len(text):
            pieces.append({**item, 'content': text[start:], 'continuation': {'unit_id': item['id'],
                'character_start': start, 'character_end': len(text), 'heading': heading, 'table_header': table_header}})
        return pieces

    def batches(self):
        batches, current = [], []
        for item in self.items:
            parts = [item] if self.fits(self.facts_prompt, self.data([item], 'facts')) else self.divide(item)
            for part in parts:
                repeated = any(row['id'] == part['id'] for row in current)
                if current and (repeated or not self.fits(self.facts_prompt, self.data([*current, part], 'facts'))):
                    batches.append(current)
                    current = []
                current.append(part)
        if current:
            batches.append(current)
        return batches

    def run(self):
        direct = self.data(self.items, 'direct')
        if self.fits(self.events_prompt, direct):
            value = self.call(self.events_prompt, direct, 'sag_extract_direct')
        else:
            batches = self.batches()
            with processing_step('sag_structure_batches', parent_step_id='sag_extract') as details:
                details['output'] = {'batches': batches, 'source_units': list(self.positions.values()),
                    'context_window_tokens': self.context, 'reserved_output_tokens': self.output, 'input_budget': self.limit}
            facts = []
            for index, batch in enumerate(batches, 1):
                result = self.call(self.facts_prompt, self.data(batch, 'facts'), f'sag_fact_extract:{index}')
                facts.extend(result['facts'])
            quotes = {}
            for fact in facts:
                for evidence in fact['evidence']:
                    quote_list = quotes.setdefault(evidence['reference'], [])
                    if evidence['quote'] not in quote_list:
                        quote_list.append(evidence['quote'])
            selected = [{'id': ref, 'content': '\n\n[以下为同一来源单元的另一处原文摘录]\n\n'.join(parts)}
                        for ref, parts in sorted(quotes.items())]
            organization = self.data(selected, 'organization', facts=facts)
            # An empty selection is still reviewed in the context of all source scopes.
            organization['data']['meta']['coverage_contexts'] = self.contexts(self.items)
            value = self.call(self.events_prompt, organization, 'sag_event_synthesis')
        with processing_step('sag_extract_result', parent_step_id='sag_extract') as details:
            details.update(value=value, operation_prefix=self.meta.get('operation_prefix'),
                           prepared_messages=list(self.request.messages), output=value)
        return AssistantModelOutput(content=json.dumps(value, ensure_ascii=False))


def generate(request, complete, validate=None):
    return Extraction(request, complete, validate).run()
