from __future__ import annotations

from typing import Any

from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.web.citations import report_citation_markdown
from backend.app.plugins.report.tools.base import AccountBoundReportTool


class WriteReportAnalysisTool(AccountBoundReportTool):
    name = "write_report_analysis"
    description = "将解读结果写入报告档案库中的目标医疗报告，返回保存结果。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id", "analysis_content"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要写入解读结果的目标医疗报告 ID。",
            },
            "analysis_content": {
                "type": "string",
                "minLength": 1,
                "description": "要保存到目标医疗报告的完整 Markdown 解读结果正文；不可为空。联网引用使用当前轮次搜索结果或网页正文返回的 [cite:引用标识]，服务端依据工具观测转换为 Markdown 链接；无法解析的标识使写入失败。代码和转义文本保持原样。",
            },
        },
        "additionalProperties": False,
    }

    def bind_runtime_arguments(self, arguments, *, context, observations):
        bound = super().bind_runtime_arguments(arguments, context=context, observations=observations)
        bound["analysis_content"] = report_citation_markdown(bound["analysis_content"], observations)
        return bound

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        normalized = self._arguments(arguments)
        report_id = str(normalized.get("report_id") or "").strip()
        analysis_content = str(normalized.get("analysis_content") or "").strip()
        output = self.service.write_report_analysis(
            self.member_id,
            report_id=report_id,
            analysis_content=analysis_content,
            session_id=str(normalized.get("session_id") or ""),
            source_message_id=str(normalized.get("source_message_id") or ""),
        )
        return ToolResult(
            name=self.name,
            output=output,
            effects={
                "resource_refs": [
                    self.service.validate_report_context(self.member_id, report_id)
                ],
                "changed_entities": [
                    {"entity_type": "report", "entity_id": report_id, "change": "analysis_written"}
                ],
            },
        )
