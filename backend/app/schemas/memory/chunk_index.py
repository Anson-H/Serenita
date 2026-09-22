"""Exact source-fragment vector identities and append-only delivery receipts."""
from pydantic import Field, model_validator
from backend.app.schemas.memory.index import IndexModel, Identifier, Digest, Text, VectorStatusInput


class ChunkVectorBindingInput(IndexModel):
    binding_id: Identifier
    chunk_id: Identifier
    event_id: Identifier
    space_id: Identifier
    vector_id: Identifier
    source_database: Text
    change_id: Identifier
    field_path: str
    character_start: int = Field(ge=0)
    character_end: int = Field(gt=0)
    rank: int = Field(ge=1)
    text_hash: Digest

    @model_validator(mode='after')
    def ordered_span(self):
        if self.character_end <= self.character_start:
            raise ValueError('原文片段结束位置必须晚于开始位置。')
        return self


class ChunkVectorStatusInput(VectorStatusInput):
    """Confirmation refers to one physically verified source_chunks record."""
