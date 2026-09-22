"""Fixed memory stages: each model returns domain data for one program-owned step."""
from dataclasses import dataclass
from functools import cached_property
from typing import Callable
from enum import StrEnum
from backend.app.application.memory.prompt_config import MemoryPromptConfig

from backend.app.application.memory.sag.adapter import MemorySAGService, extraction_input, extracted_events
from backend.app.schemas.memory.sag import SAGExtractionRequest
from backend.app.application.memory.formation.episodes import (
    MemoryEpisodeService,
    AppendEpisodeRevisionRequest, OrganizeEventRequest,
)

HOST_FIELDS = frozenset({'timezone', 'operation_id', 'input_sequence', 'coverage_receipts', 'counterevidence_receipts',
    'version', 'record_cutoff', 'read_receipt', 'processing_updates', 'embedding_model_id', 'previous_attempt_id'})


class MemoryLayer(StrEnum):
    SAG = 'sag'
    EVENT_ORGANIZATION = 'event_organization'


STAGE_LAYERS = {
    'sag_extract': MemoryLayer.SAG,
    **dict.fromkeys(('event_organization', 'revisions'), MemoryLayer.EVENT_ORGANIZATION),
}


@dataclass(frozen=True)
class StageOutput:
    name: str
    schema: type
    save: Callable


@dataclass(frozen=True)
class MemoryStage:
    name: str
    outputs: tuple[StageOutput, ...]
    requires: tuple[str, ...] = ()

    @property
    def layer(self):
        return STAGE_LAYERS[self.name]

    def drafts(self, value, group):
        return value.get(group.name, [])

    def reason(self, value):
        return value['reason']

    def request_data(self, data):
        from backend.app.application.memory.formation.stage_input import stage_input
        return stage_input(data)

    @cached_property
    def config(self):
        return MemoryPromptConfig.load(self.name)

    def prompt(self):
        return self.config.prompt()

    def output_schema(self):
        return self.config.schema('output')


    def generate(self, request, complete, validate=None):
        from backend.app.application.memory.formation.stage_validation import complete_once
        return complete_once(complete, request)


class EventOrganizationStage(MemoryStage):
    def drafts(self, value, group):
        return [value]


class SAGExtractionStage(MemoryStage):
    def drafts(self, value, group):
        return [value['data']] if any(extracted_events(value['data']['items'])) else []

    def reason(self, value):
        return value['data']['meta']['reason']

    def request_data(self, data):
        return extraction_input(data)

    def generate(self, request, complete, validate=None):
        from backend.app.application.memory.sag.long_extraction import generate
        return generate(request, complete, validate)


def formation_stages(memory, formation):
    episodes = MemoryEpisodeService(memory, formation)
    return (
        SAGExtractionStage('sag_extract', (StageOutput('extraction', SAGExtractionRequest, MemorySAGService(memory, formation).append),)),
        EventOrganizationStage('event_organization', (StageOutput('organizations', OrganizeEventRequest, episodes.organize),)),
        MemoryStage('revisions', (StageOutput('revisions', AppendEpisodeRevisionRequest, episodes.revision),), ('episode_membership',)),
    )
