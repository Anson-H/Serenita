from __future__ import annotations

from pathlib import Path

from backend.app.agent_runtime.skills.loader import DirectorySkill, discover_skills
from backend.app.agent_runtime.tools.base import Tool
from backend.app.application.report_service import ReportService
from backend.app.plugins.runtime_context import PluginRuntimeContext
from backend.app.plugins.medical_report.tools import (
    AddLabReportItemsTool,
    CreateReportTool,
    DeleteLabReportItemsTool,
    DeleteReportTool,
    LinkDuplicateSourcesTool,
    MergeReportTool,
    ReadLabDictionaryTool,
    ReadReportAnalysisTool,
    ReadReportCatalogTool,
    ReadReportInformationTool,
    ReclassifyReportTool,
    UpdateReportFieldsTool,
    WriteReportAnalysisTool,
)


PLUGIN_ID = "medical_report"
SKILLS_ROOT = Path(__file__).resolve().parent / "skills"


def build_skills() -> list[DirectorySkill]:
    return discover_skills(SKILLS_ROOT)


def build_tools(*, runtime_context: PluginRuntimeContext) -> list[Tool]:
    account_id = runtime_context.account_id
    member_id = runtime_context.member_id
    if not member_id:
        return []
    service = runtime_context.service(
        PLUGIN_ID, lambda: ReportService.for_member(account_id, member_id)
    )
    return [
        ReadReportCatalogTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        ReadReportInformationTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        ReadReportAnalysisTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        ReadLabDictionaryTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        CreateReportTool(account_id=account_id, member_id=member_id, service=service),
        LinkDuplicateSourcesTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        MergeReportTool(account_id=account_id, member_id=member_id, service=service),
        WriteReportAnalysisTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        UpdateReportFieldsTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        AddLabReportItemsTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        DeleteLabReportItemsTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        ReclassifyReportTool(
            account_id=account_id, member_id=member_id, service=service
        ),
        DeleteReportTool(account_id=account_id, member_id=member_id, service=service),
    ]


from backend.app.plugins.medical_report.resources import (
    resolve_input_model_resource as resolve_input_model_resource,
    resolve_model_resource as resolve_model_resource,
    resolve_resource as resolve_resource,
    resolve_resource_state as resolve_resource_state,
)
