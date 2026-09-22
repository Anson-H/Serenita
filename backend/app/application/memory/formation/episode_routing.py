"""Select one episode by scope without committing event membership."""
import json
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.application.memory.prompt_config import MemoryPromptConfig
from backend.app.domain.memory.references import object_reference
from backend.app.application.memory.progress import processing_step, call_operation, report_progress
from backend.app.domain.memory.stage_facts import project_object
from backend.app.application.memory.processing.checkpoint_runtime import freeze_input
from backend.app.application.memory.formation.stage_validation import (
    complete_once, parse_stage_output, require_valid,
    retry_errors, routing_errors, schema_errors, wait_for_stage_retry,
)
from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS
from backend.app.repositories.memory.reading.episode_context import MemoryEpisodeContextRepository
from backend.app.core.errors import SerenitaError


class MemoryEpisodeRouting:
    def __init__(self, memory, complete, guard, retain):
        self.memory, self.complete, self.guard, self.retain = memory, complete, guard, retain
        self.repository = MemoryEpisodeContextRepository(memory.repository)

    def select(self, actor, member, event, cutoff):
        config = MemoryPromptConfig.load('episode_search')
        with processing_step('episode_search', input={'event_id': event['event_id'], 'record_cutoff': cutoff}) as details:
            catalog = freeze_input('episode_search_catalog:' + event['event_id'], lambda:
                call_operation('读取事项范围目录', {'record_cutoff': cutoff},
                    lambda: self.repository.catalog(actor, member, cutoff)))
            data = {'pipeline_stage': 'episode_search', 'event': project_object(event),
                'episodes': [{key: row[key] for key in ('episode_id', 'scope')} for row in catalog]}
            config.validate_input(data)
            self.retain(data)
            allowed = {row['episode_id'] for row in catalog}
            value = {'episode_id': None}
            if catalog:
                for repair in range(MAX_MODEL_ATTEMPTS):
                    self.guard()
                    try:
                        output = complete_once(self.complete, ModelRequest.build(system=config.prompt(),
                            messages=[{'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                            tools=(), tool_choice=None, output_schema=config.schema('output')))
                        self.guard()
                        value = parse_stage_output(output)
                        require_valid(schema_errors(config.schema('output'), value))
                        require_valid(routing_errors(value, allowed))
                        break
                    except Exception as error:
                        errors = retry_errors(error)
                        if errors is None:
                            if repair == MAX_MODEL_ATTEMPTS - 1:
                                raise
                            wait_for_stage_retry(error, repair + 1, self.complete, check_running=self.guard)
                            continue
                        details['validation_errors'] = errors
                        if repair == MAX_MODEL_ATTEMPTS - 1:
                            raise SerenitaError('invalid_input', 'MEMORY_EPISODE_SELECTION_INVALID',
                                '事项目录筛选结果校验失败：' + str(error), details={'validation_errors': errors}) from error
                        data.update(validation_errors=errors, previous_output=output.content)
                        report_progress('episode_search', 'retrying', error_code='MEMORY_EPISODE_SELECTION_INVALID',
                            error_message=str(error), details={'event_id': event['event_id']})
                # The scope directory is evidence for the choice, not a durable authorization.
                for offset in range(0, len(catalog), 100):
                    self.memory.repository.check_references(actor, member,
                        [object_reference(row) for row in catalog[offset:offset + 100]], record_cutoff=cutoff)
            details['output'] = {**value, 'catalog_size': len(catalog), 'record_cutoff': cutoff}
            return details['output']
