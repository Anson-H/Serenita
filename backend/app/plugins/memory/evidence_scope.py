"""Adapt a conversation tool invocation to the shared evidence scope."""
from backend.app.application.memory.evidence_scope import MemoryEvidenceScope
from backend.app.core.errors import SerenitaError


def conversation_scope(context, plugin):
    if (context.account_id, context.member_id) != (plugin.account_id, plugin.member_id) or not context.member_id:
        raise SerenitaError('forbidden', 'MEMORY_TASK_SCOPE_MISMATCH', '记忆工具与当前任务成员不一致。')
    if not isinstance(context.turn_id, str) or not context.turn_id.strip():
        raise SerenitaError('forbidden', 'MEMORY_TASK_SCOPE_INVALID', '记忆工具必须绑定当前轮次的真实标识。')
    return MemoryEvidenceScope(context.account_id, context.member_id, context.turn_id,
        context.session_id, plugin.cancellation_token, plugin.deadline)
