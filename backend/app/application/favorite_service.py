from backend.app.schemas.report import report_snapshot_fields
import json
from backend.app.core.favorite_errors import FavoriteSourceConflictError
import uuid

from backend.app.application.conversations.service import ConversationService
from backend.app.application.report_service import ReportService
from backend.app.core.errors import raise_error
from backend.app.core.member_lifecycle import member_lifecycle_operation
from backend.app.core.time import local_now_iso
from backend.app.repositories.favorite_repository import FavoriteRepository
from backend.app.repositories.member_repository import MemberRepository
from backend.app.core.member_errors import member_error
from backend.app.schemas.favorite import CreateFavoriteRequest, PatchFavoriteRequest
from backend.app.core.errors import SerenitaError
from backend.app.storage.paths import app_paths


def _report_title(report: dict) -> str:
    report_type = str(report.get("report_type") or "医疗报告").strip() or "医疗报告"
    report_name = str(report.get("report_name") or "").strip()
    if not report_name or report_name == report_type:
        return report_type
    prefix = f"{report_type} - "
    return report_name if report_name.startswith(prefix) else f"{prefix}{report_name}"


def _markdown_cell(value: object) -> str:
    return str(value or "").strip().replace("|", "\\|").replace("\n", "<br>") or "—"


def _append_report_fields(
    lines: list[str],
    heading: str,
    values: dict | None,
    fields: tuple[tuple[str, str], ...],
) -> None:
    lines.extend(["", f"## {heading}", ""])
    source = values or {}
    populated = False
    for key, label in fields:
        value = str(source.get(key) or "").strip()
        if not value:
            continue
        lines.append(f"- **{label}**：{value}")
        populated = True
    if not populated:
        lines.append("暂无内容")


def _report_snapshot(report: dict) -> str:
    lines = [
        f"# {_report_title(report)}",
        "",
        f"- **医疗报告类型**：{str(report.get('report_type') or '—').strip() or '—'}",
        f"- **医疗报告时间**：{str(report.get('report_time') or '—').strip() or '—'}",
        f"- **就诊机构**：{str(report.get('institution_name') or '—').strip() or '—'}",
    ]
    report_type = report.get("report_type")
    if report_type == "检验报告":
        lines.extend(
            [
                "",
                "## 检验指标",
                "",
                "| 指标 | 结果 | 参考范围 | 标记 |",
                "| --- | --- | --- | --- |",
            ]
        )
        results = report.get("lab_test_results") or []
        if results:
            for item in results:
                lines.append(
                    "| "
                    + " | ".join(
                        _markdown_cell(item.get(key))
                        for key in (
                            "item_name_zh",
                            "result_text",
                            "reference_text",
                            "flag_text",
                        )
                    )
                    + " |"
                )
        else:
            lines.append("| 暂无指标 | — | — | — |")
    elif report_type == "检查报告":
        _append_report_fields(
            lines,
            "检查结果",
            report.get("examination_report"),
            report_snapshot_fields("examination_report"),
        )
    elif report_type == "病理报告":
        _append_report_fields(
            lines,
            "病理结果",
            report.get("pathology_report"),
            report_snapshot_fields("pathology_report"),
        )
    elif report_type == "手术报告":
        _append_report_fields(
            lines,
            "手术记录",
            report.get("surgery_report"),
            report_snapshot_fields("surgery_report"),
        )
    elif report_type in {"门诊病历", "急诊病历"}:
        table = "outpatient_report" if report_type == "门诊病历" else "emergency_report"
        _append_report_fields(lines, report_type, report.get(table), report_snapshot_fields(table))
    else:
        other_report = report.get("other_report")
        body = (other_report or {}).get("report_body")
        lines.extend(["", "## 医疗报告内容", "", str(body or "暂无内容").strip()])
    analysis_content = str(report.get("analysis_content") or "").strip()
    if analysis_content:
        lines.extend(["", "## 解读结果", "", analysis_content])
    return "\n".join(lines).strip()


