from __future__ import annotations
from backend.app.schemas.report import REPORT_AGENT_EDITABLE_FIELDS

from typing import Any

from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.medical_report.tools.import_tools import ParsedReportWriteTool, trusted_source_arguments
from backend.app.plugins.medical_report.tools.base import AccountBoundReportTool


def _effects(tool: AccountBoundReportTool, report_id: str, change: str) -> dict[str, Any]:
    return {
        "resource_refs": (
            [tool.service.validate_report_context(tool.member_id, report_id)]
            if tool.service.report_exists(tool.member_id, report_id)
            else []
        ),
        "changed_entities": [
            {"entity_type": "report", "entity_id": report_id, "change": change}
        ],
    }


class UpdateReportFieldsTool(AccountBoundReportTool):
    name = "update_report_fields"
    description = "更新一份医疗报告的基础信息或结构化内容，返回更新后的医疗报告。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id", "updates"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要更新的医疗报告 ID。",
            },
            "updates": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "description": "要在同一事务中执行的字段更新列表；任一更新无效时整次更新失败。",
                "items": {
                    "type": "object",
                    "required": ["field", "value"],
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": sorted(REPORT_AGENT_EDITABLE_FIELDS),
                            "description": "要更新的结构化字段名。",
                        },
                        "value": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "字段的新值；必填字段不可清空，可选字段可传空值清空。",
                        },
                        "item_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "field 为 lab_result、lab_reference 或 lab_flag 时必填，用于定位目标检验指标；更新其它字段时省略。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        report_id = str(values["report_id"])
        output = self.service.update_report_fields(
            self.member_id,
            report_id,
            updates=[dict(item) for item in values["updates"]],
        )
        return ToolResult(
            self.name,
            output,
            _effects(self, report_id, "fields_updated"),
        )


class AddLabReportItemsTool(AccountBoundReportTool):
    name = "add_lab_report_items"
    description = "向一份检验报告添加检验指标记录，返回更新后的医疗报告。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id", "items"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要添加指标记录的检验报告 ID。",
            },
            "items": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "description": "要在同一事务中添加到目标医疗报告的指标记录列表；任一记录无效时整次添加失败。",
                "items": {
                    "type": "object",
                    "required": ["item_id", "result_text"],
                    "properties": {
                        "item_id": {
                            "type": "string",
                            "minLength": 1,
                            "description": "当前账号检验指标分类目录中的稳定指标 ID；主分类必须与目标医疗报告一致，且目标医疗报告尚未包含该指标。",
                        },
                        "result_text": {
                            "type": "string",
                            "minLength": 1,
                            "description": "包含数值与单位的检验结果原文。",
                        },
                        "reference_text": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "参考值或参考范围原文；未知时传空值或省略。",
                        },
                        "flag_text": {
                            "type": "string",
                            "enum": ["未标记", "正常", "异常", "偏高", "偏低"],
                            "description": "结果标记；省略时为未标记。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        report_id = str(values["report_id"])
        output = self.service.add_lab_report_items(
            self.member_id,
            report_id,
            items=[dict(item) for item in values["items"]],
        )
        return ToolResult(
            self.name,
            output,
            _effects(self, report_id, "lab_items_added"),
        )


class DeleteLabReportItemsTool(AccountBoundReportTool):
    name = "delete_lab_report_items"
    description = "从一份检验报告删除检验指标记录，返回更新后的医疗报告。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id", "item_ids"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要删除指标记录的检验报告 ID。",
            },
            "item_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
                "description": "要从目标医疗报告中删除的指标 ID 列表；删除后目标医疗报告必须至少保留一项指标，检验指标分类目录中的指标定义保持不变。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        report_id = str(values["report_id"])
        output = self.service.delete_lab_report_items(
            self.member_id,
            report_id,
            item_ids=[str(item) for item in values["item_ids"]],
        )
        return ToolResult(
            self.name,
            output,
            _effects(self, report_id, "lab_items_deleted"),
        )


class ReclassifyReportTool(ParsedReportWriteTool):
    name = "reclassify_report"
    description = "使用经过校验的新结构重分类一份医疗报告，返回重分类后的医疗报告。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id", "report", "sources"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要重分类的既有医疗报告 ID；重分类后保留执行时的医疗报告时间和全部已保存来源。",
            },
            **ParsedReportWriteTool.common_properties(),
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        report_id = str(values["report_id"])
        output = self.service.reclassify_report(
            self.member_id,
            report_id,
            report=dict(values["report"]),
            sources=list(values["sources"]),
            **trusted_source_arguments(values),
        )
        return ToolResult(self.name, output, _effects(self, report_id, "reclassified"))


class DeleteReportTool(AccountBoundReportTool):
    name = "delete_report"
    description = "删除一份医疗报告及其已保存内容，返回删除结果。"
    bind_conversation = True
    input_schema = {
        "type": "object",
        "required": ["report_id"],
        "properties": {
            "report_id": {
                "type": "string",
                "minLength": 1,
                "description": "要删除的医疗报告 ID。",
            }
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        report_id = str(values["report_id"])
        affected_resource = self.service.validate_report_context(
            self.member_id, report_id
        )
        output = self.service.delete_report(
            self.member_id,
            report_id,
        )
        return ToolResult(
            self.name,
            output,
            {
                "affected_resource_refs": [affected_resource],
                "changed_entities": [
                    {"entity_type": "report", "entity_id": report_id, "change": "deleted"}
                ],
            },
        )
