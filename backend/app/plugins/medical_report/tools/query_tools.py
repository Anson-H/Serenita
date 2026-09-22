from __future__ import annotations
from copy import deepcopy
from backend.app.agent_runtime.tools.pagination import automatic_pages, paginated_collection

from typing import Any

from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.plugins.medical_report.tools.base import AccountBoundReportTool
from backend.app.schemas.report import DETAILED_REPORT_SELECTABLE_FIELDS


REPORT_CATALOG_LOGICAL_PAGE_SIZE = 24
REPORT_INFORMATION_LOGICAL_PAGE_SIZE = 12
LAB_DICTIONARY_LOGICAL_PAGE_SIZE = 100
REPORT_ANALYSIS_LOGICAL_PAGE_SIZE = 24




def _paginated_report_result(*, tool: AccountBoundReportTool, output: dict[str, Any], collection_field: str, page_size: int) -> ToolResult:
    source_refs = [
        {'resource_type': 'report_source', 'resource_id': source['resource_id'],
         'report_id': report['report_id'], 'member_id': tool.member_id}
        for report in output.get(collection_field, [])
        for source in report.get('sources', [])
    ]
    return paginated_collection(name=tool.name, output=output, collection_field=collection_field,
                                page_size=page_size, effects={
                                    "resource_refs": _report_resource_refs(tool, output, collection_field),
                                    **({'model_resource_refs': source_refs} if source_refs else {}),
                                })


def _report_resource_refs(
    tool: AccountBoundReportTool,
    output: dict[str, Any],
    collection_field: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    items = output.get(collection_field)
    if not isinstance(items, list):
        return refs
    for item in items:
        if not isinstance(item, dict):
            continue
        report_id = str(item.get("report_id") or "").strip()
        if not report_id or report_id in seen:
            continue
        seen.add(report_id)
        refs.append(tool.service.validate_report_context(tool.member_id, report_id))
    return refs


class ReadReportCatalogTool(AccountBoundReportTool):
    name = "read_report_catalog"
    description = "读取当前账号中匹配的医疗报告目录，返回用于定位医疗报告的目录信息。"
    input_schema = {
        "type": "object",
        "properties": {
            "before_date": {
                "type": "string",
                "description": "可选医疗报告日期上界（含当天），格式 YYYY-MM-DD；省略或传空字符串时不设上界。",
            },
            "after_date": {
                "type": "string",
                "description": "可选医疗报告日期下界（含当天），格式 YYYY-MM-DD；省略或传空字符串时不设下界。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = deepcopy(self._arguments(arguments))
        return automatic_pages(lambda cursor: _paginated_report_result(
            tool=self,
            output=self.service.read_report_catalog(
                self.member_id, **values, cursor=cursor, limit=REPORT_CATALOG_LOGICAL_PAGE_SIZE,
            ),
            collection_field="reports", page_size=REPORT_CATALOG_LOGICAL_PAGE_SIZE,
        ))


class ReadReportInformationTool(AccountBoundReportTool):
    name = "read_report_information"
    description = "读取匹配医疗报告的医疗报告事实。"
    input_schema = {
        "type": "object",
        "properties": {
            "report_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限定要读取的医疗报告 ID 列表；省略时读取 filters 匹配的全部医疗报告，传空数组时不返回医疗报告。",
            },
            "item_id": {
                "type": "string",
                "description": "检验指标的稳定 ID；传入非空值后每份检验报告只保留该指标的结果行，省略或传空字符串时不筛选指标，其他医疗报告类型不受影响。",
            },
            "filters": {
                "type": "object",
                "description": "医疗报告筛选条件；省略或传空对象时不按医疗报告类型筛选。",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["检验报告", "检查报告", "病理报告", "手术报告", "门诊病历", "急诊病历", "其它医疗报告"],
                        "description": "仅返回该类型的医疗报告。",
                    }
                },
                "additionalProperties": False,
            },
            "fields": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": sorted(DETAILED_REPORT_SELECTABLE_FIELDS),
                },
                "description": "要返回的可选字段列表；省略或传空数组时返回全部基础信息和结构化内容且不含 sources。选择 sources 时返回来源元数据并将来源原文交给模型。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        output = self.service.query_evidence(
            self.member_id, **self._arguments(arguments)
        )
        return _paginated_report_result(
            tool=self,
            output=output,
            collection_field="reports",
            page_size=REPORT_INFORMATION_LOGICAL_PAGE_SIZE,
        )


class ReadLabDictionaryTool(AccountBoundReportTool):
    name = "read_lab_dictionary"
    description = "读取当前账号的完整检验指标分类目录。"
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.read_lab_dictionary(self.member_id, **values)
        return _paginated_report_result(
            tool=self,
            output=output,
            collection_field="items",
            page_size=LAB_DICTIONARY_LOGICAL_PAGE_SIZE,
        )


class ReadReportAnalysisTool(AccountBoundReportTool):
    name = "read_report_analysis"
    description = "读取匹配医疗报告的既有解读结果。"
    input_schema = {
        "type": "object",
        "properties": {
            "report_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限定要读取解读结果的医疗报告 ID 列表；省略时读取全部存在解读结果的医疗报告，传空数组时不返回解读结果。",
            },
        },
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        values = self._arguments(arguments)
        output = self.service.read_report_analysis(self.member_id, **values)
        return _paginated_report_result(
            tool=self,
            output=output,
            collection_field="analyses",
            page_size=REPORT_ANALYSIS_LOGICAL_PAGE_SIZE,
        )