class FavoriteService:
    def __init__(
        self,
        repository=None,
        conversation_service=None,
        member_repository=None,
        report_service_factory=None,
        *, paths=None,
    ):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.repository = repository or FavoriteRepository(paths=self.paths)
        self.conversations = conversation_service or ConversationService(paths=self.paths)
        self.members = member_repository or MemberRepository(paths=self.paths)
        self.report_service_factory = report_service_factory or (lambda actor, member: ReportService.for_member(actor, member, members=self.members))

    def _source_available(self, account_id, row):
        if row["source_type"] == "report":
            try:
                return self.report_service_factory(
                    account_id, row["member_id"]
                ).report_exists(row["member_id"], row["source_id"])
            except SerenitaError as exc:
                if exc.kind in {"forbidden", "missing"}:
                    return False
                raise
        return (
            self.conversations.conversation_exists(account_id, row["source_session_id"])
            and self.conversations.source_message_for_favorite(
                account_id, row["source_session_id"], row["source_id"]
            )
            is not None
        )

    def _response(self, account_id, row, include_snapshot=True):
        result = {
            "favorite_id": row["favorite_id"],
            "member_id": row["member_id"],
            "member_name": self.members.historical_member_name(
                account_id, "favorite", row["favorite_id"]
            ),
            "source_type": row["source_type"],
            "source_session_id": row["source_session_id"],
            "source_id": row["source_id"],
            "title": row["title"],
            "content_summary": row["content_snapshot"][:80],
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"],
        }
        if include_snapshot:
            result.update(
                source_available=self._source_available(account_id, row),
                content_snapshot=row["content_snapshot"],
                updated_at=row["updated_at"],
            )
        return result

    def _row(self, account_id, favorite_id):
        row = self.repository.get(account_id, favorite_id)
        if row is None:
            raise_error('missing', "NOT_FOUND", "收藏不存在。")
        return row

    def list_favorites(self, account_id):
        return {
            "favorites": [
                self._response(account_id, row, False)
                for row in self.repository.list(account_id)
            ],
            "has_more": False,
            "next_cursor": None,
        }

    @member_lifecycle_operation
    def create_favorite(self, account_id, payload: CreateFavoriteRequest):
        if payload.source_type not in {"message", "report"}:
            raise_error('invalid_input', "INVALID_REQUEST", "不支持该收藏来源类型。")
        source_session_id = payload.source_session_id or ""
        if payload.source_type == "report":
            if not payload.member_id:
                member_error("MEMBER_REQUIRED", "收藏医疗报告必须指定成员。", 'invalid_input')
            member_id = payload.member_id
            access = self.members.resolve(account_id, member_id)
            report = self.report_service_factory(account_id, member_id).get_report(
                member_id, payload.source_id
            )
            content, title = _report_snapshot(report), _report_title(report)
            guard = access.guard()
        else:
            if not source_session_id:
                raise_error('invalid_input', "INVALID_REQUEST", "收藏回答时缺少来源聊天。")
            session = self.conversations.session_binding(
                account_id, source_session_id
            )
            if session is None:
                raise_error('missing', "NOT_FOUND", "来源聊天不存在。")
            member_id = session["member_id"]
            if payload.member_id is not None and payload.member_id != member_id:
                member_error("MEMBER_MISMATCH", "收藏与来源聊天关联的成员不一致。", 'conflict')
            source = self.conversations.source_message_for_favorite(
                account_id, source_session_id, payload.source_id
            )
            if not source:
                raise_error('missing', "NOT_FOUND", "来源消息不存在或不可收藏。")
            content = source["content"]
            title = source["title"] if source["title"] != "新聊天" else content[:20]
            guard = self.members.private_reference_guard()
        favorite_id = str(uuid.uuid4())
        timestamp = local_now_iso()
        try:
            with guard:
                if payload.source_type == "message" and member_id is not None:
                    member_id = self.conversations.session_binding(
                        account_id, source_session_id
                    )["member_id"]
                self.repository.create(
                    account_id,
                    {
                        "favorite_id": favorite_id,
                        "member_id": member_id,
                        "source_type": payload.source_type,
                        "source_session_id": source_session_id,
                        "source_id": payload.source_id,
                        "title": title,
                        "content_snapshot": content,
                        "tags": json.dumps(payload.tags, ensure_ascii=False),
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    },
                )
        except FavoriteSourceConflictError:
            duplicate_name = "医疗报告" if payload.source_type == "report" else "回答"
            raise_error('conflict', "CONFLICT", f"该{duplicate_name}已收藏。")
        return self.get_favorite(account_id, favorite_id)

    def get_favorite(self, account_id, favorite_id):
        return self._response(account_id, self._row(account_id, favorite_id))

    def patch_favorite(self, account_id, favorite_id, payload: PatchFavoriteRequest):
        row = self._row(account_id, favorite_id)
        title = payload.title.strip() if payload.title is not None else row["title"]
        if not title:
            raise_error('invalid_input', "INVALID_REQUEST", "收藏标题不能为空。")
        tags = (
            payload.tags
            if payload.tags is not None
            else json.loads(row["tags"] or "[]")
        )
        self.repository.update(
            account_id,
            favorite_id,
            title,
            json.dumps(tags, ensure_ascii=False),
            local_now_iso(),
        )
        return self.get_favorite(account_id, favorite_id)

    def delete_favorite(self, account_id, favorite_id):
        self._row(account_id, favorite_id)
        self.repository.delete_many(account_id, [favorite_id])
        return {"success": True, "favorite_id": favorite_id, "message": "已取消收藏"}

    def batch_delete_favorites(self, account_id, favorite_ids):
        deleted, missing = self.repository.delete_many(account_id, favorite_ids)
        return {
            "success": True,
            "deleted_ids": deleted,
            "failed": [{"favorite_id": item, "code": "NOT_FOUND"} for item in missing],
        }
