"""Declared coverage of actual business changes and memory time ranges."""
from pydantic import Field,JsonValue,model_validator
from backend.app.schemas.memory.values import MemoryModel,SourceCategory,Text,MemoryTime
from backend.app.schemas.memory.evidence import ChangeReference

class ReadCoverage(MemoryModel):
    source_category: SourceCategory
    source_database: Text
    change_sequence: int | None = Field(default=None, ge=1)
    target_time: MemoryTime = Field(default_factory=MemoryTime)
    filters: dict[str, JsonValue] = Field(default_factory=dict)
    business_changes: list[dict[str, str]] = Field(default_factory=list)
    unread: list[str] = Field(default_factory=list)
    complete: bool = False

    @model_validator(mode="after")
    def truthful_coverage(self):
        self.business_changes=[ChangeReference.model_validate(ref).model_dump() for ref in self.business_changes]

        if self.complete and self.unread:
            raise ValueError("存在未读内容时不能声明完整覆盖。")
        return self

