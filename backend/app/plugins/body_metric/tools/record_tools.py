"""Executable body metric tools."""

from copy import deepcopy

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.agent_runtime.tools.pagination import automatic_pages
from backend.app.application.body_metric_service import BodyMetricService
from backend.app.domain.body_metric_statistics import category
from backend.app.plugins.body_metric.resources import body_reference
from backend.app.plugins.resource_effects import resource_effects

DESCRIPTIONS = {
    "read_body_metric_catalog": "读取身体指标分类目录，返回支持的指标和记录类型。",
    "read_body_record_catalog": "读取当前成员中匹配的身体指标记录目录，返回用于定位记录的目录信息。",
    "read_body_record": "读取当前成员的身体指标记录，返回记录内容和图片关联信息。",
    "read_body_statistics": "读取当前成员的身体指标统计，返回趋势、统计口径和数据覆盖信息。",
    "create_body_record": "为当前成员创建身体指标记录，返回创建结果。",
    "update_body_record": "更新当前成员的身体指标记录，返回更新后的内容。",
    "delete_body_record": "删除当前成员的一条身体指标记录及其图片关联，返回删除结果。",
    "attach_body_record_file": "将会话图片保存为饮食记录附件，返回保存结果。",
    "detach_body_record_file": "解除饮食记录的图片关联，返回解除结果。",
}


class BodyTool(Tool):
    def __init__(self, context, name, schema):
        self.context = context
        self.name = name
        self.description = DESCRIPTIONS[name]
        self.input_schema = schema
        self.service = context.service("body_metric", BodyMetricService)

    def bind_runtime_arguments(self, arguments, *, context, observations):
        if (context.account_id, context.member_id) != (
            self.context.account_id,
            self.context.member_id,
        ):
            raise PermissionError("身体指标工具与当前任务成员不一致。")
        return dict(arguments)

    def run(self, arguments):
        arguments = deepcopy(arguments)
        if self.name == "read_body_record_catalog":
            return automatic_pages(
                lambda offset: self._run({**arguments, "offset": offset or 0, "limit": 24}),
                next_field="next_offset",
            )
        if self.name == "read_body_statistics" and arguments.get("series_id"):
            return automatic_pages(lambda cursor: self._run({**arguments, "cursor": cursor, "limit": 100}))
        return self._run(arguments)

    def _run(self, arguments):
        a = dict(arguments)
        actor, member = self.context.account_id, self.context.member_id
        name = self.name
        s = self.service
        effects = {}
        if name == "read_body_metric_catalog":
            out = s.catalog(actor, member)
        elif name == "read_body_record_catalog":
            a.setdefault("limit", 24)
            out = s.query(actor, member, **a)
            out["items"] = [
                {k: v for k, v in r.items() if k not in ("data", "notes")}
                | {
                    "summary": r["data"].get("activity")
                    or r["data"].get("meal_type")
                    or r["metric"]
                    or r["kind"]
                }
                for r in out["items"]
            ]
        elif name == "read_body_record":
            out = s.read(actor, member, a["record_id"])
        elif name == "read_body_statistics":
            series_id = a.pop("series_id", None)
            if series_id:
                out = s.series_data(actor, member, series_id, **a)
            else:
                if any(k in a for k in ("cursor", "limit", "view")):
                    raise ValueError("趋势分页参数须与 series_id 同时提供。")
                out = s.statistics(actor, member, **a)
        elif name == "create_body_record":
            out = s.create(actor, member, a["record"], a["request_id"])
        elif name == "update_body_record":
            out = s.update(actor, member, a["record_id"], a["changes"])
        elif name == "delete_body_record":
            affected = s.read(actor, member, a["record_id"])
            out = s.delete(actor, member, a["record_id"])
            effects = resource_effects(body_reference(affected), "deleted")
        elif name == "attach_body_record_file":
            source = self.context.read_conversation_attachment(a["resource_id"])
            out = s.attach(
                actor,
                member,
                a["record_id"],
                source.original_filename,
                source.mime_type,
                source.content_bytes,
            )
        else:
            out = s.detach(actor, member, a["record_id"], a["file_id"])
        if out.get("kind"):
            out["path"] = (
                f"/health/{member}/body-metrics/{category(out)}?record={out['record_id']}"
            )
            if name != "read_body_record":
                effects = resource_effects(body_reference(out), "created" if name == "create_body_record" else "modified")
        return ToolResult(name=name, output=out, effects=effects)
