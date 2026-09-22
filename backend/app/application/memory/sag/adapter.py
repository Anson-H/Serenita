"""Validate native SAG results and preserve events, entities and evidence."""
from copy import deepcopy
import json

from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import stable_memory_id
from backend.app.schemas.memory.sag import SAGExtractionRequest
from backend.app.application.memory.sag.core import HostEventProcessor
from backend.app.domain.memory.entity_associations import entity_associations
from types import SimpleNamespace
from backend.app.application.memory.formation.stage_validation import extraction_errors, schema_errors


def fail(code, message, errors=None):
    raise SerenitaError('invalid_input', code, message,
        details={'validation_errors': errors} if errors else None)


def extraction_coverage(reads):
    """Give extraction the reading limits without internal queries or task identifiers."""
    scopes = {}
    for read in reads:
        if not read:
            continue
        refs = read.get('references') or (read.get('query') or {}).get('references') or []
        if refs and all(ref.get('object_type') in {'processing_attempt'} for ref in refs):
            continue
        coverage = read.get('coverage') or {}
        summary = {key: coverage[key] for key in ('object_types', 'matching_objects', 'returned_objects') if key in coverage}
        if 'complete' in read:
            summary['complete'] = read['complete']
        elif 'complete' in coverage:
            summary['complete'] = coverage['complete']
        for key in ('gaps', 'unread'):
            if read.get(key):
                summary[key] = read[key]
        if read.get('next_cursor'):
            summary['complete'] = False
        if summary:
            scopes[json.dumps(summary, ensure_ascii=False, sort_keys=True)] = summary
    return list(scopes.values())


def extraction_input(data):
    sources = {row['source_key']: row for row in data['change_sources'] if row['source_key'] in data['source_keys']}
    from backend.app.domain.memory.source_markdown import KINDS
    titles = list(dict.fromkeys(source.get('title') or KINDS.get(source['resource_type'], '业务记录') for source in sources.values()))
    processor = HostEventProcessor(MemoryPromptConfig.load('sag_extract'))
    fragments = source_fragments(sources)
    request = processor._build_input([SimpleNamespace(content=row['content']) for row in fragments],
        {'document_title': '；'.join(titles)}, 'ARTICLE')
    request['data']['meta'].update({key: data[key] for key in ('pipeline_stage', 'operation_prefix', 'record_cutoff',
        'retrieval', 'validation_errors', 'previous_output', 'entity_catalog') if key in data})
    if 'entity_catalog' in data:
        request['data']['meta']['entity_catalog'] = [
            {key: row[key] for key in ('entity_id', 'name', 'type', 'aliases')}
            for row in data['entity_catalog']]
    request['data']['meta']['coverage'] = extraction_coverage(data.get('coverage', []))
    positions = []
    for row in fragments:
        source = sources[row['source_key']]
        positions.append({**{key: row[key] for key in ('id', 'source_key', 'character_start', 'character_end', 'kind')},
            'document_context': source.get('document_context', {}),
            'section_heading': row['section_heading']})
    request['data']['meta']['source_fragments'] = positions
    return request


def extracted_events(items):
    """Flatten with SAG's original parser; host construction keeps raw fields."""
    from zleap.sag.modules.extract.parser import ResultParser
    next_index = 0

    def create_event(item, index_map, all_item_ids, context):
        nonlocal next_index
        event = SimpleNamespace(id=next_index, title=item['title'], raw_data=item)
        next_index += 1
        return event

    for event in ResultParser(create_event=create_event).parse_events(items, [], None):
        yield event.id, event.raw_data


