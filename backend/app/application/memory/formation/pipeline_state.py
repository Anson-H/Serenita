"""Mutable state of one fixed generation pipeline and its serialized checkpoint."""
from copy import deepcopy
from dataclasses import dataclass, field
from backend.app.domain.memory.references import reference_key
from backend.app.core.errors import SerenitaError


@dataclass
class MemoryPipelineState:
    results: list = field(default_factory=list)
    references: dict = field(default_factory=dict)
    new_events: list = field(default_factory=list)
    retrieval: dict | None = None
    episode_groups: dict = field(default_factory=dict)
    created_episodes: set = field(default_factory=set)
    source_input: object = None
    source_input_step: dict | None = None
    extraction_input: object = None
    selected_episode_id: str | None = None
    sag_index_context: dict = field(default_factory=dict)

    def export(self):
        return deepcopy({'results': self.results, 'references': list(self.references.values()),
            'new_events': self.new_events, 'retrieval': self.retrieval,
            'episode_groups': self.episode_groups, 'created_episodes': sorted(self.created_episodes),
            'source_input': self.source_input, 'source_input_step': self.source_input_step,
            'extraction_input': self.extraction_input, 'selected_episode_id': self.selected_episode_id,
            'sag_index_context': self.sag_index_context})

    @classmethod
    def restore(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise SerenitaError('conflict', 'MEMORY_CHECKPOINT_DAMAGED', '流水线检查点字段与当前契约不同。')
        state = deepcopy(value)
        state['references'] = {reference_key(ref): ref for ref in state['references']}
        state['created_episodes'] = set(state['created_episodes'])
        return cls(**state)

    def export_preparation(self):
        return deepcopy({'source_input': self.source_input, 'source_input_step': self.source_input_step,
            'extraction_input': self.extraction_input, 'episode_groups': self.episode_groups})

    def restore_preparation(self, value):
        self.source_input = deepcopy(value['source_input'])
        self.source_input_step = deepcopy(value['source_input_step'])
        self.extraction_input = deepcopy(value['extraction_input'])
        self.episode_groups = deepcopy(value['episode_groups'])
