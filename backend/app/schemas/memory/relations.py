"""Immutable Event edges with fixed meaning and direction."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import AfterValidator, Field, model_validator

from backend.app.schemas.memory.values import MemoryModel, Text, canonical_uuid

Identifier = Annotated[str, AfterValidator(canonical_uuid)]
RelationType = Literal["Continues", "Supersedes", "ConflictsWith", "Cancels", "Duplicates", "Supplements", "Supports", "Precedes", "CausalClaim", "Contains"]
RELATION_TYPES = ("Continues", "Supersedes", "ConflictsWith", "Cancels", "Duplicates", "Supplements", "Supports", "Precedes", "CausalClaim", "Contains")
SYMMETRIC_RELATIONS = frozenset({"ConflictsWith"})
class RelationDecision(MemoryModel):
    from_event_id: Identifier = Field(description="实际读取的起点 Event UUID；有向关系遵循类型语义，对称关系任一端均可作为起点。")
    to_event_id: Identifier = Field(description="实际读取的另一个 Event UUID，不能与起点相同。")
    relation_type: RelationType = Field(description="创建时确定的十种关系之一；保存后不能改变。Supersedes 表示新事件更正旧事件，不取代任何已有边。")

    @model_validator(mode="after")
    def distinct_endpoints(self):
        if self.from_event_id == self.to_event_id:
            raise ValueError("Event 关系必须连接两个不同对象。")
        return self


class RelationDraft(RelationDecision):
    reason: Text = Field(description="根据两个事件及其原始依据，说明关系类型和方向的理由；必要细节、判断依据和不确定之处统一写在这里。")


class EventRelationInput(RelationDraft):
    relation_id: Identifier