class MemorySAGService:
    def __init__(self, memory, formation):
        self.memory, self.formation = memory, formation

    def validate(self, actor, member, values, *, binding, entity_catalog=None):
        request = SAGExtractionRequest.model_validate(values)
        self.formation.require_binding(actor, member, binding)
        schema = MemoryPromptConfig.load('sag_extract').schema('output')
        output = {'type': 'response', 'data': {'items': request.items, 'meta': request.meta}}
        errors = schema_errors(schema, output)
        sources = self.formation.require_change_reads(actor, member, request.source_keys, binding=binding)
        fragments = source_fragments(sources)
        if not errors:
            if entity_catalog is None:
                from backend.app.repositories.memory.facts.entity_catalog import entity_catalog as read_catalog
                entity_catalog = read_catalog(self.memory.repository, actor, member)
            errors.extend(extraction_errors(request.items, {row['id'] for row in fragments}, entity_catalog))
        if errors:
            fail(errors[0]['code'], errors[0]['message'], errors)
        return request, fragments, sources

    def append(self, actor, member, values, *, binding, entity_catalog=None):
        from backend.app.repositories.memory.indexing.sag_entities import entity_save_guard
        def check_running():
            import time
            self.formation.require_binding(actor, member, binding)
            plugin = binding.scope
            if plugin.cancellation_token is not None:
                plugin.cancellation_token.raise_if_cancelled()
            if plugin.deadline is not None and time.monotonic() >= plugin.deadline:
                raise SerenitaError('timeout', 'MEMORY_ENTITY_SAVE_TIMEOUT', '实体匹配与保存的时间预算已用尽。')
        with entity_save_guard(self.memory.repository, actor, member, check_running):
            return self._append(actor, member, values, binding=binding, entity_catalog=entity_catalog)

    def _append(self, actor, member, values, *, binding, entity_catalog=None):
        if entity_catalog is None:
            from backend.app.repositories.memory.facts.entity_catalog import entity_catalog as read_catalog
            entity_catalog = read_catalog(self.memory.repository, actor, member)
        request, fragments, sources = self.validate(actor, member, values, binding=binding, entity_catalog=entity_catalog)
        from backend.app.application.memory.sag.entity_resolution import resolve_entities
        batch = list(extracted_events(request.items))
        resolved = resolve_entities(batch, self.memory.repository, actor, member, request.operation_id, catalog=entity_catalog)
        events, entities, links, evidence, names = [], [], [], [], []
        extraction_mentions = {}
        op = request.operation_id
        identities = {index: stable_memory_id(member, op, 'event', str(index)) for index, _ in batch}
        created_entities = set()
        for index, event in batch:
            event_id = identities[index]
            used_keys = {fragments[ref - 1]['source_key'] for ref in event['references']}
            events.append({'event_id': event_id,
                'title': event['title'], 'summary': event['summary'], 'content': event['content'],
                'category': event['category'], 'priority': event['priority'],
                'occurrence_time': event.get('occurrence_time')})
            extraction_mentions[event_id] = deepcopy(event.get('entities', []))
            event_identities = {}
            for number, mention in enumerate(event.get('entities', [])):
                resolution = resolved.get((index, number))
                if resolution is None:
                    continue
                entity = resolution['entity']
                identity = entity['entity_id']
                extraction_mentions[event_id][number]['entity_id'] = identity
                extraction_mentions[event_id][number]['type'] = entity['type']
                for alias in resolution['aliases']:
                    names.append({'entity_id': identity, 'name_id': stable_memory_id(member, op, 'entity_name',
                        f'{index}-{number}-{alias}'), 'event_id': event_id, 'name': alias})
                key = (mention['type'], mention['name'])
                if key in event_identities and event_identities[key] != identity:
                    fail('MEMORY_ENTITY_IDENTITY_CONFLICT', '同一事件中的相同实体名称与类型不能指向不同身份。')
                event_identities[key] = identity
                if resolution['new'] and identity not in created_entities:
                    entities.append({'entity_id': identity, 'entity_type': entity['type'],
                        'canonical_name': entity['name'], 'event_id': event_id})
                    created_entities.add(identity)
            evidence.extend({'event_id': event_id, **sources[key]['reference']} for key in sorted(used_keys))
            links.extend(entity_associations(event_id, event.get('entities', []), event_identities))
        commit = self.memory.repository.write(actor, member, op, {
            'events': events, 'event_evidence': evidence, 'entities': entities,
            'event_entities': links, 'entity_names': names}, command={'extraction': request.model_dump(mode='json')}, extraction_mentions=extraction_mentions)
        return {'member_id': member, 'commit': commit, 'event_ids': {str(index): identities[index] for index, _ in batch},
            'index_context': {event_id: {
                'links': [row for row in links if row['event_id'] == event_id],
                'names': [row for row in names if row['event_id'] == event_id]} for event_id in identities.values()},
            'evidence': evidence, 'coverage': {'events': len(events), 'evidence': len(evidence)}, 'gaps': [], 'unread': []}

from backend.app.domain.memory.source_chunks import source_fragments
