from __future__ import annotations
from backend.app.application.report_source_store import ReportSourceStore
from backend.app.application.report_presenter import model_report_evidence, safe_detail
from backend.app.application.report_thumbnail import render_source_thumbnail
from backend.app.application.report_validation import (
    normalize_analysis_content,
    validate_final_parsed_report,
    normalize_report_time,
)

import hashlib
import json
from copy import deepcopy
from functools import wraps
from backend.app.repositories.member_repository import MemberAccess, MemberRepository
from backend.app.core.member_errors import member_error
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from backend.app.agent_runtime.prompts import ATTACHED_EXISTING_CONTENT_PREFIX
from backend.app.core.errors import raise_error
from backend.app.core.time import local_now
from backend.app.repositories.report_repository import ReportRepository
from backend.app.repositories.report_values import REPORT_PREFIXES
from backend.app.schemas.report import (
    REPORT_AGENT_EDITABLE_FIELDS,
    REPORT_EDITABLE_FIELDS,
    DETAILED_REPORT_CORE_FIELDS,
    DETAILED_REPORT_OPTIONAL_FIELDS,
    DETAILED_REPORT_SELECTABLE_FIELDS,
    DETAILED_REPORT_SOURCE_FIELD,
)
from backend.app.storage.paths import AppPaths


MAX_REPORT_FILES = 20
MAX_REPORT_BATCH_BYTES = 100 * 1024 * 1024


def _now() -> datetime:
    return local_now()


def _now_iso() -> str:
    return _now().isoformat()


def authorized_report(*, write: bool = False):
    def decorate(method):
        @wraps(method)
        def authorized(self, member_id, *args, **kwargs):
            if member_id != self.scope.member_id:
                member_error(
                    "MEMBER_MISMATCH", "请求的成员与当前任务不一致。", "conflict"
                )
            with self.scope.guard(write=write) as live:
                if live.account_id != self.account_id:
                    member_error(
                        "MEMBER_MISMATCH",
                        "健康档案所有者与当前存储不一致。",
                        "conflict",
                    )
                result = method(self, member_id, *args, **kwargs)
            if write and method.__name__ != "write_report_analysis":
                from backend.app.core.notification_runtime import notification_runtime
                runtime = notification_runtime(self.paths)
                runtime.changed(tuple(runtime.revisions), reschedule=True)
            return result

        return authorized

    return decorate


