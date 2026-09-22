"""Shared server-owned proof, read coverage and append contract for judgments."""

from pydantic import Field

from backend.app.domain.memory.references import reference_key
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import MemoryWrite
from backend.app.schemas.memory.values import MemoryModel, Text


class ReadJudgmentContext(MemoryModel):
    operation_id: Text = Field(max_length=200, description="本次追加的稳定操作标识；同一参数重试保持不变，改变判断使用新标识。")
    input_sequence: int = Field(ge=0, description="实际读取结果的成功提交截点；必须与所选范围读取凭据一致，不得自行提升截点。")
    coverage_receipts: list[Text] = Field(min_length=1, max_length=20, description="当前轮次实际读取结果的 coverage_read_receipt，至少一项；服务取得真实查询、来源类别、变更进度及已读未读范围，模型不能填写覆盖内容。")


class MemoryJudgmentService:
    def __init__(self, memory, formation):
        self.memory, self.formation = memory, formation

    def _request(self, schema, actor, member, values, binding):
        self.formation.require_binding(actor, member, binding)
        return self.memory._validate(schema, values)

    def _read(self, actor, member, references, request, binding, *, require_sources=True):
        refs = list({reference_key(value): value for value in references}.values())
        return self.formation.require_read_objects(actor, member, refs, binding=binding,
            record_cutoff=request.input_sequence, require_sources=require_sources)

    def _coverage(self, actor, member, request, binding, *, actual):
        if len(set(request.coverage_receipts)) != len(request.coverage_receipts):
            raise SerenitaError('invalid_input', 'MEMORY_COVERAGE_DUPLICATE', '范围读取凭据不能重复。')
        for receipt in request.coverage_receipts:
            observed = binding.coverage_reads.get(receipt)
            if observed is None or observed['record_cutoff'] != request.input_sequence:
                raise SerenitaError('forbidden', 'MEMORY_COVERAGE_NOT_READ', '输入范围必须来自当前任务同一截点的实际读取。')
            self.memory.repository.evidence.require_coverage(actor, member, observed, request.input_sequence)

    @staticmethod
    def _command(request):
        return request.model_dump(mode="json", exclude={"coverage_receipts"})

    def _append(self, actor, member, request, binding, payload):
        batch = self.memory._validate(MemoryWrite, payload)
        commit = self.memory.repository.write(actor, member, request.operation_id, batch, command=self._command(request))
        return {"member_id": member, "commit": commit, "references": [item for values in commit["objects"].values() for item in values], "gaps": [], "unread": []}

