from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.agent_runtime.tools.parameters import model_parameters
from backend.app.plugins.medical_report.tools.base import AccountBoundReportTool
from backend.app.schemas.report import ParsedReport


_PARSED_REPORT_SCHEMA = model_parameters(ParsedReport)

_SOURCE_REFERENCE_SCHEMA = {
    "oneOf": [
        {
            "type": "object",
            "required": ["source_type"],
            "properties": {
                "source_type": {
                    "type": "string",
                    "const": "conversation_text",
                    "description": "来源类型：当前用户消息正文。",
                },
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["source_type", "resource_id"],
            "properties": {
                "source_type": {
                    "type": "string",
                    "const": "conversation_attachment",
                    "description": "来源类型：当前会话附件。",
                },
                "resource_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "当前可见附件的资源 ID。",
                },
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["source_type", "read_call_id", "report_id", "resource_id"],
            "properties": {
                "source_type": {
                    "type": "string",
                    "const": "report_source",
                    "description": "来源类型：已保存的医疗报告原件。",
                },
                "read_call_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "返回该原件的 `read_report_information` 工具调用 ID。",
                },
                "report_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "该原件当前关联的医疗报告 ID。",
                },
                "resource_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "该医疗报告原件的资源 ID。",
                },
            },
            "additionalProperties": False,
        },
    ]
}


class ParsedReportWriteTool(AccountBoundReportTool):
    bind_conversation = True
    bind_report_sources = True

    @staticmethod
    def common_properties() -> dict[str, Any]:
        return {
            "report": {
                **deepcopy(_PARSED_REPORT_SCHEMA),
                "description": "待写入医疗报告的基础信息和结构化内容；工具在写入前校验结构、时间、名称及检验指标分类，校验失败时不写入。",
            },
            "sources": {
                "type": "array",
                "minItems": 1,
                "items": deepcopy(_SOURCE_REFERENCE_SCHEMA),
                "description": "支持医疗报告事实的来源引用；至少一项，同一来源不能重复。工具校验来源权限及文件完整性，正文和文件路径由系统提供。",
            },
        }

    def input_schema_for_context(self, context: Any) -> dict[str, Any]:
        schema = deepcopy(self.input_schema)
        attachment = schema["properties"]["sources"]["items"]["oneOf"][1]
        attachment["properties"]["resource_id"]["enum"] = sorted(
            str(value) for value in (context.memory.get("visible_attachments") or {})
        )
        return schema

class CreateReportTool(ParsedReportWriteTool):
    name = "create_report"
    description = "将一份医疗报告写入医疗报告档案库，返回创建结果。"
    input_schema = {
        "type": "object",
        "required": ["report", "sources"],
        "properties": {
            **ParsedReportWriteTool.common_properties(),
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.create_report_from_parsed(
            self.member_id,
            report=dict(values["report"]),
            sources=list(values["sources"]),
            **trusted_source_arguments(values),
        )
        return ToolResult(
            self.name,
            output,
            {
                "resource_refs": [
                    self.service.validate_report_context(self.member_id, output["report_id"])
                ],
                "created_entities": [
                    {"entity_type": "report", "entity_id": output["report_id"]}
                ],
            },
        )


class LinkDuplicateSourcesTool(ParsedReportWriteTool):
    name = "link_duplicate_sources"
    description = "将来源关联到一份既有医疗报告，返回关联结果。"
    input_schema = {
        "type": "object",
        "required": ["report", "sources", "target_report_id"],
        "properties": {
            **ParsedReportWriteTool.common_properties(),
            "target_report_id": {
                "type": "string",
                "minLength": 1,
                "description": "接收提交来源的既有医疗报告 ID；该操作仅追加来源，并保留已有基础信息和结构化内容。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.link_parsed_report_sources(
            self.member_id,
            report=dict(values["report"]),
            sources=list(values["sources"]),
            target_report_id=str(values["target_report_id"]),
            **trusted_source_arguments(values),
        )
        return ToolResult(
            self.name,
            output,
            {
                "resource_refs": [
                    self.service.validate_report_context(self.member_id, output["report_id"])
                ],
                "changed_entities": [
                    {"entity_type": "report", "entity_id": output["report_id"], "change": "source_linked"}
                ],
            },
        )


class MergeReportTool(ParsedReportWriteTool):
    name = "merge_report"
    description = "将补充的医疗报告事实和来源合并到一份既有医疗报告，返回合并结果。"
    input_schema = {
        "type": "object",
        "required": ["report", "sources", "target_report_id"],
        "properties": {
            **ParsedReportWriteTool.common_properties(),
            "target_report_id": {
                "type": "string",
                "minLength": 1,
                "description": "接收缺失字段、新检验指标和来源的既有医疗报告 ID；已有字段值不同或指标映射冲突时整次合并失败。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.merge_parsed_report(
            self.member_id,
            report=dict(values["report"]),
            sources=list(values["sources"]),
            target_report_id=str(values["target_report_id"]),
            **trusted_source_arguments(values),
        )
        return ToolResult(
            self.name,
            output,
            {
                "resource_refs": [
                    self.service.validate_report_context(self.member_id, output["report_id"])
                ],
                "changed_entities": [
                    {"entity_type": "report", "entity_id": output["report_id"], "change": "merged"}
                ],
            },
        )


def trusted_source_arguments(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(values.get("session_id") or ""),
        "source_message_id": str(values.get("source_message_id") or ""),
        "source_text": str(values.get("source_text") or ""),
        "visible_attachments": dict(values.get("visible_attachments") or {}),
        "authorized_report_sources": dict(values.get("authorized_report_sources") or {}),
    }
