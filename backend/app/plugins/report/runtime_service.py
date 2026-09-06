from __future__ import annotations
from typing import Any, Optional, Iterable
from backend.app.plugins.report.domain_service import ReportDomainService
from backend.app.plugins.report.observation_resolver import (
    ParsedReportObservationResolver,
)


class RuntimeReportService:
    def __init__(
        self,
        member_id: str,
        service: ReportDomainService,
        observation_resolver,
        conversation_resource_resolver,
        message_resolver,
    ):
        self._member_id = member_id
        self._service = service
        self._observations = ParsedReportObservationResolver(
            observation_resolver=observation_resolver,
            conversation_resource_resolver=conversation_resource_resolver,
            message_resolver=message_resolver,
            report_source_resolver=lambda report_id, resource_id: (
                service.resolve_report_source(member_id, report_id, resource_id)
            ),
        )

    def add_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._service.add_lab_report_items(member_id, report_id, items=items)

    def delete_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        item_ids: list[str],
    ) -> dict[str, Any]:
        return self._service.delete_lab_report_items(
            member_id, report_id, item_ids=item_ids
        )

    def delete_report(
        self,
        member_id: str,
        report_id: str,
    ) -> dict[str, Any]:
        return self._service.delete_report(member_id, report_id)

    def query_evidence(
        self,
        member_id: str,
        *,
        report_ids: Optional[Iterable[str]] = None,
        item_id: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        return self._service.query_evidence(
            member_id,
            report_ids=report_ids,
            item_id=item_id,
            filters=filters,
            fields=fields,
        )

    def read_lab_dictionary(
        self,
        member_id: str,
    ) -> dict[str, Any]:
        return self._service.read_lab_dictionary(member_id)

    def read_report_analysis(
        self,
        member_id: str,
        *,
        report_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        return self._service.read_report_analysis(member_id, report_ids=report_ids)

    def read_report_catalog(
        self,
        member_id: str,
        *,
        before_date: str | None = None,
        after_date: str | None = None,
    ) -> dict[str, Any]:
        return self._service.read_report_catalog(
            member_id, before_date=before_date, after_date=after_date
        )

    def report_exists(self, member_id: str, report_id: str) -> bool:
        return self._service.report_exists(member_id, report_id)

    def update_report_fields(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._service.update_report_fields(member_id, report_id, updates=updates)

    def validate_parsed_reports(
        self,
        member_id: str,
        *,
        reports: list[dict[str, Any]],
        source_text: str,
        session_id: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return self._service.validate_parsed_reports(
            member_id,
            reports=reports,
            source_text=source_text,
            session_id=session_id,
            source_message_id=source_message_id,
            visible_attachments=visible_attachments,
            authorized_report_sources=authorized_report_sources,
        )

    def validate_report_context(self, member_id: str, report_id: str) -> dict[str, Any]:
        return self._service.validate_report_context(member_id, report_id)

    def write_report_analysis(
        self,
        member_id: str,
        *,
        report_id: str,
        analysis_content: str,
        session_id: str = "",
        source_message_id: str = "",
    ) -> dict[str, Any]:
        return self._service.write_report_analysis(
            member_id,
            report_id=report_id,
            analysis_content=analysis_content,
            session_id=session_id,
            source_message_id=source_message_id,
        )

    def create_report_from_parsed(
        self,
        member_id: str,
        *,
        parse_call_id: str,
        report_index: int,
        session_id: str,
        visible_message_ids: set[str],
    ) -> dict[str, Any]:
        if member_id != self._member_id:
            raise PermissionError("报告工具成员与当前任务不一致。")
        resolved = self._observations.resolve(
            parse_call_id=parse_call_id,
            report_index=report_index,
            session_id=session_id,
            visible_message_ids=visible_message_ids,
        )
        return self._service.create_report_from_parsed(
            member_id,
            parsed_report=resolved.report,
            parsed_sources=resolved.sources,
            session_id=session_id,
        )

    def link_parsed_report_sources(
        self,
        member_id: str,
        *,
        parse_call_id: str,
        report_index: int,
        target_report_id: str,
        session_id: str,
        visible_message_ids: set[str],
    ) -> dict[str, Any]:
        if member_id != self._member_id:
            raise PermissionError("报告工具成员与当前任务不一致。")
        resolved = self._observations.resolve(
            parse_call_id=parse_call_id,
            report_index=report_index,
            session_id=session_id,
            visible_message_ids=visible_message_ids,
        )
        return self._service.link_parsed_report_sources(
            member_id,
            parsed_report=resolved.report,
            parsed_sources=resolved.sources,
            session_id=session_id,
            target_report_id=target_report_id,
        )

    def merge_parsed_report(
        self,
        member_id: str,
        *,
        parse_call_id: str,
        report_index: int,
        target_report_id: str,
        session_id: str,
        visible_message_ids: set[str],
    ) -> dict[str, Any]:
        if member_id != self._member_id:
            raise PermissionError("报告工具成员与当前任务不一致。")
        resolved = self._observations.resolve(
            parse_call_id=parse_call_id,
            report_index=report_index,
            session_id=session_id,
            visible_message_ids=visible_message_ids,
        )
        return self._service.merge_parsed_report(
            member_id,
            parsed_report=resolved.report,
            parsed_sources=resolved.sources,
            session_id=session_id,
            target_report_id=target_report_id,
        )

    def reclassify_report(
        self,
        member_id: str,
        report_id: str,
        *,
        parse_call_id: str,
        report_index: int,
        session_id: str,
        visible_message_ids: set[str],
    ) -> dict[str, Any]:
        if member_id != self._member_id:
            raise PermissionError("报告工具成员与当前任务不一致。")
        resolved = self._observations.resolve(
            parse_call_id=parse_call_id,
            report_index=report_index,
            session_id=session_id,
            visible_message_ids=visible_message_ids,
        )
        return self._service.reclassify_report(
            member_id,
            report_id,
            parsed_report=resolved.report,
            parsed_sources=resolved.sources,
        )