class ReportService:
    @authorized_report()
    def source_thumbnail(self, member_id: str, report_id: str, resource_id: str):
        path, _filename, mime_type = self.source_download(
            member_id, report_id, resource_id
        )
        return render_source_thumbnail(path, mime_type)

    def __init__(
        self,
        scope: MemberAccess,
        repository: Optional[ReportRepository] = None,
        *,
        paths: Optional[AppPaths] = None,
    ):
        self._scope = scope
        self.paths = paths or scope.access_repository.paths
        self.repository = repository or ReportRepository(self.account_id, self.paths)
        if (
            self.paths.root.resolve() != scope.access_repository.paths.root.resolve()
            or self.repository.paths.root.resolve() != self.paths.root.resolve()
            or self.repository.account_id != scope.account_id
        ):
            raise ValueError("医疗报告存储必须与已授权成员的账号和数据根一致。")
        self.sources = ReportSourceStore(self.repository)

    @property
    def scope(self) -> MemberAccess:
        return self._scope

    @property
    def account_id(self) -> str:
        return self._scope.account_id

    @classmethod
    def for_member(cls, actor_account_id: str, member_id: str, *, members=None):
        return cls((members or MemberRepository()).resolve(actor_account_id, member_id))

    # Public integration points for conversation/report-agent code.
    @authorized_report()
    def report_exists(self, member_id: str, report_id: str) -> bool:
        return self.repository.report_exists(member_id, report_id)

    def _validate_write_input(
        self,
        member_id: str,
        *,
        report: dict[str, Any],
        sources: list[dict[str, Any]],
        source_text: str,
        session_id: str,
        source_message_id: str,
        visible_attachments: dict[str, dict[str, Any]],
        authorized_report_sources: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Validate content and resolve trusted sources before any persistence."""
        prepared = validate_final_parsed_report(report)
        if not isinstance(sources, list) or not sources:
            raise ValueError("每份医疗报告必须绑定至少一个来源。")
        canonical_sources: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for reference in sources:
            source, key = self.sources.validate_parsed_source_reference(
                member_id, reference,
                source_text=source_text,
                session_id=session_id,
                source_message_id=source_message_id,
                visible_attachments=visible_attachments,
                authorized_report_sources=authorized_report_sources,
            )
            if key in seen:
                raise ValueError("同一份医疗报告不能重复绑定同一个来源。")
            seen.add(key)
            canonical_sources.append(source)
        return prepared, canonical_sources

    @authorized_report()
    def read_report_sources(self, member_id: str, report_id: str) -> dict[str, Any]:
        """Return safe metadata for every original linked to one visible report."""

        detail = self.repository.get_report_detail(member_id, report_id)
        if detail is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        sources = []
        for source_index, source in enumerate(detail.get("sources") or []):
            resource_id = str(source.get("resource_id") or "")
            path = self.sources.source_path(member_id, source)
            if not resource_id or not path.is_file():
                raise_error(
                    "missing", "REPORT_SOURCE_NOT_FOUND", "医疗报告原始文件不存在。"
                )
            sources.append(
                {
                    "source_index": source_index,
                    "resource_type": "report_source",
                    "report_id": report_id,
                    "resource_id": resource_id,
                    "filename": path.name,
                    "mime_type": str(source.get("mime_type") or ""),
                    "size_bytes": int(source.get("size_bytes") or path.stat().st_size),
                    "sha256": str(source.get("sha256") or ""),
                    "is_primary": bool(source.get("is_primary")),
                }
            )
        if not sources:
            raise_error("missing", "REPORT_SOURCE_NOT_FOUND", "医疗报告没有已保存原件。")
        return {"report_id": report_id, "sources": sources}

    @authorized_report(write=True)
    def write_report_analysis(
        self,
        member_id: str,
        *,
        report_id: str,
        analysis_content: str,
        session_id: str = "",
        source_message_id: str = "",
    ) -> dict[str, Any]:
        """Write an Agent-authored analysis to an existing report."""

        parsed = normalize_analysis_content(analysis_content)
        stored = self.repository.save_report_analysis(
            member_id,
            report_id,
            parsed,
        )
        if stored is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        return {
            "report_id": report_id,
            "analysis_content": stored.get("analysis_content"),
            "analysis_updated_at": stored.get("analysis_updated_at"),
            "analysis_outdated": stored.get("analysis_outdated", False),
            "conversation_binding": {
                "session_id": session_id,
                "source_message_id": source_message_id,
            },
        }

    @authorized_report()
    def validate_report_context(self, member_id: str, report_id: str) -> dict[str, Any]:
        detail = self.repository.get_report(member_id, report_id)
        if detail is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        return {
            "resource_type": "report",
            "resource_id": report_id,
            "member_id": member_id,
            "report_time": detail["report_time"],
            "report_type": detail["report_type"],
            "report_name": detail["report_name"],
            "captured_created_at": detail["created_at"],
            "captured_updated_at": detail["updated_at"],
        }

    @authorized_report()
    def report_resource_state(self, member_id: str, report_id: str) -> dict[str, Any]:
        detail = self.repository.get_report(member_id, report_id)
        state: dict[str, Any] = {
            "resource_type": "report",
            "resource_id": report_id,
            "member_id": member_id,
            "availability": "available" if detail is not None else "deleted",
        }
        if detail is not None:
            state["current_created_at"] = detail["created_at"]
            state["current_updated_at"] = detail["updated_at"]
        return state

    @authorized_report()
    def report_evidence(
        self, member_id: str, report_ids: Optional[Iterable[str]] = None
    ) -> list[dict[str, Any]]:
        evidence = []
        for item in self.repository.report_evidence(member_id, report_ids):
            safe = safe_detail(item)
            # Agent/model evidence is deliberately narrower than the report-detail
            # response. It never includes the member_id, source filenames/URLs, or
            # repository bookkeeping.
            evidence.append(model_report_evidence(safe))
        return evidence

    @authorized_report()
    def conversation_input_resource(
        self, member_id: str, report_id: str
    ) -> dict[str, Any]:
        """Resolve report evidence and prior AI interpretation for one user message."""

        detail = self.repository.get_report(member_id, report_id)
        if detail is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        presented = safe_detail(detail)
        report_evidence = model_report_evidence(presented)
        analysis_content = str(presented.get("analysis_content") or "").strip()
        existing_ai_analysis = (
            {
                "analysis_content": analysis_content,
                "analysis_updated_at": presented.get("analysis_updated_at"),
                "analysis_outdated": bool(presented.get("analysis_outdated")),
            }
            if analysis_content
            else None
        )
        return {
            "resource_type": "report",
            "resource_id": report_id,
            "member_id": member_id,
            "original_filename": str(presented.get("report_name") or report_id),
            "mime_type": "text/plain",
            "text": ATTACHED_EXISTING_CONTENT_PREFIX
            + json.dumps(
                {
                    "report": report_evidence,
                    "existing_ai_analysis": existing_ai_analysis,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }

    @authorized_report()
    def read_report_catalog(self, member_id: str, *, before_date: str | None = None,
                            after_date: str | None = None, cursor: str | None = None,
                            limit: int = 24) -> dict[str, Any]:
        from backend.app.schemas.medical_log import calendar_date

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("目录每页数量须为 1 至 100。")
        before_date = calendar_date(before_date or None)
        after_date = calendar_date(after_date or None)
        if before_date and after_date and before_date < after_date:
            raise ValueError("日期下界不能晚于上界。")
        return self.repository.report_catalog(member_id, before_date=before_date,
                                              after_date=after_date, cursor=cursor, limit=limit)

    def _evidence_requested_type(
        self, filters: Optional[dict[str, Any]]
    ) -> Optional[str]:
        if not filters:
            return None
        requested_type = filters.get("report_type")
        if requested_type and requested_type not in REPORT_PREFIXES:
            raise ValueError("医疗报告类型筛选值无效。")
        return requested_type

    @staticmethod
    def _filter_reports_by_type(
        reports: list[dict[str, Any]],
        requested_type: Optional[str],
    ) -> list[dict[str, Any]]:
        if not requested_type:
            return reports
        return [
            report for report in reports if report.get("report_type") == requested_type
        ]

    def _current_evidence_reports(
        self,
        member_id: str,
        report_ids: Optional[Iterable[str]],
        requested_type: Optional[str],
    ) -> list[dict[str, Any]]:
        if report_ids is None:
            summaries = self.repository.list_reports(
                member_id, report_type=requested_type
            )["reports"]
            report_ids = [report["report_id"] for report in summaries]
        reports = self.report_evidence(member_id, report_ids)
        return self._filter_reports_by_type(reports, requested_type)

    @staticmethod
    def _sort_evidence_reports(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            reports,
            key=lambda item: (
                str(item.get("report_time") or ""),
                str(item.get("report_id") or ""),
            ),
            reverse=True,
        )

    @staticmethod
    def _normalize_detailed_report_fields(
        fields: Optional[list[str]],
    ) -> tuple[frozenset[str], bool]:
        if not fields:
            return (
                frozenset(
                    DETAILED_REPORT_CORE_FIELDS | DETAILED_REPORT_OPTIONAL_FIELDS
                ),
                False,
            )
        normalized = [str(value) for value in fields]
        unknown = set(normalized) - DETAILED_REPORT_SELECTABLE_FIELDS
        if unknown:
            raise ValueError("fields 包含不支持的字段：" + "、".join(sorted(unknown)))
        selected = DETAILED_REPORT_CORE_FIELDS | (
            set(normalized) & DETAILED_REPORT_OPTIONAL_FIELDS
        )
        return frozenset(selected), DETAILED_REPORT_SOURCE_FIELD in normalized

    @staticmethod
    def _project_detailed_report_fields(
        reports: list[dict[str, Any]],
        selected_fields: frozenset[str],
    ) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in report.items() if key in selected_fields}
            for report in reports
        ]

    @authorized_report()
    def query_evidence(
        self,
        member_id: str,
        *,
        report_ids: Optional[Iterable[str]] = None,
        item_id: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Return one allow-listed detailed evidence snapshot for report tools."""
        selected_fields, include_sources = self._normalize_detailed_report_fields(
            fields
        )
        requested_type = self._evidence_requested_type(filters)

        reports = self._current_evidence_reports(member_id, report_ids, requested_type)

        if item_id:
            for report in reports:
                report["lab_test_results"] = [
                    item
                    for item in report.get("lab_test_results") or []
                    if item.get("item_id") == item_id
                ]
        reports = self._sort_evidence_reports(reports)
        total = len(reports)
        reports = self._project_detailed_report_fields(reports, selected_fields)
        if include_sources:
            for report in reports:
                source_detail = self.read_report_sources(
                    member_id, str(report["report_id"])
                )
                report["sources"] = list(source_detail.get("sources") or [])

        return {
            "total": total,
            "reports": reports,
        }

    @authorized_report()
    def resolve_report_source(self, member_id: str, report_id: str, resource_id: str):
        return self.repository.source_for_report(member_id, report_id, resource_id)

    @authorized_report()
    def member_lab_dictionary(self, member_id: str) -> dict[str, Any]:
        return self.repository.lab_dictionary(member_id)

    @authorized_report()
    def read_lab_dictionary(
        self,
        member_id: str,
    ) -> dict[str, Any]:
        dictionary = self.repository.lab_dictionary(member_id)
        items = [
            {
                key: item.get(key)
                for key in (
                    "item_id",
                    "item_name_zh",
                    "aliases",
                    "description",
                    "primary_category_name",
                    "related_category_names",
                )
            }
            for item in dictionary.get("items") or []
        ]
        categories = [
            {
                "category_name": category.get("category_name"),
                "description": category.get("description"),
            }
            for category in dictionary.get("categories") or []
        ]
        total = len(items)
        return {
            "total": total,
            "items": items,
            "categories": categories,
        }

    @authorized_report()
    def read_report_analysis(
        self,
        member_id: str,
        *,
        report_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        if report_ids is None:
            summaries = self.repository.list_reports(member_id)["reports"]
            report_ids = [
                str(item["report_id"]) for item in summaries if item.get("has_analysis")
            ]
        requested_ids = list(
            dict.fromkeys(
                str(value).strip() for value in report_ids if str(value or "").strip()
            )
        )
        analyses: list[dict[str, Any]] = []
        for report_id in requested_ids:
            detail = self.repository.get_report_detail(member_id, report_id)
            if detail is None:
                continue
            analysis_content = str(detail.get("analysis_content") or "")
            if not analysis_content.strip():
                continue
            analyses.append(
                {
                    "report_id": report_id,
                    "report_type": detail.get("report_type"),
                    "report_name": detail.get("report_name"),
                    "report_time": detail.get("report_time"),
                    "institution_name": detail.get("institution_name"),
                    "analysis_content": analysis_content,
                    "analysis_outdated": bool(detail.get("analysis_outdated")),
                    "analysis_updated_at": detail.get("analysis_updated_at"),
                }
            )
        analyses.sort(
            key=lambda item: (
                str(item.get("report_time") or ""),
                str(item.get("report_id") or ""),
            ),
            reverse=True,
        )
        total = len(analyses)
        return {
            "total": total,
            "analyses": analyses,
        }

    @authorized_report()
    def list_reports(
        self,
        member_id: str,
        *,
        report_type: Optional[str] = None,
    ) -> dict[str, Any]:
        self.sources.drain_file_cleanup(member_id)
        normalized_type = None
        if report_type and report_type not in {"all", "全部"}:
            if report_type not in REPORT_PREFIXES:
                raise_error("invalid_input", "INVALID_REQUEST", "医疗报告类型筛选值无效。")
            normalized_type = report_type
        return self.repository.list_reports(member_id, report_type=normalized_type)

    @authorized_report()
    def get_report(self, member_id: str, report_id: str) -> dict[str, Any]:
        self.sources.drain_file_cleanup(member_id)
        detail = self.repository.get_report(member_id, report_id)
        if detail is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        return safe_detail(detail)

    @authorized_report(write=True)
    def create_manual_report(
        self,
        member_id: str,
        *,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        """Create one report from an explicit report-page text entry."""

        try:
            prepared = validate_final_parsed_report(
                {**deepcopy(report), "source_kind": "unknown"}
            )
            created = self.repository.create_manual_report(member_id, prepared)
        except ValueError as exc:
            raise_error("invalid_input", "INVALID_REPORT", str(exc))
        return self.get_report(member_id, created["report_id"])

    @authorized_report(write=True)
    def add_report_sources(
        self,
        member_id: str,
        report_id: str,
        *,
        uploads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Attach user-selected originals to one existing report-page record."""

        self.sources.drain_file_cleanup(member_id)
        if self.repository.get_report_detail(member_id, report_id) is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法补充原件。",
            )
        if not uploads:
            raise_error("invalid_input", "INVALID_REQUEST", "请至少选择一份医疗报告原件。")
        if len(uploads) > MAX_REPORT_FILES:
            raise_error(
                "invalid_input",
                "TOO_MANY_FILES",
                f"每次最多补充 {MAX_REPORT_FILES} 份医疗报告原件。",
            )

        normalized_uploads = [
            self.sources.normalize_upload(upload) for upload in uploads
        ]
        if (
            sum(len(upload["content"]) for upload in normalized_uploads)
            > MAX_REPORT_BATCH_BYTES
        ):
            raise_error(
                "resource_limit",
                "FILE_BATCH_TOO_LARGE",
                "单次补充的医疗报告文件总大小不能超过 100MB。",
            )

        digest_names: dict[str, list[str]] = {}
        for upload in normalized_uploads:
            digest = hashlib.sha256(upload["content"]).hexdigest()
            digest_names.setdefault(digest, []).append(upload["original_filename"])
        repeated_names = [
            names[-1] for names in digest_names.values() if len(names) > 1
        ]
        if repeated_names:
            raise_error(
                "conflict",
                "REPORT_SOURCE_DUPLICATE",
                f"所选文件中包含重复原件：{'、'.join(repeated_names)}。",
            )
        existing_digests = self.repository.source_digests_for_report(
            member_id, report_id
        )
        already_linked_names = [
            upload["original_filename"]
            for upload in normalized_uploads
            if hashlib.sha256(upload["content"]).hexdigest() in existing_digests
        ]
        if already_linked_names:
            raise_error(
                "conflict",
                "REPORT_SOURCE_DUPLICATE",
                f"以下原件已经关联到该医疗报告：{'、'.join(already_linked_names)}。",
            )

        created_resource_ids: list[str] = []
        try:
            for upload in normalized_uploads:
                resource_id = self.sources.new_id("RESOURCE")
                self.sources.persist_normalized_upload(
                    member_id,
                    upload,
                    resource_id=resource_id,
                )
                created_resource_ids.append(resource_id)
            self.repository.link_report_sources(
                member_id,
                report_id=report_id,
                resource_ids=created_resource_ids,
                reject_duplicate_content=True,
            )
        except LookupError:
            self.sources.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法补充原件。",
            )
        except Exception:
            self.sources.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise
        return self.get_report(member_id, report_id)

    def _apply_report_field_updates(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
        editable_fields: frozenset[str],
    ) -> dict[str, Any]:
        if not updates:
            raise_error(
                "invalid_input", "INVALID_REPORT_FIELD", "字段更新列表不能为空。"
            )
        prepared: list[dict[str, Any]] = []
        for update in updates:
            field = str(update.get("field") or "")
            if field not in editable_fields:
                raise_error(
                    "invalid_input", "REPORT_FIELD_NOT_EDITABLE", "该字段不可编辑。"
                )
            value = update.get("value")
            try:
                if field == "report_time":
                    if not str(value or "").strip():
                        raise ValueError("就诊时间不能为空。")
                    value = normalize_report_time(str(value))
                elif field in {"started_at", "ended_at"} and str(value or "").strip():
                    value = normalize_report_time(str(value))
            except ValueError as exc:
                raise_error("invalid_input", "INVALID_REPORT_FIELD", str(exc))
            prepared.append(
                {
                    "field": field,
                    "value": value,
                    "item_id": update.get("item_id"),
                }
            )
        try:
            updated = self.repository.update_report_fields(
                member_id,
                report_id,
                updates=prepared,
            )
        except LookupError as exc:
            raise_error("missing", "REPORT_FIELD_NOT_FOUND", str(exc))
        except ValueError as exc:
            raise_error("invalid_input", "INVALID_REPORT_FIELD", str(exc))
        if updated is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法继续更新。",
            )
        return self.get_report(member_id, report_id)

    @authorized_report(write=True)
    def update_report_fields(
        self,
        member_id: str,
        report_id: str,
        *,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply explicit Agent field mutations to one report in one transaction."""

        return self._apply_report_field_updates(
            member_id,
            report_id,
            updates=updates,
            editable_fields=REPORT_AGENT_EDITABLE_FIELDS,
        )

    @authorized_report(write=True)
    def update_report_field(
        self,
        member_id: str,
        report_id: str,
        *,
        field: str,
        value: str | None,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply the report page's single explicit field mutation."""

        return self._apply_report_field_updates(
            member_id,
            report_id,
            updates=[{"field": field, "value": value, "item_id": item_id}],
            editable_fields=REPORT_EDITABLE_FIELDS,
        )

    @authorized_report(write=True)
    def add_lab_report_item(
        self,
        member_id: str,
        report_id: str,
        *,
        item_id: str,
        result_text: str,
        reference_text: str | None,
        flag_text: str,
    ) -> dict[str, Any]:
        """Append one explicit dictionary-backed result from the report page."""

        try:
            updated = self.repository.add_lab_report_item(
                member_id,
                report_id,
                item_id=item_id,
                result_text=result_text,
                reference_text=reference_text,
                flag_text=flag_text,
            )
        except LookupError as exc:
            raise_error("missing", "REPORT_LAB_ITEM_NOT_FOUND", str(exc))
        except ValueError as exc:
            raise_error("invalid_input", "INVALID_REPORT_LAB_ITEM_ADD", str(exc))
        if updated is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法继续添加指标。",
            )
        return self.get_report(member_id, report_id)

    @authorized_report(write=True)
    def add_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Append explicit Agent-provided results to one lab report in one transaction."""

        try:
            updated = self.repository.add_lab_report_items(
                member_id,
                report_id,
                items=items,
            )
        except LookupError as exc:
            raise_error("missing", "REPORT_LAB_ITEMS_NOT_FOUND", str(exc))
        except ValueError as exc:
            raise_error("invalid_input", "INVALID_REPORT_LAB_ITEMS_ADD", str(exc))
        if updated is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法继续添加指标。",
            )
        return self.get_report(member_id, report_id)

    @authorized_report(write=True)
    def delete_lab_report_items(
        self,
        member_id: str,
        report_id: str,
        *,
        item_ids: list[str],
    ) -> dict[str, Any]:
        """Delete explicit indicators from one laboratory report in one transaction."""

        try:
            updated = self.repository.delete_lab_report_items(
                member_id,
                report_id,
                item_ids=item_ids,
            )
        except LookupError as exc:
            raise_error("missing", "REPORT_LAB_ITEMS_NOT_FOUND", str(exc))
        except ValueError as exc:
            raise_error("invalid_input", "INVALID_REPORT_LAB_ITEMS_DELETE", str(exc))
        if updated is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法继续删除指标。",
            )
        return self.get_report(member_id, report_id)

    @authorized_report(write=True)
    def delete_report(
        self,
        member_id: str,
        report_id: str,
    ) -> dict[str, Any]:
        """Delete a report after an explicit report-page delete action."""

        self.sources.drain_file_cleanup(member_id)
        deleted = self.repository.delete_report(member_id, report_id)
        if deleted is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无需再次删除。",
            )
        self.sources.drain_file_cleanup(member_id)
        return {"report_id": report_id, "deleted": True}

    @authorized_report(write=True)
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
    ) -> dict[str, Any]:
        parsed_report, parsed_sources = self._validate_write_input(
            member_id, report=report, sources=sources,
            session_id=session_id, source_text=source_text,
            source_message_id=source_message_id,
            visible_attachments=visible_attachments,
            authorized_report_sources=authorized_report_sources,
        )
        current = self.repository.get_report(member_id, report_id)
        if current is None:
            raise_error("missing", "REPORT_NOT_FOUND", "医疗报告不存在。")
        prepared = parsed_report
        prepared["report_time"] = str(current["report_time"])
        visible_original = any(
            source.get("source_type") == "report_source"
            and str(source.get("report_id") or "") == report_id
            for source in parsed_sources
        )
        if not visible_original:
            raise ValueError(
                '重新分类必须绑定通过 read_report_information(fields=["sources"]) 读取的当前医疗报告原件。'
            )
        updated = self.repository.reclassify_report(member_id, report_id, prepared)
        if updated is None:
            raise_error(
                "missing",
                "REPORT_NOT_FOUND",
                "医疗报告已不存在，可能已被删除或合并，无法继续重新分类。",
            )
        return self.get_report(member_id, report_id)

    @authorized_report()
    def source_download(
        self, member_id: str, report_id: str, resource_id: str
    ) -> tuple[Path, str, str]:
        self.sources.drain_file_cleanup(member_id)
        source = self.repository.source_for_report(member_id, report_id, resource_id)
        if source is None:
            raise_error("missing", "REPORT_SOURCE_NOT_FOUND", "医疗报告原始文件不存在。")
        path = self.sources.source_path(member_id, source)
        if not path.is_file():
            raise_error("missing", "REPORT_SOURCE_NOT_FOUND", "医疗报告原始文件不存在。")
        return path, path.name, source["mime_type"]

    @authorized_report(write=True)
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
    ) -> dict[str, Any]:
        parsed_report, parsed_sources = self._validate_write_input(
            member_id, report=report, sources=sources,
            session_id=session_id, source_text=source_text,
            source_message_id=source_message_id,
            visible_attachments=visible_attachments,
            authorized_report_sources=authorized_report_sources,
        )
        sources, created_resource_ids = self.sources.ensure_parsed_sources(
            member_id, parsed_sources, session_id=session_id
        )
        try:
            return self.repository.create_report_from_parsed(
                member_id,
                deepcopy(parsed_report),
                resource_ids=[str(source["resource_id"]) for source in sources],
            )
        except Exception:
            self.sources.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise

    @authorized_report(write=True)
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
    ) -> dict[str, Any]:
        _parsed_report, parsed_sources = self._validate_write_input(
            member_id, report=report, sources=sources,
            session_id=session_id, source_text=source_text,
            source_message_id=source_message_id,
            visible_attachments=visible_attachments,
            authorized_report_sources=authorized_report_sources,
        )
        sources, created_resource_ids = self.sources.ensure_parsed_sources(
            member_id, parsed_sources, session_id=session_id
        )
        try:
            return self.repository.link_parsed_report_sources(
                member_id,
                report_id=target_report_id,
                resource_ids=[str(source["resource_id"]) for source in sources],
            )
        except Exception:
            self.sources.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise

    @authorized_report(write=True)
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
    ) -> dict[str, Any]:
        parsed_report, parsed_sources = self._validate_write_input(
            member_id, report=report, sources=sources,
            session_id=session_id, source_text=source_text,
            source_message_id=source_message_id,
            visible_attachments=visible_attachments,
            authorized_report_sources=authorized_report_sources,
        )
        sources, created_resource_ids = self.sources.ensure_parsed_sources(
            member_id, parsed_sources, session_id=session_id
        )
        try:
            return self.repository.merge_parsed_report(
                member_id,
                deepcopy(parsed_report),
                report_id=target_report_id,
                resource_ids=[str(source["resource_id"]) for source in sources],
            )
        except Exception:
            self.sources.cleanup_new_unlinked_sources(member_id, created_resource_ids)
            raise
