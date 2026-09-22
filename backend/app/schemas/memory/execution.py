"""Immutable execution ownership and the actual sequence of Harness evidence."""
from typing import Literal
from pydantic import Field, JsonValue, field_validator
from backend.app.schemas.memory.values import MemoryModel, MemoryReference, Text, local_time_value, canonical_uuid


class MemoryExecutionEntryInput(MemoryModel):
    attempt_id: Text
    entry_id: Text
    entry_sequence: int = Field(ge=1)
    entry_kind: Literal['model_request', 'model_result']
    payload: dict[str, JsonValue]
    dependencies: list[MemoryReference] = Field(default_factory=list, max_length=2000)
    _ids = field_validator('attempt_id', 'entry_id')(canonical_uuid)


class MemoryProcessingStepInput(MemoryModel):
    attempt_id: Text
    progress_id: Text
    step_id: Text
    parent_step_id: Text | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: Text | None = None
    error_message: Text | None = None
    status: Literal['running', 'retrying', 'completed', 'failed', 'skipped']
    _ids = field_validator('attempt_id', 'progress_id')(canonical_uuid)
