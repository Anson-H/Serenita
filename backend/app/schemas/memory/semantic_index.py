"""Entity-name and event/entity-role vector bindings with exact text provenance."""
from typing import Literal
from pydantic import model_validator
from backend.app.schemas.memory.index import IndexModel, Identifier, Text, Digest, VectorStatusInput


class SemanticVectorBindingInput(IndexModel):
    binding_id: Identifier
    entity_id: Identifier
    event_id: Identifier | None = None
    name_id: Identifier | None = None
    space_id: Identifier
    vector_id: Identifier
    index_kind: Literal['entity_name', 'entity_role']
    text_hash: Digest

    @model_validator(mode='after')
    def exact_target(self):
        if self.index_kind == 'entity_role' and self.name_id is not None:
            raise ValueError('实体作用向量不能引用名称明细。')
        if (self.index_kind == 'entity_role') != (self.event_id is not None):
            raise ValueError('实体作用向量必须指定事件；名称向量通过实体或别名读取依据事件。')
        return self


class SemanticVectorStatusInput(VectorStatusInput):
    """Same append-only delivery states, referring to a semantic binding."""
