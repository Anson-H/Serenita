"""Host-only save command; the SAG model contract is defined in sag_extract.yaml."""
from pydantic import Field
from backend.app.schemas.memory.append import MemoryModel, Text


class SAGExtractionRequest(MemoryModel):
    operation_id: Text
    source_keys: list[Text] = Field(min_length=1)
    items: list[dict]
    meta: dict
