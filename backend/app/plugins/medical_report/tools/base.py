from __future__ import annotations

from typing import Any, Protocol, Optional, Iterable

from backend.app.agent_runtime.tools.base import Tool


class ReportToolService(Protocol):
    def add_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def delete_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        item_ids: list[str],
    ) -> dict[str, Any]: ...

    def delete_report(
        self,
        member_id: str,
        report_id: str,
    ) -> dict[str, Any]: ...

    def query_evidence(
        self,
        member_id: str,
        *,
        report_ids: Optional[Iterable[str]] = None,
        item_id: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        fields: Optional[list[str]] = None,
    ) -> dict[str, Any]: ...

    def read_lab_dictionary(
        self,
        member_id: str,
    ) -> dict[str, Any]: ...

    def read_report_analysis(
        self,
        member_id: str,
        *,
        report_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]: ...

    def read_report_catalog(
        self,
        member_id: str,
        *,
        before_date: str | None = None,
        after_date: str | None = None,
        cursor: str | None = None,
        limit: int = 24,
    ) -> dict[str, Any]: ...

    def report_exists(self, member_id: str, report_id: str) -> bool: ...

    def update_report_fields(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def validate_report_context(
        self, member_id: str, report_id: str
    ) -> dict[str, Any]: ...

    def write_report_analysis(
        self,
        member_id: str,
        *,
        report_id: str,
        analysis_content: str,
        session_id: str = "",
        source_message_id: str = "",
    ) -> dict[str, Any]: ...

    def create_report_from_parsed(
        self,
        member_id: str,
        *,
        report: dict[str, Any],
        sources: list[dict[str, Any]],
        session_id: str,
        source_text: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...

    def link_parsed_report_sources(
        self,
        member_id: str,
        *,
        report: dict[str, Any],
        sources: list[dict[str, Any]],
        target_report_id: str,
        session_id: str,
        source_text: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...

    def merge_parsed_report(
        self,
        member_id: str,
        *,
        report: dict[str, Any],
        sources: list[dict[str, Any]],
        target_report_id: str,
        session_id: str,
        source_text: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...

    def reclassify_report(
        self,
        member_id: str,
        report_id: str,
        *,
        report: dict[str, Any],
        sources: list[dict[str, Any]],
        session_id: str,
        source_text: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class AccountBoundReportTool(Tool):
    bind_report_sources = False

    def __init__(self, *, account_id: str, member_id: str, service: ReportToolService):
        if not account_id:
            raise ValueError(
                "A medical report tool must be bound to an authenticated account_id."
            )
        self.account_id = account_id
        self.member_id = member_id
        self.service = service

    def _arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_account = arguments.get("account_id")
        if requested_account is not None and requested_account != self.account_id:
            raise PermissionError(
                "Medical report tool account_id does not match the authenticated account_id."
            )
        return {key: value for key, value in arguments.items() if key != "account_id"}

    def bind_runtime_arguments(
        self,
        arguments: dict[str, Any],
        *,
        context: Any,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bound = super().bind_runtime_arguments(
            arguments, context=context, observations=observations
        )
        if context.member_id != self.member_id:
            raise PermissionError("Medical report tool member does not match the current task.")
        if self.bind_report_sources:
            bound["source_text"] = str(getattr(context, "input_text", "") or "")
            bound["authorized_report_sources"] = _authorized_report_sources(
                observations
            )
        return bound


def _authorized_report_sources(
    observations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index only sources returned by visible, successful evidence reads."""

    authorized: dict[str, dict[str, Any]] = {}
    for item in observations:
        if item.get("name") != "read_report_information":
            continue
        call_id = str(item.get("call_id") or "")
        output = item.get("output")
        if not call_id or not isinstance(output, dict):
            continue
        reports = output.get("reports")
        if not isinstance(reports, list):
            continue
        for report in reports:
            if not isinstance(report, dict):
                continue
            report_id = str(report.get("report_id") or "")
            for source in report.get("sources") or []:
                if not isinstance(source, dict):
                    continue
                resource_id = str(source.get("resource_id") or "")
                if not report_id or not resource_id:
                    continue
                key = "\0".join((call_id, report_id, resource_id))
                authorized[key] = dict(source)
    return authorized
