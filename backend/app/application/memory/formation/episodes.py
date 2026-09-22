"""Fixed episode scopes and complete append-only summary/state revisions."""
from typing import Literal
from pydantic import Field, model_validator
from backend.app.schemas.memory.relations import RelationDecision
from backend.app.core.errors import SerenitaError
from backend.app.application.memory.formation.judgments import MemoryJudgmentService, ReadJudgmentContext
from backend.app.schemas.memory.values import MemoryModel, Text, stable_memory_id
from backend.app.schemas.memory.episodes import Identifier


class UnrelatedDecision(MemoryModel):
    from_event_id: Identifier | None = None
    to_event_id: Identifier | None = None
    relation_type: Literal['Unrelated']
    scope: Text = Field(description="最终决定独立时，为当前新事件生成事项范围；创建后固定，用于判断事件归属。")


class OrganizeEventRequest(ReadJudgmentContext):
    event_id: Identifier
    episode_id: Identifier | None = None
    scope: Text | None = Field(default=None, description="新建事项的范围，创建后固定，用于判断事件归属；加入已有事项时为 null。")
    relation: RelationDecision | UnrelatedDecision | None = None
    reason: Text = Field(description="当前事件唯一的最终联合判断理由；在归属与关系确定后输出。独立时解释独立依据；加入时同时解释所属事项、连接事件、关系类型和方向，并原样用于归属和边关系。")

    @property
    def unrelated(self):
        return isinstance(self.relation, UnrelatedDecision)

    @model_validator(mode='after')
    def complete_decision(self):
        if self.unrelated:
            return self
        if self.episode_id is None:
            if self.scope is None or self.relation is not None:
                raise ValueError('独立事项必须提供固定范围，且不创建事件关系。')
        elif self.scope is not None or self.relation is None:
            raise ValueError('加入已有事项必须同时提供一条关系，不提供新事项范围。')
        elif self.event_id not in {self.relation.from_event_id, self.relation.to_event_id}:
            raise ValueError('关系必须连接当前新事件。')
        return self


class AppendEpisodeRevisionRequest(ReadJudgmentContext):
    episode_id: Identifier
    version: int = Field(ge=1)
    trigger_event_id: Identifier
    summary: Text = Field(description="整个事项截至当前输入的完整经过，包含关键事件、进展和转折；保留不确定内容。")
    state: Text = Field(description="事项当前的完整状态，说明实际时间、支持与反对的依据及未知部分。不能把计划、建议当作已经执行。")
    reason: Text = Field(description="本次新事件带来的变化；内容没有变化时也说明。")


class MemoryEpisodeService(MemoryJudgmentService):
    def organize(self, actor, member, values, *, binding):
        request = self._request(OrganizeEventRequest, actor, member, values, binding)
        episode_id = None if request.unrelated else request.episode_id
        scope = request.relation.scope if request.unrelated else request.scope
        reason = request.reason
        refs = [{"object_type": "event", "object_id": request.event_id}]
        if episode_id is not None:
            target = next(identity for identity in (request.relation.from_event_id, request.relation.to_event_id)
                if identity != request.event_id)
            refs.extend([{"object_type": "episode", "object_id": request.episode_id},
                {"object_type": "event", "object_id": target},
                {"object_type": "episode_membership", "object_id": target}])
        actual = self._read(actor, member, refs, request, binding)
        self._coverage(actor, member, request, binding, actual=actual)
        identity = episode_id or stable_memory_id(member, request.operation_id, 'episode', request.event_id)
        payload = {'episode_memberships': [{'event_id': request.event_id, 'episode_id': identity, 'reason': reason}]}
        if episode_id is None:
            payload['episodes'] = [{'episode_id': identity, 'scope': scope}]
        else:
            # The Repository checks the target membership again inside the write transaction.
            membership = next(row for row in actual.values() if row['object_type'] == 'episode_membership')
            if membership['episode_id'] != request.episode_id:
                raise SerenitaError('invalid_input', 'MEMORY_EPISODE_SCOPE', '连接事件不属于所选事项。')
            payload['event_relations'] = [{'relation_id': stable_memory_id(member, request.operation_id, 'event_relation', 'relation'),
                **request.relation.model_dump(mode='json'), 'reason': reason}]
        return self._append(actor, member, request, binding, payload)

    def revision(self, actor, member, values, *, binding, generation_input):
        request = self._request(AppendEpisodeRevisionRequest, actor, member, values, binding)
        refs = [
            {"object_type": "episode", "object_id": request.episode_id},
            {"object_type": "episode_membership", "object_id": request.trigger_event_id}]
        if request.version > 1:
            refs.append({"object_type": "episode_revision", "object_id": request.episode_id, "version": request.version - 1})
        actual = self._read(actor, member, refs, request, binding)
        self._coverage(actor, member, request, binding, actual=actual)
        value = request.model_dump(mode="json", exclude=set(ReadJudgmentContext.model_fields))
        receipt = generation_input['execution_receipt']
        if (receipt['request'].get('object_type') != 'memory_execution_entry'
                or receipt['result'].get('object_type') != 'memory_execution_entry'
                or receipt['request']['object_id'] != receipt['result']['object_id']
                or receipt['request']['object_id'] != binding.scope.task_id
                or generation_input.get('draft_scope') != binding.scope.task_id):
            raise SerenitaError('forbidden', 'MEMORY_REVISION_INPUT_INVALID', '事项版本的模型请求、结果与固定输入必须属于当前绑定的处理尝试。')
        origin = {'episode_id': request.episode_id, 'version': request.version,
            'attempt_id': receipt['request']['object_id'],
            'request_entry_id': receipt['request']['item_id'], 'result_entry_id': receipt['result']['item_id'],
            'fixed_input': generation_input['fixed_input'], 'draft_scope': generation_input['draft_scope']}
        return self._append(actor, member, request, binding, {
            'episode_revisions': [value], 'episode_revision_inputs': [origin]})

