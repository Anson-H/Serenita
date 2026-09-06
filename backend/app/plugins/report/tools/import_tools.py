from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.report.tools.base import AccountBoundReportTool
from backend.app.schemas.report import ExtractedReports


def _inline_schema_references(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_inline_schema_references(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        resolved = deepcopy(definitions[reference.rsplit("/", 1)[-1]])
        resolved.update({key: item for key, item in value.items() if key != "$ref"})
        return _inline_schema_references(resolved, definitions)
    return {
        key: _inline_schema_references(item, definitions)
        for key, item in value.items()
        if key != "$defs"
    }


_REPORT_SCHEMA = ExtractedReports.model_json_schema()
_REPORTS_SCHEMA = _inline_schema_references(
    _REPORT_SCHEMA["properties"]["reports"], _REPORT_SCHEMA.get("$defs", {})
)
_PARSED_REPORT_SCHEMA = deepcopy(_REPORTS_SCHEMA["items"])

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
                    "description": "来源类型：已保存的报告原件。",
                },
                "read_call_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "返回该原件的 `read_report_information` 工具调用 ID。",
                },
                "report_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "该原件当前关联的报告 ID。",
                },
                "resource_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "该报告原件的资源 ID。",
                },
            },
            "additionalProperties": False,
        },
    ]
}

class ValidateParsedReportsTool(AccountBoundReportTool):
    name = "validate_parsed_reports"
    description = "校验一批最终医疗报告并返回完整解析校验结果。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["reports"],
        "properties": {
            "reports": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "description": "要共同校验的 1 至 100 份最终医疗报告，每项由来源引用和对应报告内容组成。",
                "items": {
                    "type": "object",
                    "required": ["sources", "report"],
                    "properties": {
                        "sources": {
                            "type": "array",
                            "minItems": 1,
                            "items": deepcopy(_SOURCE_REFERENCE_SCHEMA),
                            "description": "支持该报告事实的来源引用列表；至少一项，同一来源多次出现时只保留一项。",
                        },
                        "report": {
                            **deepcopy(_PARSED_REPORT_SCHEMA),
                            "description": "该医疗报告的基础信息和结构化内容。",
                        },
                    },
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": False,
    }

    def input_schema_for_context(self, context: Any) -> dict[str, Any]:
        schema = deepcopy(self.input_schema)
        allowed = sorted(
            str(value)
            for value in (context.memory.get("visible_attachments") or {})
        )
        attachment_schema = schema["properties"]["reports"]["items"]["properties"][
            "sources"
        ]["items"]["oneOf"][1]
        attachment_schema["properties"]["resource_id"]["enum"] = allowed
        return schema

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.validate_parsed_reports(
            self.member_id,
            reports=list(values["reports"]),
            session_id=str(values.get("session_id") or ""),
            source_message_id=str(values.get("source_message_id") or ""),
            source_text=str(values.get("source_text") or ""),
            visible_attachments=dict(values.get("visible_attachments") or {}),
            authorized_report_sources=dict(
                values.get("authorized_report_sources") or {}
            ),
        )
        return ToolResult(self.name, output, _parsed_batch_retention_effect())


class _ParsedReportWriteTool(AccountBoundReportTool):
    bind_conversation = True

    @staticmethod
    def common_properties() -> dict[str, Any]:
        return {
            "parse_call_id": {
                "type": "string",
                "minLength": 1,
                "description": "产生目标完整解析校验结果的 `validate_parsed_reports` 工具调用 ID。",
            },
            "report_index": {
                "type": "integer",
                "minimum": 0,
                "description": "目标报告项在完整解析校验结果 reports 数组中的零基索引；该项提供要处理的报告事实和全部已验证来源。",
            },
        }

    def _write_values(self, arguments: dict[str, Any]) -> dict[str, Any]:
        # 完整语料是强建议而非放行条件：只要本轮存在可信校验 Observation，
        # 未读齐语料也允许写入；若观测过语料版本，服务端仍会做 CAS 校验。
        return self._arguments(arguments)


class CreateReportTool(_ParsedReportWriteTool):
    name = "create_report"
    description = "将完整解析校验结果中的一份医疗报告写入报告档案库，返回创建结果。"
    input_schema = {
        "type": "object",
        "required": ["parse_call_id", "report_index"],
        "properties": {
            **_ParsedReportWriteTool.common_properties(),
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._write_values(arguments)
        output = self.service.create_report_from_parsed(
            self.member_id,
            parse_call_id=str(values["parse_call_id"]),
            report_index=int(values["report_index"]),
            **_trusted_write_arguments(values),
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
                **_resolved_parse_effect(values),
            },
        )


class LinkDuplicateSourcesTool(_ParsedReportWriteTool):
    name = "link_duplicate_sources"
    description = "将已验证来源关联到一份既有医疗报告，返回关联结果。"
    input_schema = {
        "type": "object",
        "required": ["parse_call_id", "report_index", "target_report_id"],
        "properties": {
            **_ParsedReportWriteTool.common_properties(),
            "target_report_id": {
                "type": "string",
                "minLength": 1,
                "description": "接收目标报告项全部已验证来源的既有医疗报告 ID；该操作仅追加来源，并保留已有基础信息和结构化内容。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._write_values(arguments)
        output = self.service.link_parsed_report_sources(
            self.member_id,
            parse_call_id=str(values["parse_call_id"]),
            report_index=int(values["report_index"]),
            target_report_id=str(values["target_report_id"]),
            **_trusted_write_arguments(values),
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
                **_resolved_parse_effect(values),
            },
        )


class MergeReportTool(_ParsedReportWriteTool):
    name = "merge_report"
    description = "将新增报告事实和来源合并到一份既有医疗报告，返回合并结果。"
    input_schema = {
        "type": "object",
        "required": ["parse_call_id", "report_index", "target_report_id"],
        "properties": {
            **_ParsedReportWriteTool.common_properties(),
            "target_report_id": {
                "type": "string",
                "minLength": 1,
                "description": "接收目标报告项缺失字段、新检验指标和已验证来源的既有医疗报告 ID；已有字段值不同或指标映射冲突时整次合并失败。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._write_values(arguments)
        output = self.service.merge_parsed_report(
            self.member_id,
            parse_call_id=str(values["parse_call_id"]),
            report_index=int(values["report_index"]),
            target_report_id=str(values["target_report_id"]),
            **_trusted_write_arguments(values),
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
                **_resolved_parse_effect(values),
            },
        )


def _parsed_batch_retention_effect() -> dict[str, Any]:
    return {
        "context_retention": {
            "collection_field": "reports",
            "index_field": "report_index",
        }
    }


def _resolved_parse_effect(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolved_context_items": [
            {
                "call_id": str(values["parse_call_id"]),
                "index": int(values["report_index"]),
            }
        ]
    }


def _trusted_write_arguments(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(values.get("session_id") or ""),
        "visible_message_ids": {
            str(item) for item in values.get("visible_message_ids", [])
        },
    }
