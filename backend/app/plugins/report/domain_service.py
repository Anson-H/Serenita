from __future__ import annotations
from typing import Protocol, Any, Optional, Iterable


class ReportDomainService(Protocol):
    def add_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def create_report_from_parsed(
        self,
        member_id: str,
        *,
        parsed_report: dict[str, Any],
        parsed_sources: list[dict[str, Any]],
        session_id: str = "",
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

    def link_parsed_report_sources(
        self,
        member_id: str,
        *,
        parsed_report: dict[str, Any],
        parsed_sources: list[dict[str, Any]],
        target_report_id: str,
        session_id: str = "",
    ) -> dict[str, Any]: ...

    def merge_parsed_report(
        self,
        member_id: str,
        *,
        parsed_report: dict[str, Any],
        parsed_sources: list[dict[str, Any]],
        target_report_id: str,
        session_id: str = "",
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
    ) -> dict[str, Any]: ...

    def reclassify_report(
        self,
        member_id: str,
        report_id: str,
        *,
        parsed_report: dict[str, Any],
        parsed_sources: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def report_exists(self, member_id: str, report_id: str) -> bool: ...

    def resolve_report_source(
        self, member_id: str, report_id: str, resource_id: str
    ): ...

    def update_report_fields(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

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
