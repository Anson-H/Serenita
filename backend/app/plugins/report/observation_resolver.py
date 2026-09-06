"""Resolve trusted report observations and recheck their source references."""

from dataclasses import dataclass
from typing import Any, Callable
from backend.app.plugins.runtime_context import (
    ObservationResolver,
    ConversationResourceResolver,
    MessageResolver,
)


@dataclass(frozen=True)
class ResolvedParsedReport:
    report: dict[str, Any]
    sources: list[dict[str, Any]]


class ParsedReportObservationResolver:
    def __init__(
        self,
        *,
        observation_resolver: ObservationResolver | None,
        conversation_resource_resolver: ConversationResourceResolver | None,
        message_resolver: MessageResolver | None,
        report_source_resolver: Callable[[str, str], dict | None],
    ):
        self._observation_resolver = observation_resolver
        self._conversation_resource_resolver = conversation_resource_resolver
        self._message_resolver = message_resolver
        self._report_source_resolver = report_source_resolver

    def resolve(self, *, parse_call_id, report_index, session_id, visible_message_ids):
        if self._observation_resolver is None:
            raise RuntimeError("当前运行环境不能解析工具观测引用。")
        resolved = self._observation_resolver(
            call_id=str(parse_call_id),
            allowed_tools={"validate_parsed_reports"},
            session_id=str(session_id),
            visible_message_ids={str(item) for item in visible_message_ids},
        )
        if not isinstance(resolved, dict):
            raise PermissionError(
                "完整解析校验结果不属于当前可见会话分支或已经不可用。"
            )
        output = resolved.get("output")
        reports = output.get("reports") if isinstance(output, dict) else None
        if (
            not isinstance(reports, list)
            or report_index < 0
            or report_index >= len(reports)
        ):
            raise LookupError("完整解析校验结果中的 report_index 不存在。")
        item = reports[report_index]
        if (
            not isinstance(item, dict)
            or int(item.get("report_index", -1)) != report_index
        ):
            raise ValueError("完整解析校验结果中的索引与对应工具观测不一致。")
        report = item.get("report")
        if not isinstance(report, dict):
            raise ValueError("完整解析校验结果不包含结构化报告。")
        source_indexes = item.get("source_indexes")
        raw_sources = output.get("sources")
        if not isinstance(source_indexes, list) or not isinstance(raw_sources, list):
            raise ValueError("完整解析校验结果不包含可信来源绑定。")
        sources: list[dict] = []
        for source_index in source_indexes:
            if (
                not isinstance(source_index, int)
                or source_index < 0
                or source_index >= len(raw_sources)
                or not isinstance(raw_sources[source_index], dict)
            ):
                raise ValueError("完整解析校验结果中的来源索引无效。")
            sources.append(
                self._trusted_source(dict(raw_sources[source_index]), resolved)
            )
        if not sources:
            raise ValueError("每份解析报告必须绑定至少一个可信来源。")
        return ResolvedParsedReport(report=report, sources=sources)

    def _trusted_source(self, source: dict, resolved: dict) -> dict:
        source_type = str(source.get("source_type") or "")
        if source_type == "conversation_attachment":
            if self._conversation_resource_resolver is None:
                raise RuntimeError("当前运行环境不能解析会话附件。")
            trusted = self._conversation_resource_resolver(
                str(source.get("resource_id") or "")
            )
            if not isinstance(trusted, dict):
                raise PermissionError("解析附件已经不可用或不属于当前会话。")
            return {**source, **trusted}
        if source_type == "conversation_text":
            if (
                str(source.get("session_id") or "")
                != str(resolved.get("session_id") or "")
                or str(source.get("message_id") or "")
                != str(resolved.get("source_message_id") or "")
                or self._message_resolver is None
            ):
                raise PermissionError("解析文本不属于原始会话消息。")
            message = self._message_resolver(str(source.get("message_id") or ""))
            if not isinstance(message, dict):
                raise PermissionError("解析文本消息已经不可用。")
            return {**source, "source_text": str(message.get("content") or "")}
        if source_type == "report_source":
            stored = self._report_source_resolver(
                str(source.get("report_id") or ""),
                str(source.get("resource_id") or ""),
            )
            if stored is None:
                raise PermissionError("报告原件已经不可用或不属于当前账号。")
            return {
                **source,
                "mime_type": str(stored.get("mime_type") or ""),
                "sha256": str(stored.get("sha256") or ""),
            }
        raise ValueError("完整解析校验结果中的来源类型无效。")
